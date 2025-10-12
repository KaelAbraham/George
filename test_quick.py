#!/usr/bin/env python3
"""
Quick API test using requests directly
"""

import requests
import json

def quick_test():
    """Quick test of Ollama API."""
    print("🚀 Quick Phi-3 Test")
    
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": "phi3:instruct",
        "prompt": "You are George, a writing assistant. Answer briefly: What makes a good fantasy character?",
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 100  # Short response
        }
    }
    
    try:
        print("Sending request...")
        response = requests.post(url, json=payload, timeout=45)
        
        if response.status_code == 200:
            result = response.json()
            text = result.get('response', '').strip()
            print(f"✅ Success: {text}")
        else:
            print(f"❌ Error: {response.status_code}")
            
    except requests.exceptions.Timeout:
        print("❌ Timeout occurred")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    quick_test()