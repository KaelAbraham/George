#!/usr/bin/env python3
"""
Run script for George Flask web application.
"""

import sys
import os
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Change to project root directory
os.chdir(project_root)

# Import and run the main Flask app (no longer app_simple)
if __name__ == '__main__':
    try:
        # This is the key change: we import 'app' from the new 'app.py'
        from src.george.ui.app import create_app
        
        app = create_app()
        print("Starting George Flask application...")
        print("Open your browser to: http://localhost:5000")
        print("Press Ctrl+C to stop the server.")
        app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
    except ImportError as e:
        print(f"Error importing Flask app: {e}")
        print("Please ensure the application structure is correct and all dependencies are installed.")


