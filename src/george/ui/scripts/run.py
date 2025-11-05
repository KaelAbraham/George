"""
Run script for Standalone George - Easy startup for the complete application.
"""
import os
import sys
import subprocess
import logging
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
def check_dependencies():
    """Check if required dependencies are available."""
    try:
        import spacy
        import flask
        import chromadb
        logger.info("Core dependencies available")
        return True
    except ImportError as e:
        logger.error(f"Missing dependencies: {e}")
        return False
def main():
    """Main entry point for running George."""
    print("=" * 60)
    print("Standalone George - Local-first AI Assistant for Authors")
    print("=" * 60)
    # Check dependencies
    if not check_dependencies():
        logger.error("Please install required dependencies first")
        return 1
    # Check if we have test files
    fixtures_dir = os.path.join(os.path.dirname(__file__), 'tests', 'fixtures')
    sample_files = ['sample.txt', 'sample.md', 'sample.docx']
    available_files = []
    for filename in sample_files:
        file_path = os.path.join(fixtures_dir, filename)
        if os.path.exists(file_path):
            available_files.append((filename, file_path))
    if available_files:
        print("\nAvailable sample files:")
        for i, (filename, file_path) in enumerate(available_files, 1):
            size = os.path.getsize(file_path)
            print(f"  {i}. {filename} ({size} bytes)")
        print(f"\nTo process a sample file, run:")
        print(f"  python main.py --mode workflow --file {available_files[0][1]}")
        print(f"  python main.py --mode chat")
    else:
        print("\nNo sample files found. Add your manuscript files to get started.")
    print("\nTo start the web interface:")
    print("  python main.py --mode chat")
    print("\nFor more options:")
    print("  python main.py --help")
    print("\n" + "=" * 60)
    print("George is ready! Import your manuscript to begin.")
    print("=" * 60)
    return 0
if __name__ == "__main__":
    sys.exit(main())