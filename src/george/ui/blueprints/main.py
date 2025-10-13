"""Main UI routes for George application."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from werkzeug.utils import secure_filename
import os

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Home page that lists all projects."""
    projects = current_app.project_manager.list_projects()
    # Sort projects by name for consistency
    sorted_projects = sorted(projects, key=lambda p: p.get('name', ''))
    return render_template('projects.html', projects=sorted_projects)

@main_bp.route('/create_project', methods=['POST'])
def create_project():
    """Handles new project creation."""
    project_name = request.form.get('project_name')
    if not project_name or not project_name.strip():
        flash('Project name cannot be empty.', 'error')
        return redirect(url_for('main.index'))
    
    try:
        current_app.project_manager.create_project(project_name)
        flash(f"Project '{project_name}' created successfully!", 'success')
    except Exception as e:
        flash(str(e), 'error')
        
    return redirect(url_for('main.index'))

@main_bp.route('/project/<project_name>')
def project_dashboard(project_name):
    """Shows the dashboard for a specific project."""
    try:
        project_data = current_app.project_manager.load_project(project_name)
        return f"<h1>Project Dashboard for {project_data['project_name']}</h1><p>Next, we will build the file upload and chat features here.</p>"
    except Exception as e:
        flash(str(e), 'error')
        return redirect(url_for('main.index'))

# We will re-integrate upload, chat, etc., into the project context later.
# For now, we focus on the project dashboard.
