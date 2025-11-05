"""Test script for the AI-Router service."""
import requests
import json

BASE_URL = "http://localhost:5000"

def test_health():
    """Test the health endpoint."""
    print("Testing /health...")
    response = requests.get(f"{BASE_URL}/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    assert response.status_code == 200
    print("✅ Health check passed\n")

def test_chat():
    """Test the chat endpoint."""
    print("Testing /chat...")
    payload = {
        "message": "What color are Edie's eyes?",
        "project_id": "test_project"
    }
    response = requests.post(f"{BASE_URL}/chat", json=payload)
    print(f"Status: {response.status_code}")
    result = response.json()
    print(f"Response: {json.dumps(result, indent=2)}")
    assert response.status_code == 200
    assert 'response' in result
    assert 'intent' in result
    print("✅ Chat test passed\n")

def test_chat_no_project():
    """Test chat without project_id."""
    print("Testing /chat without project_id...")
    payload = {
        "message": "How can I improve my writing?"
    }
    response = requests.post(f"{BASE_URL}/chat", json=payload)
    print(f"Status: {response.status_code}")
    result = response.json()
    print(f"Response: {json.dumps(result, indent=2)}")
    assert response.status_code == 200
    assert 'response' in result
    print("✅ Chat without project_id test passed\n")

if __name__ == "__main__":
    print("=" * 60)
    print("🧪 AI-Router Service Tests")
    print("=" * 60)
    print(f"Testing service at: {BASE_URL}\n")
    
    try:
        test_health()
        test_chat()
        test_chat_no_project()
        print("=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
    except AssertionError as e:
        print(f"❌ Test failed: {e}")
    except requests.exceptions.ConnectionError:
        print(f"❌ Could not connect to {BASE_URL}")
        print("   Make sure the AI-Router service is running:")
        print("   python ai_router/app.py")
