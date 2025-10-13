"""
Test script to verify that the Flask application can be created and started without errors.
This helps catch any configuration issues early in the development process.
"""
import sys
import os
# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
def test_app_creation():
    try:
        from src.ui.app import create_app
        app = create_app()
        print("✓ Flask application created successfully")
        return True
    except Exception as e:
        print(f"✗ Failed to create Flask application: {e}")
        return False
def test_app_routes():
    try:
        from src.ui.app import create_app
        app = create_app()
        with app.test_client() as client:
            # Test the root route
            response = client.get('/')
            if response.status_code == 200:
                print("✓ Root route accessible")
            else:
                print(f"✗ Root route returned status code {response.status_code}")
                return False
        return True
    except Exception as e:
        print(f"✗ Failed to test app routes: {e}")
        return False
if __name__ == "__main__":
    print("Testing Flask application...")
    print("=" * 40)
    results = []
    results.append(test_app_creation())
    results.append(test_app_routes())
    print("=" * 40)
    if all(results):
        print("✓ Flask application tests passed!")
        print("The application is ready to be started with 'python -m src.ui.app'")
    else:
        print("✗ Some Flask application tests failed. Check the errors above.")