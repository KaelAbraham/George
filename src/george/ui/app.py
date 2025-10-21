import os
from flask import Flask, render_template, current_app # Added current_app for logging
from jinja2 import TemplateNotFound
from dotenv import load_dotenv
from pathlib import Path # Use Path for better path handling

# --- Load environment variables from .env file ---
load_dotenv()

# --- Import Blueprints ---
# Use relative imports within the UI package
from .blueprints.main import main_bp
from .blueprints.auth import auth_bp
from .blueprints.project_manager import project_bp
from .blueprints.chat import chat_bp
from .blueprints.upload import upload_bp
from .api.endpoints import api_bp

def create_app():
    """Create and configure the Flask application."""
    # Use template_folder='templates' explicitly if structure differs, but default is fine here.
    # Use static_folder='static' explicitly if structure differs, but default is fine here.
    app = Flask(__name__, instance_relative_config=True)

    # --- Configuration ---
    # Load the secret key from environment variable
    app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'default-dev-key-CHANGE-ME')
    if app.config['SECRET_KEY'] == 'default-dev-key-CHANGE-ME' and app.env == 'production':
         # Use Flask's built-in logger
         app.logger.warning("SECURITY WARNING: Using default SECRET_KEY in production! Set the FLASK_SECRET_KEY environment variable.")

    # Base directory of the project (assuming app.py is two levels down from root)
    # src/george/ui/app.py -> src/george -> src -> project_root
    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    # Define upload folder relative to the project root
    upload_folder_path = base_dir / 'src' / 'data' / 'uploads'
    app.config['UPLOAD_FOLDER'] = str(upload_folder_path)
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16MB

    # Ensure upload folder exists
    try:
        upload_folder_path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        app.logger.error(f"Could not create upload folder at {upload_folder_path}: {e}")
        # Depending on severity, you might want to raise an exception here

    # --- Initialize Project Manager ---
    from .project_manager import ProjectManager
    projects_base_dir = base_dir / 'src' / 'george' / 'ui' / 'instance'
    app.project_manager = ProjectManager(str(projects_base_dir))

    # --- Register Blueprints ---
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(project_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(api_bp, url_prefix='/api')

    # --- Error Handlers ---
    @app.errorhandler(404)
    @app.errorhandler(TemplateNotFound)
    def handle_not_found_error(e):
        """Custom 404 handler for missing pages or templates."""
        app.logger.warning(f"Not Found Error: {e}")
        # Attempt to render a custom 404 page
        try:
             return render_template('404.html'), 404
        except TemplateNotFound:
             # Fallback if 404.html itself is missing
             return "<h1>404 Not Found</h1><p>The page you were looking for doesn't exist.</p>", 404

    @app.errorhandler(500)
    def handle_internal_server_error(e):
         """Custom 500 handler for unexpected errors."""
         # Log the full exception details
         app.logger.error(f"Internal Server Error: {e}", exc_info=True)
         # Attempt to render a custom 500 page
         try:
             return render_template('500.html'), 500
         except TemplateNotFound:
              # Fallback if 500.html is missing
             return "<h1>500 Internal Server Error</h1><p>Something went wrong on our end. Please try again later.</p>", 500

    # Ensure this function always returns the app instance
    return app

# --- REMOVED the if __name__ == '__main__': block ---
# The application should be run using run_web.py or a WSGI server like Gunicorn.