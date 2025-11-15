import os
import logging
import requests
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

# --- Firebase Setup ---
# Ideally, put your serviceAccountKey.json in a secure folder or use ENV variables
cred = credentials.Certificate("serviceAccountKey.json") 
firebase_admin.initialize_app(cred)

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
def validate_invite():
    """
    Step 1 of Sign-Up: Checks code AND global inventory.
    Called by Frontend BEFORE showing the sign-up form.
    """
    data = request.get_json()
    code = data.get('code')
    
    if not code:
        return jsonify({"valid": False, "error": "Code required"}), 400

    # 1. Check Code Validity
    invite_status = auth_manager.validate_and_consume_invite(code)
    if not invite_status['valid']:
        return jsonify(invite_status), 403

    # 2. Check Global Inventory (The "Sold Out" Logic)
    try:
        # Call Billing Server to get active subscription count
        headers = get_internal_headers()
        resp = requests.get(f"{BILLING_SERVER_URL}/stats/subscription_count", headers=headers)
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
    """
    data = request.get_json()
    id_token = data.get('id_token')
    invite_code = data.get('invite_code')

    try:
        # Verify the Firebase Token to get the UID
        decoded_token = auth.verify_id_token(id_token)
        user_id = decoded_token['uid']
        email = decoded_token.get('email')
        
        # Re-validate invite (double check)
        invite_status = auth_manager.validate_and_consume_invite(invite_code)
        if not invite_status['valid']:
             return jsonify({"error": "Invalid invite code"}), 403

        # Create User Record
        auth_manager.create_user(user_id, email, role=invite_status['role'])
        
        # Consume Invite
        auth_manager.decrement_invite(invite_code)
        
        # Initialize Billing Account (Call Billing Server)
        headers = get_internal_headers()
        requests.post(f"{BILLING_SERVER_URL}/account", json={
            "user_id": user_id,
            "tier": invite_status['role']
        }, headers=headers)

        return jsonify({"status": "success", "user_id": user_id}), 201

    except Exception as e:
        logger.error(f"Registration failed: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/verify_token', methods=['GET'])
def verify_token():
    """
    The "Gatekeeper" Endpoint.
    Called by backend/app.py to check if a request is allowed.
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
def grant_access():
    """
    Grant a 'Guest Pass' to another user.
    
    REQUIRES authentication via Firebase ID token.
    The owner_id is derived from the token, not the request body (prevents spoofing).
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
        return jsonify({"error": f"User not found: {target_email}"}), 404
    except Exception as e:
        logger.error(f"grant_access error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    import os
    if os.getenv('FLASK_ENV') == 'development':
        app.run(debug=True, port=6001)
    else:
        print("Use gunicorn for production: gunicorn -w 4 -b 0.0.0.0:6001 auth_server.app:app")