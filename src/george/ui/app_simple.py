from flask import Flask, request, render_template, jsonify, flash, redirect, url_for, session
from werkzeug.utils import secure_filename
import os
import sys
from pathlib import Path
import json
import threading

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent.parent / '.env')

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# ============================================================
# NEW LLM INITIALIZATION
# The complex logic is now inside llm_integration.py
# ============================================================
try:
    from llm_integration import create_george_ai
    GEORGE_AI_AVAILABLE = True
    KNOWLEDGE_EXTRACTION_AVAILABLE = False
    
    # Initialize George AI with the new routing system.
    # It will automatically pick up the API key from the GEMINI_API_KEY environment variable.
    george_ai = create_george_ai()
    print("[OK] George AI initialized with multi-client routing system.")
    
    # Try to import knowledge extraction (optional)
    try:
        from knowledge_extraction.orchestrator import KnowledgeExtractor
        KNOWLEDGE_EXTRACTION_AVAILABLE = True
        print("[OK] Knowledge Extraction available")
    except ImportError as ke_error:
        print(f"[WARN] Knowledge Extraction not available: {ke_error}")
        print("   (Falling back to raw content mode)")
        
except (ImportError, ValueError) as e:
    print(f"CRITICAL ERROR: George AI not available: {e}")
    print("Please ensure your GEMINI_API_KEY environment variable is set.")
    GEORGE_AI_AVAILABLE = False
    KNOWLEDGE_EXTRACTION_AVAILABLE = False
    george_ai = None
# ============================================================

# Global knowledge extractor instances (one per project/file)
knowledge_extractors = {}
processing_status = {}

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Change this to a secure secret key

# Configuration
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# File processing functions (unchanged)
def read_file_content(file_path):
    # ... existing code ...
    try:
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if file_ext == '.txt' or file_ext == '.md':
            for encoding in ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        return f.read()
                except UnicodeDecodeError:
                    continue
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()
        elif file_ext == '.docx':
            try:
                import docx
                doc = docx.Document(file_path)
                return '\n'.join([paragraph.text for paragraph in doc.paragraphs])
            except ImportError:
                return "Error: python-docx not installed. Cannot read .docx files."
        else:
            return "Unsupported file format."
    except Exception as e:
        return f"Error reading file: {str(e)}"

def extract_basic_info(content, filename):
    # ... existing code ...
    words = len(content.split())
    characters = len(content)
    lines = len(content.split('\n'))
    import re
    potential_names = re.findall(r'\b[A-Z][a-z]+\b', content)
    common_words = {'The', 'And', 'But', 'Or', 'In', 'On', 'At', 'To', 'For', 'Of', 'With', 'By'}
    potential_names = [name for name in set(potential_names) if name not in common_words]
    return {
        'filename': filename,
        'word_count': words,
        'character_count': characters,
        'line_count': lines,
        'potential_entities': potential_names[:10],
        'content_preview': content[:500] + '...' if len(content) > 500 else content
    }
    
# Main routes (unchanged for now)
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    # ... (This function remains largely the same, but the background thread logic now uses the updated modules) ...
    print(f"[UPLOAD] Function called - Method: {request.method}")
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
            upload_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            try:
                file.save(upload_path)
                content = read_file_content(upload_path)
                file_info = extract_basic_info(content, filename)
                
                project_id = filename.replace('.', '_').replace(' ', '_')
                project_path = os.path.join(os.path.dirname(upload_path), 'projects', project_id)
                
                session['current_file'] = {
                    'filename': filename,
                    'path': upload_path,
                    'info': file_info,
                    'project_id': project_id
                }
                session['upload_time'] = str(Path(upload_path).stat().st_mtime)
                
                global george_ai, knowledge_extractors, processing_status
                if GEORGE_AI_AVAILABLE and george_ai:
                    george_ai.clear_history() # Clear history for new file
                    
                    if KNOWLEDGE_EXTRACTION_AVAILABLE:
                        print(f"[START] Background knowledge extraction for {filename}")
                        processing_status[project_id] = { 'status': 'processing', 'progress': 0, 'message': 'Extracting entities...' }
                        
                        def process_in_background():
                            try:
                                print(f"[THREAD] Background thread started for {project_id}")
                                # The orchestrator now correctly uses the Pro model via get_knowledge_client()
                                extractor = KnowledgeExtractor(george_ai, project_path)
                                knowledge_extractors[project_id] = extractor
                                summary = extractor.process_manuscript(content, filename)
                                processing_status[project_id] = {
                                    'status': 'complete', 'progress': 100, 'message': f'Extracted {summary["characters"]} characters', 'summary': summary
                                }
                                print(f"[COMPLETE] Background processing complete for {filename}")
                            except Exception as e:
                                processing_status[project_id] = { 'status': 'error', 'progress': 0, 'message': f'Error: {str(e)}' }
                                print(f"❌ Error processing {filename}: {e}")
                                import traceback
                                traceback.print_exc()
                        
                        thread = threading.Thread(target=process_in_background, daemon=True)
                        thread.start()
                
                flash(f'Manuscript "{filename}" uploaded! Knowledge extraction running in background...', 'success')
                return redirect(url_for('chat'))
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                flash(f'File uploaded but processing failed: {str(e)}', 'error')
                return redirect(request.url)
        else:
            flash('Invalid file type. Please upload .txt, .md, or .docx files.', 'error')
    
    return render_template('upload.html')

