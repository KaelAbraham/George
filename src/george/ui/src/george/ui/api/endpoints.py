"""API endpoints for George application."""
from flask import Blueprint, jsonify, request, session
import logging
import os
import sys

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__)

@api_bp.route('/projects/<project_id>/candidates')
def get_candidates(project_id):
    """Get entity candidates for a project."""
    try:
        # For now, return mock data - in a real implementation this would
        # load from the knowledge base or process the uploaded file
        candidates = [
            {
                "id": 1,
                "text": "Elias",
                "type": "PERSON",
                "confidence": 0.95,
                "context": "Elias the blacksmith, his hands calloused and his back aching from the forge",
                "approved": None
            },
            {
                "id": 2,
                "text": "Lyra", 
                "type": "PERSON",
                "confidence": 0.92,
                "context": "Lyra the scholar, surrounded by dusty scrolls and the silent weight of history",
                "approved": None
            },
            {
                "id": 3,
                "text": "Finn",
                "type": "PERSON", 
                "confidence": 0.89,
                "context": "Finn the minstrel was tired of the fickle crowds and the meager coin",
                "approved": None
            },
            {
                "id": 4,
                "text": "the woods",
                "type": "LOCATION",
                "confidence": 0.78,
                "context": "in a part of the woods they had never explored",
                "approved": None
            }
        ]
        return jsonify(candidates)
    except Exception as e:
        logger.error(f"Error getting candidates: {e}")
        return jsonify({"error": str(e)}), 500

@api_bp.route('/projects/<project_id>/candidates/<int:candidate_id>', methods=['POST'])
def update_candidate(project_id, candidate_id):
    """Update candidate approval status."""
    try:
        data = request.get_json()
        approved = data.get('approved')
        
        # In a real implementation, this would update the database
        logger.info(f"Candidate {candidate_id} {'approved' if approved else 'rejected'}")
        
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error updating candidate: {e}")
        return jsonify({"error": str(e)}), 500

@api_bp.route('/projects/<project_id>/finalize', methods=['POST'])
def finalize_project(project_id):
    """Finalize the project and build knowledge base."""
    try:
        # In a real implementation, this would:
        # 1. Get approved entities
        # 2. Build the knowledge base
        # 3. Set up the project for chat
        
        logger.info(f"Finalizing project {project_id}")
        return jsonify({"success": True, "message": "Knowledge base built successfully"})
    except Exception as e:
        logger.error(f"Error finalizing project: {e}")
        return jsonify({"error": str(e)}), 500

@api_bp.route('/projects/<project_id>/chat', methods=['POST'])
def chat_message(project_id):
    """Handle chat messages."""
    try:
        data = request.get_json()
        message = data.get('message', '')
        
        # Simple mock response - in real implementation this would
        # query the knowledge base and generate AI responses
        response = f"I understand you're asking about: '{message}'. Based on your story about Elias, Lyra, and Finn, I can help you explore their character development and the magical elements of your world."
        
        return jsonify({
            "response": response,
            "sources": ["Your manuscript: Elias.txt"]
        })
    except Exception as e:
        logger.error(f"Error in chat: {e}")
        return jsonify({"error": str(e)}), 500