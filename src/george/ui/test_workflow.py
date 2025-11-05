#!/usr/bin/env python3
"""
Test session and file loading
"""

import sys
import os
from pathlib import Path
import requests
import json

def test_complete_workflow():
    """Test the complete file loading workflow."""
    print("🧪 Testing Complete Workflow")
    print("=" * 40)
    
    # Step 1: Check Flask app is running
    try:
        response = requests.get("http://localhost:5000/api/ai/status", timeout=5)
        if response.status_code == 200:
            print("✅ Flask app is running")
        else:
            print("❌ Flask app not responding correctly")
            return
    except Exception as e:
        print(f"❌ Flask app not running: {e}")
        return
    
    # Step 2: Check file status before upload
    try:
        response = requests.get("http://localhost:5000/api/file/current")
        data = response.json()
        print(f"📊 Initial file status: {data}")
    except Exception as e:
        print(f"❌ Error checking file status: {e}")
    
    # Step 3: Try to simulate a file upload with session
    # We'll create a simple session by making a request that sets cookies
    session = requests.Session()
    
    try:
        # First, get the homepage to establish a session
        response = session.get("http://localhost:5000/")
        print(f"✅ Established session: {response.status_code}")
        
        # Now try to upload a file
        file_path = "Elias.txt"
        if os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                files = {'manuscript': (file_path, f, 'text/plain')}
                response = session.post("http://localhost:5000/upload", files=files, allow_redirects=False)
                
            print(f"📤 Upload response: {response.status_code}")
            if response.status_code == 302:
                print("✅ Upload successful (got redirect)")
                
                # Check file status after upload
                response = session.get("http://localhost:5000/api/file/current")
                data = response.json()
                print(f"📊 File status after upload: {data}")
            else:
                print(f"❌ Upload failed: {response.text}")
        else:
            print(f"❌ File {file_path} not found")
            
    except Exception as e:
        print(f"❌ Upload test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_complete_workflow()