"""Main UI routes for George application."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from werkzeug.utils import secure_filename
import os
import sys
from pathlib import Path

# Add the src directory to the path so we can import from george
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

try:
    from george.core import GeorgeProcessor
    from george.knowledge_base.builder import KnowledgeBaseBuilder
    george_available = True
except ImportError as e:
    print(f"Warning: George modules not available: {e}")
    george_available = False

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Home page with project overview."""
    return render_template('index.html')

@main_bp.route('/upload', methods=['GET', 'POST'])
def upload():
    """Upload and process manuscript."""
    if request.method == 'POST':
        if 'manuscript' not in request.files:
            flash('No file selected', 'error')
            return redirect(request.url)
        
        file = request.files['manuscript']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            file.save(upload_path)
            
            if george_available:
                try:
                    # Process with George
                    processor = GeorgeProcessor()
                    entities = processor.extract_entities(upload_path)
                    
                    flash('Manuscript uploaded and processed successfully!', 'success')
                    return redirect(url_for('main.entity_validation', filename=filename))
                except Exception as e:
                    flash(f'Error processing manuscript: {str(e)}', 'error')
            else:
                flash('Manuscript uploaded! (Processing unavailable - George modules not found)', 'success')
                return redirect(url_for('main.index'))
        else:
            flash('Invalid file type. Please upload .txt, .md, or .docx files.', 'error')
    
    return render_template('upload.html')

@main_bp.route('/entity_validation')
@main_bp.route('/entity_validation/<filename>')
def entity_validation(filename=None):
    """Entity validation page."""
    # For now, use mock data
    mock_entities = [
        {'name': 'Elias', 'type': 'CHARACTER', 'confidence': 0.95, 'context': 'Main protagonist'},
        {'name': 'Silverdale', 'type': 'LOCATION', 'confidence': 0.88, 'context': 'Town setting'},
        {'name': 'The Old Library', 'type': 'LOCATION', 'confidence': 0.82, 'context': 'Key location'},
    ]
    return render_template('entity_validation.html', entities=mock_entities, filename=filename)

@main_bp.route('/chat')
def chat():
    """Chat interface page."""
    return render_template('chat.html')

@main_bp.route('/test')
def test():
    """Test page."""
    return render_template('test.html')

def allowed_file(filename):
    """Check if file type is allowed."""
    allowed_extensions = {'txt', 'md', 'docx'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

@main_bp.route('/projects/<project_id>/chat')
def chat(project_id):
    """Chat interface page."""
    return render_template('chat.html', project_id=project_id)