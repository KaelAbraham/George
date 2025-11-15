#!/usr/bin/env python3
"""
Deploy frontend to production server via HTTP
Run this on the server or use via curl
"""
import subprocess
import json
import os

def deploy_frontend():
    """Pull latest code and rebuild frontend"""
    try:
        # Change to project root
        os.chdir(os.path.expanduser('~/George'))
        
        # Pull latest changes
        print("Pulling latest code from git...")
        subprocess.run(['git', 'pull', 'origin', 'master'], check=True)
        
        # Change to frontend directory
        os.chdir('frontend')
        
        # Clean build artifacts
        print("Cleaning old builds...")
        subprocess.run(['rm', '-rf', 'node_modules', 'package-lock.json', 'dist'], check=False)
        
        # Install dependencies
        print("Installing dependencies...")
        subprocess.run(['npm', 'install'], check=True)
        
        # Build
        print("Building React app...")
        result = subprocess.run(['npm', 'run', 'build'], check=True, capture_output=True, text=True)
        
        print(result.stdout)
        print("✅ Frontend build successful!")
        
        return {"status": "success", "message": "Frontend deployed successfully"}
        
    except subprocess.CalledProcessError as e:
        error_msg = f"Build failed: {e.stderr if e.stderr else str(e)}"
        print(f"❌ {error_msg}")
        return {"status": "error", "message": error_msg}
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        print(f"❌ {error_msg}")
        return {"status": "error", "message": error_msg}

if __name__ == '__main__':
    result = deploy_frontend()
    print(json.dumps(result))
