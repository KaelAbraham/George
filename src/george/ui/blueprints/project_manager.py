from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from ..auth.auth_client import verify_firebase_token

# Define the blueprint
project_bp = Blueprint('project_manager', __name__, url_prefix='/projects')

@project_bp.route('/')
@verify_firebase_token() # This decorator protects the dashboard
def dashboard():
    """Display the project dashboard with a list of existing projects."""
    try:
        projects = current_app.project_manager.list_projects()
        user_info = request.user # Get user info from the decorator
        return render_template('project_dashboard.html', projects=projects, user=user_info)
    except Exception as e:
        flash(f"An error occurred: {e}", "error")
        return render_template('project_dashboard.html', projects=[], user=request.user)

@project_bp.route('/create', methods=['GET', 'POST'])
@verify_firebase_token()
def create_project():
    """Handle project creation."""
    if request.method == 'POST':
        project_name = request.form.get('name')
        if not project_name:
            flash('Project name is required.', 'error')
            return redirect(url_for('project_manager.create_project'))
        
        try:
            current_app.project_manager.create_project(project_name)
            flash(f'Project "{project_name}" created successfully!', 'success')
            return redirect(url_for('project_manager.dashboard'))
        except Exception as e:
            flash(f"Error creating project: {e}", "error")
            
    return render_template('create_project.html') # We will create this file next