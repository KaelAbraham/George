from flask import Flask, request, render_template, jsonify, flash, redirect, url_for, session
from werkzeug.utils import secure_filename
import os
import sys
from pathlib import Path
import json
import threading

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# ============================================================
# LLM CONFIGURATION - Choose your AI backend here
# ============================================================
USE_CLOUD_API = True  # Set to False to use local Ollama

if USE_CLOUD_API:
    # Cloud API options:
    # Gemini: model="gemini-pro" (stable, free tier!) - Note: 1.5 models may require different API access
    # OpenAI: model="gpt-4o-mini" (fast, cheap) or "gpt-4o" (best quality), api_type="openai"
    # Anthropic: model="claude-3-haiku-20240307" (fast), api_type="anthropic"
    LLM_CONFIG = {
        "use_cloud": True,
        "model": "gemini-2.0-flash",  # Gemini 2.0 Flash (stable)
        "api_type": "gemini",
        "api_key": os.getenv("GEMINI_API_KEY")  # Set this environment variable
    }
else:
    # Local Ollama options: "phi3:instruct" (smart), "gemma:2b-instruct" (fast), "llama3.1:8b" (balanced)
    LLM_CONFIG = {
        "model": "gemma:2b-instruct"  # Fast local model for demo
    }
# ============================================================

# Import George AI
try:
    from llm_integration import create_george_ai, GeorgeAI
    GEORGE_AI_AVAILABLE = True
    KNOWLEDGE_EXTRACTION_AVAILABLE = False
    
    # Initialize George AI with chosen configuration
    george_ai = create_george_ai(**LLM_CONFIG)
    
    if USE_CLOUD_API:
        print(f"✅ George AI initialized with {LLM_CONFIG['model']} ({LLM_CONFIG['api_type']} cloud API)")
    else:
        print(f"✅ George AI initialized with {LLM_CONFIG['model']} (local Ollama)")
    
    # Try to import knowledge extraction (optional)
    try:
        from knowledge_extraction.orchestrator import KnowledgeExtractor
        KNOWLEDGE_EXTRACTION_AVAILABLE = True
        print("✅ Knowledge Extraction available")
    except ImportError as ke_error:
        print(f"⚠️  Knowledge Extraction not available: {ke_error}")
        print("   (Falling back to raw content mode)")
        
except ImportError as e:
    print(f"Warning: George AI not available: {e}")
    GEORGE_AI_AVAILABLE = False
    KNOWLEDGE_EXTRACTION_AVAILABLE = False
    george_ai = None

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

# File processing functions
def read_file_content(file_path):
    """Read content from uploaded file."""
    try:
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if file_ext == '.txt':
            # Try different encodings
            for encoding in ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        return f.read()
                except UnicodeDecodeError:
                    continue
            # If all encodings fail, try with error handling
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()
        elif file_ext == '.md':
            # Try different encodings for markdown
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
    """Extract basic information from file content."""
    # Simple text analysis
    words = len(content.split())
    characters = len(content)
    lines = len(content.split('\n'))
    
    # Basic entity detection (simple keyword search)
    import re
    
    # Look for capitalized words that might be names
    potential_names = re.findall(r'\b[A-Z][a-z]+\b', content)
    # Remove common words
    common_words = {'The', 'And', 'But', 'Or', 'In', 'On', 'At', 'To', 'For', 'Of', 'With', 'By'}
    potential_names = [name for name in set(potential_names) if name not in common_words]
    
    return {
        'filename': filename,
        'word_count': words,
        'character_count': characters,
        'line_count': lines,
        'potential_entities': potential_names[:10],  # Top 10
        'content_preview': content[:500] + '...' if len(content) > 500 else content
    }

# Log all requests
@app.before_request
def log_request():
    print(f"🌐 Incoming {request.method} request to {request.path}")
    
# Simple routes without dependencies for now
@app.route('/')
def index():
    """Home page with project overview."""
    return render_template('index.html')

