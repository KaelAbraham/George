"""Main application file for the filesystem server."""
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
import os
from services import DocumentParser, TextChunker, DocumentParserError

app = Flask(__name__)

# Configuration
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
PROJECTS_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'projects')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PROJECTS_FOLDER'] = PROJECTS_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['PROJECTS_FOLDER'], exist_ok=True)

# Initialize services
parser = DocumentParser()
chunker = TextChunker()

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'txt', 'md', 'docx'}

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'manuscript' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['manuscript']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        project_id = filename.replace('.', '_').replace(' ', '_')
        project_path = os.path.join(app.config['PROJECTS_FOLDER'], project_id)
        os.makedirs(project_path, exist_ok=True)
        
        upload_path = os.path.join(project_path, filename)
        file.save(upload_path)

        try:
            parsed_data = parser.parse(upload_path)
            chunks = chunker.chunk_text(parsed_data['content'], filename)
            
            # For simplicity, we'll just return a summary.
            # In a real application, you would store this data.
            return jsonify({
                'message': 'File uploaded and processed successfully',
                'project_id': project_id,
                'filename': filename,
                'metadata': parsed_data.get('metadata', {}),
                'chunk_count': len(chunks)
            }), 200
        except DocumentParserError as e:
            return jsonify({'error': str(e)}), 500
    else:
        return jsonify({'error': 'File type not allowed'}), 400

@app.route('/project/<project_id>/files', methods=['GET'])
def list_files(project_id):
    project_path = os.path.join(app.config['PROJECTS_FOLDER'], project_id)
    if not os.path.isdir(project_path):
        return jsonify({'error': 'Project not found'}), 404
    
    files = [f for f in os.listdir(project_path) if os.path.isfile(os.path.join(project_path, f))]
    return jsonify({'project_id': project_id, 'files': files})

@app.route('/file/<project_id>/<filename>', methods=['GET'])
def get_file(project_id, filename):
    project_path = os.path.join(app.config['PROJECTS_FOLDER'], project_id)
    file_path = os.path.join(project_path, filename)
    
    if not os.path.isfile(file_path):
        return jsonify({'error': 'File not found'}), 404
        
    try:
        parsed_data = parser.parse(file_path)
        return jsonify({
            'project_id': project_id,
            'filename': filename,
            'content': parsed_data['content'],
            'metadata': parsed_data.get('metadata', {})
        })
    except DocumentParserError as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)
