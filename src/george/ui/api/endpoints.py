from flask import Blueprint, jsonify, request
from ..auth.auth_client import verify_firebase_token
from ...knowledge_extraction.orchestrator import KnowledgeExtractor
from ...llm_integration import create_george_ai
import os

api_bp = Blueprint('api', __name__, url_prefix='/api')

# --- Helper function to "Georgeify" the response ---
def georgeify_response(raw_text, sources=[]):
    """Formats a raw AI response into George's voice."""
    # This is a simple implementation of the "Georgeification" layer.
    # It can be made more sophisticated later.
    
    # Basic tone consistency checks
    raw_text = raw_text.replace("I think", "The text suggests")
    raw_text = raw_text.replace("In my opinion", "Based on the manuscript")
    
    formatted_response = f"Here is the information based on your manuscript:\n\n- {raw_text}"
    
    if sources:
        source_list = ", ".join(sources)
        formatted_response += f"\n\n[Sources: {source_list}]"
        
    return formatted_response

@api_bp.route('/projects/<project_id>/chat', methods=['POST'])
@verify_firebase_token()
def project_chat(project_id):
    """Handles a chat message for a specific project."""
    data = request.get_json()
    question = data.get('question')

    if not question:
        return jsonify({"error": "No question provided"}), 400

    try:
        # --- This is the full, intelligent workflow ---
        
        # 1. Initialize the AI and Knowledge Extractor for this project
        # In a real app, you would manage these instances more globally
        project_path = os.path.join("src/data/uploads/projects", project_id)
        george_ai = create_george_ai(model="phi3:mini:instruct") # Using your preferred fast model
        extractor = KnowledgeExtractor(george_ai, project_path)

        # 2. Let the orchestrator handle the query (Intent, Retrieval, Generation)
        result = extractor.answer_query(question)

        if result['success']:
            # 3. Apply the "Georgeification" Layer
            final_answer = georgeify_response(result['response'], sources=[f"{project_id} knowledge base"])
            return jsonify({"answer": final_answer})
        else:
            return jsonify({"error": result.get('error', 'An unknown error occurred')}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# You can remove the old mock routes if you wish, or keep them for other testing.