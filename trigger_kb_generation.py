"""
Trigger Knowledge Base Generation for a project
"""
import requests
import json

# Configuration
BASE_URL = "http://127.0.0.1:5001"
PROJECT_ID = "With a Twist"

# You need to get your Firebase token from the browser
# Open browser console and run: localStorage.getItem('firebaseToken')
TOKEN = input("Paste your Firebase token from browser localStorage: ").strip()

# Make the API call
url = f"{BASE_URL}/api/projects/{PROJECT_ID}/process"
headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

print(f"\n🚀 Triggering Knowledge Base generation for '{PROJECT_ID}'...")
print(f"Endpoint: {url}\n")

try:
    response = requests.post(url, headers=headers)
    
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    if response.status_code == 200:
        print("\n✅ Knowledge Base generation started successfully!")
    else:
        print(f"\n❌ Error: {response.status_code}")
        
except Exception as e:
    print(f"\n❌ Error: {e}")
