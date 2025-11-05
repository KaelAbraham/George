"""Test script for the filesystem server."""
import requests
import os

# Create a dummy file to upload
with open("dummy_manuscript.txt", "w") as f:
    f.write("This is a test manuscript.")

# Test the /upload endpoint
url = "http://127.0.0.1:5001/upload"
with open('dummy_manuscript.txt', 'rb') as f:
    files = {'manuscript': f}
    response = requests.post(url, files=files)

print(response.json())

# Clean up the dummy file
os.remove("dummy_manuscript.txt")
