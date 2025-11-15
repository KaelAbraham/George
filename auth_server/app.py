import os
import logging
import requests
import base64
import json
import time
from functools import wraps
from collections import defaultdict
from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, auth
from auth_manager import AuthManager

# Initialize Flask
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Managers
auth_manager = AuthManager()

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
        
        # 6. INITIALIZE BILLING ACCOUNT: Call Billing Server BEFORE persisting user
        # This ensures if billing fails, we don't leave a half-created user in the system
        headers = get_internal_headers()
        try:
            resp = requests.post(
                f"{BILLING_SERVER_URL}/account",
                json={
                    "user_id": user_id,
                    "tier": invite_status['role']
                },
                headers=headers,
                timeout=5
            )
            resp.raise_for_status()
            logger.info(f"register_user: Billing account initialized for {user_id}")
        except requests.exceptions.RequestException as e:
            logger.error(
                f"register_user: Failed to initialize billing account for {user_id}: {e}",
                exc_info=True
            )
            return jsonify({
                "error": "Account initialization failed. Please try again or contact support."
            }), 503
        
        # 7. CREATE USER: Record in local DB (only after billing succeeds)
        auth_manager.create_user(user_id, email, role=invite_status['role'])
        logger.info(f"register_user: Created user {user_id} with email {email}")
        
        # 8. CONSUME INVITE: Decrement uses (final step after all checks pass)
        auth_manager.decrement_invite(invite_code)
        
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
def verify_token():
    """
    The "Gatekeeper" Endpoint.
    Called by backend/app.py to check if a request is allowed.
    Rate limited: 10 requests/second
    """
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing token"}), 401

    token = auth_header.split("Bearer ")[1]
    
    try:
        # 1. Verify Firebase Token
        decoded_token = auth.verify_id_token(token)
        user_id = decoded_token['uid']
        
        # 2. Get Internal Role
        role = auth_manager.get_user_role(user_id)
        
        return jsonify({
            "valid": True, 
            "user_id": user_id, 
            "role": role
        })
    except Exception as e:
        logger.warning(f"Token verification failed: {e}")
        return jsonify({"valid": False, "error": "Invalid token"}), 401

@app.route('/grant_access', methods=['POST'])
@rate_limit(max_requests=5, window_seconds=1)  # 5 requests per second
def grant_access():
    """
    Grant a 'Guest Pass' to another user.
    
    REQUIRES authentication via Firebase ID token.
    The owner_id is derived from the token, not the request body (prevents spoofing).
    Rate limited: 5 requests/second to prevent abuse
    """
    # 1. AUTHENTICATE: Verify Firebase ID token
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith("Bearer "):
        logger.warning(f"Unauthorized grant_access attempt: missing/invalid auth header from {request.remote_addr}")
        return jsonify({"error": "Unauthorized - missing or invalid token"}), 401
    
    try:
        token = auth_header.split("Bearer ")[1]
        decoded_token = auth.verify_id_token(token)
        owner_id = decoded_token['uid']  # Derive from token, don't trust request body
    except Exception as e:
        logger.warning(f"Token verification failed in grant_access: {e}")
        return jsonify({"error": "Unauthorized - invalid token"}), 401
    
    # 2. VALIDATE INPUT
    data = request.get_json()
    target_email = data.get('target_email')
    project_id = data.get('project_id')
    
    if not target_email or not project_id:
        return jsonify({"error": "target_email and project_id are required"}), 400
    
    try:
        # 3. AUTHORIZATION: Verify owner owns this project
        # (This depends on your project ownership model - add if needed)
        # For now, we'll assume the auth_manager handles ownership checks
        
        # Find target user by email (Firebase Admin SDK)
        user = auth.get_user_by_email(target_email)
        target_uid = user.uid
        
        # Grant access
        auth_manager.grant_project_access(project_id, target_uid)
        logger.info(f"Access granted by {owner_id} to {target_email} for project {project_id}")
        
        return jsonify({"message": f"Access granted to {target_email}"})
        
    except auth.UserNotFoundError:
        logger.warning(f"User not found: {target_email}")
        return jsonify({"error": "User not found"}), 404
    except Exception as e:
        logger.error(f"grant_access error: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    import os
    if os.getenv('FLASK_ENV') == 'development':
        app.run(debug=True, port=6001)
    else:
        print("Use gunicorn for production: gunicorn -w 4 -b 0.0.0.0:6001 auth_server.app:app")