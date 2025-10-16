"""Main UI routes for George application."""
from flask import Blueprint, render_template, redirect, url_for
from ..auth.auth_client import verify_firebase_token

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Home page - public landing page."""
    # Public landing page (no authentication required)
    return render_template('index.html')

@main_bp.route('/dashboard')
@verify_firebase_token()
def dashboard():
    """Renders the main user dashboard after login."""
    # Redirect to the projects list - the actual dashboard
    return redirect(url_for('project_manager.list_projects'))

# Additional general routes (upload, chat, etc.) can be added here
# Project-specific routes are now in the project_manager blueprint
