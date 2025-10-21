import firebase_admin
from firebase_admin import credentials, auth
from flask import request, jsonify, redirect, url_for, flash, session
from pathlib import Path

# --- Initialize Firebase Admin SDK ---
# Path to your Firebase service account key
# Navigate from src/george/ui/auth/ up to project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
CREDENTIALS_PATH = PROJECT_ROOT / "george-6a8da-firebase-adminsdk-fbsvc-e85c43d430.json"

if not firebase_admin._apps:
    if not CREDENTIALS_PATH.exists():
        raise FileNotFoundError(f"Firebase credentials not found at {CREDENTIALS_PATH}")
    cred = credentials.Certificate(str(CREDENTIALS_PATH))
    firebase_admin.initialize_app(cred)
# ---------------------------------------------

def verify_firebase_token():
    """
    Decorator to protect routes by verifying the Firebase ID token or session.
    Redirects browsers to the login page and returns JSON for API clients.
    """
    def decorator(f):
        from functools import wraps
        @wraps(f)
        def wrapper(*args, **kwargs):
            # First check if user has a valid session
            if 'user_id' in session and 'user_email' in session:
                # User has a valid session, populate request.user
                request.user = {
                    'uid': session['user_id'],
                    'email': session['user_email']
                }
                return f(*args, **kwargs)
            
            # No session, check for Authorization header (for API calls)
            id_token = None
            if 'Authorization' in request.headers:
                # The token is usually sent as "Bearer <token>"
                id_token = request.headers['Authorization'].split(' ').pop()

            if not id_token:
                # Check if the client prefers HTML (i.e., it's a browser)
                if 'text/html' in request.accept_mimetypes:
                    flash("Please log in to access this page.", "warning")
                    return redirect(url_for('auth.login'))
                else:
                    # The client is an API client, so return JSON
                    return jsonify({"message": "Token is missing!"}), 401

            try:
                # Verify the token against the Firebase Auth API
                decoded_token = auth.verify_id_token(id_token)
                # You can add the user's info to the request context if needed
                request.user = decoded_token
            except Exception as e:
                # Token is invalid or expired
                # Check if the client prefers HTML (i.e., it's a browser)
                if 'text/html' in request.accept_mimetypes:
                    flash("Your session has expired or is invalid. Please log in.", "error")
                    return redirect(url_for('auth.login'))
                else:
                    # The client is an API client, so return JSON
                    return jsonify({"message": f"Token is invalid: {e}"}), 401

            return f(*args, **kwargs)
        return wrapper
    return decorator