@app.route('/chat')
def chat():
    file_info = session.get('current_file', {})
    return render_template('chat.html', file_info=file_info)

# --- API Endpoints ---
@app.route('/api/chat', methods=['POST'])
def api_chat():
    """API endpoint for chat, now using the full routing logic."""
    data = request.get_json()
    message = data.get('message', '')
    
    if not message:
        return jsonify({'error': 'No message provided'}), 400
    
    if GEORGE_AI_AVAILABLE and george_ai and george_ai.is_available():
        try:
            file_info = session.get('current_file', {})
            project_context = ""

            if file_info:
                project_id = file_info.get('project_id')
                filename = file_info.get('filename', 'Unknown')
                
                # Check if knowledge extraction is complete and use the smart answer method
                if project_id and project_id in knowledge_extractors and knowledge_extractors[project_id].processing_complete:
                    extractor = knowledge_extractors[project_id]
                    print(f"[QUERY] Using knowledge extraction for query: '{message}'")
                    result = extractor.answer_query(message)
                    if result['success']:
                         return jsonify({
                            'response': result['response'], 'model': result['model'], 'timestamp': 'now',
                            'sources': [f'Knowledge base: {filename}'], 'context_used': True, 'extraction_used': True
                        })

                # Fallback to raw content if processing is not done
                print(f"📄 Using raw content fallback for query.")
                content_preview = file_info['info'].get('content_preview', '')
                project_context = f"Current manuscript: \"{filename}\"\n\nHere is the beginning of the story:\n\n{content_preview}"
            else:
                project_context = "No manuscript uploaded yet. Providing general writing advice."
            
            # This call now uses the full AIRouter pipeline
            result = george_ai.chat(message, project_context)
            
            return jsonify({
                'response': result['response'], 'model': result.get('model', 'N/A'),
                'timestamp': 'now', 'sources': [f'Manuscript: {file_info.get("filename", "None")}' if file_info else 'General knowledge'],
                'context_used': bool(file_info)
            })

        except Exception as e:
            return jsonify({'response': f"Sorry, an error occurred: {str(e)}", 'timestamp': 'now'}), 500
    else:
        return jsonify({'response': "AI service is not available.", 'timestamp': 'now'})

# Other API endpoints and helper functions (mostly unchanged)
@app.route('/api/file/current')
def api_current_file():
    # ... existing code ...
    file_info = session.get('current_file', {})
    if file_info:
        return jsonify({
            'loaded': True, 'filename': file_info.get('filename'),
            'info': file_info.get('info', {}), 'upload_time': session.get('upload_time', 'Unknown')
        })
    else:
        return jsonify({'loaded': False, 'message': 'No file currently loaded'})

@app.route('/api/processing/status')
def api_processing_status():
    # ... existing code ...
    file_info = session.get('current_file', {})
    if not file_info:
        return jsonify({'processing': False, 'message': 'No file loaded'})
    project_id = file_info.get('project_id')
    if not project_id or project_id not in processing_status:
        return jsonify({'processing': False, 'status': 'unknown', 'message': 'No processing info'})
    return jsonify({**processing_status[project_id], 'processing': processing_status[project_id]['status'] == 'processing'})

@app.route('/api/file/clear', methods=['POST'])
def api_clear_file():
    # ... existing code ...
    session.pop('current_file', None)
    session.pop('upload_time', None)
    if george_ai: george_ai.clear_history()
    return jsonify({'success': True, 'message': 'File and AI memory cleared'})

def allowed_file(filename):
    # ... existing code ...
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'txt', 'md', 'docx'}

if __name__ == '__main__':
    print("Starting George Flask application with multi-client AI router...")
    print("Open your browser to: http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
