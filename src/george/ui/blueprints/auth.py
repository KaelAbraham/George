from flask import Blueprint, render_template

# Define the blueprint
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

@auth_bp.route('/login')
def login():
    """Displays the login page."""
    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    """Handles user logout."""
    # (We will add the logout logic here later)
    return "Logged out!"