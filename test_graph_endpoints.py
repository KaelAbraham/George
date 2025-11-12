#!/usr/bin/env python3
"""Test the graph server endpoints."""
import requests
import json
import time

BASE_URL = "http://localhost:5002"
PROJECT_ID = "test_project"

def test_graph_endpoints():
    """Test creating nodes and edges in the graph."""
    
    print("Testing Graph Server Endpoints...")
    print("=" * 50)
    
    # Test 1: Add a node
    print("\n1. Adding node 'Frodo'...")
    node_data = {
        "node_id": "Frodo",
        "type": "character",
        "summary": "A hobbit from the Shire"
    }
    response = requests.post(f"{BASE_URL}/graph/{PROJECT_ID}/node", json=node_data)
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}")
    
    # Test 2: Add another node
    print("\n2. Adding node 'Gandalf'...")
    node_data = {
        "node_id": "Gandalf",
        "type": "character",
        "summary": "A wizard"
    }
    response = requests.post(f"{BASE_URL}/graph/{PROJECT_ID}/node", json=node_data)
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}")
    
    # Test 3: Add an edge (relationship)
    print("\n3. Adding edge 'Frodo' -> 'Gandalf' (KNOWS)...")
    edge_data = {
        "node_from": "Frodo",
        "node_to": "Gandalf",
        "label": "KNOWS"
    }
    response = requests.post(f"{BASE_URL}/graph/{PROJECT_ID}/edge", json=edge_data)
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}")
    
    # Test 4: Get the graph
    print("\n4. Retrieving the graph...")
    response = requests.get(f"{BASE_URL}/graph/{PROJECT_ID}")
    print(f"   Status: {response.status_code}")
    graph_data = response.json()
    print(f"   Nodes: {len(graph_data['nodes'])}")
    print(f"   Edges: {len(graph_data['edges'])}")
    print(f"   Full response: {json.dumps(graph_data, indent=2)}")
    
    print("\n" + "=" * 50)
    print("✅ All tests completed successfully!")

if __name__ == "__main__":
    try:
        test_graph_endpoints()
    except Exception as e:
        print(f"❌ Error: {e}")
