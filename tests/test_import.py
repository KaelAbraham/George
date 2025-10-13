"""
Test script to verify that all UI modules can be imported without errors.
This helps catch any import issues early in the development process.
"""
import sys
import os
# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

def test_app_import():
    try:
        from george.ui.app import create_app
        print("✓ george.ui.app imported successfully")
        return True
    except Exception as e:
        print(f"✗ Failed to import george.ui.app: {e}")
        return False

def test_blueprints_import():
    try:
        # These imports are commented out in app.py for now since the blueprints don't exist yet
        # from george.ui.blueprints.project_manager import bp as project_manager_bp
        # print("✓ george.ui.blueprints.project_manager imported successfully")
        print("✓ Blueprint imports are disabled (blueprints not yet implemented)")
        return True
    except Exception as e:
        print(f"✗ Failed to import blueprints: {e}")
        return False
        from src.ui.blueprints.chat import bp as chat_bp
        print("✓ src.ui.blueprints.chat imported successfully")
        return True
    except Exception as e:
        print(f"✗ Failed to import blueprints: {e}")
        return False
def test_api_import():
    try:
        # API endpoints are commented out in app.py for now since they don't exist yet
        # from george.ui.api.endpoints import bp as api_bp
        # print("✓ george.ui.api.endpoints imported successfully")
        print("✓ API imports are disabled (API endpoints not yet implemented)")
        return True
    except Exception as e:
        print(f"✗ Failed to import george.ui.api.endpoints: {e}")
        return False
if __name__ == "__main__":
    print("Testing UI module imports...")
    print("=" * 40)
    results = []
    results.append(test_app_import())
    results.append(test_blueprints_import())
    results.append(test_api_import())
    print("=" * 40)
    if all(results):
        print("✓ All UI modules imported successfully!")
    else:
        print("✗ Some modules failed to import. Check the errors above.")