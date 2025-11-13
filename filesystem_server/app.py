"""Main application file for the filesystem server."""
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
import os
# --- UPDATED IMPORTS ---
from services import DocumentParser, TextChunker, WebSanitizer, DocumentParserError
import requests 
import dataclasses 
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
CHROMA_SERVER_URL = "http://localhost:5002" 

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
# ... (existing code) ...
    if not project_id:
        return jsonify({"error": "Project ID is required"}), 400

    if file and allowed_file(file.filename):
# ... (existing code) ...
        project_path = os.path.join(app.config['PROJECTS_FOLDER'], project_id)
        os.makedirs(project_path, exist_ok=True)
        
        upload_path = os.path.join(project_path, filename)
# ... (existing code) ...

        try:
            # 1. Parse File
            parsed_data = parser.parse(upload_path)
# ... (existing code) ...
            
            # 2. Chunk Text
            # We'll use the filename as the chapter for now
            chapter_name = os.path.splitext(filename)[0]
# ... (existing code) ...
            
            # 3. Hand-off to Chroma-Core Server
            
            # Convert list of TextChunk dataclasses to plain dicts for JSON
            chunk_dicts = []
# ... (existing code) ...
                chunk_data = dataclasses.asdict(chunk)
                # Create a metadata dict for Chroma
                chroma_metadata = {
# ... (existing code) ...
                    "character_end": chunk.character_end
                }
                # Add the text and metadata to our list
                chunk_dicts.append({
# ... (existing code) ...
                    "id": f"{project_id}_{filename}_{i}" # Create a unique ID
                })

            collection_name = f"project_{project_id}"