@app.route('/upload-test')
def upload_test():
    """Minimal upload test page."""
    return render_template('upload_test.html')

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    """Upload and process manuscript."""
    print(f"🔥🔥🔥 UPLOAD FUNCTION CALLED - Method: {request.method}")
    if request.method == 'POST':
        print("DEBUG: POST request received")
        print(f"DEBUG: request.files keys: {list(request.files.keys())}")
        print(f"DEBUG: request.form keys: {list(request.form.keys())}")
        print(f"DEBUG: request.content_type: {request.content_type}")
        
        if 'manuscript' not in request.files:
            print("DEBUG: No 'manuscript' in request.files")
            print(f"DEBUG: All files in request: {dict(request.files)}")
            flash('No file selected', 'error')
            return redirect(request.url)
        
        file = request.files['manuscript']
        print(f"DEBUG: File object: {file}")
        print(f"DEBUG: Filename: {file.filename}")
        
        if file.filename == '':
            print("DEBUG: Empty filename")
            flash('No file selected', 'error')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            upload_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            print(f"DEBUG: Upload path: {upload_path}")
            
            try:
                file.save(upload_path)
                print(f"DEBUG: File saved successfully to {upload_path}")
                
                # Process the uploaded file
                content = read_file_content(upload_path)
                print(f"DEBUG: Content length: {len(content) if content else 0}")
                
                file_info = extract_basic_info(content, filename)
                print(f"DEBUG: File info: {file_info}")
                
                # Create project directory for knowledge base
                project_id = filename.replace('.', '_').replace(' ', '_')
                project_path = os.path.join(os.path.dirname(upload_path), 'projects', project_id)
                
                # Store file info in session for chat context
                # DON'T store full content - only path and metadata to avoid cookie size limit
                session['current_file'] = {
                    'filename': filename,
                    'path': upload_path,
                    'info': file_info,
                    'project_id': project_id
                }
                session['upload_time'] = str(Path(upload_path).stat().st_mtime)
                
                # IMPORTANT: Clear AI conversation history when loading new file
                global george_ai, knowledge_extractors, processing_status
                if GEORGE_AI_AVAILABLE and george_ai:
                    george_ai.conversation_history = []
                    print("DEBUG: Cleared AI conversation history for new file")
                    
                    # Start background knowledge extraction (if available)
                    if KNOWLEDGE_EXTRACTION_AVAILABLE:
                        print(f"🚀 Starting background knowledge extraction for {filename}")
                        processing_status[project_id] = {
                            'status': 'processing',
                            'progress': 0,
                            'message': 'Extracting entities from manuscript...'
                        }
                    else:
                        print(f"⚠️  Knowledge extraction not available, using raw content mode")
                        processing_status[project_id] = {
                            'status': 'unavailable',
                            'progress': 0,
                            'message': 'Knowledge extraction not available'
                        }
                    
                    if KNOWLEDGE_EXTRACTION_AVAILABLE:
                        def process_in_background():
                            try:
                                print(f"🔥 BACKGROUND THREAD STARTED for {project_id}")
                                print(f"🔥 Creating KnowledgeExtractor with project_path: {project_path}")
                                extractor = KnowledgeExtractor(george_ai, project_path)
                                knowledge_extractors[project_id] = extractor
                                print(f"🔥 KnowledgeExtractor created successfully")
                                
                                processing_status[project_id]['message'] = 'Processing manuscript...'
                                print(f"🔥 Starting process_manuscript() with content length: {len(content)}")
                                summary = extractor.process_manuscript(content, filename)
                                print(f"🔥 process_manuscript() completed with summary: {summary}")
                                
                                processing_status[project_id] = {
                                    'status': 'complete',
                                    'progress': 100,
                                    'message': f'Extracted {summary["characters"]} characters, {summary["locations"]} locations',
                                    'summary': summary
                                }
                                print(f"✅ Background processing complete for {filename}")
                            except Exception as e:
                                processing_status[project_id] = {
                                    'status': 'error',
                                    'progress': 0,
                                    'message': f'Error: {str(e)}'
                                }
                                print(f"❌ Error processing {filename}: {e}")
                                import traceback
                                traceback.print_exc()
                        
                        print(f"🔥 Creating background thread for {project_id}")
                        thread = threading.Thread(target=process_in_background, daemon=True)
                        print(f"🔥 Starting background thread...")
                        thread.start()
                        print(f"🔥 Background thread started! Thread alive: {thread.is_alive()}")
                
                print("DEBUG: File info stored in session")
                flash(f'Manuscript "{filename}" uploaded! Knowledge extraction running in background...', 'success')
                # Redirect directly to chat instead of entity validation
                return redirect(url_for('chat'))
                
            except Exception as e:
                print(f"DEBUG: Error during processing: {e}")
                import traceback
                traceback.print_exc()
                flash(f'File uploaded but processing failed: {str(e)}', 'error')
                return redirect(request.url)
        else:
            print(f"DEBUG: File not allowed: {file.filename}")
            flash('Invalid file type. Please upload .txt, .md, or .docx files.', 'error')
    
    return render_template('upload.html')

