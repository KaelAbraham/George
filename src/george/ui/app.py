from flask import Flask
import os
import sys
from pathlib import Path

# Add the parent directory to the path so we can import from src.george
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import the project manager
try:
    from ui.project_manager import ProjectManager
except ImportError:
    # Handle the case where the script is run from a different directory
    from george.ui.project_manager import ProjectManager


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.secret_key = 'your-super-secret-key-change-me'  # IMPORTANT: Change this!

    # --- Configuration ---
    # Use a directory relative to the instance folder for persistent data.
    # The instance folder is created outside the src folder.
    app.config['UPLOAD_FOLDER'] = os.path.join(app.instance_path, 'uploads')
    app.config['PROJECTS_BASE_DIR'] = os.path.join(app.instance_path, 'projects')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

    # Ensure instance folders exist
    try:
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        os.makedirs(app.config['PROJECTS_BASE_DIR'], exist_ok=True)
    except OSError:
        pass

    # --- Initialize Extensions & Services ---
    # Make the ProjectManager available to the whole app
    app.project_manager = ProjectManager(base_dir=app.config['PROJECTS_BASE_DIR'])


    # --- Register Blueprints ---
    from .blueprints.main import main_bp
    from .blueprints.auth import auth_bp
    from .blueprints.project_manager import project_manager_bp
    # from .api.endpoints import api_bp # We will add this back later

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(project_manager_bp)
    # app.register_blueprint(api_bp, url_prefix='/api')

    return app

# This allows running the app directly for development
if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=5000)
