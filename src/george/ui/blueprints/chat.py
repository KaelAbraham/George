from flask import Blueprint, render_template, abort, request, current_app
from ..auth.auth_client import verify_firebase_token

# Define the blueprint for project-specific chat
chat_bp = Blueprint('chat', __name__, url_prefix='/projects/<project_id>/chat')

@chat_bp.route('/')
@verify_firebase_token() # Protect this route
def chat_interface(project_id):
    """Displays the chat interface for a specific project."""
    try:
        # Use the app's project manager instead of creating a new one
        pm = current_app.project_manager
        
        # We load the project to make sure it exists and to pass its info to the template
        project = pm.load_project(project_id)
        if not project:
            abort(404) 
            
        # The user's info is available from the decorator
        user_info = request.user
        return render_template('chat.html', 
                             project=project, 
                             project_name=project_id,
                             user=user_info)
    except Exception as e:
        # In a real app, log this error
        print(f"Error loading project for chat: {e}")
        abort(404)