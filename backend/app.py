"""
George Knowledge Extractor - Flask Backend
A demo application for extracting and querying knowledge from manuscripts using AI.
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import json
from pathlib import Path
from dotenv import load_dotenv
from gemini_client import GeminiClient

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for frontend communication

# Configuration
UPLOAD_FOLDER = Path('uploads')
KNOWLEDGE_BASE_FOLDER = Path('knowledge_base')
ALLOWED_EXTENSIONS = {'txt', 'md'}

UPLOAD_FOLDER.mkdir(exist_ok=True)
KNOWLEDGE_BASE_FOLDER.mkdir(exist_ok=True)

# Initialize Gemini client
try:
    gemini = GeminiClient()
    print("✅ Gemini API client initialized")
except Exception as e:
    print(f"❌ Failed to initialize Gemini client: {e}")
    gemini = None

# Global state (in production, use Redis or database)
extraction_status = {
    'processing': False,
    'progress': 0,
    'message': 'Ready',
    'entities': None
}


def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/')
def index():
    """Health check endpoint."""
    return jsonify({
        'status': 'running',
        'service': 'George Knowledge Extractor',
        'gemini_ready': gemini is not None
    })


@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload and start knowledge extraction."""
    if not gemini:
        return jsonify({'error': 'Gemini API not initialized'}), 500
    
    # Check if file is in request
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed. Use .txt or .md'}), 400
    
    try:
        # Save uploaded file
        filename = secure_filename(file.filename)
        filepath = UPLOAD_FOLDER / filename
        file.save(filepath)
        
        # Read file content
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Update status
        extraction_status['processing'] = True
        extraction_status['progress'] = 10
        extraction_status['message'] = 'Extracting entities...'
        
        # Extract entities
        entities = gemini.extract_entities(content)
        
        extraction_status['progress'] = 30
        extraction_status['message'] = 'Building character profiles...'
        
        # Build profiles for each entity
        profiles = {}
        total_entities = (len(entities.get('characters', [])) + 
                         len(entities.get('locations', [])) + 
                         len(entities.get('terms', [])))
        
        if total_entities == 0:
            extraction_status['processing'] = False
            extraction_status['progress'] = 100
            extraction_status['message'] = 'No entities found'
            return jsonify({'error': 'No entities found in document'}), 400
        
        current_entity = 0
        
        # Process characters
        for char in entities.get('characters', []):
            current_entity += 1
            progress = 30 + int((current_entity / total_entities) * 60)
            extraction_status['progress'] = progress
            extraction_status['message'] = f'Building profile for {char}...'
            
            profile = gemini.build_profile(char, 'character', content)
            profiles[f'character_{char}'] = profile
            
            # Save profile to file
            profile_path = KNOWLEDGE_BASE_FOLDER / f'character_{char.replace(" ", "_")}.md'
            with open(profile_path, 'w', encoding='utf-8') as f:
                f.write(profile)
        
        # Process locations
        for loc in entities.get('locations', []):
            current_entity += 1
            progress = 30 + int((current_entity / total_entities) * 60)
            extraction_status['progress'] = progress
            extraction_status['message'] = f'Building profile for {loc}...'
            
            profile = gemini.build_profile(loc, 'location', content)
            profiles[f'location_{loc}'] = profile
            
            profile_path = KNOWLEDGE_BASE_FOLDER / f'location_{loc.replace(" ", "_")}.md'
            with open(profile_path, 'w', encoding='utf-8') as f:
                f.write(profile)
        
        # Process terms (limit to first 5 to save time)
        for term in entities.get('terms', [])[:5]:
            current_entity += 1
            progress = 30 + int((current_entity / total_entities) * 60)
            extraction_status['progress'] = progress
            extraction_status['message'] = f'Building profile for {term}...'
            
            profile = gemini.build_profile(term, 'term', content)
            profiles[f'term_{term}'] = profile
            
            profile_path = KNOWLEDGE_BASE_FOLDER / f'term_{term.replace(" ", "_")}.md'
            with open(profile_path, 'w', encoding='utf-8') as f:
                f.write(profile)
        
        # Complete
        extraction_status['processing'] = False
        extraction_status['progress'] = 100
        extraction_status['message'] = 'Extraction complete!'
        extraction_status['entities'] = entities
        
        return jsonify({
            'success': True,
            'filename': filename,
            'entities': entities,
            'profiles_created': len(profiles)
        })
        
    except Exception as e:
        extraction_status['processing'] = False
        extraction_status['message'] = f'Error: {str(e)}'
        return jsonify({'error': str(e)}), 500


@app.route('/status', methods=['GET'])
def get_status():
    """Get current extraction status."""
    return jsonify(extraction_status)


@app.route('/query', methods=['POST'])
def query():
    """Answer a question using the knowledge base."""
    if not gemini:
        return jsonify({'error': 'Gemini API not initialized'}), 500
    
    data = request.get_json()
    question = data.get('question', '')
    
    if not question:
        return jsonify({'error': 'No question provided'}), 400
    
    try:
        # Load relevant profiles from knowledge base
        context_parts = []
        
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


@app.route('/entities', methods=['GET'])
def get_entities():
    """Get list of extracted entities."""
    if extraction_status['entities']:
        return jsonify(extraction_status['entities'])
    else:
        return jsonify({
            'characters': [],
            'locations': [],
            'terms': []
        })


if __name__ == '__main__':
    print("=" * 60)
    print("🚀 George Knowledge Extractor")
    print("=" * 60)
    print("Backend server starting...")
    print("Open your browser to the frontend (index.html)")
    print("API running on: http://127.0.0.1:5001")
    print("=" * 60)
    
    # Use waitress instead of Flask's built-in server (Python 3.14 compatibility)
    from waitress import serve
    serve(app, host='127.0.0.1', port=5001)
