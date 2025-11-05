#!/usr/bin/env python3
"""
George - Standalone AI assistant for authors and world-builders.
DEPRECATED: This entry point is no longer used.

The application now uses a modular backend architecture:
- See backend/app.py for the Flask server
- See backend/knowledge_extraction/ for AI logic

To run the server, use: python backend/app.py
"""
import sys

print("⚠️  WARNING: This entry point is deprecated.")
print("The old monolithic orchestrator has been removed.")
print("Please use the backend server instead: python backend/app.py")
sys.exit(1)