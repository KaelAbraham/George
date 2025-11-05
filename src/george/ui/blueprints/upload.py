import os
import logging
import tempfile
from flask import Blueprint, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename

# Import the HTTP backend client
from ..auth.auth_client import verify_firebase_token
from ..backend_client import backend_client

# Define the blueprint, now tied to a specific project
upload_bp = Blueprint('upload', __name__, url_prefix='/projects/<project_id>/upload')

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {'txt', 'md', 'docx'}

def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@upload_bp.route('/', methods=['GET'])
@verify_firebase_token()
def show_upload_form(project_id):
    """Display the manuscript upload page for a specific project."""
    try:
        user_id = request.user.get('uid') if hasattr(request, 'user') else None
        
        if not user_id:
            flash("Unauthorized access.", "error")
            return redirect(url_for('project.dashboard'))
        
        # Get project info from backend via HTTP
        response = backend_client.get_project(project_id, user_id)
        
        if not response.get('success'):
            flash(f"Project '{project_id}' not found.", "error")
            return redirect(url_for('project.dashboard'))
        
        project = response.get('data', {})
        return render_template('upload.html', project=project)
    except Exception as e:
        logger.error(f"Error loading project {project_id} for upload: {e}", exc_info=True)
        flash("Error loading project data.", "error")
        return redirect(url_for('project.dashboard'))

@upload_bp.route('/process', methods=['POST'])
@verify_firebase_token()
def process_upload(project_id):
    """Handle manuscript file upload via the backend API."""
    try:
        user_id = request.user.get('uid') if hasattr(request, 'user') else None
        
        if not user_id:
            flash("Unauthorized access.", "error")
            return redirect(url_for('project.dashboard'))
        
        # Verify project exists
        response = backend_client.get_project(project_id, user_id)
        if not response.get('success'):
            flash(f"Project '{project_id}' not found.", "error")
            return redirect(url_for('project.dashboard'))

        if 'manuscript' not in request.files:
            flash('No file selected.', 'error')
            return redirect(url_for('upload.show_upload_form', project_id=project_id))

        file = request.files['manuscript']
        if file.filename == '':
            flash('No file selected.', 'error')
            return redirect(url_for('upload.show_upload_form', project_id=project_id))

        if not (file and allowed_file(file.filename)):
            flash('Invalid file type. Please upload a .docx, .md, or .txt file.', 'error')
            return redirect(url_for('upload.show_upload_form', project_id=project_id))

        original_filename = secure_filename(file.filename)
        
        try:
            # Save file to temporary location
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(original_filename)[1]) as tmp:
                file.save(tmp.name)
                temp_file_path = tmp.name
            
            # Upload via backend HTTP API
            logger.info(f"Uploading manuscript {original_filename} to project {project_id}")
            response = backend_client.upload_manuscript(project_id, temp_file_path, user_id)
            
            # Clean up temp file
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            
            if response.get('success'):
                flash(f'Manuscript "{original_filename}" uploaded successfully!', 'success')
                return redirect(url_for('project.dashboard'))
            else:
                error_msg = response.get('error', 'Unknown error during upload')
                logger.error(f"Backend upload failed: {error_msg}")
                flash(f'Error uploading file: {error_msg}', 'error')
                return redirect(url_for('upload.show_upload_form', project_id=project_id))

        except Exception as e:
            logger.error(f"Error during file upload for project {project_id}: {e}", exc_info=True)
            flash(f'Error uploading file: {str(e)}', 'error')
            return redirect(url_for('upload.show_upload_form', project_id=project_id))

    except Exception as e:
        logger.error(f"General error during upload process for project {project_id}: {e}", exc_info=True)
        flash("An unexpected error occurred during upload.", "error")
        return redirect(url_for('project.dashboard'))