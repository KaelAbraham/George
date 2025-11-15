"""Main application file for the filesystem server."""
from flask import Flask, request, jsonify, g
from werkzeug.utils import secure_filename
import os
import logging
import subprocess
import tempfile
# --- UPDATED IMPORTS ---
from services import DocumentParser, TextChunker, WebSanitizer, DocumentParserError
import requests 
import dataclasses 
import uuid
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
PROJECTS_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'projects')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PROJECTS_FOLDER'] = PROJECTS_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB (increased for large PDFs)

# --- MIDDLEWARE: Extract user_id from X-User-ID header ---
@app.before_request
def extract_user_id():
    """
    Extract X-User-ID from request headers and store in g.user_id.
    This ensures all requests have a user_id for path resolution.
    """
    user_id = request.headers.get('X-User-ID')
    if user_id:
        g.user_id = user_id
    else:
        # Default to 'default' if no user_id provided
        g.user_id = 'default'

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

# --- HELPER FUNCTIONS ---

def get_project_path(project_id):
    """
    Get the full project path including user_id.
    Structure: PROJECTS_FOLDER / user_id / project_id
    """
    return os.path.join(app.config['PROJECTS_FOLDER'], g.user_id, project_id)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def convert_to_markdown(input_path):
    """
    Converts a document (docx, pdf, odt, etc.) to Markdown format.
    Returns the path to the converted .md file, or None if conversion fails.
    Uses pandoc via pypandoc.
    """
    try:
        import pypandoc
    except ImportError:
        logger.warning("pypandoc not installed, skipping conversion")
        return None
    
    try:
        # Generate output path (replace extension with .md)
        base_name = os.path.splitext(input_path)[0]
        output_path = f"{base_name}.md"
        
        # Use pandoc to convert
        logger.info(f"Converting {input_path} to {output_path}")
        pypandoc.convert_file(input_path, 'md', outputfile=output_path)
        
        if os.path.exists(output_path):
            logger.info(f"Successfully converted to: {output_path}")
            return output_path
        else:
            logger.error(f"Conversion succeeded but output file not found: {output_path}")
            return None
            
    except Exception as e:
        logger.error(f"Error converting {input_path} to markdown: {e}", exc_info=True)
        return None

# --- NEW: FILE UPLOAD WITH CONVERSION ENDPOINT ---

