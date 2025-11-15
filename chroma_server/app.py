"""Main application file for the ChromaDB server."""
from flask import Flask, request, jsonify
from functools import wraps
import os
import logging
from db_manager import ChromaManager, GraphManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- INTERNAL SERVICE TOKEN ---
INTERNAL_TOKEN = os.getenv("INTERNAL_SERVICE_TOKEN", None)

app = Flask(__name__)

# Initialize ChromaDB manager and Graph manager
db_manager = ChromaManager()
graph_manager = GraphManager()

# --- DECORATOR: Require Internal Service Token ---
def require_internal_token(f):
    """
    Decorator to protect internal service endpoints.
    Checks X-INTERNAL-TOKEN header against INTERNAL_SERVICE_TOKEN env var.
    In dev mode (no token configured), allows all requests.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if INTERNAL_TOKEN is None:
            # Dev mode: allow if not configured
            return f(*args, **kwargs)
        token = request.headers.get("X-INTERNAL-TOKEN")
        if not token or token != INTERNAL_TOKEN:
            logger.warning(f"Unauthorized internal request: missing or invalid token")
            return jsonify({"error": "Forbidden"}), 403
        return f(*args, **kwargs)
    return decorated

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

# ===== Graph Endpoints =====

@app.route('/graph/<project_id>/node', methods=['POST'])
def add_node(project_id):
    """Add a node to the knowledge graph for a project."""
    data = request.get_json()
    node_id = data.get('node_id')
    node_type = data.get('type', 'unknown')
    
    if not node_id:
        return jsonify({'error': 'node_id is required'}), 400
    
    try:
        # Extract attributes (everything except node_id and type)
        attrs = {k: v for k, v in data.items() if k not in ['node_id', 'type']}
        attrs['type'] = node_type
        
        graph_manager.add_node(project_id, node_id, **attrs)
        graph_manager.save_graph(project_id)
        
        return jsonify({'message': f"Node '{node_id}' added to graph for project '{project_id}'"}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/graph/<project_id>/edge', methods=['POST'])
def add_edge(project_id):
    """Add an edge (relationship) to the knowledge graph for a project."""
    data = request.get_json()
    node_from = data.get('node_from')
    node_to = data.get('node_to')
    label = data.get('label', 'related_to')
    
    if not node_from or not node_to:
        return jsonify({'error': 'node_from and node_to are required'}), 400
    
    try:
        # Extract attributes (everything except node_from, node_to, label)
        attrs = {k: v for k, v in data.items() if k not in ['node_from', 'node_to', 'label']}
        attrs['label'] = label
        
        graph_manager.add_edge(project_id, node_from, node_to, **attrs)
        graph_manager.save_graph(project_id)
        
        return jsonify({'message': f"Edge from '{node_from}' to '{node_to}' added to graph"}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/graph/<project_id>', methods=['GET'])
def get_graph(project_id):
    """Get the knowledge graph for a project."""
    try:
        g = graph_manager.get_or_create_graph(project_id)
        
        # Convert graph to JSON-serializable format
        nodes = [{'id': node, **g.nodes[node]} for node in g.nodes()]
        edges = [{'source': u, 'target': v, **g.edges[u, v]} for u, v in g.edges()]
        
        return jsonify({
            'project_id': project_id,
            'nodes': nodes,
            'edges': edges,
            'num_nodes': len(nodes),
            'num_edges': len(edges)
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5002)
