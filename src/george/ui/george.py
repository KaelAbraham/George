#!/usr/bin/env python3
"""
George - Standalone AI assistant for authors and world-builders.
Main entry point script.
"""
import sys
import os

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from george.core import main

if __name__ == "__main__":
    sys.exit(main())