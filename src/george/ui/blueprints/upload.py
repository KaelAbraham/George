import os
import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from werkzeug.utils import secure_filename
from pathlib import Path

# Assuming these imports are correct relative to the blueprints folder
from ..auth.auth_client import verify_firebase_token
from ...project_manager import ProjectManager
from ...parsers.parsers import read_manuscript_file # Import the parser

# Define the blueprint, now tied to a specific project
upload_bp = Blueprint('upload', __name__, url_prefix='/projects/<project_id>/upload')

logger = logging.getLogger(__name__)
pm = ProjectManager(base_dir="src/data/uploads") # Initialize ProjectManager

ALLOWED_EXTENSIONS = {'txt', 'md', 'docx'}

def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@upload_bp.route('/', methods=['GET'])
@verify_firebase_token()
def show_upload_form(project_id):
    """Display the manuscript upload page for a specific project."""
    try:
        project = pm.load_project(project_id)
        if not project:
            flash(f"Project '{project_id}' not found.", "error")
            return redirect(url_for('project_manager.dashboard'))
        return render_template('upload.html', project=project)
    except Exception as e:
        logger.error(f"Error loading project {project_id} for upload: {e}", exc_info=True)
        flash("Error loading project data.", "error")
        return redirect(url_for('project_manager.dashboard'))

@upload_bp.route('/process', methods=['POST'])
@verify_firebase_token()
def process_upload(project_id):
    """Handle manuscript file upload, convert to MD, and save."""
    try:
        project = pm.load_project(project_id)
        if not project:
            flash(f"Project '{project_id}' not found.", "error")
            return redirect(url_for('project_manager.dashboard'))

        if 'manuscript' not in request.files:
            flash('No file selected.', 'error')
            return redirect(url_for('upload.show_upload_form', project_id=project_id))

        file = request.files['manuscript']
        if file.filename == '':
            flash('No file selected.', 'error')
            return redirect(url_for('upload.show_upload_form', project_id=project_id))

        if file and allowed_file(file.filename):
            original_filename = secure_filename(file.filename)
            project_dir = Path(pm.get_project_path(project_id))
            
            # --- Save temporarily to read content ---
            # Ensure the uploads directory within the project exists
            temp_upload_dir = project_dir / "temp_uploads"
            temp_upload_dir.mkdir(parents=True, exist_ok=True)
            temp_file_path = temp_upload_dir / original_filename
            file.save(temp_file_path) # Save the uploaded file temporarily

            try:
                # --- Read content using the parser ---
                logger.info(f"Reading content from temporary file: {temp_file_path}")
                file_content = read_manuscript_file(str(temp_file_path))

                # --- Define the new Markdown filename ---
                md_filename = Path(original_filename).stem + ".md"
                md_file_path = project_dir / md_filename

                # --- Save content as Markdown ---
                logger.info(f"Saving converted content to: {md_file_path}")
                with open(md_file_path, 'w', encoding='utf-8') as f:
                    f.write(file_content)

                # --- Update project metadata ---
                logger.info(f"Updating project metadata with new file: {md_filename}")
                pm.add_manuscript_file(project_id, md_filename)
                # Ensure the status reflects that KB needs generation/regeneration
                pm.update_project_status(project_id, "created") 

                flash(f'Manuscript "{original_filename}" uploaded and converted to "{md_filename}" successfully!', 'success')
                
                # Clean up temporary file
                temp_file_path.unlink()

                # Redirect back to the project dashboard to show updated status
                return redirect(url_for('project_manager.dashboard'))

            except ValueError as ve: # Catch specific parser errors
                 logger.error(f"Unsupported file type uploaded: {original_filename}. Error: {ve}")
                 flash(f'Error processing file: {ve}', 'error')
                 temp_file_path.unlink(missing_ok=True) # Clean up temp file on error
                 return redirect(url_for('upload.show_upload_form', project_id=project_id))
            except Exception as e:
                 logger.error(f"Error reading/converting file {original_filename}: {e}", exc_info=True)
                 flash(f'Error processing file. Check logs for details.', 'error')
                 temp_file_path.unlink(missing_ok=True) # Clean up temp file on error
                 return redirect(url_for('upload.show_upload_form', project_id=project_id))

        else:
            flash('Invalid file type. Please upload a .docx, .md, or .txt file.', 'error')
            return redirect(url_for('upload.show_upload_form', project_id=project_id))

    except Exception as e:
        logger.error(f"General error during upload process for project {project_id}: {e}", exc_info=True)
        flash("An unexpected error occurred during upload.", "error")
        return redirect(url_for('project_manager.dashboard'))