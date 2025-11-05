"""Main application file for the ChromaDB server."""
from flask import Flask, request, jsonify
from db_manager import ChromaManager

app = Flask(__name__)

# Initialize ChromaDB manager
db_manager = ChromaManager()

@app.route('/create_collection', methods=['POST'])
def create_collection():
    data = request.get_json()
    collection_name = data.get('collection_name')
    if not collection_name:
        return jsonify({'error': 'collection_name is required'}), 400
    
    collection = db_manager.get_or_create_collection(collection_name)
    if collection:
        return jsonify({'message': f"Collection '{collection_name}' created or already exists."}), 200
    else:
        return jsonify({'error': f"Failed to create collection '{collection_name}'"}), 500

@app.route('/add_chunks', methods=['POST'])
def add_chunks():
    data = request.get_json()
    collection_name = data.get('collection_name')
    chunks = data.get('chunks')
    if not collection_name or not chunks:
        return jsonify({'error': 'collection_name and chunks are required'}), 400
    
    try:
        texts = [chunk['text'] for chunk in chunks]
        metadatas = [chunk.get('metadata', {}) for chunk in chunks]
        ids = [chunk.get('id') for chunk in chunks]
        
        db_manager.add_texts(collection_name, texts, metadatas, ids)
        return jsonify({'message': f"Added {len(chunks)} chunks to '{collection_name}'"}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/query', methods=['POST'])
def query():
    data = request.get_json()
    collection_name = data.get('collection_name')
    query_texts = data.get('query_texts')
    n_results = data.get('n_results', 5)
    where = data.get('where')
    
    if not collection_name or not query_texts:
        return jsonify({'error': 'collection_name and query_texts are required'}), 400
        
    try:
        results = db_manager.query(collection_name, query_texts, n_results, where)
        return jsonify(results), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5002)
