import firebase_admin
from firebase_admin import credentials, auth
from flask import request, jsonify, redirect, url_for, flash # Added redirect, url_for, flash
import logging
from functools import wraps # Import wraps for proper decorator metadata

logger = logging.getLogger(__name__)

# --- Firebase Admin Initialization ---
# It's better to initialize Firebase Admin only once when the app starts.
# We'll assume initialization happens in app.py or a dedicated config file.
# If not, the initialization code would need to be here or imported.
# Example (assuming it's done elsewhere):
# try:
#     firebase_admin.get_app()
# except ValueError:
#     # Initialize here if not already done
#     CREDENTIALS_PATH = "path/to/your/service-account-key.json"
#     try:
#         cred = credentials.Certificate(CREDENTIALS_PATH)
#         firebase_admin.initialize_app(cred)
#         logger.info("Firebase Admin initialized in auth_client.")
#     except Exception as init_e:
#         logger.critical(f"Failed to initialize Firebase Admin in auth_client: {init_e}")


def verify_firebase_token():
    """
    Decorator to protect Flask routes by verifying the Firebase ID token.
    Redirects browser clients to the login page on failure.
    Returns JSON error for API clients on failure.
    """
    def decorator(f):
        @wraps(f) # Use wraps to preserve original function metadata
        def wrapper(*args, **kwargs):
            id_token = None
            auth_header = request.headers.get('Authorization')

            if auth_header and auth_header.startswith('Bearer '):
                id_token = auth_header.split(' ').pop()

            if not id_token:
                logger.warning("Auth decorator: No token provided.")
                # --- Handle based on client type ---
                if 'text/html' in request.accept_mimetypes:
                    flash("You must be logged in to access this page.", "warning")
                    return redirect(url_for('auth.login', next=request.url)) # Redirect to login
                else:
                    return jsonify({"message": "Authorization token is missing!"}), 401

            try:
                # Verify the token against the Firebase Auth API
                # Ensure Firebase Admin SDK is initialized before this call
                decoded_token = auth.verify_id_token(id_token)
                # Add the user's info to the request context (Flask's 'g' is better, but request works)
                request.user = decoded_token
                logger.debug(f"Auth decorator: Token verified for user UID: {decoded_token.get('uid')}")
            except auth.ExpiredIdTokenError:
                 logger.warning("Auth decorator: Expired token received.")
                 if 'text/html' in request.accept_mimetypes:
                     flash("Your session has expired. Please log in again.", "error")
                     return redirect(url_for('auth.login', next=request.url))
                 else:
                     return jsonify({"message": "Token has expired."}), 401
            except Exception as e:
                logger.error(f"Auth decorator: Token verification failed: {e}", exc_info=True)
                # --- Handle based on client type ---
                if 'text/html' in request.accept_mimetypes:
                    flash("Authentication failed. Please log in again.", "error")
                    return redirect(url_for('auth.login', next=request.url)) # Redirect to login
                else:
                    # The client is an API client, so return JSON
                    return jsonify({"message": f"Token is invalid or verification failed."}), 401

            # If token is valid, proceed with the original function
            return f(*args, **kwargs)
        # No need for manual __name__ assignment when using @wraps
        # wrapper.__name__ = f.__name__ + '_decorated'
        return wrapper
    return decorator

# --- Example of usage (for reference, already in blueprints) ---
# from flask import Blueprint
# from .auth_client import verify_firebase_token
# example_bp = Blueprint('example', __name__)
#
# @example_bp.route('/secure-page')
# @verify_firebase_token()
# def secure_page():
#     user_id = request.user['uid']
#     return f"Hello, user {user_id}! This is a secure page."
#
# @example_bp.route('/secure-api')
# @verify_firebase_token()
# def secure_api():
#     user_id = request.user['uid']
#     return jsonify({"message": f"Hello, user {user_id}! Secure data here."})