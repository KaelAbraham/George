#!/usr/bin/env python3
"""
Simple direct test to bypass all browser issues
"""
import requests
import time

def test_complete_workflow():
    """Test the complete workflow step by step"""
    print("🧪 DIRECT WORKFLOW TEST")
    print("=" * 50)
    
    # Use a session to maintain cookies
    session = requests.Session()
    
    try:
        # 1. Load test file
        print("1️⃣ Loading test file...")
        response = session.post('http://localhost:5000/api/file/load-test')
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Success: {data['success']}")
            print(f"   📄 File: {data['info']['filename']}")
            print(f"   📊 Words: {data['info']['word_count']}")
            print(f"   🧠 Entities: {len(data['info']['potential_entities'])}")
        else:
            print(f"   ❌ Failed: {response.status_code}")
            return
        
        # 2. Check if file persists
        print("\n2️⃣ Checking file persistence...")
        response = session.get('http://localhost:5000/api/file/current')
        if response.status_code == 200:
            data = response.json()
            if data['loaded']:
                print(f"   ✅ File loaded: {data['filename']}")
                print(f"   📊 Words: {data['info']['word_count']}")
            else:
                print("   ❌ No file loaded")
                return
        
        # 3. Test chat with context
        print("\n3️⃣ Testing chat with file context...")
        chat_data = {
            'message': 'Who is Elias? Tell me about him.',
            'model': 'gemma:2b'
        }
        response = session.post('http://localhost:5000/api/chat', json=chat_data)
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Chat response length: {len(data['response'])}")
            print(f"   🤖 Response preview: {data['response'][:200]}...")
            
            # Check if the response mentions the file content
            if 'Elias' in data['response']:
                print("   ✅ Response mentions Elias - file context working!")
            else:
                print("   ⚠️ Response doesn't mention Elias - check context")
        else:
            print(f"   ❌ Chat failed: {response.status_code}")
    
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_complete_workflow()