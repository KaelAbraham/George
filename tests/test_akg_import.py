import sys
import os
# Add the src directory to the path
sys.path.insert(0, '/app/local_story_ai_1423/src')
def test_akg_import():
    try:
        import akg
        print("AKG module imported successfully")
        print(f"AKG version: {akg.__version__}")
        print(f"Available classes: {akg.__all__}")
        return True
    except ImportError as e:
        print(f"Failed to import AKG module: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False
if __name__ == "__main__":
    test_akg_import()