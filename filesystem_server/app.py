"""Main application file for the filesystem server."""
from flask import Flask, request, jsonify, g
from werkzeug.utils import secure_filename
from functools import wraps
import os
import logging
import subprocess
import tempfile
import sys
from pathlib import Path

# Add backend to path to import service_utils
sys.path.insert(0, str(Path(__file__).parent.parent / 'backend'))

# --- UPDATED IMPORTS ---
from services import DocumentParser, TextChunker, WebSanitizer, DocumentParserError
from service_utils import require_internal_token, INTERNAL_TOKEN
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
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max upload size
app.config['MAX_CONTENT_LENGTH_JSON'] = 10 * 1024 * 1024  # 10MB for JSON payloads

# Upload size limits for different operations
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB for file uploads
MAX_CONTENT_SIZE = 5 * 1024 * 1024  # 5MB for save_file endpoint content

# --- MIDDLEWARE: Validate internal token and extract user_id ---
@app.before_request
def validate_token_and_extract_user_id():
    """
    CRITICAL SECURITY: Validate X-INTERNAL-TOKEN before trusting X-User-ID header.
    
    This prevents header spoofing attacks where an attacker could set:
        X-User-ID: victim-user-123
    to access another user's files.
    
    By requiring the internal token, we ensure that X-User-ID only comes from
    authenticated backend services that we trust.
    
    Flow:
    1. Validate X-INTERNAL-TOKEN matches INTERNAL_SERVICE_TOKEN
    2. Only if token is valid, extract and use X-User-ID
    3. Reject all requests without valid token (403 Forbidden)
    """
    
    # In dev mode, if no token is configured, allow all requests (for development)
    if not INTERNAL_TOKEN:
        # Dev mode: extract user_id without validation
        user_id = request.headers.get('X-User-ID', 'default')
        g.user_id = user_id
        return
    
    # Production mode: token is configured, enforce it
    received_token = request.headers.get('X-INTERNAL-TOKEN')
    
    # Validate token
    if not received_token or received_token != INTERNAL_TOKEN:
        logger.warning(
            f"Unauthorized request: invalid/missing X-INTERNAL-TOKEN from {request.remote_addr}"
        )
        return jsonify({"error": "Unauthorized - invalid internal token"}), 403
    
    # Token is valid, now we can trust X-User-ID
    user_id = request.headers.get('X-User-ID', 'default')
    if not user_id:
        logger.warning(f"Request with valid token but missing X-User-ID from {request.remote_addr}")
        user_id = 'default'
    
    g.user_id = user_id
    logger.debug(f"Authorized request for user {user_id} with valid internal token")

# --- NEW: Define allowed extensions set ---
ALLOWED_EXTENSIONS = {'txt', 'md', 'docx', 'pdf', 'odt'}

# Internal service URLs (6000-series ports are reserved for internal services)
CHROMA_SERVER_URL = os.getenv("CHROMA_SERVER_URL", "http://localhost:6003") 

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

def validate_project_path(full_path, project_id):
    """
    Validate that the resolved path stays within the project directory.
    Prevents path traversal attacks (e.g., ../../../etc/passwd).
    Returns True if safe, False otherwise.
    """
    project_path = get_project_path(project_id)
    # Resolve symlinks and normalize paths
    real_full_path = os.path.realpath(os.path.abspath(full_path))
    real_project_path = os.path.realpath(os.path.abspath(project_path))
    # Ensure the file is within the project directory
    return real_full_path.startswith(real_project_path + os.sep) or real_full_path == real_project_path

