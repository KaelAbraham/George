"""Test script for the ChromaDB server."""
import requests
import json

BASE_URL = "http://127.0.0.1:5002"

def test_create_collection():
    print("Testing /create_collection...")
    response = requests.post(f"{BASE_URL}/create_collection", json={'collection_name': 'test_collection'})
    print(response.json())
    assert response.status_code == 200

def test_add_chunks():
    print("\nTesting /add_chunks...")
    chunks = [
        {'text': 'This is a test document.', 'id': '1'},
        {'text': 'This is another test document.', 'id': '2'}
    ]
    response = requests.post(f"{BASE_URL}/add_chunks", json={'collection_name': 'test_collection', 'chunks': chunks})
    print(response.json())
    assert response.status_code == 200

def test_query():
    print("\nTesting /query...")
    response = requests.post(f"{BASE_URL}/query", json={'collection_name': 'test_collection', 'query_texts': ['test']})
    print(response.json())
    assert response.status_code == 200

if __name__ == "__main__":
    test_create_collection()
    test_add_chunks()
    test_query()
