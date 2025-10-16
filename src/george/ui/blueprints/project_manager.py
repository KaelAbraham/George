"""Project management routes - handles project CRUD operations."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from ..auth.auth_client import verify_firebase_token

# This blueprint handles project-specific operations
project_manager_bp = Blueprint('project_manager', __name__, url_prefix='/projects')

@project_manager_bp.route('/')
@verify_firebase_token()
def list_projects():
    """Display all projects for the authenticated user."""
    projects = current_app.project_manager.list_projects()
    sorted_projects = sorted(projects, key=lambda p: p.get('name', ''))
    user_info = request.user
    return render_template('project_dashboard.html', projects=sorted_projects, user=user_info)

@project_manager_bp.route('/create', methods=['GET', 'POST'])
@verify_firebase_token()
def create_project():
    """Handle project creation."""
    if request.method == 'GET':
        return render_template('create_project.html')
    
    # POST request
    project_name = request.form.get('name') or request.form.get('project_name')
    if not project_name or not project_name.strip():
        flash('Project name cannot be empty.', 'error')
        return redirect(url_for('project_manager.list_projects'))
    
    try:
        current_app.project_manager.create_project(project_name)
        flash(f'Project "{project_name}" created successfully!', 'success')
    except Exception as e:
        flash(f'Error creating project: {str(e)}', 'error')
    
    return redirect(url_for('project_manager.list_projects'))

@project_manager_bp.route('/<project_name>')
@verify_firebase_token()
def view_project(project_name):
    """View a specific project's details."""
    try:
        project_data = current_app.project_manager.load_project(project_name)
        user_info = request.user
        return render_template('project_detail.html', project=project_data, user=user_info)
    except Exception as e:
        flash(f'Error loading project: {str(e)}', 'error')
        return redirect(url_for('project_manager.list_projects'))