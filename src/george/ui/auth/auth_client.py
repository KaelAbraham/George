import firebase_admin
from firebase_admin import credentials, auth
from flask import request, jsonify, redirect, url_for, flash # Added redirect, url_for, flash
import logging
from functools import wraps # Import wraps for proper decorator metadata
import os # Added os import
from pathlib import Path # Added Path import

logger = logging.getLogger(__name__)

# --- Firebase Admin Initialization ---
# Ensure Firebase Admin SDK is initialized only ONCE.
# This should ideally happen in your main app factory (create_app).
# We add a check here to initialize if it hasn't been done yet,
# but the primary initialization should be in app.py.
if not firebase_admin._apps:
    logger.warning("Firebase Admin SDK not initialized. Attempting initialization in auth_client.")
    # Calculate path to service account key relative to this file
    # auth_client.py -> auth -> ui -> george -> src -> project_root
    try:
        base_dir = Path(__file__).resolve().parent.parent.parent.parent.parent
        # Look for the key file in the project root or instance folder (adjust as needed)
        # It's better to configure this path via Flask app config
        credential_path_options = [
            base_dir / "service-account-key.json",
            base_dir / "instance" / "service-account-key.json" # Common Flask pattern
        ]
        CREDENTIALS_PATH = None
        for path_option in credential_path_options:
            if path_option.exists():
                CREDENTIALS_PATH = str(path_option)
                break
        
        if CREDENTIALS_PATH:
            cred = credentials.Certificate(CREDENTIALS_PATH)
            firebase_admin.initialize_app(cred)
            logger.info(f"Firebase Admin initialized in auth_client using key: {CREDENTIALS_PATH}")
        else:
            logger.critical("Firebase service account key not found in expected locations. Authentication will fail.")
            # Define a dummy auth object to prevent NameErrors if needed
            class DummyAuth:
                def verify_id_token(self, *args, **kwargs):
                    raise Exception("Firebase Admin SDK not initialized.")
            auth = DummyAuth()

    except Exception as init_e:
        logger.critical(f"Failed to initialize Firebase Admin SDK in auth_client: {init_e}", exc_info=True)
        class DummyAuth:
            def verify_id_token(self, *args, **kwargs):
                raise Exception("Firebase Admin SDK failed to initialize.")
        auth = DummyAuth()


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

            # Extract token from "Bearer <token>" header
            if auth_header and auth_header.startswith('Bearer '):
                id_token = auth_header.split(' ').pop()

            # --- Check if Token Exists ---
            if not id_token:
                logger.warning("Auth decorator: No token provided in Authorization header.")
                # Handle based on client type
                if 'text/html' in request.accept_mimetypes:
                    flash("You must be logged in to access this page.", "warning")
                    # Redirect to login, passing the originally requested URL
                    return redirect(url_for('auth.login', next=request.url))
                else: # API client
                    return jsonify({"message": "Authorization token is missing!"}), 401

            # --- Verify Token ---
            try:
                # Verify the token against the Firebase Auth API
                # This requires the Firebase Admin SDK to be initialized
                decoded_token = auth.verify_id_token(id_token)

                # Add the user's info to the request context for use in the route
                # Using request attributes is simple, Flask's 'g' object is another option
                request.user = decoded_token
                logger.debug(f"Auth decorator: Token verified for user UID: {decoded_token.get('uid')}")

            # --- Handle Specific Verification Errors ---
            except auth.ExpiredIdTokenError:
                 logger.warning(f"Auth decorator: Expired token received for path: {request.path}")
                 if 'text/html' in request.accept_mimetypes:
                     flash("Your session has expired. Please log in again.", "error")
                     return redirect(url_for('auth.login', next=request.url))
                 else:
                     return jsonify({"message": "Token has expired."}), 401
            except auth.InvalidIdTokenError as e:
                 logger.error(f"Auth decorator: Invalid token received for path: {request.path}. Error: {e}")
                 if 'text/html' in request.accept_mimetypes:
                     flash("Authentication failed (invalid token). Please log in again.", "error")
                     return redirect(url_for('auth.login', next=request.url))
                 else:
                     return jsonify({"message": f"Token is invalid."}), 401
            # --- Handle General Errors (e.g., Firebase SDK not init) ---
            except Exception as e:
                logger.error(f"Auth decorator: Token verification failed unexpectedly for path: {request.path}. Error: {e}", exc_info=True)
                if 'text/html' in request.accept_mimetypes:
                    flash("Authentication failed due to a server error. Please try logging in again.", "error")
                    return redirect(url_for('auth.login', next=request.url))
                else:
                    return jsonify({"message": f"Token verification failed unexpectedly."}), 500 # Use 500 for server error

            # If token is valid, proceed with the original function
            return f(*args, **kwargs)

        return wrapper
    return decorator