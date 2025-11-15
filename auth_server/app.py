import os
import logging
import requests
import base64
import json
import time
import sys
from pathlib import Path
from functools import wraps
from collections import defaultdict
from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, auth

# Add backend to path to import service_utils
sys.path.insert(0, str(Path(__file__).parent.parent / 'backend'))

from auth_manager import AuthManager
from pending_billing_queue import PendingBillingQueue
from service_utils import require_internal_token, ResilientServiceClient, ServiceUnavailable

# Initialize Flask
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Managers
auth_manager = AuthManager()
pending_billing_queue = PendingBillingQueue()

# --- RATE LIMITING ---
# Simple in-memory rate limiter to prevent brute-force attacks
# Stores (IP, endpoint) → list of timestamps
rate_limit_store = defaultdict(list)

def rate_limit(max_requests=5, window_seconds=1):
    """
    Simple rate limiter decorator.
    
    Args:
        max_requests: Max requests allowed in the window
        window_seconds: Time window in seconds
    
    Returns:
        429 Too Many Requests if limit exceeded
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            # Get client IP
            client_ip = request.remote_addr
            endpoint = request.path
            key = (client_ip, endpoint)
            
            # Get current time
            now = time.time()
            
            # Clean old requests outside the window
            rate_limit_store[key] = [
                timestamp for timestamp in rate_limit_store[key]
                if now - timestamp < window_seconds
            ]
            
            # Check if limit exceeded
            if len(rate_limit_store[key]) >= max_requests:
                logger.warning(f"Rate limit exceeded for {client_ip} on {endpoint}")
                return jsonify({"error": "Too many requests"}), 429
            
            # Record this request
            rate_limit_store[key].append(now)
            
            # Call the actual endpoint
            return f(*args, **kwargs)
        return decorated
    return decorator

# --- FIREBASE AUTHENTICATION DECORATOR ---

def require_firebase_auth(f):
    """
    Decorator to extract and verify Firebase ID token from Authorization header.
    
    Automatically extracts the user_id from the Firebase token and passes it
    as a keyword argument to the decorated function. This eliminates duplicate
    token extraction and verification logic across endpoints.
    
    Usage:
        @app.route('/protected_endpoint', methods=['POST'])
        @require_firebase_auth
        def protected_endpoint(user_id):
            # user_id is automatically extracted and verified
            return jsonify({"user_id": user_id})
    
    Returns:
        401 Unauthorized if token is missing, invalid, or verification fails
        Function result otherwise
    """
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
            decoded_token = auth.verify_id_token(token)
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

# --- Firebase Setup ---
# SECURITY: Load Firebase service account from environment variable (base64 encoded)
# Never commit serviceAccountKey.json to git!
#
# To set up:
# 1. Download serviceAccountKey.json from Firebase Console
# 2. Encode to base64: cat serviceAccountKey.json | base64
# 3. Set environment variable: export GOOGLE_CREDENTIALS_BASE64="<base64-encoded-json>"
#
# Development: Create .env file with:
#   GOOGLE_CREDENTIALS_BASE64=<base64-encoded-json>
#
try:
    google_creds_b64 = os.environ.get("GOOGLE_CREDENTIALS_BASE64")
    if not google_creds_b64:
        # Fallback for development: try loading from file (must be in .gitignore)
        try:
            with open("serviceAccountKey.json", "r") as f:
                cred_dict = json.load(f)
            cred = credentials.Certificate(cred_dict)
            logger.warning("⚠️  Using serviceAccountKey.json from disk - set GOOGLE_CREDENTIALS_BASE64 for production")
        except FileNotFoundError:
            logger.error("ERROR: GOOGLE_CREDENTIALS_BASE64 env var not set and serviceAccountKey.json not found")
            logger.error("Set GOOGLE_CREDENTIALS_BASE64 environment variable with base64-encoded service account JSON")
            raise
    else:
        # Production: Decode base64 credentials
        cred_json = base64.b64decode(google_creds_b64).decode('utf-8')
        cred_dict = json.loads(cred_json)
        cred = credentials.Certificate(cred_dict)
        logger.info("✓ Firebase credentials loaded from GOOGLE_CREDENTIALS_BASE64")
    
    firebase_admin.initialize_app(cred)
    logger.info("✓ Firebase initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Firebase: {e}")
    raise

# --- Configuration ---
# --- SERVICE DISCOVERY ---
# Internal service URLs (6000-series ports are reserved for internal services)
BILLING_SERVER_URL = os.environ.get("BILLING_SERVER_URL", "http://localhost:6004")
INTERNAL_SERVICE_TOKEN = os.environ.get("INTERNAL_SERVICE_TOKEN")
USER_CAP = 500 # Your hard limit

# Initialize resilient billing client
billing_client = ResilientServiceClient(
    base_url=BILLING_SERVER_URL,
    service_name="billing_server",
    timeout=5.0,
    max_retries=2,  # Fast fail during registration - queue if fails
    circuit_breaker_threshold=3,
    circuit_breaker_timeout=30
)

def get_internal_headers():
    """Get headers dict with internal service token for requests to other services."""
    if INTERNAL_SERVICE_TOKEN:
        return {"X-INTERNAL-TOKEN": INTERNAL_SERVICE_TOKEN}
    return {}

@app.route('/validate_invite', methods=['POST'])
@rate_limit(max_requests=5, window_seconds=1)  # 5 requests per second
def validate_invite():
    """
    Step 1 of Sign-Up: Checks code AND global inventory.
    Called by Frontend BEFORE showing the sign-up form.
    Rate limited: 5 requests/second to prevent brute-force
    
    IMPORTANT: This endpoint only VALIDATES the invite code.
    It does NOT consume/decrement the invite. The invite is only consumed
    during /register_user after billing account is successfully initialized.
    
    This prevents users from burning valid invites by refreshing the page
    or retrying failed signup attempts.
    """
    data = request.get_json()
    code = data.get('code')
    
    if not code:
        return jsonify({"valid": False, "error": "Code required"}), 400

    # 1. Check Code Validity (validation only - no side effects)
    invite_status = auth_manager.validate_invite(code)
    if not invite_status['valid']:
        return jsonify(invite_status), 403

    # 2. Check Global Inventory (The "Sold Out" Logic)
    try:
        # Call Billing Server to get active subscription count
        headers = get_internal_headers()
        resp = requests.get(f"{BILLING_SERVER_URL}/stats/subscription_count", headers=headers, timeout=3)
        if resp.status_code == 200:
            count = resp.json().get('count', 0)
            if count >= USER_CAP:
                return jsonify({
                    "valid": False, 
                    "error": "We are currently at full capacity. Please join the waitlist."
                }), 503
    except Exception as e:
        logger.error(f"Failed to check inventory: {e}")
        # Fail open or closed? For a startup, maybe fail open (allow signup) if billing is down?
        # Let's be safe and log it but allow for now if code is valid.
        pass

    return jsonify({"valid": True, "role": invite_status['role']})

@app.route('/register_user', methods=['POST'])
def register_user():
    """
    Step 2 of Sign-Up: Called AFTER Firebase creates the user.
    This records them in our local DB and consumes the invite.
    
    SECURITY MODEL:
    - Client authentication: Firebase ID token (user must have created account in Firebase)
    - Service authentication: X-INTERNAL-TOKEN header for calls to billing_server
    - Downstream enforcement: billing_server validates X-INTERNAL-TOKEN before allowing account creation
    
    This prevents:
    1. Unauthenticated users from registering (Firebase token required)
    2. Unauthorized billing account creation (internal token required)
    3. Half-created users (billing must succeed before persisting local user)
    
    Validates:
    - id_token is valid Firebase ID token
    - email exists in token
    - invite_code is valid
    - user doesn't already exist
    """
    # 1. VALIDATE INPUT: Check required fields
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400
    
    id_token = data.get('id_token')
    invite_code = data.get('invite_code')
    
    if not id_token or not isinstance(id_token, str):
        logger.warning(f"register_user: missing or invalid id_token from {request.remote_addr}")
        return jsonify({"error": "id_token is required and must be a string"}), 400
    
    if not invite_code or not isinstance(invite_code, str):
        logger.warning(f"register_user: missing or invalid invite_code from {request.remote_addr}")
        return jsonify({"error": "invite_code is required and must be a string"}), 400

    try:
        # 2. VERIFY TOKEN: Decode Firebase ID token
        decoded_token = auth.verify_id_token(id_token)
        user_id = decoded_token.get('uid')
        email = decoded_token.get('email')
        email_verified = decoded_token.get('email_verified', False)
        
        # 3. VALIDATE TOKEN CONTENTS: Ensure email exists and is verified
        if not email:
            logger.warning(f"register_user: Firebase token missing email for user {user_id}")
            return jsonify({"error": "Firebase token must have an email"}), 400
        
        # Optionally enforce email verification (set to True for production)
        if not email_verified:
            logger.warning(f"register_user: Email not verified for {email}")
            # Could return 400 to require verification:
            # return jsonify({"error": "Email must be verified"}), 400
            # For now, allow but log it
            pass
        
        # 4. VALIDATE INVITE: Check code is valid and not consumed yet
        invite_status = auth_manager.validate_invite(invite_code)
        if not invite_status.get('valid'):
            error_msg = invite_status.get('error', 'Invalid invite code')
            logger.warning(f"register_user: Invalid invite code '{invite_code}': {error_msg}")
            return jsonify({"error": error_msg}), 403
        
        # 5. CHECK DUPLICATE: Ensure user doesn't already exist
        existing_user = auth_manager.get_user_role(user_id)
        if existing_user:
            logger.warning(f"register_user: User {user_id} already exists")
            return jsonify({"error": "User already registered"}), 409
        
        # 6. INITIALIZE BILLING ACCOUNT: Try to create billing account with resilience
        # CHANGED: Now uses ResilientServiceClient with exponential backoff and circuit breaker
        # If billing_server is down, we queue for retry instead of blocking user registration
        # This prevents "zombie users" (Firebase account exists but no billing account)
        # SECURITY: Billing Server validates X-INTERNAL-TOKEN header (see @require_internal_token decorator)
        headers = get_internal_headers()
        billing_created = False
        billing_error = None
        
        try:
            # Try to create billing account immediately with resilient client
            resp = billing_client.post(
                "/account",
                json={
                    "user_id": user_id,
                    "tier": invite_status['role']
                },
                headers=headers
            )
            
            if resp.status_code == 201:
                billing_created = True
                logger.info(f"register_user: Billing account initialized for {user_id}")
            else:
                billing_error = f"Unexpected status {resp.status_code}: {resp.text}"
                raise Exception(billing_error)
                
        except ServiceUnavailable as e:
            # Billing server is down/circuit open - queue for retry
            billing_error = f"Billing service unavailable: {e}"
            logger.warning(
                f"register_user: Billing server unavailable for {user_id}. "
                f"Queuing for background retry. User can log in immediately."
            )
        except Exception as e:
            # Other errors (timeout, connection error, etc.) - also queue for retry
            billing_error = str(e)
            logger.warning(
                f"register_user: Billing account creation failed for {user_id}: {e}. "
                f"Queuing for background retry."
            )
        
        # If billing creation failed, queue for background retry
        if not billing_created:
            pending_billing_queue.enqueue(user_id, invite_status['role'], billing_error)
            logger.info(
                f"register_user: User {user_id} queued for billing account creation. "
                f"User can log in and use the app immediately."
            )
        
        # 7. CREATE USER AND CONSUME INVITE: Atomic transaction (both succeed or both fail)
        # This ensures no half-created users even if one operation fails
        reg_result = auth_manager.complete_registration(
            user_id, 
            email, 
            role=invite_status['role'],
            invite_code=invite_code
        )
        
        if not reg_result.get('success'):
            error_msg = reg_result.get('error', 'Registration failed')
            logger.warning(f"register_user: Transaction failed for {user_id}: {error_msg}")
            return jsonify({"error": error_msg}), 500
        
        logger.info(f"register_user: Successfully registered {email} ({user_id})")
        return jsonify({"status": "success", "user_id": user_id}), 201

    except auth.InvalidIdTokenError as e:
        logger.warning(f"register_user: Invalid ID token format: {e}")
        return jsonify({"error": "Invalid or expired token"}), 401
    except auth.ExpiredIdTokenError as e:
        logger.warning(f"register_user: Expired ID token: {e}")
        return jsonify({"error": "Token has expired"}), 401
    except auth.RevokedIdTokenError as e:
        logger.warning(f"register_user: Revoked ID token: {e}")
        return jsonify({"error": "Token has been revoked"}), 401
    except Exception as e:
        logger.error(f"register_user: Unexpected error: {e}", exc_info=True)
        return jsonify({"error": "Registration failed - please try again"}), 500

@app.route('/verify_token', methods=['GET'])
@rate_limit(max_requests=10, window_seconds=1)  # 10 requests per second
@require_firebase_auth
def verify_token(user_id):
    """
    The "Gatekeeper" Endpoint.
    Called by backend/app.py to check if a request is allowed.
    Automatically extracts user_id from Firebase token via decorator.
    Rate limited: 10 requests/second
    
    SECURITY: Returns 403 Forbidden if user exists in Firebase but is not registered
    in our system (prevents unregistered users from accessing the API).
    
    ANALYTICS: Updates last_login timestamp for monitoring and analytics purposes.
    """
    try:
        # Get Internal Role - returns None if user not found in our database
        role = auth_manager.get_user_role(user_id)
        
        # CRITICAL: Reject unregistered users (Firebase token exists but no local user record)
        if role is None:
            logger.warning(f"Attempt to access API with unregistered Firebase user: {user_id}")
            return jsonify({"valid": False, "error": "User not registered"}), 403
        
        # ANALYTICS: Update last login timestamp for account health monitoring
        try:
            auth_manager.update_last_login(user_id)
        except Exception as e:
            # Log the error but don't fail the request - last_login is not critical to auth
            logger.warning(f"Failed to update last_login for {user_id}: {e}")
        
        return jsonify({
            "valid": True, 
            "user_id": user_id, 
            "role": role
        })
    except Exception as e:
        logger.error(f"Error retrieving user role for {user_id}: {e}", exc_info=True)
        return jsonify({"valid": False, "error": "Internal server error"}), 500

@app.route('/grant_access', methods=['POST'])
@rate_limit(max_requests=5, window_seconds=1)  # 5 requests per second
@require_firebase_auth
def grant_access(user_id):
    """
    Grant a 'Guest Pass' to another user.
    
    REQUIRES authentication via Firebase ID token (automatically extracted via decorator).
    The owner_id is derived from the token, not the request body (prevents spoofing).
    Rate limited: 5 requests/second to prevent abuse
    """
    # 1. VALIDATE INPUT
    data = request.get_json()
    target_email = data.get('target_email')
    project_id = data.get('project_id')
    
    if not target_email or not project_id:
        return jsonify({"error": "target_email and project_id are required"}), 400
    
    # 2. AUTHORIZATION: Verify user owns this project
    if not auth_manager.user_owns_project(user_id, project_id):
        logger.warning(f"{user_id} attempted to grant access to project they do not own: {project_id}")
        return jsonify({"error": "Forbidden"}), 403
    
    try:
        # 3. Find target user by email (Firebase Admin SDK)
        user = auth.get_user_by_email(target_email)
        target_uid = user.uid
        
        # 4. Grant access
        auth_manager.grant_project_access(project_id, target_uid)
        logger.info(f"Access granted by {user_id} to {target_email} for project {project_id}")
        
        return jsonify({"message": f"Access granted to {target_email}"})
        
    except auth.UserNotFoundError:
        logger.warning(f"User not found: {target_email}")
        return jsonify({"error": "User not found"}), 404
    except Exception as e:
        logger.error(f"grant_access error: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

@app.route('/internal/projects', methods=['POST'])
@require_internal_token
def internal_create_project():
    """
    INTERNAL-ONLY endpoint: Create a new project record with owner tracking.
    
    SECURITY: This endpoint is protected by @require_internal_token and should only
    be called by the backend service after creating project directories.
    
    This registers the project in the authoritative database, replacing filesystem
    enumeration which was vulnerable to timing attacks.
    
    Args (JSON body):
        project_id: The project ID to register
        owner_id: The Firebase UID of the project owner
        
    Returns:
        201 Created: Project successfully registered
        400 Bad Request: Missing required fields
        409 Conflict: Project already exists
        500 Server Error: Database error
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body is required"}), 400
        
        project_id = data.get('project_id')
        owner_id = data.get('owner_id')
        
        if not project_id or not owner_id:
            return jsonify({"error": "project_id and owner_id are required"}), 400
        
        # Try to register the project
        success = auth_manager.register_project(project_id, owner_id)
        
        if success:
            logger.info(f"[INTERNAL] Project created: {project_id} by {owner_id}")
            return jsonify({"message": "Project created successfully", "project_id": project_id}), 201
        else:
            # Could be already exists or database error
            # Assume already exists for now (register_project logs the reason)
            return jsonify({"error": "Project already exists"}), 409
            
    except Exception as e:
        logger.error(f"Error in /internal/projects: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

@app.route('/internal/projects/<project_id>/owner', methods=['GET'])
@require_internal_token
def internal_get_project_owner(project_id):
    """
    INTERNAL-ONLY endpoint: Get the owner of a project from the database.
    
    SECURITY: This endpoint is protected by @require_internal_token and should only
    be called by other internal services (filesystem_server, backend, etc.).
    
    Unlike filesystem scanning (timing attack vulnerable), this queries the authoritative
    database to determine project ownership.
    
    Args:
        project_id: The project ID to look up
        
    Returns:
        JSON with 'project_id' and 'owner_id' fields
        404 if project not found
        
    CRITICAL: The caller (filesystem_server) must NOT trust X-User-ID in their own requests.
    This endpoint provides the actual owner - the caller should compare it with any
    user_id they received in headers.
    """
    try:
        owner_id = auth_manager.get_project_owner(project_id)
        
        if owner_id is None:
            logger.warning(f"[INTERNAL] Project {project_id} not found")
            return jsonify({'error': 'Project not found'}), 404
        
        logger.info(f"[INTERNAL] Project owner lookup: {project_id} → {owner_id}")
        return jsonify({'project_id': project_id, 'owner_id': owner_id}), 200
        
    except Exception as e:
        logger.error(f"Error in /internal/projects/{project_id}/owner: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/internal/project_owner/<project_id>', methods=['GET'])
@require_internal_token
def get_project_owner_internal(project_id):
    """
    DEPRECATED: Use /internal/projects/<project_id>/owner instead.
    Kept for backward compatibility during migration.
    """
    try:
        owner_id = auth_manager.get_project_owner(project_id)
        
        if owner_id is None:
            logger.warning(f"[INTERNAL] Project {project_id} not found")
            return jsonify({'error': 'Project not found'}), 404
        
        logger.info(f"[INTERNAL] Project owner lookup (DEPRECATED): {project_id} → {owner_id}")
        return jsonify({'project_id': project_id, 'owner': owner_id}), 200
        
    except Exception as e:
        logger.error(f"Error in /internal/project_owner/{project_id}: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/admin/retry_pending_billing', methods=['POST'])
@require_internal_token
def retry_pending_billing():
    """
    Background worker endpoint to retry pending billing account creations.
    
    This endpoint should be called periodically (e.g., via cron or task scheduler)
    to process users who registered when billing_server was unavailable.
    
    The queue uses exponential backoff:
    - Attempt 1: Immediate (during registration)
    - Attempt 2: 30 seconds later
    - Attempt 3: 2 minutes later
    - Attempt 4: 8 minutes later
    - Attempt 5: 32 minutes later
    - After 5 attempts: Marked as failed_permanent, requires manual intervention
    
    SECURITY: Protected by @require_internal_token to prevent unauthorized access.
    Only internal services or admin scripts should call this endpoint.
    
    Returns:
        JSON summary of retry results:
        - total_pending: Number of items ready for retry
        - attempts: Number of retry attempts made
        - successes: Number of successfully created accounts
        - failures: Number of failed attempts (will retry later)
        - permanent_failures: Number of items that exceeded max retries
    """
    try:
        logger.info("[BILLING-RETRY] Starting pending billing account retry worker")
        
        # Get all pending items ready for retry
        pending_items = pending_billing_queue.get_pending_items()
        
        if not pending_items:
            logger.info("[BILLING-RETRY] No pending billing accounts to retry")
            return jsonify({
                "status": "success",
                "total_pending": 0,
                "message": "No pending billing accounts"
            }), 200
        
        logger.info(f"[BILLING-RETRY] Found {len(pending_items)} pending billing accounts")
        
        # Process each pending item
        successes = 0
        failures = 0
        permanent_failures = 0
        headers = get_internal_headers()
        
        for item in pending_items:
            user_id = item['user_id']
            tier = item['tier']
            retry_count = item['retry_count']
            
            logger.info(
                f"[BILLING-RETRY] Retrying billing account for {user_id} "
                f"(attempt {retry_count + 1}/{item['max_retries']})"
            )
            
            try:
                # Try to create billing account with resilient client
                resp = billing_client.post(
                    "/account",
                    json={"user_id": user_id, "tier": tier},
                    headers=headers
                )
                
                if resp.status_code == 201:
                    # Success!
                    pending_billing_queue.mark_retry_attempt(user_id, success=True)
                    successes += 1
                    logger.info(f"[BILLING-RETRY] ✓ Successfully created billing account for {user_id}")
                else:
                    # Unexpected status code
                    error_msg = f"Status {resp.status_code}: {resp.text}"
                    pending_billing_queue.mark_retry_attempt(user_id, success=False, error_message=error_msg)
                    failures += 1
                    logger.warning(f"[BILLING-RETRY] Failed for {user_id}: {error_msg}")
                    
            except ServiceUnavailable as e:
                # Billing server still unavailable
                error_msg = f"Service unavailable: {e}"
                pending_billing_queue.mark_retry_attempt(user_id, success=False, error_message=error_msg)
                failures += 1
                logger.warning(f"[BILLING-RETRY] Service unavailable for {user_id}, will retry later")
                
            except Exception as e:
                # Other errors (timeout, connection, etc.)
                error_msg = str(e)
                pending_billing_queue.mark_retry_attempt(user_id, success=False, error_message=error_msg)
                failures += 1
                logger.error(f"[BILLING-RETRY] Error for {user_id}: {e}", exc_info=True)
        
        # Check for permanent failures (exceeded max retries)
        permanent_failures = pending_billing_queue.get_failed_permanent_count()
        
        result = {
            "status": "success",
            "total_pending": len(pending_items),
            "attempts": len(pending_items),
            "successes": successes,
            "failures": failures,
            "permanent_failures": permanent_failures
        }
        
        logger.info(
            f"[BILLING-RETRY] Completed: {successes} successes, {failures} failures, "
            f"{permanent_failures} permanent failures"
        )
        
        # Alert if there are permanent failures requiring manual intervention
        if permanent_failures > 0:
            logger.error(
                f"[BILLING-RETRY] ⚠️ ALERT: {permanent_failures} users with permanent billing failures! "
                f"Manual intervention required. Check pending_billing table for details."
            )
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"[BILLING-RETRY] Worker failed: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

if __name__ == '__main__':
    import os
    if os.getenv('FLASK_ENV') == 'development':
        app.run(debug=True, port=6001)
    else:
        print("Use gunicorn for production: gunicorn -w 4 -b 0.0.0.0:6001 auth_server.app:app")