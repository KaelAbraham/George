"""
Shared utilities for microservices.
Provides common patterns for inter-service communication and security.
"""
import os
import logging
import time
import requests
from functools import wraps
from flask import request, jsonify
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"          # Normal operation
    OPEN = "open"              # Service failing, rejecting requests
    HALF_OPEN = "half_open"    # Testing if service recovered

# --- INTERNAL SERVICE TOKEN MANAGEMENT ---

INTERNAL_TOKEN = os.getenv("INTERNAL_SERVICE_TOKEN")

def require_internal_token(f):
    """
    Decorator to protect internal service endpoints.
    Checks X-INTERNAL-TOKEN header against INTERNAL_SERVICE_TOKEN env var.
    
    In dev mode (no token configured), allows all requests.
    In production (token configured), rejects requests without valid token.
    
    Usage:
        @app.route('/protected_endpoint', methods=['POST'])
        @require_internal_token
        def protected_endpoint():
            return jsonify({"data": "protected"}), 200
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not INTERNAL_TOKEN:
            # Dev mode: allow if not configured
            return f(*args, **kwargs)
        
        token = request.headers.get("X-INTERNAL-TOKEN")
        if not token or token != INTERNAL_TOKEN:
            logger.warning(f"Unauthorized internal request: missing or invalid token")
            return jsonify({"error": "Forbidden"}), 403
        return f(*args, **kwargs)
    return decorated


def get_internal_headers():
    """
    Get headers dict with internal service token for requests to other services.
    
    Usage:
        headers = get_internal_headers()
        resp = requests.post(
            f"{FILESYSTEM_SERVER_URL}/save_file",
            json=data,
            headers=headers,
            timeout=10
        )
    
    Returns:
        dict: Headers dict with X-INTERNAL-TOKEN if configured, empty dict otherwise
    """
    if INTERNAL_TOKEN:
        return {"X-INTERNAL-TOKEN": INTERNAL_TOKEN}
    return {}


# --- FIREBASE AUTHENTICATION DECORATOR ---

def require_firebase_auth(firebase_auth_module=None):
    """
    Decorator to extract and verify Firebase ID token from Authorization header.
    
    Automatically extracts the user_id from the Firebase token and passes it
    as a keyword argument to the decorated function. This eliminates duplicate
    token extraction and verification logic across endpoints.
    
    Args:
        firebase_auth_module: Optional Firebase auth module (e.g., firebase_admin.auth)
                            If not provided, must be imported by the calling module
    
    Usage:
        from firebase_admin import auth
        
        @app.route('/protected_endpoint', methods=['POST'])
        @require_firebase_auth(auth)
        def protected_endpoint(user_id):
            # user_id is automatically extracted and verified
            return jsonify({"user_id": user_id}), 200
    
    Returns:
        401 Unauthorized if token is missing, invalid, or verification fails
        Function result otherwise
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            # 1. Extract token from Authorization header
            auth_header = request.headers.get('Authorization')
            if not auth_header or not auth_header.startswith("Bearer "):
                logger.warning(f"Unauthorized attempt to {request.path}: missing/invalid auth header from {request.remote_addr}")
                return jsonify({"error": "Unauthorized - missing or invalid token"}), 401
            
            try:
                # 2. Extract token from "Bearer <token>" format
                token = auth_header.split("Bearer ")[1]
                
                # 3. Verify Firebase token
                if firebase_auth_module is None:
                    raise ImportError("firebase_admin.auth module not provided to decorator")
                
                decoded_token = firebase_auth_module.verify_id_token(token)
                user_id = decoded_token.get('uid')
                
                if not user_id:
                    logger.warning(f"Firebase token missing UID from {request.remote_addr}")
                    return jsonify({"error": "Unauthorized - invalid token"}), 401
                
                # 4. Call the function with user_id as keyword argument
                return f(user_id=user_id, *args, **kwargs)
            
            except Exception as e:
                logger.warning(f"Token verification failed for {request.path}: {e}")
                return jsonify({"error": "Unauthorized - invalid token"}), 401
        
        return wrapper
    return decorator


# --- RESILIENT SERVICE CLIENT WITH CIRCUIT BREAKER ---

class ServiceUnavailable(Exception):
    """Raised when a service is unavailable (circuit breaker open)."""
    pass


