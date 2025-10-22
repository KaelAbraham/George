import firebase_admin
from firebase_admin import credentials, auth
from flask import request, jsonify

# --- This is the setup you've already done ---
CREDENTIALS_PATH = "path/to/your/service-account-key.json"
if not firebase_admin._apps:
    cred = credentials.Certificate(CREDENTIALS_PATH)
    firebase_admin.initialize_app(cred)
# ---------------------------------------------

def verify_firebase_token():
    """
    Decorator to protect routes by verifying the Firebase ID token.
    """
    def decorator(f):
        def wrapper(*args, **kwargs):
            id_token = None
            if 'Authorization' in request.headers:
                # The token is usually sent as "Bearer <token>"
                id_token = request.headers['Authorization'].split(' ').pop()

            if not id_token:
                return jsonify({"message": "Token is missing!"}), 401

            try:
                # Verify the token against the Firebase Auth API
                decoded_token = auth.verify_id_token(id_token)
                # You can add the user's info to the request context if needed
                request.user = decoded_token
            except Exception as e:
                # Token is invalid or expired
                return jsonify({"message": f"Token is invalid: {e}"}), 401

            return f(*args, **kwargs)
        return wrapper
    return decorator

# --- Example of how to protect an API route ---
# from .auth_client import verify_firebase_token

# @bp.route('/my-protected-data')
# @verify_firebase_token()
# def get_protected_data():
#     # This code will only run if the token is valid
#     user_id = request.user['uid']
#     return jsonify({"message": f"Hello, user {user_id}! Here is your secret data."})