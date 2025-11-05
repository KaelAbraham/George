"""Main AI-Router service for George.
This is the central orchestration service that the front-end communicates with.
It does NOT touch files or databases directly; it only orchestrates the "Hands" services.
"""
import os
import sys
import logging
from pathlib import Path
from flask import Flask, request, jsonify
import requests
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "george"))

# Load environment variables
load_dotenv(Path(__file__).parent.parent / '.env')

# Import LLM integration
try:
    from llm_integration import create_george_ai
    LLM_AVAILABLE = True
except ImportError as e:
    logging.error(f"Failed to import llm_integration: {e}")
    LLM_AVAILABLE = False

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Service URLs (configurable via environment variables)
FILESYSTEM_SERVER_URL = os.getenv('FILESYSTEM_SERVER_URL', 'http://localhost:5001')
CHROMA_SERVER_URL = os.getenv('CHROMA_SERVER_URL', 'http://localhost:5002')
GIT_SERVER_URL = os.getenv('GIT_SERVER_URL', 'http://localhost:5003')

# Load Georgeification constitution
GEORGE_CONSTITUTION = ""
try:
    constitution_path = Path(__file__).parent.parent / "src" / "george" / "prompts" / "george_operational_protocol.txt"
    if constitution_path.exists():
        with open(constitution_path, 'r', encoding='utf-8') as f:
            GEORGE_CONSTITUTION = f.read()
        logger.info("Successfully loaded Georgeification constitution.")
    else:
        logger.warning(f"Constitution file not found at {constitution_path}")
        GEORGE_CONSTITUTION = """You are George, an AI writing assistant for authors. 
You will NEVER write, rewrite, or suggest specific language for the user's manuscript.
Your role is to provide analysis, feedback, and guidance only.
Be direct, concise, and avoid meta-language."""
except Exception as e:
    logger.error(f"Error loading constitution: {e}")
    GEORGE_CONSTITUTION = """You are George, an AI writing assistant for authors. 
You will NEVER write, rewrite, or suggest specific language for the user's manuscript.
Your role is to provide analysis, feedback, and guidance only."""

# Initialize LLM client for intent analysis and response generation
INTENT_LLM = None
RESPONSE_LLM = None

if LLM_AVAILABLE:
    try:
        # Use Gemini Flash Lite for fast intent analysis
        INTENT_LLM = create_george_ai(model="gemini-flash-lite", use_cloud=True)
        # Use Gemini Flash Lite for response generation (stateless, fast)
        RESPONSE_LLM = create_george_ai(model="gemini-flash-lite", use_cloud=True)
        logger.info("LLM clients initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize LLM clients: {e}")
        LLM_AVAILABLE = False


def analyze_intent(user_query: str, project_id: str) -> dict:
    """
    Analyze user intent using a fast LLM call (Gemini Flash Lite).
    
    Returns:
        dict with 'intent' field: 'Fact-Checking', 'Craft', or 'Support'
    """
    if not INTENT_LLM:
        logger.warning("Intent LLM not available, defaulting to 'Craft'")
        return {'intent': 'Craft'}
    
    intent_prompt = f"""Analyze the following user query and classify the intent into one of these categories:

1. Fact-Checking: Questions about facts, details, or consistency in the story (e.g., "What color are Edie's eyes?", "Where did Hugh grow up?")
2. Craft: Questions about writing technique, structure, pacing, character development (e.g., "How can I improve this scene?", "Is the pacing too fast?")
3. Support: Emotional support, frustration, or meta-questions about using the tool (e.g., "I'm stuck", "Help me with this problem")

User Query: "{user_query}"

Respond with ONLY a JSON object: {{"intent": "Fact-Checking"|"Craft"|"Support"}}"""

    try:
        result = INTENT_LLM.chat(intent_prompt, project_context="", temperature=0.0)
        if result.get('success'):
            import json
            response_text = result.get('response', '{}')
            # Try to extract JSON from response
            try:
                # Look for JSON in the response
                if '{' in response_text:
                    start = response_text.index('{')
                    end = response_text.rindex('}') + 1
                    json_str = response_text[start:end]
                    intent_result = json.loads(json_str)
                    return intent_result
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse intent JSON: {e}, response: {response_text}")
        # Fallback logic based on keywords
        query_lower = user_query.lower()
        if any(word in query_lower for word in ['what', 'who', 'where', 'when', 'color', 'age', 'name']):
            return {'intent': 'Fact-Checking'}
        elif any(word in query_lower for word in ['stuck', 'frustrated', 'help', 'how do']):
            return {'intent': 'Support'}
        else:
            return {'intent': 'Craft'}
    except Exception as e:
        logger.error(f"Error analyzing intent: {e}")
        return {'intent': 'Craft'}


