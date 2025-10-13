#!/usr/bin/env python3
"""
Test file upload functionality
"""

import requests
import os

def test_file_upload():
    """Test uploading a file to the Flask app."""
    print("🧪 Testing File Upload")
    print("=" * 30)
    
    # Check if file exists
    file_path = "Elias.txt"
    if not os.path.exists(file_path):
        print(f"❌ File {file_path} not found")
        return
    
    print(f"✅ Found file: {file_path}")
    
    # Upload file
    url = "http://localhost:5000/upload"
    
    try:
        with open(file_path, 'rb') as f:
            files = {'manuscript': (file_path, f, 'text/plain')}
            response = requests.post(url, files=files, allow_redirects=False)
            
        print(f"📤 Upload response: {response.status_code}")
        print(f"📤 Response headers: {dict(response.headers)}")
        
        if response.status_code == 302:
            print("✅ Upload successful (redirect received)")
        else:
            print(f"❌ Upload failed: {response.status_code}")
            print(f"Response text: {response.text}")
    
    except Exception as e:
        print(f"❌ Upload error: {e}")
    
    # Check file status
    try:
        status_response = requests.get("http://localhost:5000/api/file/current")
        if status_response.status_code == 200:
            data = status_response.json()
            print(f"📊 File status: {data}")
        else:
            print(f"❌ Status check failed: {status_response.status_code}")
    except Exception as e:
        print(f"❌ Status check error: {e}")

if __name__ == "__main__":
    test_file_upload()