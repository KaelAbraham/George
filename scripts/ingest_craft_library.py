import os
import sys
import requests
import json
import dataclasses
from pathlib import Path
from typing import List

# --- Path Setup ---
# This allows the script to import the services from the filesystem_server
SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
FILESYSTEM_SERVER_DIR = ROOT_DIR / "filesystem_server"
sys.path.insert(0, str(FILESYSTEM_SERVER_DIR))

try:
    # Import the exact parser and chunker you've already built
    from services import DocumentParser, TextChunker, TextChunk
    print("✅ Successfully imported services from filesystem_server.")
except ImportError as e:
    print(f"❌ Failed to import services: {e}")
    print("Please ensure 'filesystem_server/services.py' exists.")
    sys.exit(1)

# --- Configuration ---
CRAFT_LIBRARY_PATH = ROOT_DIR / "data" / "craft_library"
COLLECTION_NAME = "george_craft_library"
CHROMA_SERVER_URL = "http://localhost:5002" # Assumes chroma_server is running on port 5002

def main():
    print(f"--- Starting Craft Library Ingestion ---")
    print(f"Targeting Chroma collection: '{COLLECTION_NAME}'")
    
    # --- 1. Ensure Collection Exists ---
    try:
        print(f"Checking for collection '{COLLECTION_NAME}' at {CHROMA_SERVER_URL}...")
        res_create = requests.post(
            f"{CHROMA_SERVER_URL}/create_collection",
            json={"collection_name": COLLECTION_NAME}
        )
        res_create.raise_for_status()
        print(f"Chroma response: {res_create.json().get('message')}")
        
    except requests.exceptions.RequestException as e:
        print(f"❌ ERROR: Could not connect to chroma_server at {CHROMA_SERVER_URL}.")
        print("Please ensure the chroma_server is running.")
        return

    # --- 2. Initialize Parser and Chunker ---
    parser = DocumentParser()
    chunker = TextChunker(chunk_size=500, chunk_overlap=50) # Use the same settings as your filesystem_server
    
    all_chunks_for_ingestion = []
    
    # --- 3. Parse and Chunk All Guides ---
    print(f"Scanning for guides in: {CRAFT_LIBRARY_PATH}")
    if not os.path.isdir(CRAFT_LIBRARY_PATH):
        print(f"❌ ERROR: Directory not found: {CRAFT_LIBRARY_PATH}")
        return

    for filename in os.listdir(CRAFT_LIBRARY_PATH):
        if not (filename.endswith(".txt") or filename.endswith(".md")):
            continue
            
        file_path = CRAFT_LIBRARY_PATH / filename
        print(f"Processing guide: {filename}...")
        
        try:
            # Parse the file content
            parsed_data = parser.parse(str(file_path))
            content = parsed_data.get('content')
            
            # Chunk the content
            chunks = chunker.chunk_text(content, source_file=filename)
            
            # CRITICAL: Add the 'source_file' from the chunk object
            # into the metadata for ChromaDB. This is how the AI
            # will cite its sources.
            for chunk in chunks:
                chunk_data = dataclasses.asdict(chunk)
                # We create a new 'metadata' dict for Chroma
                # and ensure the source_file is in it.
                chroma_metadata = {
                    "source_file": chunk.source_file,
                    "chapter": chunk.chapter,
                    "paragraph_start": chunk.paragraph_start
                }
                # The 'chunk_data' now has 'text' and 'metadata'
                all_chunks_for_ingestion.append({
                    "text": chunk.text,
                    "metadata": chroma_metadata,
                    "id": f"craft_{filename}_{len(all_chunks_for_ingestion)}" # Create a unique ID
                })
                
            print(f"  > Generated {len(chunks)} chunks for {filename}.")
            
        except Exception as e:
            print(f"  > ❌ Failed to process {filename}: {e}")

    # --- 4. Send All Chunks to Chroma Server in One Batch ---
    if not all_chunks_for_ingestion:
        print("No chunks to ingest. Exiting.")
        return

    print(f"Sending {len(all_chunks_for_ingestion)} total chunks to chroma_server...")
    
    try:
        payload = {
            "collection_name": COLLECTION_NAME,
            "chunks": all_chunks_for_ingestion # This list contains dicts with 'text', 'metadata', and 'id'
        }
        
        # Note: The 'add_chunks' endpoint in your code might need a small tweak
        # to accept 'text', 'metadata', and 'id' keys instead of 'chunk' objects.
        # I've formatted the payload to match what your app.py expects.
        
        # This one call sends everything to be embedded and stored.
        res_add = requests.post(
            f"{CHROMA_SERVER_URL}/add_chunks",
            json=payload,
            timeout=60
        )
        res_add.raise_for_status()
        print(f"✅ Success! {res_add.json().get('message')}")
        
    except requests.exceptions.RequestException as e:
        print(f"❌ ERROR: Failed to add chunks to chroma_server: {e}")
        if e.response:
            print(f"Server response: {e.response.text}")

if __name__ == "__main__":
    main()