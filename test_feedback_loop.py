"""
Test script for the Feedback Loop System

This script demonstrates how to test the new feedback loop functionality.
It shows:
1. Sending a query to /chat and capturing the message_id
2. Submitting feedback to /feedback using that message_id
3. Retrieving feedback from the database

Run with:
    python test_feedback_loop.py
"""

import requests
import json
from datetime import datetime

# Configuration
BACKEND_URL = "http://localhost:5000"
AUTH_TOKEN = "test-token"  # Replace with actual token from auth server

# Headers for API requests
headers = {
    "Authorization": f"Bearer {AUTH_TOKEN}",
    "Content-Type": "application/json"
}

def test_chat_with_feedback():
    """Test the full feedback loop: chat -> get message_id -> submit feedback"""
    
    print("=" * 70)
    print("FEEDBACK LOOP SYSTEM TEST")
    print("=" * 70)
    
    # Step 1: Send a chat query
    print("\n[Step 1] Sending query to /chat endpoint...")
    chat_payload = {
        "query": "How do I improve the tension in my scene?",
        "project_id": "test-project-001"
    }
    
    try:
        chat_response = requests.post(
            f"{BACKEND_URL}/chat",
            headers=headers,
            json=chat_payload,
            timeout=10
        )
        
        if chat_response.status_code == 200:
            chat_data = chat_response.json()
            message_id = chat_data.get('message_id')
            
            print(f"✅ Chat successful!")
            print(f"   Message ID: {message_id}")
            print(f"   Response: {chat_data.get('response', 'N/A')[:100]}...")
            print(f"   Intent: {chat_data.get('intent')}")
            print(f"   Cost: ${chat_data.get('cost', 0):.4f}")
            
        else:
            print(f"❌ Chat failed: {chat_response.status_code}")
            print(f"   Response: {chat_response.text}")
            return
            
    except Exception as e:
        print(f"❌ Error calling /chat: {e}")
        return
    
    # Step 2: Submit feedback
    print(f"\n[Step 2] Submitting feedback for message_id: {message_id}...")
    
    feedback_payload = {
        "message_id": message_id,
        "rating": 1,
        "category": "helpful",
        "comment": "Great insight! This helps me think about pacing."
    }
    
    try:
        feedback_response = requests.post(
            f"{BACKEND_URL}/feedback",
            headers=headers,
            json=feedback_payload,
            timeout=10
        )
        
        if feedback_response.status_code == 201:
            feedback_data = feedback_response.json()
            feedback_id = feedback_data.get('feedback_id')
            
            print(f"✅ Feedback submitted successfully!")
            print(f"   Feedback ID: {feedback_id}")
            print(f"   Status: {feedback_data.get('status')}")
            
        else:
            print(f"❌ Feedback submission failed: {feedback_response.status_code}")
            print(f"   Response: {feedback_response.text}")
            return
            
    except Exception as e:
        print(f"❌ Error calling /feedback: {e}")
        return
    
    # Step 3: Submit different feedback ratings
    print(f"\n[Step 3] Testing different feedback ratings...")
    
    feedback_scenarios = [
        {
            "rating": -1,
            "category": "hallucination",
            "comment": "The AI referenced a scene that doesn't exist in the manuscript."
        },
        {
            "rating": 0,
            "category": "neutral",
            "comment": "Interesting perspective, but not directly applicable."
        },
        {
            "rating": 1,
            "category": "excellent",
            "comment": "This completely changed how I approach my story!"
        }
    ]
    
    for i, scenario in enumerate(feedback_scenarios, 1):
        feedback_payload = {
            "message_id": message_id,
            **scenario
        }
        
        try:
            response = requests.post(
                f"{BACKEND_URL}/feedback",
                headers=headers,
                json=feedback_payload,
                timeout=10
            )
            
            if response.status_code == 201:
                data = response.json()
                print(f"   ✅ Feedback #{i} (rating={scenario['rating']}): {data['feedback_id']}")
            else:
                print(f"   ❌ Feedback #{i} failed: {response.status_code}")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    print("\n" + "=" * 70)
    print("FEEDBACK LOOP TEST COMPLETE")
    print("=" * 70)
    print("\nNext steps:")
    print("1. Check the database at: backend/data/feedback.db")
    print("2. View API documentation at: http://localhost:5000/api/docs")
    print("3. Integrate frontend feedback UI with the /feedback endpoint")
    print("\n")

if __name__ == "__main__":
    print("\nNote: Make sure the backend is running on http://localhost:5000")
    print("To start the backend, run: cd backend && python app.py\n")
    
    test_chat_with_feedback()
