from flask import Flask, request, jsonify
from api_clients import ExternalAPIs
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
apis = ExternalAPIs()

@app.route('/lookup', methods=['GET'])
def lookup():
    """
    Main endpoint for factual/definition lookups.
    Calls Wikipedia and Wiktionary.
    """
    query = request.args.get('q')
    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400
    
    logging.info(f"External lookup for: {query}")
    
    # Get context from both sources
    wiki_context = apis.get_wikipedia(query)
    wiktionary_context = apis.get_wiktionary(query)
    
    combined_context = (wiki_context + wiktionary_context).strip()
    
    if not combined_context:
        return jsonify({"context": "No external data found.", "source": "none"}), 404
        
    return jsonify({"context": combined_context, "source": "wikipedia/wiktionary"})

@app.route('/thesaurus', methods=['GET'])
def thesaurus():
    """
    Main endpoint for creative thesaurus lookups.
    Calls Datamuse.
    """
    query = request.args.get('q')
    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400
        
    logging.info(f"Thesaurus lookup for: {query}")
    
    # Get both rhymes and synonyms for a richer context
    rhyme_context = apis.get_datamuse_rhymes(query)
    synonym_context = apis.get_datamuse_synonyms(query)
    
    combined_context = (rhyme_context + synonym_context).strip()

    if not combined_context:
        return jsonify({"context": "No thesaurus data found.", "source": "none"}), 404

    return jsonify({"context": combined_context, "source": "datamuse"})

if __name__ == '__main__':
    import os
    if os.getenv('FLASK_ENV') == 'development':
        # This server will run on a different port, e.g., 6006
        print("--- External Data Server (The Librarian) ---")
        print("Running on http://localhost:6006")
        app.run(debug=True, port=6006)
    else:
        print("Use gunicorn for production: gunicorn -w 4 -b 0.0.0.0:6006 external_data_server.app:app")