@app.route('/entity_validation')
@app.route('/entity_validation/<filename>')
def entity_validation(filename=None):
    """Entity validation page."""
    # Get file info from session if available
    file_info = session.get('current_file', {})
    
    if file_info and filename == file_info.get('filename'):
        # Use real data from uploaded file
        entities = []
        for name in file_info['info']['potential_entities']:
            entities.append({
                'name': name,
                'type': 'UNKNOWN',  # Would be determined by proper NLP
                'confidence': 0.75,
                'context': f'Found in {filename}'
            })
    else:
        # Fallback to mock data
        entities = [
            {'name': 'Elias', 'type': 'CHARACTER', 'confidence': 0.95, 'context': 'Main protagonist'},
            {'name': 'Silverdale', 'type': 'LOCATION', 'confidence': 0.88, 'context': 'Town setting'},
            {'name': 'The Old Library', 'type': 'LOCATION', 'confidence': 0.82, 'context': 'Key location'},
        ]
    
    return render_template('entity_validation.html', entities=entities, filename=filename, file_info=file_info)

@app.route('/chat')
def chat():
    """Chat interface page."""
    # Pass current file info to chat
    file_info = session.get('current_file', {})
    print(f"🔍 Chat route - session keys: {list(session.keys())}")
    print(f"🔍 Chat route - has file_info: {bool(file_info)}")
    if file_info:
        print(f"🔍 Chat route - filename: {file_info.get('filename', 'Unknown')}")
    return render_template('chat.html', file_info=file_info)

@app.route('/test')
def test():
    """Test page."""
    return render_template('test.html')

@app.route('/debug')
def debug():
    """Debug page for file loading."""
    return render_template('debug.html')

# API endpoints for demonstration
@app.route('/api/entities')
def api_entities():
    """API endpoint for entities."""
    return jsonify({
        'entities': [
            {'name': 'Elias', 'type': 'CHARACTER', 'confidence': 0.95},
            {'name': 'Silverdale', 'type': 'LOCATION', 'confidence': 0.88},
            {'name': 'The Old Library', 'type': 'LOCATION', 'confidence': 0.82},
        ]
    })

