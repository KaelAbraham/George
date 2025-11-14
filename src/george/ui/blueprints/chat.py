from flask import Blueprint, render_template, abort, request, current_app, jsonify
from ..auth.auth_client import verify_firebase_token
from ..backend_client import backend_client
import logging
import uuid

logger = logging.getLogger(__name__)

# Define the blueprint for project-specific chat
chat_bp = Blueprint('chat', __name__, url_prefix='/projects/<project_id>/chat')

@chat_bp.route('/')
@verify_firebase_token()
def chat_interface(project_id):
    """Displays the chat interface for a specific project."""
    try:
        user_id = request.user.get('uid') if hasattr(request, 'user') else None
        
        if not user_id:
            abort(401)  # Unauthorized
        
        # Get project info from backend via HTTP
        response = backend_client.get_project(project_id, user_id)
        
        if not response.get('success'):
            logger.error(f"Failed to get project {project_id}: {response.get('error')}")
            abort(404)
        
        project = response.get('data', {})
        
        # Get user info from the decorator
        user_info = request.user
        
        # Generate a session ID and get initial chat history
        session_id = str(uuid.uuid4())
        chat_history = []  # Start with empty history; frontend will load via API
        
        return render_template('chat.html', 
                             project_id=project_id,
                             session_id=session_id,
                             chat_history=chat_history,
                             project=project,
                             project_name=project.get('name', project_id),
                             user=user_info)
    except Exception as e:
        logger.error(f"Error loading chat interface for project {project_id}: {e}")
        abort(500)


@chat_bp.route('/query', methods=['POST'])
@verify_firebase_token()
def submit_query(project_id):
    """Submit a query to the backend knowledge base."""
    try:
        user_id = request.user.get('uid') if hasattr(request, 'user') else None
        
        if not user_id:
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        
        data = request.get_json()
        question = data.get('question', '')
        
        if not question:
            return jsonify({"success": False, "error": "No question provided"}), 400
        
        # Call backend API to query knowledge base
        response = backend_client.query_knowledge_base(project_id, question, user_id)
        
        return jsonify(response)
    
    except Exception as e:
        logger.error(f"Error processing query: {e}")
        return jsonify({"success": False, "error": str(e)}), 500