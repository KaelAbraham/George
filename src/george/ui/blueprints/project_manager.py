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
            
    return render_template('create_project.html')

@project_bp.route('/<project_id>', methods=['GET'])
@verify_firebase_token()
def view_project(project_id):
    """View a specific project and its files."""
    try:
        pm = current_app.project_manager
        project = pm.load_project(project_id)
        if not project:
            flash(f"Project '{project_id}' not found.", "error")
            return redirect(url_for('project_manager.dashboard'))
        
        user_info = request.user
        return render_template('project_detail.html', project=project, project_id=project_id, user=user_info)
    except Exception as e:
        flash(f"Error loading project: {e}", "error")
        return redirect(url_for('project_manager.dashboard'))

@project_bp.route('/<project_id>/upload', methods=['POST'])
@verify_firebase_token()
def upload_file(project_id):
    """Handle file upload for a project."""
    try:
        pm = current_app.project_manager
        
        # Check if file is in request
        if 'file' not in request.files:
            flash('No file uploaded.', 'error')
            return redirect(url_for('project_manager.view_project', project_id=project_id))
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected.', 'error')
            return redirect(url_for('project_manager.view_project', project_id=project_id))
        
        # Save the file to the project's manuscripts folder
        import os
        from werkzeug.utils import secure_filename
        
        filename = secure_filename(file.filename)
        project_path = pm.get_project_path(project_id)
        manuscripts_dir = os.path.join(project_path, 'manuscripts')
        
        file_path = os.path.join(manuscripts_dir, filename)
        file.save(file_path)
        
        # Update project metadata
        project = pm.load_project(project_id)
        if 'manuscripts' not in project or not isinstance(project['manuscripts'], list):
            project['manuscripts'] = []
        if filename not in project['manuscripts']:
            project['manuscripts'].append(filename)
        
        # Save updated metadata
        import json
        metadata_path = os.path.join(project_path, 'project.json')
        with open(metadata_path, 'w') as f:
            json.dump(project, f, indent=2)
        
        flash(f'File "{filename}" uploaded successfully!', 'success')
        return redirect(url_for('project_manager.view_project', project_id=project_id))
        
    except Exception as e:
        flash(f"Error uploading file: {e}", "error")
        return redirect(url_for('project_manager.view_project', project_id=project_id))