@app.route('/api/chat', methods=['POST'])
def api_chat():
    """API endpoint for chat with file context integration."""
    data = request.get_json()
    message = data.get('message', '')
    
    if not message:
        return jsonify({'error': 'No message provided'}), 400
    
    # Check for help command
    if message.lower().strip() in ['help edit', 'edit help', 'how to edit', 'editing']:
        help_text = """# 📝 Profile Editing Commands

You can edit knowledge base profiles directly through chat!

**UPDATE/CORRECT:**
- `Update Edie Ann: she has brown eyes, not blue`
- `Correct Hugh: he's 45 years old`
- `Fix Linda: she's from Mars, not Earth`

**ADD INFORMATION:**
- `Add to Edie Ann's profile: she loves robots`
- `Add to Hugh: he has a PhD in physics`

**REMOVE INFORMATION:**
- `Remove from Linda: the part about being an engineer`
- `Delete from Akkadia: the mention of blue skies`

**MERGE DUPLICATES:**
- `Merge Carroll and Dad`
- `Merge "The Workshop" and "Workshop"`

**Tips:**
✅ Use full entity names from the knowledge base
✅ Be specific about what to change
✅ One edit at a time works best

Ask "List the characters" to see available entities!"""
        
        return jsonify({
            'response': help_text,
            'model': 'help-system',
            'timestamp': 'now',
            'sources': ['Built-in help']
        })
    
    if GEORGE_AI_AVAILABLE and george_ai and george_ai.is_available():
        try:
            # Get file context from session
            file_info = session.get('current_file', {})
            print(f"🔍 API CHAT - file_info exists: {bool(file_info)}")
            
            if file_info:
                project_id = file_info.get('project_id')
                filename = file_info.get('filename', 'Unknown')
                word_count = file_info['info'].get('word_count', 0)
                
                # Check if knowledge extraction is complete
                if project_id and project_id in knowledge_extractors:
                    extractor = knowledge_extractors[project_id]
                    if extractor.processing_complete:
                        # First check if this is an EDIT command
                        print(f"🔍 Checking if query is an edit command...")
                        edit_result = extractor.edit_profile(message)
                        
                        if edit_result.get('is_edit_command'):
                            # This is an edit command - execute it
                            print(f"✏️ Edit command detected: {edit_result.get('message')}")
                            
                            if edit_result['success']:
                                return jsonify({
                                    'response': edit_result['message'],
                                    'model': 'profile-editor',
                                    'timestamp': 'now',
                                    'sources': ['Knowledge base editor'],
                                    'context_used': False,
                                    'edit_executed': True
                                })
                            else:
                                return jsonify({
                                    'response': f"❌ Edit failed: {edit_result['message']}",
                                    'model': 'profile-editor',
                                    'timestamp': 'now',
                                    'edit_executed': False
                                })
                        
                        # Not an edit command - use knowledge extraction for query
                        print(f"🚀 Using knowledge extraction for query")
                        result = extractor.answer_query(message)
                        
                        if result['success']:
                            return jsonify({
                                'response': result['response'],
                                'model': result['model'],
                                'timestamp': 'now',
                                'sources': [f'Knowledge base: {filename}'],
                                'context_used': True,
                                'extraction_used': True
                            })
                        else:
                            # Fall back to raw content if extraction fails
                            print(f"⚠️ Extraction query failed: {result.get('error')}")
                
                # Fallback: Use raw content (slower, but works during processing)
                print(f"📄 Using raw content fallback")
                file_path = file_info.get('path', '')
                
                print(f"🔍 API CHAT - file_path: {file_path}")
                print(f"🔍 API CHAT - file exists: {os.path.exists(file_path) if file_path else False}")
                
                # Read the actual content from disk
                if file_path and os.path.exists(file_path):
                    full_content = read_file_content(file_path)
                    print(f"🔍 API CHAT - full_content length: {len(full_content)}")
                    # Use first 10000 chars for context (enough to capture all main characters)
                    content_preview = full_content[:10000] + '...' if len(full_content) > 10000 else full_content
                else:
                    content_preview = file_info['info'].get('content_preview', '')
                    print(f"🔍 API CHAT - Using cached preview, length: {len(content_preview)}")
                
                project_context = f"""Current manuscript: "{filename}" ({word_count} words)

Here is the beginning of the story:

{content_preview}

When answering questions about characters, be BRIEF and DIRECT. Simply list the character names that appear in the text. The narrator's name is Carroll. Don't analyze relationships or give detailed explanations unless specifically asked."""
                print(f"🔍 API CHAT - project_context length: {len(project_context)}")
            else:
                project_context = "No manuscript uploaded yet. Providing general writing advice."
                print(f"🔍 API CHAT - No file uploaded")
            
            # Generate AI response using file context
            result = george_ai.chat(message, project_context)
            
            if result['success']:
                return jsonify({
                    'response': result['response'],
                    'model': result['model'],
                    'timestamp': 'now',
                    'sources': [f'Your manuscript: {file_info.get("filename", "None")}' if file_info else 'General knowledge'],
                    'context_used': bool(file_info)
                })
            else:
                return jsonify({
                    'response': f"Sorry, I encountered an error: {result.get('error', 'Unknown error')}",
                    'timestamp': 'now'
                })
        except Exception as e:
            return jsonify({
                'response': f"Sorry, I encountered an error processing your request: {str(e)}",
                'timestamp': 'now'
            })
    else:
        # Fallback response if AI is not available
        file_info = session.get('current_file', {})
        if file_info:
            context_note = f"(Based on your uploaded file: {file_info.get('filename', 'Unknown')})"
        else:
            context_note = "(No file uploaded yet)"
            
        return jsonify({
            'response': f"AI service is not available. You asked: '{message}'. {context_note}",
            'timestamp': 'now',
            'note': 'AI service not available'
        })

@app.route('/api/chat/stream', methods=['POST'])
def api_chat_stream():
    """API endpoint for streaming chat with Phi-3."""
    from flask import Response
    import json
    
    data = request.get_json()
    message = data.get('message', '')
    
    def generate():
        if GEORGE_AI_AVAILABLE and george_ai and george_ai.is_available():
            try:
                project_context = "Story about Elias, a young person in Silverdale with magical elements"
                
                for chunk in george_ai.chat_streaming(message, project_context):
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"
                
                yield f"data: {json.dumps({'done': True})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
        else:
            yield f"data: {json.dumps({'chunk': f'AI service not available. You asked: {message}'})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
    
    return Response(generate(), mimetype='text/plain')

@app.route('/api/ai/status')
def api_ai_status():
    """Get AI service status and model information."""
    if GEORGE_AI_AVAILABLE and george_ai:
        info = george_ai.get_model_info()
        return jsonify({
            'available': info['available'],
            'model': info['model'],
            'available_models': info['available_models'],
            'service': 'Ollama + Local LLM'
        })
    else:
        return jsonify({
            'available': False,
            'model': None,
            'service': 'Not configured',
            'error': 'George AI module not available'
        })

