"""
George Knowledge Extractor - Flask Backend
A demo application for extracting and querying knowledge from manuscripts using AI.
"""
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import json
from pathlib import Path
from dotenv import load_dotenv
import chardet
import sys

# Add the 'src' directory to the Python path
project_root = Path(__file__).parent.parent
src_path = project_root / 'src'
backend_path = project_root / 'backend'
sys.path.insert(0, str(src_path))
sys.path.insert(0, str(backend_path))

# Now we can import from the 'george' package and local 'knowledge_extraction'
from george.llm_integration import GeorgeAI
# Import from local knowledge_extraction (now in backend/)
from knowledge_extraction.orchestrator import KnowledgeExtractor

# Load environment variables from project root
load_dotenv(dotenv_path=project_root / '.env')

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for frontend communication

# Configuration
UPLOAD_FOLDER = project_root / 'data' / 'uploads'
PROJECTS_FOLDER = UPLOAD_FOLDER / 'projects'
ALLOWED_EXTENSIONS = {'txt', 'md'}

UPLOAD_FOLDER.mkdir(exist_ok=True)
PROJECTS_FOLDER.mkdir(exist_ok=True)

# Initialize AI and Knowledge Extractor
# In a real app, these would be managed more robustly.
try:
    george_ai = GeorgeAI()
    # We will initialize the extractor when a file is uploaded.
    print("✅ George AI client initialized")
except Exception as e:
    print(f"❌ Failed to initialize George AI client: {e}")
    george_ai = None


# Global state (in production, use a dedicated state manager)
# This simple dictionary is for demo purposes only.
knowledge_extractor = None
extraction_status = {
    'processing': False,
    'progress': 0,
    'message': 'Ready',
    'entities': None,
    'filename': None,
}


def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/')
def index():
    """Serve the frontend or redirect to demo."""
    from flask import redirect
    return redirect('/demo')

@app.route('/api/status')
def api_status():
    """Health check endpoint."""
    return jsonify({
        'status': 'running',
        'service': 'George Knowledge Extractor',
        'ai_ready': george_ai is not None
    })


@app.route('/demo')
def demo():
    """Serve the frontend demo page."""
    from flask import send_file
    frontend_path = Path(__file__).parent.parent / 'frontend' / 'index.html'
    if frontend_path.exists():
        return send_file(frontend_path)
    else:
        return jsonify({'error': 'Frontend not found', 'path': str(frontend_path)}), 404


