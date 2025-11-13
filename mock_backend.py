#!/usr/bin/env python3
"""
Mock Backend Server for Testing the Frontend-Backend Bridge

This is a minimal Flask server that mimics the Caudex Pro API
for testing purposes. It allows you to test the frontend bridge
without needing all backend dependencies.

Run with: python mock_backend.py
Server runs on: http://localhost:5001
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import uuid

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Mock database
mock_jobs = {}
mock_responses = {}


@app.route('/', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "ok",
        "service": "Caudex Pro AI Router (Mock)",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat()
    }), 200


@app.route('/chat', methods=['POST'])
def chat():
    """
    POST /chat - Process a chat query
    
    Request:
    {
        "query": "Your question here",
        "project_id": "project-123"
    }
    
    Response:
    {
        "response": "AI generated response",
        "intent": "answer|clarification|follow_up",
        "cost": 0.005,
        "downgraded": false,
        "balance": 9.995
    }
    """
    try:
        data = request.get_json()
        query = data.get('query', '')
        project_id = data.get('project_id', 'default')
        
        if not query:
            return jsonify({"error": "query is required"}), 400
        
        # Mock response
        job_id = str(uuid.uuid4())
        response = {
            "response": f"Mock response to: '{query}' (This is a test response from the mock backend)",
            "intent": "greeting" if "hello" in query.lower() else "general_query",
            "cost": 0.005,
            "downgraded": False,
            "balance": 9.995,
            "job_id": job_id
        }
        
        # Store in mock database
        mock_responses[job_id] = response
        
        return jsonify(response), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/jobs/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """
    GET /jobs/<job_id> - Get job status
    
    Response:
    {
        "job_id": "uuid",
        "status": "pending|running|completed|failed",
        "progress": 0-100,
        "created_at": "2025-11-13T...",
        "completed_at": "2025-11-13T...",
        "result": {...}
    }
    """
    if job_id in mock_jobs:
        return jsonify(mock_jobs[job_id]), 200
    
    # Return a mock job
    return jsonify({
        "job_id": job_id,
        "status": "completed",
        "progress": 100,
        "created_at": datetime.now().isoformat(),
        "completed_at": datetime.now().isoformat(),
        "result": mock_responses.get(job_id, {"message": "No result"})
    }), 200


@app.route('/project/<project_id>/jobs', methods=['GET'])
def get_project_jobs(project_id):
    """
    GET /project/<project_id>/jobs - List all jobs for a project
    
    Response:
    {
        "project_id": "project-123",
        "jobs": [
            {
                "job_id": "uuid",
                "status": "completed",
                "created_at": "...",
                "type": "chat|wiki_generation"
            }
        ]
    }
    """
    return jsonify({
        "project_id": project_id,
        "jobs": [
            {
                "job_id": str(uuid.uuid4()),
                "status": "completed",
                "created_at": datetime.now().isoformat(),
                "type": "chat"
            },
            {
                "job_id": str(uuid.uuid4()),
                "status": "running",
                "created_at": datetime.now().isoformat(),
                "type": "wiki_generation"
            }
        ]
    }), 200


@app.route('/project/<project_id>/generate_wiki', methods=['POST'])
def generate_wiki(project_id):
    """
    POST /project/<project_id>/generate_wiki - Trigger wiki generation
    
    Response:
    {
        "message": "Wiki generation started",
        "job_id": "uuid",
        "status_url": "/jobs/uuid"
    }
    """
    job_id = str(uuid.uuid4())
    
    mock_jobs[job_id] = {
        "job_id": job_id,
        "status": "running",
        "progress": 0,
        "created_at": datetime.now().isoformat(),
        "type": "wiki_generation"
    }
    
    return jsonify({
        "message": "Wiki generation started",
        "job_id": job_id,
        "status_url": f"/jobs/{job_id}"
    }), 202


@app.route('/admin/costs', methods=['GET'])
def get_admin_costs():
    """
    GET /admin/costs - Get aggregated cost summary (admin only)
    
    Response:
    {
        "total_tokens": 1000000,
        "total_cost": 50.25,
        "clients": {
            "triage_client": {...},
            "answer_flash_client": {...},
            "answer_pro_client": {...}
        }
    }
    """
    return jsonify({
        "total_tokens": 1000000,
        "total_cost": 50.25,
        "clients": {
            "triage_client": {
                "model": "gemini-1.5-flash",
                "tokens": 500000,
                "cost": 25.00
            },
            "answer_flash_client": {
                "model": "gemini-1.5-flash",
                "tokens": 300000,
                "cost": 15.00
            },
            "answer_pro_client": {
                "model": "gemini-1.5-pro",
                "tokens": 200000,
                "cost": 10.25
            }
        }
    }), 200


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint not found"}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error", "details": str(e)}), 500


if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Mock Backend Server Starting")
    print("=" * 60)
    print("\n📍 Server: http://localhost:5001")
    print("📍 API Docs: http://localhost:5001/api/docs")
    print("\n✅ Endpoints Available:")
    print("  POST   /chat")
    print("  GET    /jobs/<job_id>")
    print("  GET    /project/<project_id>/jobs")
    print("  POST   /project/<project_id>/generate_wiki")
    print("  GET    /admin/costs")
    print("\n💡 CORS is enabled - safe to test from frontend")
    print("=" * 60 + "\n")
    
    app.run(debug=True, host='127.0.0.1', port=5001, use_reloader=False)
