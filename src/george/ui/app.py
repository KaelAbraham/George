import os
from flask import Flask, render_template, current_app
from jinja2 import TemplateNotFound
from dotenv import load_dotenv
from pathlib import Path
import logging

# --- Load environment variables from .env file ---
# (Make sure you have a .env file in your project root)
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent.parent / '.env')

# --- Import Blueprints ---
from .blueprints.main import main_bp
from .blueprints.auth import auth_bp
from .blueprints.project_manager import project_bp
from .blueprints.chat import chat_bp
from .blueprints.upload import upload_bp
from .api.endpoints import api_bp

def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__, instance_relative_config=True)

    # --- Configuration ---
    # Load the secret key from environment variable
    app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'default-dev-key-CHANGE-ME')
    if app.config['SECRET_KEY'] == 'default-dev-key-CHANGE-ME' and app.env == 'production':
         app.logger.warning("SECURITY WARNING: Using default SECRET_KEY in production! Set the FLASK_SECRET_KEY environment variable.")

    # Define paths
    base_dir = Path(__file__).resolve().parent.parent.parent.parent # Project root
    upload_folder_path = base_dir / 'src' / 'data' / 'uploads'
    app.config['UPLOAD_FOLDER'] = str(upload_folder_path)
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16MB

    # Ensure upload folder exists
    try:
        upload_folder_path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        app.logger.error(f"Could not create upload folder at {upload_folder_path}: {e}")

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
        try:
             # You will need to create a '404.html' template
             return render_template('404.html'), 404
        except TemplateNotFound:
             return "<h1>404 Not Found</h1><p>The page you were looking for doesn't exist.</p>", 404

    @app.errorhandler(500)
    def handle_internal_server_error(e):
         """Custom 500 handler for unexpected errors."""
         app.logger.error(f"Internal Server Error: {e}", exc_info=True)
         try:
             # You will need to create a '500.html' template
             return render_template('500.html'), 500
         except TemplateNotFound:
             return "<h1>500 Internal Server Error</h1><p>Something went wrong on our end. Please try again later.</p>", 500

    return app