#!/usr/bin/env python3
"""
Minimal test for George AI integration
"""

import sys
import os
from pathlib import Path
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src' / 'george'))

def test_minimal():
    """Minimal test of George AI."""
    print("🧪 Minimal Phi-3 Test")
    print("=" * 30)
    
    try:
        from llm_integration import OllamaClient
        print("✅ Import successful")
        
        # Create client
        client = OllamaClient(model="phi3:instruct")
        print("✅ Client created")
        
        # Test availability
        available = client.is_available()
        print(f"📡 Service available: {available}")
        
        if available:
            # Test simple generation
            print("🤖 Testing generation...")
            response = client.generate_response("What is 2+2?", "")
            print(f"💬 Response: {response}")
        else:
            print("❌ Service not available")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_minimal()