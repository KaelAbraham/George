#!/usr/bin/env python3
import os

endpoints_code = """import os
import logging
from flask import Blueprint, jsonify, request
from ..auth.auth_client import verify_firebase_token
from ..backend_client import backend_client

api_bp = Blueprint('api', __name__, url_prefix='/api')
logger = logging.getLogger(__name__)


# --- Project Chat Endpoint (via HTTP) ---
@api_bp.route('/projects/<project_id>/chat', methods=['POST'])
@verify_firebase_token()
def project_chat(project_id):
    \"\"\"Handles a chat message for a specific project.\"\"\"
    try:
        data = request.get_json()
        question = data.get('question')
        user_id = request.user.get('uid') if hasattr(request, 'user') else None
        
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401
        
        if not question:
            return jsonify({'error': 'No question provided'}), 400
        
        response = backend_client.query_knowledge_base(project_id, question, user_id)
        
        if response.get('success'):
            return jsonify({
                'success': True,
                'answer': response.get('data', {}).get('answer', 'No answer generated'),
                'sources': response.get('data', {}).get('sources', [])
            })
        else:
            error_msg = response.get('error', 'Unknown error')
            return jsonify({'error': error_msg}), 500
    
    except Exception as e:
        logger.error(f'Error in project_chat endpoint: {e}', exc_info=True)
        return jsonify({'error': f'An unexpected server error occurred: {e}'}), 500


# --- Process Manuscript Endpoint (via HTTP) ---
@api_bp.route('/projects/<project_id>/process', methods=['POST'])
@verify_firebase_token()
def process_manuscript(project_id):
    \"\"\"Triggers knowledge base generation for a project.\"\"\"
    try:
        user_id = request.user.get('uid') if hasattr(request, 'user') else None
        
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401
        
        response = backend_client.generate_knowledge_base(project_id, user_id)
        
        if response.get('success'):
            return jsonify({
                'success': True,
                'message': 'Knowledge base generation started',
                'data': response.get('data')
            })
        else:
            error_msg = response.get('error', 'Unknown error')
            return jsonify({'error': error_msg}), 500
    
    except Exception as e:
        logger.error(f'Error in process_manuscript endpoint: {e}', exc_info=True)
        return jsonify({'error': f'An unexpected server error occurred: {e}'}), 500


# --- Health Check Endpoint ---
@api_bp.route('/health', methods=['GET'])
def health_check():
    \"\"\"Check if backend services are healthy.\"\"\"
    try:
        response = backend_client.check_health()
        
        if response.get('success'):
            return jsonify({
                'success': True,
                'status': 'Backend services are operational'
            })
        else:
            return jsonify({
                'success': False,
                'status': 'Backend services are unavailable'
            }), 503
    
    except Exception as e:
        logger.error(f'Error in health check endpoint: {e}')
        return jsonify({
            'success': False,
            'status': f'Health check failed: {e}'
        }), 503


# --- Project Status Endpoint ---
@api_bp.route('/projects/<project_id>/status', methods=['GET'])
@verify_firebase_token()
def project_status(project_id):
    \"\"\"Get the current status of a project.\"\"\"
    try:
        user_id = request.user.get('uid') if hasattr(request, 'user') else None
        
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401
        
        response = backend_client.get_status(project_id, user_id)
        
        if response.get('success'):
            return jsonify({
                'success': True,
                'data': response.get('data')
            })
        else:
            error_msg = response.get('error', 'Unknown error')
            return jsonify({'error': error_msg}), 500
    
    except Exception as e:
        logger.error(f'Error getting project status: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500


# --- Project Entities Endpoint ---
@api_bp.route('/projects/<project_id>/entities', methods=['GET'])
@verify_firebase_token()
def project_entities(project_id):
    \"\"\"Get entities from a project.\"\"\"
    try:
        user_id = request.user.get('uid') if hasattr(request, 'user') else None
        
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401
        
        response = backend_client.get_entities(project_id, user_id)
        
        if response.get('success'):
            return jsonify({
                'success': True,
                'data': response.get('data')
            })
        else:
            error_msg = response.get('error', 'Unknown error')
            return jsonify({'error': error_msg}), 500
    
    except Exception as e:
        logger.error(f'Error getting project entities: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500
"""

target_path = r'c:\Users\kael_\George\src\george\ui\api\endpoints.py'
with open(target_path, 'w', encoding='utf-8') as f:
    f.write(endpoints_code)

print(f"✓ Successfully wrote {target_path}")
