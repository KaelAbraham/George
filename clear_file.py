#!/usr/bin/env python3
"""
Manual clear script - run this to clear the file from your browser session
"""
import requests

def clear_browser_session():
    """Clear the file from a browser session by testing all possible sessions"""
    print("🧹 Manual File Clear Tool")
    print("=" * 30)
    
    # Try to clear using a fresh session (won't work for browser sessions)
    session1 = requests.Session()
    try:
        result = session1.post('http://localhost:5000/api/file/clear')
        print(f"Fresh session clear: {result.status_code}")
    except:
        print("Could not connect to Flask app")
        return
    
    # The browser maintains its own session cookies, so we can't clear it externally
    # The best we can do is restart the Flask app to clear all sessions
    print("\n💡 To clear the browser session:")
    print("1. Stop the Flask app (Ctrl+C in terminal)")
    print("2. Restart it with: python src\\george\\ui\\app_simple.py")
    print("3. Refresh your browser")
    print("\nOr just load a new file to replace the current one!")

if __name__ == "__main__":
    clear_browser_session()