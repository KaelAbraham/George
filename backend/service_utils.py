"""
Shared utilities for microservices.
Provides common patterns for inter-service communication and security.
"""
import os
import logging
from functools import wraps
from flask import request, jsonify

logger = logging.getLogger(__name__)

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
