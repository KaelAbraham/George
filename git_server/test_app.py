"""Test script for the git server."""
import requests
import os

BASE_URL = "http://127.0.0.1:5003"
PROJECT_ID = "test_project"

def test_snapshot():
    print("Testing /snapshot...")
    # Create a dummy file to commit
    project_path = os.path.join('git_server', 'projects', PROJECT_ID)
    os.makedirs(project_path, exist_ok=True)
    with open(os.path.join(project_path, "test.txt"), "w") as f:
        f.write("This is a test file.")
        
    response = requests.post(f"{BASE_URL}/snapshot/{PROJECT_ID}")
    print(response.json())
    assert response.status_code == 200

def test_history():
    print("\nTesting /history...")
    response = requests.get(f"{BASE_URL}/history/{PROJECT_ID}")
    print(response.json())
    assert response.status_code == 200

if __name__ == "__main__":
    test_snapshot()
    test_history()