# ... (existing code) ...
                "chunks": chunk_dicts
            }
            
            # Call the /create_collection endpoint first to be safe
            try:
                requests.post(
                    f"{CHROMA_SERVER_URL}/create_collection",
# ... (existing code) ...
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
# ... (existing code) ...
            response.raise_for_status() # Raise an error if chroma-core fails
            
            return jsonify({
                'message': 'File uploaded and processed successfully',
# ... (existing code) ...
            }), 201
            
        except DocumentParserError as e:
            return jsonify({'error': str(e)}), 500
        except requests.exceptions.RequestException as e:
# ... (existing code) ...
            return jsonify({"error": f"File processed, but indexing service failed: {e.response.text if e.response else 'No response'}"}), 502
        except Exception as e:
            app.logger.error(f"An unexpected error occurred: {e}", exc_info=True)
            return jsonify({'error': f"An unexpected error occurred: {e}"}), 500
    else:
        return jsonify({'error': 'File type not allowed. Allowed: txt, md, docx, pdf, odt'}), 400

# --- NEW: SECURE WEB IMPORT ENDPOINTS ---

@app.route('/preview_url', methods=['POST'])
def preview_url():
    """
    STEP 1 of Web Import (Called by Backend JobManager)
    Fetches a URL, sanitizes it, and saves it to a temp file.
    Returns the preview text for user confirmation.
    Does NOT index it yet.
    """
    data = request.get_json()
    url = data.get('url')
    project_id = data.get('project_id')
    job_id = data.get('job_id') # Passed through from the backend
    
    if not url or not project_id or not job_id:
        return jsonify({'error': 'url, project_id, and job_id are required'}), 400
        
    try:
        # 1. Sanitize
        app.logger.info(f"[{job_id}] Sanitizing URL: {url}")
        result = WebSanitizer.fetch_and_sanitize(url)
        
        # 2. Save to _temp folder
        temp_dir = os.path.join(app.config['PROJECTS_FOLDER'], project_id, '_temp')
        os.makedirs(temp_dir, exist_ok=True)
        
        # We'll name the temp file after the job_id for easy tracking
        temp_filename = f"{job_id}.json"
        temp_path = os.path.join(temp_dir, temp_filename)
        
        # Save the *full* sanitized data as JSON
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False) 
            
        app.logger.info(f"[{job_id}] Saved sanitized preview to {temp_path}")

        # 3. Return Preview
        return jsonify({
            'job_id': job_id,
            'temp_file_id': temp_filename,
            'title': result['title'],
            'url': result['source_url'],
            'preview_text': result['content'][:1000] + "..." # Send a snippet
        })

    except Exception as e:
        app.logger.error(f"[{job_id}] Failed during /preview_url: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/confirm_url_import', methods=['POST'])
def confirm_url_import():
    """
    STEP 2 of Web Import (Called by Backend JobManager after user confirmation)
    Takes a temp_file_id, reads the sanitized data, chunks it,
    and sends it to the chroma_server.
    """
    data = request.get_json()
    project_id = data.get('project_id')
    temp_file_id = data.get('temp_file_id') # e.g., "abc-123.json"
    job_id = data.get('job_id')
    
    if not project_id or not temp_file_id or not job_id:
        return jsonify({'error': 'project_id, temp_file_id, and job_id required'}), 400
        
    temp_path = os.path.join(app.config['PROJECTS_FOLDER'], project_id, '_temp', temp_file_id)
    if not os.path.exists(temp_path):
        app.logger.error(f"[{job_id}] Confirm failed: temp file not found at {temp_path}")
        return jsonify({'error': 'Preview expired or not found'}), 404
        
    try:
        app.logger.info(f"[{job_id}] Confirming import for {temp_path}")
        # 1. Read the Temp File
        with open(temp_path, 'r', encoding='utf-8') as f:
            import_data = json.load(f)
            
        content = import_data['content']
        source_url = import_data['source_url'] # This is the "unremoveable tag"
        title = import_data['title']
        
        # 2. Chunk It
        chunks = chunker.chunk_text(content, source_file=source_url, chapter=title)
        
        # 3. Send to Chroma
        chunk_dicts = []
        for i, chunk in enumerate(chunks):
            chunk_data = dataclasses.asdict(chunk)
            chroma_metadata = {
                "source_file": chunk.source_file, # This will be the URL
                "chapter": chunk.chapter,
                "paragraph_start": chunk.paragraph_start,
                "paragraph_end": chunk.paragraph_end,
                "character_start": chunk.character_start,
                "character_end": chunk.character_end
            }
            chunk_dicts.append({
                "text": chunk.text,
                "metadata": chroma_metadata,
                "id": f"{project_id}_web_{job_id}_{i}" # Create a unique, traceable ID
            })

        collection_name = f"project_{project_id}"
        payload = {
            "collection_name": collection_name,
            "chunks": chunk_dicts
        }
        
        # Ensure collection exists (idempotent)
        requests.post(
            f"{CHROMA_SERVER_URL}/create_collection",
            json={"collection_name": collection_name},
            timeout=10
        ).raise_for_status()

        # Send chunks to be indexed
        response = requests.post(
            f"{CHROMA_SERVER_URL}/add_chunks", 
            json=payload, 
            timeout=60
        )
        response.raise_for_status()
        
        # 4. Cleanup Temp File
        os.remove(temp_path)
        
        app.logger.info(f"[{job_id}] Successfully imported and indexed {source_url}")
        return jsonify({'message': 'Web page imported successfully', 'chunk_count': len(chunk_dicts)}), 200

    except requests.exceptions.RequestException as e:
            app.logger.error(f"[{job_id}] Failed to hand off chunks to chroma-core: {e}")
            return jsonify({"error": f"File processed, but indexing service failed: {e.response.text if e.response else 'No response'}"}), 502
    except Exception as e:
        app.logger.error(f"[{job_id}] Failed to confirm import: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# --- Standard File Serving Endpoints ---

@app.route('/project/<project_id>/files', methods=['GET'])
def list_files(project_id):
# ... (existing code) ...
    project_path = os.path.join(app.config['PROJECTS_FOLDER'], project_id)
    if not os.path.isdir(project_path):
        return jsonify({'error': 'Project not found'}), 404
# ... (existing code) ...
    
    files = [f for f in os.listdir(project_path) if os.path.isfile(os.path.join(project_path, f))]
    return jsonify({'project_id': project_id, 'files': files})

@app.route('/file/<project_id>/<filename>', methods=['GET'])
def get_file_content(project_id, filename):
# ... (existing code) ...
    file_path = os.path.join(project_path, filename)
    
    if not os.path.isfile(file_path):
# ... (existing code) ...
        
    try:
        parsed_data = parser.parse(file_path)
# ... (existing code) ...
            'filename': filename,
            'content': parsed_data['content'],
            'metadata': parsed_data.get('metadata', {})
# ... (existing code) ...
    except DocumentParserError as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)