"""Main application file for the ChromaDB server."""
from flask import Flask, request, jsonify
from functools import wraps
import os
import logging
import sys
from pathlib import Path

# Add backend to path to import service_utils
sys.path.insert(0, str(Path(__file__).parent.parent / 'backend'))

from db_manager import ChromaManager, GraphManager
from service_utils import require_internal_token

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- INTERNAL SERVICE TOKEN ---
INTERNAL_TOKEN = os.getenv("INTERNAL_SERVICE_TOKEN", None)

app = Flask(__name__)

# Initialize ChromaDB manager and Graph manager with error handling
try:
    db_manager = ChromaManager()
    logger.info("ChromaDB manager initialized successfully")
except Exception as e:
    print(f"FATAL: Could not initialize ChromaDB: {e}", file=sys.stderr)
    logger.error(f"ChromaDB initialization failed: {e}", exc_info=True)
    db_manager = None

try:
    graph_manager = GraphManager()
    logger.info("Graph manager initialized successfully")
except Exception as e:
    print(f"FATAL: Could not initialize GraphManager: {e}", file=sys.stderr)
    logger.error(f"GraphManager initialization failed: {e}", exc_info=True)
    graph_manager = None

# --- HEALTH CHECK ENDPOINTS ---

@app.route('/health', methods=['GET'])
def health():
    """
    Simple health check endpoint.
    Returns 200 if service is running, regardless of backend status.
    """
    return jsonify({'status': 'ok', 'service': 'chroma_server'}), 200

@app.route('/ready', methods=['GET'])
def readiness():
    """
    Readiness probe - checks if all dependencies are initialized.
    Returns 200 if ready, 503 if not.
    """
    status = {
        'ready': True,
        'db_manager': db_manager is not None and db_manager.client is not None,
        'graph_manager': graph_manager is not None
    }
    
    if not status['db_manager']:
        logger.warning("Readiness check failed: db_manager not initialized")
    if not status['graph_manager']:
        logger.warning("Readiness check failed: graph_manager not initialized")
    
    is_ready = status['db_manager'] and status['graph_manager']
    status_code = 200 if is_ready else 503
    
    return jsonify(status), status_code

@app.route('/create_collection', methods=['POST'])
def create_collection():
    if db_manager is None or db_manager.client is None:
        return jsonify({'error': 'Database service unavailable'}), 503
    
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
    if db_manager is None or db_manager.client is None:
        return jsonify({'error': 'Database service unavailable'}), 503
    
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
    if db_manager is None or db_manager.client is None:
        return jsonify({'error': 'Database service unavailable'}), 503
    
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
    if graph_manager is None:
        return jsonify({'error': 'Graph service unavailable'}), 503
    
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
    if graph_manager is None:
        return jsonify({'error': 'Graph service unavailable'}), 503
    
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
    if graph_manager is None:
        return jsonify({'error': 'Graph service unavailable'}), 503
    
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
    import os
    if os.getenv('FLASK_ENV') == 'development':
        app.run(debug=True, port=6003)
    else:
        print("Use gunicorn for production: gunicorn -w 4 -b 0.0.0.0:6003 chroma_server.app:app")
