"""Main application file for the filesystem server."""
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
import os
from services import DocumentParser, TextChunker, WebSanitizer, DocumentParserError
import requests # <-- Make sure requests is imported
import dataclasses # <-- Import dataclasses
import uuid
import json

app = Flask(__name__)

# Configuration
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
PROJECTS_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'projects')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PROJECTS_FOLDER'] = PROJECTS_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB (increased for large PDFs)

# --- NEW: Define allowed extensions set ---
ALLOWED_EXTENSIONS = {'txt', 'md', 'docx', 'pdf', 'odt'}

# URL for the *next* server in the chain
CHROMA_SERVER_URL = "http://localhost:5002" # Make sure this is your chroma_server address

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['PROJECTS_FOLDER'], exist_ok=True)

# Initialize services
parser = DocumentParser()
chunker = TextChunker()

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload/<project_id>', methods=['POST'])
def upload_file(project_id):
    """
    Handles file upload, validation, parsing, chunking,
    and forwards chunks to the chroma-core server.
    """
    if 'manuscript' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['manuscript']
    
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    if not project_id:
        return jsonify({"error": "Project ID is required"}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        
        project_path = os.path.join(app.config['PROJECTS_FOLDER'], project_id)
        os.makedirs(project_path, exist_ok=True)
        
        upload_path = os.path.join(project_path, filename)
        file.save(upload_path)

        try:
            # 1. Parse File
            parsed_data = parser.parse(upload_path)
            content = parsed_data['content']
            
            # 2. Chunk Text
            # We'll use the filename as the chapter for now
            chapter_name = os.path.splitext(filename)[0]
            chunks = chunker.chunk_text(content, filename, chapter=chapter_name)
            
            # 3. Hand-off to Chroma-Core Server
            
            # Convert list of TextChunk dataclasses to plain dicts for JSON
            chunk_dicts = []
            for i, chunk in enumerate(chunks):
                chunk_data = dataclasses.asdict(chunk)
                # Create a metadata dict for Chroma
                chroma_metadata = {
                    "source_file": chunk.source_file,
                    "chapter": chunk.chapter,
                    "paragraph_start": chunk.paragraph_start,
                    "paragraph_end": chunk.paragraph_end,
                    "character_start": chunk.character_start,
                    "character_end": chunk.character_end
                }
                # Add the text and metadata to our list
                chunk_dicts.append({
                    "text": chunk.text,
                    "metadata": chroma_metadata,
                    "id": f"{project_id}_{filename}_{i}" # Create a unique ID
                })

            collection_name = f"project_{project_id}"
            
            payload = {
                "collection_name": collection_name,
                "chunks": chunk_dicts
            }
            
            # Call the /create_collection endpoint first to be safe
            try:
                requests.post(
                    f"{CHROMA_SERVER_URL}/create_collection",
                    json={"collection_name": collection_name},
                    timeout=10
                ).raise_for_status()
            except requests.exceptions.RequestException as e:
                # We can ignore errors if collection already exists, but log others
                if e.response and e.response.status_code != 500: # 500 is often "already exists"
                     app.logger.warning(f"Collection creation failed (may already exist): {e}")
                elif not e.response:
                    app.logger.error(f"Failed to connect to chroma_server: {e}")
                    return jsonify({"error": f"File processed, but failed to connect to chroma_server: {e}"}), 502

            # This is the MCP "protocol" in action:
            response = requests.post(
                f"{CHROMA_SERVER_URL}/add_chunks", 
                json=payload, 
                timeout=60
            )
            response.raise_for_status() # Raise an error if chroma-core fails
            
            return jsonify({
                'message': 'File uploaded and processed successfully',
                'project_id': project_id,
                'filename': filename,
                'metadata': parsed_data.get('metadata', {}),
                'chunk_count': len(chunks),
                'indexing_response': response.json()
            }), 201
            
        except DocumentParserError as e:
            return jsonify({'error': str(e)}), 500
        except requests.exceptions.RequestException as e:
            app.logger.error(f"Failed to hand off chunks to chroma-core: {e}")
            return jsonify({"error": f"File processed, but indexing service failed: {e.response.text if e.response else 'No response'}"}), 502
        except Exception as e:
            app.logger.error(f"An unexpected error occurred: {e}", exc_info=True)
            return jsonify({'error': f"An unexpected error occurred: {e}"}), 500
    else:
        return jsonify({'error': 'File type not allowed. Allowed: txt, md, docx, pdf, odt'}), 400

@app.route('/preview_url', methods=['POST'])
def preview_url():
    """
    Fetches a URL, sanitizes it, and saves it to a temp file.
    Returns the preview text for user confirmation.
    Does NOT index it yet.
    """
    data = request.get_json()
    url = data.get('url')
    project_id = data.get('project_id')
    
    if not url or not project_id:
        return jsonify({'error': 'url and project_id required'}), 400
        
    try:
        # 1. Sanitize
        result = WebSanitizer.fetch_and_sanitize(url)
        
        # 2. Save to _temp folder
        temp_id = str(uuid.uuid4())
        temp_dir = os.path.join(app.config['PROJECTS_FOLDER'], project_id, '_temp')
        os.makedirs(temp_dir, exist_ok=True)
        
        temp_filename = f"web_import_{temp_id}.txt"
        temp_path = os.path.join(temp_dir, temp_filename)
        
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(result, f) 
            
        # 3. Return Preview
        return jsonify({
            'temp_file_id': temp_filename,
            'title': result['title'],
            'url': result['source_url'],
            'preview_text': result['content'][:1000] + "..." 
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/confirm_url_import', methods=['POST'])
def confirm_url_import():
    """
    Takes a temp_file_id, reads the sanitized data, chunks it,
    and sends it to the chroma_server.
    """
    data = request.get_json()
    project_id = data.get('project_id')
    temp_file_id = data.get('temp_file_id')
    
    if not project_id or not temp_file_id:
        return jsonify({'error': 'project_id and temp_file_id required'}), 400
        
    temp_path = os.path.join(app.config['PROJECTS_FOLDER'], project_id, '_temp', temp_file_id)
    if not os.path.exists(temp_path):
        return jsonify({'error': 'Preview expired or not found'}), 404
        
    try:
        # 1. Read the Temp File
        with open(temp_path, 'r', encoding='utf-8') as f:
            import_data = json.load(f)
            
        content = import_data['content']
        source_url = import_data['source_url']
        title = import_data['title']
        
        # 2. Chunk It
        chunks = chunker.chunk_text(content, source_file=source_url, chapter=title)
        
        # 3. Send to Chroma
        chunk_dicts = []
        for i, chunk in enumerate(chunks):
            chunk_data = dataclasses.asdict(chunk)
            chroma_metadata = {
                "source_file": chunk.source_file,
                "chapter": chunk.chapter,
                "paragraph_start": chunk.paragraph_start,
                "paragraph_end": chunk.paragraph_end,
                "character_start": chunk.character_start,
                "character_end": chunk.character_end
            }
            chunk_dicts.append({
                "text": chunk.text,
                "metadata": chroma_metadata,
                "id": f"{project_id}_web_{temp_file_id}_{i}"
            })

        collection_name = f"project_{project_id}"
        payload = {
            "collection_name": collection_name,
            "chunks": chunk_dicts
        }
        
        # Ensure collection exists
        requests.post(
            f"{CHROMA_SERVER_URL}/create_collection",
            json={"collection_name": collection_name},
            timeout=10
        ).raise_for_status()

        response = requests.post(
            f"{CHROMA_SERVER_URL}/add_chunks", 
            json=payload, 
            timeout=60
        )
        response.raise_for_status()
        
        # 4. Cleanup
        os.remove(temp_path)
        
        return jsonify({'message': 'Web page imported successfully', 'response': response.json()}), 200

    except requests.exceptions.RequestException as e:
        app.logger.error(f"Failed to hand off chunks to chroma-core: {e}")
        return jsonify({"error": f"File processed, but indexing service failed: {e.response.text if e.response else 'No response'}"}), 502
    except Exception as e:
        app.logger.error(f"Failed to confirm import: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/project/<project_id>/files', methods=['GET'])
def list_files(project_id):
    project_path = os.path.join(app.config['PROJECTS_FOLDER'], project_id)
    if not os.path.isdir(project_path):
        return jsonify({'error': 'Project not found'}), 404
    
    files = [f for f in os.listdir(project_path) if os.path.isfile(os.path.join(project_path, f))]
    return jsonify({'project_id': project_id, 'files': files})

@app.route('/file/<project_id>/<filename>', methods=['GET'])
def get_file_content(project_id, filename):
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