#!/usr/bin/env python3
"""
Quick deployment helper for George frontend
Copy dist folder to production server
"""
import os
import shutil
import subprocess
from pathlib import Path

def verify_build():
    """Verify the build was successful"""
    dist_path = Path("frontend/dist/index.html")
    
    if not dist_path.exists():
        print("❌ Build not found. Run: npm run build")
        return False
    
    content = dist_path.read_text()
    
    # Check for React root
    if '<div id="root"></div>' not in content:
        print("❌ index.html does not contain React root")
        return False
    
    # Check for old HTML
    if '<div class="container">' in content:
        print("❌ Old HTML found in index.html")
        return False
    
    print("✅ Build verified - React app is ready")
    return True

def create_deployment_archive():
    """Create a tar.gz of the dist folder"""
    dist_path = Path("frontend/dist")
    archive_name = "frontend-dist.tar.gz"
    
    print(f"📦 Creating {archive_name}...")
    shutil.make_archive(
        "frontend-dist",
        "gztar",
        "frontend",
        "dist"
    )
    
    archive_size = Path(archive_name).stat().st_size / 1024 / 1024
    print(f"✅ Created {archive_name} ({archive_size:.2f} MB)")
    return archive_name

def print_deployment_instructions():
    """Print GCP console instructions"""
    instructions = """
╔════════════════════════════════════════════════════════════════╗
║           DEPLOY TO PRODUCTION - GCP CONSOLE METHOD            ║
╚════════════════════════════════════════════════════════════════╝

1. Open GCP Console: https://console.cloud.google.com/compute/instances
2. Find "caudex-pro-backend-vm" and click SSH button
3. Run these commands in the web terminal:

   cd ~/George && git pull origin master
   cd frontend
   rm -rf dist node_modules package-lock.json
   npm install --legacy-peer-deps
   npm run build
   sudo rm -rf /var/www/caudex-pro/*
   sudo cp -r dist/* /var/www/caudex-pro/
   sudo chown -R sw33fami1y:sw33fami1y /var/www/caudex-pro/

4. Verify:
   curl https://app.caudex.pro/ | head -20

5. Visit https://app.caudex.pro in your browser
   Should see: React Login Page (NOT old HTML)

════════════════════════════════════════════════════════════════

Need help? Check FRONTEND_DEPLOYMENT.md for detailed instructions
"""
    print(instructions)

if __name__ == "__main__":
    os.chdir(Path(__file__).parent)
    
    if verify_build():
        create_deployment_archive()
        print_deployment_instructions()
    else:
        print("\n❌ Deployment preparation failed")
        exit(1)