@app.route('/projects/<project_id>/upload', methods=['POST'])
def upload_file_with_conversion(project_id):
    """
    [SIMPLE UPLOAD] Handles file upload, saves original, and creates .md conversion.
    Returns file info and conversion status.
    Uses X-User-ID header for user-isolated storage.
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file provided in request"}), 400
    
    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    if not project_id:
        return jsonify({"error": "Project ID is required"}), 400
    
    if not allowed_file(file.filename):
        return jsonify({"error": f"File type not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"}), 400
    
    try:
        # Create project directory using user-isolated path
        project_path = get_project_path(project_id)
        os.makedirs(project_path, exist_ok=True)
        
        # Secure the filename
        filename = secure_filename(file.filename)
        file_path = os.path.join(project_path, filename)
        
        # Save the original file
        logger.info(f"[{g.user_id}:{project_id}] Saving file: {filename}")
        file.save(file_path)
        
        result = {
            'project_id': project_id,
            'original_file': filename,
            'original_path': file_path,
            'conversion': {
                'attempted': False,
                'success': False,
                'markdown_file': None,
                'markdown_path': None
            }
        }
        
        # Check if file needs conversion to markdown
        file_ext = os.path.splitext(filename)[1].lower()
        
        # Convert docx, pdf, odt to markdown (skip txt and md as they don't need conversion)
        if file_ext in ['.docx', '.pdf', '.odt']:
            result['conversion']['attempted'] = True
            logger.info(f"[{g.user_id}:{project_id}] Converting {filename} to markdown")
            
            markdown_path = convert_to_markdown(file_path)
            if markdown_path:
                markdown_filename = os.path.basename(markdown_path)
                result['conversion']['success'] = True
                result['conversion']['markdown_file'] = markdown_filename
                result['conversion']['markdown_path'] = markdown_path
                logger.info(f"[{g.user_id}:{project_id}] Conversion successful: {markdown_filename}")
            else:
                logger.warning(f"[{g.user_id}:{project_id}] Conversion failed for {filename}")
        
        return jsonify({
            'message': 'File uploaded successfully',
            'success': True,
            **result
        }), 201
        
    except Exception as e:
        logger.error(f"Error in /projects/{project_id}/upload: {e}", exc_info=True)
        return jsonify({"error": f"File upload failed: {str(e)}"}), 500

# --- EXISTING: UPLOAD/PROCESSING ENDPOINT (for chroma integration) ---

@app.route('/upload/<project_id>', methods=['POST'])
def upload_file(project_id):
    """
    Handles file upload, validation, parsing, chunking,
    and forwards chunks to the chroma-core server.
    Uses X-User-ID header for user-isolated storage.
    """
    if 'manuscript' not in request.files:
        return jsonify({"error": "No manuscript file provided"}), 400
        
    file = request.files['manuscript']
    filename = secure_filename(file.filename) if file else None
    
    if not project_id:
        return jsonify({"error": "Project ID is required"}), 400

    if file and allowed_file(file.filename):
        project_path = get_project_path(project_id)
        os.makedirs(project_path, exist_ok=True)
        
        upload_path = os.path.join(project_path, filename)
        file.save(upload_path)

        try:
            # 1. Parse File
            parsed_data = parser.parse(upload_path)
            
            # 2. Chunk Text
            # We'll use the filename as the chapter for now
            chapter_name = os.path.splitext(filename)[0]
            chunks = chunker.chunk_text(parsed_data['content'], chapter=chapter_name)
            
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
                'chunk_count': len(chunk_dicts),
                'filename': filename
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

# --- NEW: SECURE WEB IMPORT ENDPOINTS ---

@app.route('/preview_url', methods=['POST'])
def preview_url():
    """
    STEP 1 of Web Import (Called by Backend JobManager)
    Fetches a URL, sanitizes it, and saves it to a temp file.
    Returns the preview text for user confirmation.
    Does NOT index it yet.
    Uses X-User-ID header for user-isolated storage.
    """
    data = request.get_json()
    url = data.get('url')
    project_id = data.get('project_id')
    job_id = data.get('job_id') # Passed through from the backend
    
    if not url or not project_id or not job_id:
        return jsonify({'error': 'url, project_id, and job_id are required'}), 400
        
    try:
        # 1. Sanitize
        app.logger.info(f"[{g.user_id}:{job_id}] Sanitizing URL: {url}")
        result = WebSanitizer.fetch_and_sanitize(url)
        
        # 2. Save to _temp folder using user-isolated path
        project_path = get_project_path(project_id)
        temp_dir = os.path.join(project_path, '_temp')
        os.makedirs(temp_dir, exist_ok=True)
        
        # We'll name the temp file after the job_id for easy tracking
        temp_filename = f"{job_id}.json"
        temp_path = os.path.join(temp_dir, temp_filename)
        
        # Save the *full* sanitized data as JSON
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False) 
            
        app.logger.info(f"[{g.user_id}:{job_id}] Saved sanitized preview to {temp_path}")

        # 3. Return Preview
        return jsonify({
            'job_id': job_id,
            'temp_file_id': temp_filename,
            'title': result['title'],
            'url': result['source_url'],
            'preview_text': result['content'][:1000] + "..." # Send a snippet
        })

    except Exception as e:
        app.logger.error(f"[{g.user_id}:{job_id}] Failed during /preview_url: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/confirm_url_import', methods=['POST'])
def confirm_url_import():
    """
    STEP 2 of Web Import (Called by Backend JobManager after user confirmation)
    Takes a temp_file_id, reads the sanitized data, chunks it,
    and sends it to the chroma_server.
    Uses X-User-ID header for user-isolated storage.
    """
    data = request.get_json()
    project_id = data.get('project_id')
    temp_file_id = data.get('temp_file_id') # e.g., "abc-123.json"
    job_id = data.get('job_id')
    
    if not project_id or not temp_file_id or not job_id:
        return jsonify({'error': 'project_id, temp_file_id, and job_id required'}), 400
        
    temp_path = os.path.join(get_project_path(project_id), '_temp', temp_file_id)
    if not os.path.exists(temp_path):
        app.logger.error(f"[{g.user_id}:{job_id}] Confirm failed: temp file not found at {temp_path}")
        return jsonify({'error': 'Preview expired or not found'}), 404
        
    try:
        app.logger.info(f"[{g.user_id}:{job_id}] Confirming import for {temp_path}")
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
        app.logger.error(f"[{g.user_id}:{job_id}] Failed to confirm import: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# --- File Save Endpoint ---

@app.route('/save_file', methods=['POST'])
def save_file():
    """
    Save file content to a project.
    Used by backend to save generated files (e.g., wiki generation).
    Uses X-User-ID header for user-isolated storage.
    """
    data = request.get_json()
    project_id = data.get('project_id')
    file_path = data.get('file_path')  # e.g., "wiki/entities.md"
    content = data.get('content', '')
    
    if not project_id or not file_path:
        return jsonify({'error': 'project_id and file_path are required'}), 400
    
    try:
        # Get the project path with user_id
        project_path = get_project_path(project_id)
        
        # Build full file path and ensure directory exists
        full_path = os.path.join(project_path, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        # Write the file
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        app.logger.info(f"[{g.user_id}:{project_id}] Saved file: {file_path}")
        return jsonify({'message': 'File saved successfully', 'path': full_path}), 200
        
    except Exception as e:
        app.logger.error(f"[{g.user_id}:{project_id}] Failed to save file: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# --- Standard File Serving Endpoints ---

@app.route('/project/<project_id>/files', methods=['GET'])
def list_files(project_id):
    """List all files in a project. Uses X-User-ID header for user-isolated storage."""
    project_path = get_project_path(project_id)
    if not os.path.isdir(project_path):
        return jsonify({'error': 'Project not found'}), 404
    
    files = [f for f in os.listdir(project_path) if os.path.isfile(os.path.join(project_path, f))]
    return jsonify({'project_id': project_id, 'files': files})

@app.route('/file/<project_id>/<filename>', methods=['GET'])
def get_file_content(project_id, filename):
    """Get file content from a project. Uses X-User-ID header for user-isolated storage."""
    project_path = get_project_path(project_id)
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
    app.run(debug=True, port=6002)
