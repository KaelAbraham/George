#!/usr/bin/env python3
"""
Test script to verify session functionality with the Flask app.
"""
import requests
import json

def test_session_workflow():
    """Test the complete session workflow."""
    base_url = "http://localhost:5000"
    
    print("🧪 Testing Flask Session Workflow")
    print("=" * 50)
    
    # Create a session to persist cookies
    session = requests.Session()
    
    try:
        # 1. Test homepage
        print("1️⃣ Testing homepage...")
        response = session.get(f"{base_url}/")
        print(f"   Status: {response.status_code}")
        
        # 2. Test load test file
        print("2️⃣ Testing load test file...")
        response = session.post(f"{base_url}/api/file/load-test")
        if response.status_code == 200:
            data = response.json()
            print(f"   Success: {data.get('success')}")
            print(f"   Message: {data.get('message')}")
            print(f"   Session test: {data.get('session_test', 'N/A')}")
        else:
            print(f"   Error: {response.status_code}")
            print(f"   Response: {response.text}")
        
        # 3. Test session persistence
        print("3️⃣ Testing session persistence...")
        response = session.get(f"{base_url}/api/session/test")
        if response.status_code == 200:
            data = response.json()
            print(f"   Test value: {data.get('test_value')}")
            print(f"   Has current file: {data.get('has_current_file')}")
            print(f"   Filename: {data.get('filename')}")
            print(f"   Session keys: {data.get('session_keys')}")
        else:
            print(f"   Error: {response.status_code}")
        
        # 4. Test chat page
        print("4️⃣ Testing chat page...")
        response = session.get(f"{base_url}/chat")
        print(f"   Status: {response.status_code}")
        
        # 5. Test file current API
        print("5️⃣ Testing file current API...")
        response = session.get(f"{base_url}/api/file/current")
        if response.status_code == 200:
            data = response.json()
            print(f"   Has file: {data.get('has_file', False)}")
            if data.get('has_file'):
                print(f"   Filename: {data.get('filename')}")
        
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to Flask app. Make sure it's running on localhost:5000")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_session_workflow()