class ResilientServiceClient:
    """
    HTTP client with circuit breaker pattern and retry logic for inter-service communication.
    
    Features:
    - Automatic retry with exponential backoff
    - Circuit breaker pattern to prevent cascading failures
    - Timeout protection
    - Internal token management
    - Comprehensive logging
    
    Usage:
        client = ResilientServiceClient("http://chroma:6003", max_retries=3)
        try:
            response = client.post("/query", json={"query": "..."})
        except ServiceUnavailable:
            # Handle circuit breaker open
            logger.error("Chroma service is down")
        except requests.RequestException as e:
            # Handle persistent failures
            logger.error(f"Chroma call failed after retries: {e}")
    """
    
    def __init__(self, base_url: str, service_name: str = "Service", 
                 max_retries: int = 3, timeout: int = 10,
                 failure_threshold: int = 5, recovery_timeout: int = 60):
        """
        Initialize resilient client.
        
        Args:
            base_url: Base URL of the service (e.g., "http://chroma:6003")
            service_name: Name for logging (e.g., "Chroma Server")
            max_retries: Number of retry attempts (default 3)
            timeout: Request timeout in seconds (default 10)
            failure_threshold: Failures before circuit opens (default 5)
            recovery_timeout: Seconds before trying to recover (default 60)
        """
        self.base_url = base_url.rstrip('/')
        self.service_name = service_name
        self.max_retries = max_retries
        self.timeout = timeout
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        
        # Circuit breaker state
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.last_state_change = datetime.now()
    
    def _get_headers(self) -> dict:
        """Get headers with internal token."""
        headers = get_internal_headers()
        return headers if headers else {}
    
    def _should_attempt_reset(self) -> bool:
        """Check if circuit should attempt reset (HALF_OPEN)."""
        if self.state != CircuitState.OPEN:
            return False
        
        # Try to recover after recovery_timeout
        if datetime.now() - self.last_state_change >= timedelta(seconds=self.recovery_timeout):
            logger.info(f"[{self.service_name}] Circuit breaker entering HALF_OPEN state")
            self.state = CircuitState.HALF_OPEN
            self.failure_count = 0
            return True
        
        return False
    
    def _record_success(self):
        """Record successful request."""
        if self.state == CircuitState.HALF_OPEN:
            logger.info(f"[{self.service_name}] Circuit breaker CLOSED (service recovered)")
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.last_state_change = datetime.now()
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0  # Reset on any success
    
    def _record_failure(self):
        """Record failed request and update circuit state."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.state == CircuitState.HALF_OPEN:
            # Service still failing, open circuit again
            logger.warning(f"[{self.service_name}] Circuit breaker OPEN (service still failing)")
            self.state = CircuitState.OPEN
            self.last_state_change = datetime.now()
            self.failure_count = 0  # Reset for next recovery attempt
        elif self.failure_count >= self.failure_threshold and self.state == CircuitState.CLOSED:
            logger.warning(f"[{self.service_name}] Circuit breaker OPEN (threshold reached: {self.failure_count}/{self.failure_threshold})")
            self.state = CircuitState.OPEN
            self.last_state_change = datetime.now()
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """
        Make HTTP request with retry logic.
        
        Args:
            method: HTTP method ('get', 'post', 'put', 'delete')
            endpoint: API endpoint (e.g., '/query')
            **kwargs: Additional arguments for requests method
        
        Returns:
            requests.Response object
        
        Raises:
            ServiceUnavailable: If circuit breaker is open
            requests.RequestException: If all retries fail
        """
        # Check circuit breaker before attempting
        if self.state == CircuitState.OPEN:
            if not self._should_attempt_reset():
                logger.warning(f"[{self.service_name}] Circuit breaker OPEN - rejecting request")
                raise ServiceUnavailable(f"{self.service_name} circuit breaker is open")
        
        url = f"{self.base_url}{endpoint}"
        
        # Ensure timeout is set
        if 'timeout' not in kwargs:
            kwargs['timeout'] = self.timeout
        
        # Add internal token headers
        if 'headers' not in kwargs:
            kwargs['headers'] = {}
        kwargs['headers'].update(self._get_headers())
        
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"[{self.service_name}] {method.upper()} {endpoint} (attempt {attempt + 1}/{self.max_retries})")
                
                response = requests.request(method, url, **kwargs)
                
                # Raise for HTTP errors (4xx, 5xx)
                response.raise_for_status()
                
                # Success
                self._record_success()
                logger.debug(f"[{self.service_name}] ✓ {method.upper()} {endpoint} succeeded")
                return response
                
            except requests.exceptions.Timeout as e:
                last_exception = e
                logger.warning(f"[{self.service_name}] Timeout on attempt {attempt + 1}/{self.max_retries}")
                self._record_failure()
                
            except requests.exceptions.ConnectionError as e:
                last_exception = e
                logger.warning(f"[{self.service_name}] Connection failed on attempt {attempt + 1}/{self.max_retries}: {e}")
                self._record_failure()
                
            except requests.exceptions.HTTPError as e:
                # Don't retry on 4xx errors (client errors) except 429 (rate limit)
                if response.status_code < 500 and response.status_code != 429:
                    logger.error(f"[{self.service_name}] Client error {response.status_code}: {response.text}")
                    raise
                
                last_exception = e
                logger.warning(f"[{self.service_name}] Server error {response.status_code} on attempt {attempt + 1}/{self.max_retries}")
                self._record_failure()
                
            except requests.exceptions.RequestException as e:
                last_exception = e
                logger.warning(f"[{self.service_name}] Request failed on attempt {attempt + 1}/{self.max_retries}: {e}")
                self._record_failure()
            
            # Exponential backoff: 1s, 2s, 4s, etc.
            if attempt < self.max_retries - 1:
                backoff_time = 2 ** attempt
                logger.debug(f"[{self.service_name}] Retrying in {backoff_time}s...")
                time.sleep(backoff_time)
        
        # All retries exhausted
        logger.error(f"[{self.service_name}] ✗ All {self.max_retries} retry attempts failed: {last_exception}")
        raise last_exception or requests.RequestException(f"Failed to connect to {self.service_name}")
    
    def get(self, endpoint: str, **kwargs) -> requests.Response:
        """Make GET request with circuit breaker and retry."""
        return self._make_request('get', endpoint, **kwargs)
    
    def post(self, endpoint: str, **kwargs) -> requests.Response:
        """Make POST request with circuit breaker and retry."""
        return self._make_request('post', endpoint, **kwargs)
    
    def put(self, endpoint: str, **kwargs) -> requests.Response:
        """Make PUT request with circuit breaker and retry."""
        return self._make_request('put', endpoint, **kwargs)
    
    def delete(self, endpoint: str, **kwargs) -> requests.Response:
        """Make DELETE request with circuit breaker and retry."""
        return self._make_request('delete', endpoint, **kwargs)
    
    def get_status(self) -> dict:
        """
        Get circuit breaker status for monitoring/debugging.
        
        Returns:
            dict: Status information
        """
        return {
            "service": self.service_name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "last_failure": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "last_state_change": self.last_state_change.isoformat()
        }

