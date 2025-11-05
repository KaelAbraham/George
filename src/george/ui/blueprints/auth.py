import firebase_admin
from firebase_admin import credentials, auth, firestore # <-- ADD 'firestore' IMPORT
from flask import request, jsonify, redirect, url_for, flash
import logging
from functools import wraps
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# --- Firebase Admin Initialization ---
# (Initialization code remains the same... ensure it's running)
if not firebase_admin._apps:
    logger.warning("Firebase Admin SDK not initialized. Attempting initialization in auth_client.")
    try:
        base_dir = Path(__file__).resolve().parent.parent.parent.parent.parent
        credential_path = base_dir / "service-account-key.json" # Assumes key is in root
        
        if credential_path.exists():
            cred = credentials.Certificate(str(credential_path))
            firebase_admin.initialize_app(cred)
            logger.info(f"Firebase Admin initialized in auth_client using key: {credential_path}")
        else:
            logger.critical(f"Firebase service account key not found at {credential_path}. Authentication will fail.")
            
    except Exception as init_e:
        logger.critical(f"Failed to initialize Firebase Admin SDK in auth_client: {init_e}", exc_info=True)


# --- NEW: Function to get or create customer document ---
def get_or_create_customer_profile(user_id: str, email: str) -> dict:
    """
    Fetches a user's customer profile from Firestore, creating one
    with default "Indie" tier settings if it doesn't exist.
    """
    db = firestore.client()
    customer_ref = db.collection('customers').document(user_id)
    
    try:
        doc = customer_ref.get()
        if doc.exists:
            logger.debug(f"Customer profile found for user: {user_id}")
            return doc.to_dict()
        else:
            # User exists in Auth, but not in Firestore. Create the customer document.
            logger.info(f"No customer profile found for user: {user_id}. Creating default 'Indie' profile.")
            
            new_customer_data = {
                'email': email,
                'subscriptionTier': 'Indie',       # Default to Indie
                'subscriptionStatus': 'active',      # Start as active
                'creditBalance': 15,                 # Indie tier starting credits
                'creditsRollover': 0,                # No rollover credits to start
                'paymentProviderCustomerID': None,   # To be filled by payment processor
                'createdAt': firestore.SERVER_TIMESTAMP
            }
            
            customer_ref.set(new_customer_data)
            logger.info(f"Successfully created customer profile for user: {user_id}")
            return new_customer_data
            
    except Exception as e:
        logger.error(f"Error getting or creating customer profile for user {user_id}: {e}", exc_info=True)
        # In case of error, we can't proceed securely
        raise Exception(f"Failed to get or create customer profile: {e}")

# --- UPDATED: Decorator now loads customer profile ---
def verify_firebase_token():
    """
    Decorator to protect Flask routes by verifying the Firebase ID token
    AND loading/creating the customer profile.
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            id_token = None
            auth_header = request.headers.get('Authorization')

            if auth_header and auth_header.startswith('Bearer '):
                id_token = auth_header.split(' ').pop()

            if not id_token:
                logger.warning("Auth decorator: No token provided.")
                if 'text/html' in request.accept_mimetypes:
                    flash("You must be logged in to access this page.", "warning")
                    return redirect(url_for('auth.login', next=request.url))
                else:
                    return jsonify({"message": "Authorization token is missing!"}), 401

            try:
                # --- Step 1: Verify the token ---
                decoded_token = auth.verify_id_token(id_token)
                user_id = decoded_token.get('uid')
                user_email = decoded_token.get('email')

                if not user_id or not user_email:
                    raise auth.InvalidIdTokenError("Token is missing 'uid' or 'email'.")
                
                logger.debug(f"Auth decorator: Token verified for user UID: {user_id}")
                
                # --- Step 2 (NEW): Get or create the customer profile ---
                customer_profile = get_or_create_customer_profile(user_id, user_email)
                
                # Attach both auth info and customer profile to the request
                request.user_auth = decoded_token  # The raw auth token info
                request.user = customer_profile # The firestore customer profile

            except auth.ExpiredIdTokenError:
                 logger.warning(f"Auth decorator: Expired token received for path: {request.path}")
                 if 'text/html' in request.accept_mimetypes:
                     flash("Your session has expired. Please log in again.", "error")
                     return redirect(url_for('auth.login', next=request.url))
                 else:
                     return jsonify({"message": "Token has expired."}), 401
            except Exception as e:
                logger.error(f"Auth decorator: Token verification or customer profile creation failed: {e}", exc_info=True)
                if 'text/html' in request.accept_mimetypes:
                    flash(f"Authentication failed. Please log in again.", "error")
                    return redirect(url_for('auth.login', next=request.url))
                else:
                    return jsonify({"message": f"Authentication failed: {e}"}), 401

            return f(*args, **kwargs)
        
        return wrapper
    return decorator