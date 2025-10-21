from flask import Blueprint, render_template, request, jsonify, session
from firebase_admin import auth as firebase_auth

# Define the blueprint
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

@auth_bp.route('/login')
def login():
    """Displays the login page."""
    return render_template('login.html')

@auth_bp.route('/session', methods=['POST'])
def create_session():
    """Creates a server-side session after Firebase authentication."""
    try:
        # Get the ID token from the request
        id_token = None
        if 'Authorization' in request.headers:
            id_token = request.headers['Authorization'].split(' ').pop()
        
        if not id_token:
            data = request.get_json()
            id_token = data.get('idToken')
        
        if not id_token:
            return jsonify({'error': 'No token provided'}), 401
        
        # Verify the token with Firebase Admin SDK
        decoded_token = firebase_auth.verify_id_token(id_token)
        uid = decoded_token['uid']
        email = decoded_token.get('email', '')
        
        # Store user info in Flask session
        session['user_id'] = uid
        session['user_email'] = email
        session['firebase_token'] = id_token
        session.permanent = True  # Make session persist
        
        return jsonify({
            'status': 'success',
            'message': 'Session created',
            'user': {'uid': uid, 'email': email}
        })
        
    except Exception as e:
        return jsonify({'error': f'Authentication failed: {str(e)}'}), 401

@auth_bp.route('/logout')
def logout():
    """Handles user logout."""
    session.clear()
    return render_template('login.html')