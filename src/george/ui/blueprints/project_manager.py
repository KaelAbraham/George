from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from ..auth.auth_client import verify_firebase_token
from ..backend_client import backend_client
import logging

logger = logging.getLogger(__name__)

# Define the blueprint
project_bp = Blueprint('project', __name__, url_prefix='/projects')

@project_bp.route('/')
@verify_firebase_token()
def dashboard():
    """Display the project dashboard with a list of existing projects."""
    try:
        user_id = request.user.get('uid') if hasattr(request, 'user') else None
        
        if not user_id:
            flash("Unauthorized access.", "error")
            return redirect(url_for('auth.login'))
        
        # Get projects from backend via HTTP
        response = backend_client.list_projects(user_id)
        
        if not response.get('success'):
            logger.error(f"Failed to list projects: {response.get('error')}")
            projects = []
        else:
            projects = response.get('data', [])
        
        user_info = request.user
        return render_template('project_dashboard.html', projects=projects, user=user_info)
    except Exception as e:
        logger.error(f"Error loading projects for dashboard: {e}", exc_info=True)
        flash(f"An error occurred loading projects. Please check logs.", "error")
        user_info = getattr(request, 'user', None)
        return render_template('project_dashboard.html', projects=[], user=user_info)

@project_bp.route('/create', methods=['GET', 'POST'])
@verify_firebase_token()
def create_project():
    """Handle project creation."""
    if request.method == 'POST':
        project_name = request.form.get('name')
        user_id = request.user.get('uid') if hasattr(request, 'user') else None
        
        if not user_id:
            flash("Unauthorized access.", "error")
            return redirect(url_for('auth.login'))
        
        if not project_name:
            flash('Project name is required.', 'error')
            return redirect(url_for('project.create_project'))
        
        try:
            # Create project via backend HTTP API
            response = backend_client.create_project(project_name, user_id)
            
            if response.get('success'):
                logger.info(f"Project '{project_name}' created successfully")
                flash(f'Project "{project_name}" created successfully!', 'success')
                return redirect(url_for('project.dashboard'))
            else:
                error_msg = response.get('error', 'Unknown error')
                logger.error(f"Backend error creating project: {error_msg}")
                flash(f"Error creating project: {error_msg}", "error")
        except Exception as e:
            logger.error(f"Error creating project '{project_name}': {e}", exc_info=True)
            flash(f"Error creating project: {e}", "error")
            
    return render_template('create_project.html')

@project_bp.route('/<project_id>', methods=['GET'])
@verify_firebase_token()
def view_project(project_id):
    """View a specific project and its files."""
    try:
        user_id = request.user.get('uid') if hasattr(request, 'user') else None
        
        if not user_id:
            flash("Unauthorized access.", "error")
            return redirect(url_for('auth.login'))
        
        # Get project via backend HTTP API
        response = backend_client.get_project(project_id, user_id)
        
        if not response.get('success'):
            logger.warning(f"Project '{project_id}' not found or access denied")
            flash(f"Project '{project_id}' not found.", "error")
            return redirect(url_for('project.dashboard'))
        
        project = response.get('data', {})
        user_info = request.user
        return render_template('project_detail.html', project=project, project_id=project_id, user=user_info)
    except Exception as e:
        logger.error(f"Error loading project '{project_id}': {e}", exc_info=True)
        flash(f"Error loading project: {e}", "error")
        return redirect(url_for('project.dashboard'))

@project_bp.route('/<project_id>/status', methods=['GET'])
@verify_firebase_token()
def get_project_status(project_id):
    """Get the current status of a project (for AJAX requests)."""
    try:
        user_id = request.user.get('uid') if hasattr(request, 'user') else None
        
        if not user_id:
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        
        # Get status via backend HTTP API
        response = backend_client.get_status(project_id, user_id)
        return jsonify(response)
    except Exception as e:
        logger.error(f"Error getting project status for '{project_id}': {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@project_bp.route('/<project_id>/entities', methods=['GET'])
@verify_firebase_token()
def get_project_entities(project_id):
    """Get entities from project (for AJAX requests)."""
    try:
        user_id = request.user.get('uid') if hasattr(request, 'user') else None
        
        if not user_id:
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        
        # Get entities via backend HTTP API
        response = backend_client.get_entities(project_id, user_id)
        return jsonify(response)
    except Exception as e:
        logger.error(f"Error getting entities for project '{project_id}': {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500