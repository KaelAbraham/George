from flask import Blueprint, render_template, redirect, url_for

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """
    Main landing page.
    For now, we will redirect directly to the project dashboard.
    Later, this can be a beautiful landing page for new users.
    """
    # Redirect all traffic to the login page to start
    return redirect(url_for('auth.login'))