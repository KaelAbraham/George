#!/usr/bin/env python3
"""
Test file processing functionality directly
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src' / 'george' / 'ui'))

def test_file_processing():
    """Test the file processing functions directly."""
    print("🧪 Testing File Processing")
    print("=" * 30)
    
    # Import the functions from the Flask app
    try:
        from app_simple import read_file_content, extract_basic_info
        print("✅ Imported functions successfully")
    except Exception as e:
        print(f"❌ Import failed: {e}")
        return
    
    # Test file processing
    file_path = "data/uploads/Elias.txt"
    
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return
    
    print(f"✅ File exists: {file_path}")
    
    try:
        # Test reading content
        content = read_file_content(file_path)
        print(f"✅ Read content: {len(content)} characters")
        print(f"Preview: {content[:200]}...")
        
        # Test extracting info
        file_info = extract_basic_info(content, "Elias.txt")
        print(f"✅ Extracted info: {file_info}")
        
        print("🎉 File processing test successful!")
        
    except Exception as e:
        print(f"❌ Processing failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_file_processing()