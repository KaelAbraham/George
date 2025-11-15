#!/usr/bin/env python3
"""
Upload frontend dist files to GCP server via HTTP POST
"""
import os
import sys
import requests
from pathlib import Path

# Configuration
SERVER_URL = "http://35.232.130.101"
DIST_PATH = Path("C:/Users/kael_/George/frontend/dist")

def upload_files():
    """Upload all files from dist directory to server"""
    if not DIST_PATH.exists():
        print(f"Error: {DIST_PATH} not found")
        return False
    
    print(f"Uploading files from {DIST_PATH}")
    
    # Get all files recursively
    files_to_upload = []
    for root, dirs, files in os.walk(DIST_PATH):
        for file in files:
            file_path = Path(root) / file
            relative_path = file_path.relative_to(DIST_PATH)
            files_to_upload.append((file_path, relative_path))
    
    print(f"Found {len(files_to_upload)} files to upload")
    
    # Note: This requires a file upload endpoint on your server
    # For now, this is a template - you'll need to set up an endpoint
    print("\n=== ALTERNATIVE: Use GCP Web SSH Console ===")
    print("1. Open GCP Console → Compute Engine → Instances → george-instance")
    print("2. Click 'SSH' button to open web console")
    print("3. Run these commands:")
    print("")
    print("   # Create upload directory")
    print("   mkdir -p /tmp/frontend-upload")
    print("   cd /tmp/frontend-upload")
    print("")
    print("4. Copy-paste the following to upload files:")
    print("   (You'll need to use browser upload or manually copy files)")
    print("")
    return False

if __name__ == "__main__":
    upload_files()
