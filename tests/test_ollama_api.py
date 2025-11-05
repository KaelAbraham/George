#!/usr/bin/env python3
"""
Simple test for Ollama API connectivity
"""

import requests
import json
import time

def test_ollama_api():
    """Test direct connection to Ollama API."""
    print("🔧 Testing Ollama API Connection")
    print("=" * 40)
    
    base_url = "http://localhost:11434"
    
    # Test 1: Check if API is responding
    try:
        print("1. Testing API availability...")
        response = requests.get(f"{base_url}/api/tags", timeout=10)
        if response.status_code == 200:
            print("✅ API is responding")
            models = response.json()
            print(f"   Available models: {len(models.get('models', []))}")
        else:
            print(f"❌ API returned status: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ API connection failed: {e}")
        return False
    
    # Test 2: Simple generation test
    try:
        print("\n2. Testing simple generation...")
        payload = {
            "model": "phi3:instruct",
            "prompt": "Say hello in one sentence.",
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 50
            }
        }
        
        start_time = time.time()
        response = requests.post(
            f"{base_url}/api/generate",
            json=payload,
            timeout=30
        )
        end_time = time.time()
        
        if response.status_code == 200:
            result = response.json()
            generated_text = result.get('response', '').strip()
            print(f"✅ Generation successful!")
            print(f"   Response: {generated_text}")
            print(f"   Time taken: {end_time - start_time:.2f} seconds")
        else:
            print(f"❌ Generation failed: {response.status_code}")
            print(f"   Error: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ Generation timed out (>30 seconds)")
        return False
    except Exception as e:
        print(f"❌ Generation error: {e}")
        return False
    
    print("\n✅ All tests passed!")
    return True

if __name__ == "__main__":
    test_ollama_api()