@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload and start knowledge extraction."""
    global knowledge_extractor  # Use the global extractor instance

    if not george_ai:
        return jsonify({'error': 'George AI not initialized'}), 500
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed. Use .txt or .md'}), 400
    
    try:
        filename = secure_filename(file.filename)
        project_name = Path(filename).stem
        project_path = PROJECTS_FOLDER / project_name
        project_path.mkdir(exist_ok=True)

        filepath = project_path / filename
        file.save(filepath)
        
        # Initialize the orchestrator for this project
        knowledge_extractor = KnowledgeExtractor(george_ai, str(project_path))
        
        with open(filepath, 'rb') as f:
            raw_data = f.read()
            encoding = chardet.detect(raw_data)['encoding'] or 'utf-8'
        
        try:
            content = raw_data.decode(encoding)
        except (UnicodeDecodeError, TypeError):
            content = raw_data.decode('latin-1', errors='replace')

        # Update status before starting the background thread
        extraction_status.update({
            'processing': True,
            'progress': 5,
            'message': 'Starting knowledge extraction...',
            'filename': filename,
        })

        # In a real app, you'd use a task queue like Celery.
        # Here, we'll just run it and let the client poll for status.
        # This is NOT robust for production.
        result = knowledge_extractor.process_manuscript(content, filename)

        # Update final status
        extraction_status.update({
            'processing': False,
            'progress': 100,
            'message': 'Extraction complete!',
            'entities': result,
        })
        
        return jsonify({
            'success': True,
            'message': 'Extraction complete!',
            'data': result
        })
        
    except Exception as e:
        extraction_status.update({
            'processing': False,
            'message': f'Error: {str(e)}'
        })
        return jsonify({'error': str(e)}), 500


@app.route('/status', methods=['GET'])
def get_status():
    """Return the current status of the knowledge extraction process."""
    return jsonify(extraction_status)


@app.route('/entities', methods=['GET'])
def get_entities():
    """Return the extracted entities after processing is complete."""
    if extraction_status['processing']:
        return jsonify({'error': 'Processing not complete'}), 400
    
    if not knowledge_extractor:
        return jsonify({'error': 'Extraction has not been run yet.'}), 400

    try:
        # Get entity names grouped by type
        extractor = knowledge_extractor.extractor
        characters = [e.name for e in extractor.get_entities_by_type('character')]
        locations = [e.name for e in extractor.get_entities_by_type('location')]
        terms = [e.name for e in extractor.get_entities_by_type('term')]
        print(f"[ENTITIES] characters={len(characters)} locations={len(locations)} terms={len(terms)}")
        
        return jsonify({
            'characters': characters,
            'locations': locations,
            'terms': terms,
            'total': len(characters) + len(locations) + len(terms)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/query', methods=['POST'])
def query():
    """Answer a question using the knowledge base."""
    global knowledge_extractor
    if not knowledge_extractor:
        return jsonify({'error': 'Knowledge base not ready. Please upload a file first.'}), 400
    
    data = request.get_json()
    question = data.get('question', '')
    
    if not question:
        return jsonify({'error': 'No question provided'}), 400
    
    try:
        result = knowledge_extractor.answer_query(question)
        print(f"[QUERY][DEBUG] extractor_result={result}")
        if not isinstance(result, dict):
            print(f"[QUERY][ERROR] Unexpected response type: {type(result)}")
            return jsonify({'error': 'Unexpected response from knowledge extractor.'}), 500

        if not result.get('success'):
            error_message = result.get('error') or result.get('response') or 'Unknown error from knowledge extractor'
            print(f"[QUERY][ERROR] {error_message}")
            return jsonify({'error': error_message}), 500

        answer_text = result.get('response')
        if not answer_text:
            answer_text = '⚠️ I could not compose an answer for that question.'

        answer_payload = {
            'answer': answer_text,
            'model': result.get('model'),
            'context_used': result.get('context_used'),
        }

        if result.get('fallback_used'):
            answer_payload['fallback_used'] = True
            answer_payload['fallback_reason'] = result.get('fallback_reason')

        print(f"[QUERY][OK] context_used={answer_payload['context_used']} model={answer_payload['model']} fallback={result.get('fallback_used', False)}")
        return jsonify(answer_payload)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
        
        # Simple keyword matching to find relevant profiles
        question_lower = question.lower()
        
        for profile_file in KNOWLEDGE_BASE_FOLDER.glob('*.md'):
            # Check if entity name appears in question
            entity_name = profile_file.stem.split('_', 1)[1].replace('_', ' ')
            
            if entity_name.lower() in question_lower:
                with open(profile_file, 'r', encoding='utf-8') as f:
                    context_parts.append(f.read())
        
        # If no specific entities mentioned, load all character profiles
        if not context_parts:
            for profile_file in KNOWLEDGE_BASE_FOLDER.glob('character_*.md'):
                with open(profile_file, 'r', encoding='utf-8') as f:
                    context_parts.append(f.read())
        
        # Combine context
        context = '\n\n---\n\n'.join(context_parts)
        
        if not context:
            return jsonify({
                'answer': 'No knowledge base available. Please upload a document first.'
            })
        
        # Get answer from Gemini
        answer = gemini.answer_query(question, context)
        
        return jsonify({
            'question': question,
            'answer': answer,
            'sources_used': len(context_parts)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("=" * 60)
    print("🚀 George Knowledge Extractor")
    print("=" * 60)
    print("Backend server starting...")
    print("Open your browser to the frontend (index.html)")
    print("API running on: http://127.0.0.1:5001")
    print("=" * 60)
    
    # Run Flask development server
    app.run(host='0.0.0.0', port=5001, debug=False, threaded=True)