@app.route('/api/ai/switch-model', methods=['POST'])
def api_switch_model():
    """Switch to a different model."""
    global george_ai
    
    if not GEORGE_AI_AVAILABLE:
        return jsonify({'error': 'George AI not available'}), 400
    
    data = request.get_json()
    new_model = data.get('model', '')
    
    if not new_model:
        return jsonify({'error': 'Model name required'}), 400
    
    try:
        # Create new AI instance with different model
        new_george_ai = create_george_ai(model=new_model)
        
        if new_george_ai.is_available():
            george_ai = new_george_ai
            return jsonify({
                'success': True,
                'model': new_model,
                'message': f'Switched to {new_model}'
            })
        else:
            return jsonify({
                'error': f'Model {new_model} is not available'
            }), 400
            
    except Exception as e:
        return jsonify({
            'error': f'Failed to switch model: {str(e)}'
        }), 500

@app.route('/api/file/current')
def api_current_file():
    """Get information about the currently loaded file."""
    file_info = session.get('current_file', {})
    print(f"DEBUG: Session file info: {file_info}")
    
    if file_info:
        # Don't send full content, just metadata
        return jsonify({
            'loaded': True,
            'filename': file_info.get('filename'),
            'info': file_info.get('info', {}),
            'upload_time': session.get('upload_time', 'Unknown')
        })
    else:
        return jsonify({
            'loaded': False,
            'message': 'No file currently loaded'
        })

@app.route('/api/processing/status')
def api_processing_status():
    """Get knowledge extraction processing status."""
    file_info = session.get('current_file', {})
    
    if not file_info:
        return jsonify({
            'processing': False,
            'message': 'No file loaded',
            'ready_for_queries': False
        })
    
    project_id = file_info.get('project_id')
    if not project_id or project_id not in processing_status:
        return jsonify({
            'processing': False,
            'status': 'unknown',
            'message': 'No processing information available',
            'ready_for_queries': False
        })
    
    status = processing_status[project_id]
    is_complete = status['status'] == 'complete'
    
    # Enhanced message for completion
    if is_complete:
        summary = status.get('summary', {})
        ready_message = f"✅ READY! Extracted {summary.get('characters', 0)} characters, {summary.get('locations', 0)} locations, {summary.get('terms', 0)} terms. You can now ask questions!"
    else:
        ready_message = status.get('message', '')
    
    return jsonify({
        'processing': status['status'] == 'processing',
        'status': status['status'],
        'progress': status.get('progress', 0),
        'message': ready_message,
        'summary': status.get('summary', {}),
        'ready_for_queries': is_complete
    })

@app.route('/api/file/clear', methods=['POST'])
def api_clear_file():
    """Clear the currently loaded file from session."""
    print("🔍 *** API CLEAR FILE CALLED ***")
    try:
        current_file = session.get('current_file')
        print(f"🔍 Current file before clear: {current_file is not None}")
        if current_file:
            print(f"🔍 Clearing file: {current_file.get('filename', 'Unknown')}")
        
        session.pop('current_file', None)
        session.pop('upload_time', None)
        session.pop('test_value', None)  # Also clear test value
        
        # IMPORTANT: Clear AI conversation history too!
        global george_ai
        if GEORGE_AI_AVAILABLE and george_ai:
            george_ai.conversation_history = []
            print("🔍 Cleared AI conversation history")
        
        print(f"🔍 Session keys after clear: {list(session.keys())}")
        
        result = {
            'success': True,
            'message': 'File and AI memory cleared'
        }
        print(f"🔍 Returning: {result}")
        return jsonify(result)
    except Exception as e:
        print(f"🔍 Error in clear endpoint: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/session/test')
def api_session_test():
    """Test session persistence."""
    test_val = session.get('test_value', 'NOT_FOUND')
    current_file = session.get('current_file')
    return jsonify({
        'test_value': test_val,
        'has_current_file': current_file is not None,
        'session_keys': list(session.keys()),
        'filename': current_file.get('filename') if current_file else None
    })

# Test endpoint removed - Elias.txt deleted, use normal upload instead

@app.route('/api/ai/reset', methods=['POST'])
def api_reset_ai():
    """Reset AI conversation history completely."""
    print("🔍 *** RESETTING AI MEMORY ***")
    try:
        global george_ai
        if GEORGE_AI_AVAILABLE and george_ai:
            george_ai.conversation_history = []
            print("🔍 AI conversation history cleared")
            return jsonify({
                'success': True,
                'message': 'AI memory reset successfully'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'AI not available'
            })
    except Exception as e:
        print(f"🔍 Error resetting AI: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def allowed_file(filename):
    """Check if file type is allowed."""
    allowed_extensions = {'txt', 'md', 'docx'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

if __name__ == '__main__':
    print("Starting George Flask application...")
    print("Open your browser to: http://localhost:5000")
    print("Press Ctrl+C to stop the server.")
    # Disable auto-reload to preserve sessions during development
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)