def query_knowledge_base(user_query: str, project_id: str, intent: str, n_results: int = 5) -> list:
    """
    Query the knowledge base via HTTP call to chroma-core/mcp-server.
    
    Returns:
        list of relevant context chunks
    """
    try:
        # Use project_id as collection_name
        collection_name = project_id if project_id else "default"
        
        query_payload = {
            'collection_name': collection_name,
            'query_texts': [user_query],
            'n_results': n_results,
            'where': {}  # Optional filter
        }
        
        response = requests.post(
            f"{CHROMA_SERVER_URL}/query",
            json=query_payload,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            # Extract documents from ChromaDB response
            documents = result.get('documents', [])
            if documents and len(documents) > 0:
                # ChromaDB returns lists of lists, get first query's results
                return documents[0] if isinstance(documents[0], list) else documents
            return []
        else:
            logger.warning(f"ChromaDB query failed: {response.status_code} - {response.text}")
            return []
    except requests.exceptions.RequestException as e:
        logger.error(f"Error querying knowledge base: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error in query_knowledge_base: {e}")
        return []


def assemble_georgeified_prompt(user_query: str, context_chunks: list, intent: str) -> str:
    """
    Assemble the "Georgeified" prompt with constitution and context.
    This is the critical step that enforces the core philosophy.
    """
    # Build context section from retrieved chunks
    context_text = ""
    if context_chunks:
        context_text = "\n\n--- Relevant Context from Knowledge Base ---\n"
        for i, chunk in enumerate(context_chunks[:5], 1):  # Limit to top 5 chunks
            context_text += f"\n[Context {i}]\n{chunk}\n"
        context_text += "\n--- End Context ---\n"
    
    # Assemble the full prompt with constitution
    georgeified_prompt = f"""{GEORGE_CONSTITUTION}

{context_text}

User Query: "{user_query}"

Intent Category: {intent}

Based on the context provided above (if any), answer the user's query following the George Operational Protocol.
Remember: You will NEVER write, rewrite, or suggest specific language for the user's manuscript.
Provide analysis, feedback, and guidance only. Be direct and concise."""

    return georgeified_prompt


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'llm_available': LLM_AVAILABLE and INTENT_LLM is not None and RESPONSE_LLM is not None,
        'llm_initialized': INTENT_LLM is not None and RESPONSE_LLM is not None,
        'services': {
            'filesystem_server': FILESYSTEM_SERVER_URL,
            'chroma_server': CHROMA_SERVER_URL,
            'git_server': GIT_SERVER_URL
        }
    }), 200


@app.route('/chat', methods=['POST'])
def chat():
    """
    Main chat endpoint - implements the stateless chat loop.
    
    Expected JSON payload:
    {
        "message": "user's query",
        "project_id": "project_identifier"
    }
    
    Returns:
    {
        "response": "AI response text",
        "intent": "Fact-Checking|Craft|Support",
        "context_used": true/false,
        "model": "model_name"
    }
    """
    if not LLM_AVAILABLE or not RESPONSE_LLM:
        return jsonify({
            'error': 'LLM service not available. Please check configuration.'
        }), 500
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON payload provided'}), 400
    
    user_query = data.get('message', '').strip()
    project_id = data.get('project_id', '')
    
    if not user_query:
        return jsonify({'error': 'No message provided'}), 400
    
    try:
        # Step 1: Analyze Intent (fast LLM call)
        logger.info(f"Analyzing intent for query: {user_query[:50]}...")
        intent_result = analyze_intent(user_query, project_id)
        intent = intent_result.get('intent', 'Craft')
        logger.info(f"Intent classified as: {intent}")
        
        # Step 2: Query Knowledge Base (HTTP call to chroma-server)
        context_chunks = []
        context_used = False
        if project_id:
            logger.info(f"Querying knowledge base for project: {project_id}")
            context_chunks = query_knowledge_base(user_query, project_id, intent)
            context_used = len(context_chunks) > 0
            logger.info(f"Retrieved {len(context_chunks)} context chunks")
        
        # Step 3: Assemble Georgeified Prompt
        georgeified_prompt = assemble_georgeified_prompt(user_query, context_chunks, intent)
        
        # Step 4: Get Answer (second LLM call)
        logger.info("Generating response with Georgeified prompt...")
        result = RESPONSE_LLM.chat(
            georgeified_prompt,
            project_context="",  # Context is already in the prompt
            temperature=0.7
        )
        
        if result.get('success'):
            response_text = result.get('response', '')
            model_name = result.get('model', 'gemini-flash-lite')
            
            return jsonify({
                'response': response_text,
                'intent': intent,
                'context_used': context_used,
                'context_chunks_count': len(context_chunks),
                'model': model_name,
                'success': True
            }), 200
        else:
            error_msg = result.get('error', 'Unknown error generating response')
            logger.error(f"LLM response generation failed: {error_msg}")
            return jsonify({
                'error': f'Failed to generate response: {error_msg}',
                'success': False
            }), 500
            
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}", exc_info=True)
        return jsonify({
            'error': f'Internal server error: {str(e)}',
            'success': False
        }), 500


if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🤖 George AI-Router Service")
    logger.info("=" * 60)
    logger.info(f"Filesystem Server: {FILESYSTEM_SERVER_URL}")
    logger.info(f"Chroma Server: {CHROMA_SERVER_URL}")
    logger.info(f"Git Server: {GIT_SERVER_URL}")
    logger.info(f"LLM Available: {LLM_AVAILABLE}")
    logger.info("=" * 60)
    logger.info("Starting server on http://0.0.0.0:5000")
    logger.info("Main endpoint: POST /chat")
    logger.info("=" * 60)
    
    app.run(host='0.0.0.0', port=5000, debug=True)