def validate_stream_size(stream, max_size=None):
    """
    Validate the size of an uploaded file stream before reading.
    Returns file size in bytes if valid, raises ValueError if too large.
    """
    if max_size is None:
        max_size = MAX_FILE_SIZE
    
    # Check Content-Length header if available
    content_length = request.content_length
    if content_length and content_length > max_size:
        raise ValueError(f"File size ({content_length} bytes) exceeds maximum allowed ({max_size} bytes)")
    
    return True

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
        # Validate stream size before processing
        try:
            validate_stream_size(file.stream, MAX_FILE_SIZE)
        except ValueError as e:
            return jsonify({"error": str(e)}), 413  # 413 Payload Too Large
        
        # Create project directory using user-isolated path
        project_path = get_project_path(project_id)
        os.makedirs(project_path, exist_ok=True)
        
        # Secure the filename
        filename = secure_filename(file.filename)
        file_path = os.path.join(project_path, filename)
        
        # Validate path to prevent traversal attacks
        if not validate_project_path(file_path, project_id):
            logger.warning(f"[{g.user_id}:{project_id}] Path traversal attempt detected: {file_path}")
            return jsonify({"error": "Invalid file path"}), 400
        
        # Save the original file
        logger.info(f"[{g.user_id}:{project_id}] Saving file: {filename}")
        file.save(file_path)
        
        # Verify the file size after saving
        file_size = os.path.getsize(file_path)
        if file_size > MAX_FILE_SIZE:
            os.remove(file_path)
            logger.warning(f"[{g.user_id}:{project_id}] File size {file_size} exceeds limit, removed")
            return jsonify({"error": f"File size exceeds maximum allowed ({MAX_FILE_SIZE} bytes)"}), 413
        
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
        # Validate stream size before processing
        try:
            validate_stream_size(file.stream, MAX_FILE_SIZE)
        except ValueError as e:
            return jsonify({"error": str(e)}), 413  # 413 Payload Too Large
        
        project_path = get_project_path(project_id)
        os.makedirs(project_path, exist_ok=True)
        
        upload_path = os.path.join(project_path, filename)
        
        # Validate path to prevent traversal attacks
        if not validate_project_path(upload_path, project_id):
            logger.warning(f"[{g.user_id}:{project_id}] Path traversal attempt detected: {upload_path}")
            return jsonify({"error": "Invalid file path"}), 400
        
        file.save(upload_path)
        
        # Verify the file size after saving
        file_size = os.path.getsize(upload_path)
        if file_size > MAX_FILE_SIZE:
            os.remove(upload_path)
            logger.warning(f"[{g.user_id}:{project_id}] File size {file_size} exceeds limit, removed")
            return jsonify({"error": f"File size exceeds maximum allowed ({MAX_FILE_SIZE} bytes)"}), 413

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
@require_internal_token
def save_file():
    """
    Save file content to a project.
    Used by backend to save generated files (e.g., wiki generation).
    Uses X-User-ID header for user-isolated storage.
    Protected by internal service token.
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body must be valid JSON'}), 400
    
    project_id = data.get('project_id')
    file_path = data.get('file_path')  # e.g., "wiki/entities.md"
    content = data.get('content', '')
    
    if not project_id or not file_path:
        return jsonify({'error': 'project_id and file_path are required'}), 400
    
    # Validate content size
    content_size = len(content.encode('utf-8'))
    if content_size > MAX_CONTENT_SIZE:
        return jsonify({'error': f'Content size ({content_size} bytes) exceeds maximum allowed ({MAX_CONTENT_SIZE} bytes)'}), 413
    
    try:
        # Get the project path with user_id
        project_path = get_project_path(project_id)
        
        # Build full file path and ensure directory exists
        full_path = os.path.join(project_path, file_path)
        
        # Validate path to prevent traversal attacks
        if not validate_project_path(full_path, project_id):
            logger.warning(f"[{g.user_id}:{project_id}] Path traversal attempt detected: {full_path}")
            return jsonify({'error': 'Invalid file path'}), 400
        
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        # Write the file
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        app.logger.info(f"[{g.user_id}:{project_id}] Saved file: {file_path} ({content_size} bytes)")
        return jsonify({'message': 'File saved successfully', 'path': full_path, 'size': content_size}), 200
        
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
    
    # Validate path to prevent traversal attacks
    if not validate_project_path(file_path, project_id):
        logger.warning(f"[{g.user_id}:{project_id}] Path traversal attempt detected: {file_path}")
        return jsonify({'error': 'Invalid file path'}), 400
    
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
    import os
    if os.getenv('FLASK_ENV') == 'development':
        app.run(debug=True, port=6002)
    else:
        print("Use gunicorn for production: gunicorn -w 4 -b 0.0.0.0:6002 filesystem_server.app:app")
