"""
George - Standalone AI assistant for authors and world-builders.
Local-first AI assistant for manuscript analysis and world-building.

NOTE: Old monolithic orchestrators (core.py, main.py) have been deprecated.
The application now uses a modular backend architecture with:
- backend/app.py (Flask server)
- backend/knowledge_extraction/ (AI logic)
- backend/prompts/ (System prompts)
"""

__all__ = []

__version__ = "1.0.0"