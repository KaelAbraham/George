"""
Startup script for George Backend Flask Server
"""
import sys
from pathlib import Path

# Add the src directory to Python path
project_root = Path(__file__).parent
src_path = project_root / 'src'
sys.path.insert(0, str(src_path))

# Now import and run the Flask app
from backend.app import app

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 George Knowledge Extractor Backend")
    print("=" * 60)
    print("Starting server on http://0.0.0.0:5001")
    print("Press Ctrl+C to stop")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5001, debug=False)
