"""
George Backend - AI Router with Cost Governor & Graceful Degradation
Intelligent routing with cost awareness, role-based access, and smart model selection.
"""
import os
import requests
import logging
import json
import uuid
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS

# Add the 'src' directory to the Python path
project_root = Path(__file__).parent.parent
src_path = project_root / 'src'
backend_path = project_root / 'backend'
import sys
sys.path.insert(0, str(src_path))
sys.path.insert(0, str(backend_path))

# Import local modules
from llm_client import GeminiClient
from job_manager import JobManager
from session_manager import SessionManager

# Load environment variables from project root
load_dotenv(dotenv_path=project_root / '.env')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize global JobManager instance
job_manager = JobManager(db_path="data/jobs.db")

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# --- Service URLs ---
AUTH_SERVER_URL = os.environ.get("AUTH_SERVER_URL", "http://localhost:5005")
BILLING_SERVER_URL = os.environ.get("BILLING_SERVER_URL", "http://localhost:5004")
CHROMA_SERVER_URL = os.environ.get("CHROMA_SERVER_URL", "http://localhost:5002")

# --- Constants ---
PRO_MODEL_THRESHOLD = 0.50  # 50 cents minimum balance to use Pro model
FLASH_MODEL = "gemini-1.5-flash-latest"
PRO_MODEL = "gemini-1.5-pro-latest"

# --- Initialize Clients & Managers ---
try:
    # Multiple clients for different routing tiers
    triage_client = GeminiClient(model=FLASH_MODEL)
    answer_client_flash = GeminiClient(model=FLASH_MODEL)
    answer_client_pro = GeminiClient(model=PRO_MODEL)
    polish_client = GeminiClient(model=FLASH_MODEL)
    
    session_manager = SessionManager()
    
    logger.info("✅ All AI clients initialized successfully.")
except Exception as e:
    logger.critical(f"❌ Failed to initialize clients: {e}", exc_info=True)

# --- Prompt Templates ---
GEORGE_CONSTITUTION = """You are George, a sophisticated writing support agent.
Your role is to help writers through diagnostic analysis, not co-writing.
Be insightful, encouraging, and grounded in the text provided."""

AI_ROUTER_PROMPT_v4 = """Analyze this user query and respond with valid JSON only:
{
    "intent": "craft_support" | "creative_task" | "emotional_support" | "complex_analysis",
    "knowledge_source": "PROJECT_KB" | "CAUDEX_SUPPORT_KB" | "NONE",
    "requires_memory": true | false,
    "explanation": "brief reasoning"
}

User Query: {user_query}
Project ID: {project_id}"""

COREF_RESOLUTION_PROMPT = """Rewrite the user query for clarity, resolving pronouns and implicit references.
Keep the rewritten query concise and self-contained.

Chat History:
{chat_history}

Original Query: {user_query}

Rewritten Query:"""

POLISH_PROMPT_TEMPLATE = """You are George, a warm and insightful writing support agent.
Rephrase the following response to be natural, helpful, and encouraging.
{downgrade_notice}

Draft Response:
{draft_answer}

Polished Response:"""


# --- Helper Functions ---

def _get_user_from_request(request) -> Optional[Dict[str, Any]]:
    """Verify user token via Auth Server."""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return None
    try:
        resp = requests.post(
            f"{AUTH_SERVER_URL}/verify_token",
            headers={"Authorization": auth_header},
            timeout=5
        )
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception as e:
        logger.error(f"Auth verification failed: {e}")
        return None


def get_user_balance(user_id: str) -> float:
    """Fetch user's API pool balance from Billing Server."""
    try:
        resp = requests.get(
            f"{BILLING_SERVER_URL}/balance/{user_id}",
            timeout=5
        )
        if resp.status_code == 200:
            return float(resp.json().get('balance', 0.0))
    except Exception as e:
        logger.error(f"Failed to get balance for {user_id}: {e}")
    return 0.0


def deduct_cost(user_id: str, job_id: str, cost: float, description: str):
    """Log transaction in Billing Server."""
    try:
        requests.post(
            f"{BILLING_SERVER_URL}/deduct",
            json={
                "user_id": user_id,
                "cost": cost,
                "job_id": job_id,
                "description": description
            },
            timeout=5
        )
    except Exception as e:
        logger.error(f"Failed to deduct cost for {user_id}: {e}")


def get_triage_data(user_query: str, project_id: str) -> Dict[str, Any]:
    """CALL 1: Triage query for intent and knowledge source."""
    prompt = AI_ROUTER_PROMPT_v4.format(
        user_query=user_query,
        project_id=project_id
    )
    result = triage_client.chat(prompt)
    try:
        data = json.loads(result['response'])
        return data
    except Exception as e:
        logger.error(f"Triage parse failed: {e}. Defaulting to craft support.")
        return {
            "intent": "craft_support",
            "knowledge_source": "CAUDEX_SUPPORT_KB",
            "requires_memory": False,
            "explanation": "Parse error - safe default"
        }


def resolve_memory(triage_data: Dict, user_id: str, project_id: str) -> Tuple[str, str]:
    """CALL 1.5: Handle memory & coreference resolution if needed."""
    user_query = triage_data.get('original_query', '')
    
    if not triage_data.get('requires_memory', False):
        return user_query, ""  # No rewrite needed

    logger.info(f"Query requires memory. Fetching history for project={project_id}")
    
    # Fetch conversation history from session manager
    history_list = session_manager.get_recent_history(project_id, user_id)
    chat_history_str = session_manager.format_history_for_prompt(history_list)
    
    # Rewrite query with triage client (cheapest model)
    rewrite_prompt = COREF_RESOLUTION_PROMPT.format(
        chat_history=chat_history_str,
        user_query=user_query
    )
    result = triage_client.chat(rewrite_prompt)
    
    rewritten_query = result['response'].strip()
    logger.info(f"Query rewritten: '{user_query[:50]}...' -> '{rewritten_query[:50]}...'")
    
    return rewritten_query, chat_history_str


def get_chroma_context(query: str, collection_name: str) -> str:
    """Fetch RAG context from Chroma Server."""
    if not collection_name or collection_name == "NONE":
        return ""
    
    try:
        resp = requests.post(
            f"{CHROMA_SERVER_URL}/query",
            json={
                "collection_name": collection_name,
                "query_texts": [query],
                "n_results": 5
            },
            timeout=10
        )
        if resp.status_code == 200:
            results = resp.json()
            docs = results.get('documents', [[]])[0]
            metadatas = results.get('metadatas', [[]])[0]
            context_str = "\n\n".join(
                f"[Source: {meta.get('source_file', 'Unknown')}]\n{doc}"
                for doc, meta in zip(docs, metadatas)
            )
            return context_str
    except Exception as e:
        logger.error(f"Chroma query failed: {e}")
    
    return ""


# --- Health Check ---

@app.route('/api/status', methods=['GET'])
def api_status():
    """Health check endpoint."""
    return jsonify({
        'status': 'running',
        'service': 'George Backend - AI Router',
        'version': '2.0'
    })


# --- Main Chat Endpoint ---

@app.route('/chat', methods=['POST'])
def chat():
    """
    Main stateless chat endpoint with 3-call AI routing loop.
    
    Flow:
    1. TRIAGE: Classify intent & knowledge source (Flash - cheapest)
    2. MEMORY: Resolve coreference if needed (Flash)
    3. RESOURCE GATHERING: Fetch RAG context from Chroma
    4. EXECUTION: Generate answer (Flash or Pro based on cost governor)
    5. POLISH: "Georgeify" response (Flash)
    """
    
    # --- AUTHENTICATION (The Gatekeeper) ---
    auth_data = _get_user_from_request(request)
    if not auth_data:
        return jsonify({"error": "Invalid or missing authentication token"}), 401
    
    user_id = auth_data.get('user_id')
    user_role = auth_data.get('role', 'guest')
    
    if not user_id:
        return jsonify({"error": "User ID not found in auth response"}), 401
    
    # Parse request
    data = request.get_json()
    user_query = data.get('query', '').strip()
    project_id = data.get('project_id', '').strip()
    
    if not user_query or not project_id:
        return jsonify({"error": "query and project_id are required"}), 400
    
    try:
        # --- CALL 1: TRIAGE ---
        logger.info(f"[TRIAGE] user={user_id} query='{user_query[:50]}...'")
        triage_data = get_triage_data(user_query, project_id)
        triage_data['original_query'] = user_query
        intent = triage_data.get('intent', 'craft_support')
        
        # --- GUARDRAILS ---
        if intent == "creative_task":
            logger.info(f"[GUARDRAIL] Creative task blocked for user {user_id}")
            return jsonify({
                "response": "I see you're working on a creative task! My role is to be your diagnostic partner, not a co-writer. If you write a draft, I'd be happy to analyze it for you.",
                "intent": "creative_task"
            }), 200
        
        if intent == "emotional_support":
            logger.info(f"[GUARDRAIL] Emotional support fallback for user {user_id}")
            return jsonify({
                "response": "It sounds like you're stuck. That's a normal part of the creative process! Take a short break, or try approaching the scene from a different character's perspective.",
                "intent": "emotional_support"
            }), 200

        # --- CALL 1.5: MEMORY & REWRITE ---
        rewritten_query, chat_history_str = resolve_memory(triage_data, user_id, project_id)

        # --- RESOURCE GATHERING ---
        knowledge_source = triage_data.get('knowledge_source', 'NONE')
        kb_name = ""
        
        if knowledge_source == "PROJECT_KB":
            kb_name = f"project_{project_id}"
        elif knowledge_source == "CAUDEX_SUPPORT_KB":
            kb_name = "george_craft_library"
        
        context_str = get_chroma_context(rewritten_query, kb_name)
        logger.info(f"[RAG] Retrieved {len(context_str)} chars from {knowledge_source}")

        # --- CALL 2: EXECUTION WITH COST GOVERNOR ---
        
        # 1. Check Balance
        user_balance = get_user_balance(user_id)
        logger.info(f"[COST_GOVERNOR] user={user_id} balance=${user_balance:.2f} role={user_role}")
        
        # 2. Select Model (Governor Logic)
        model_to_use = answer_client_flash
        downgrade_flag = False
        selected_model_name = FLASH_MODEL
        
        if intent == 'complex_analysis' and user_role == 'admin':
            # Admins can use Pro if they have sufficient balance
            if user_balance >= PRO_MODEL_THRESHOLD:
                model_to_use = answer_client_pro
                selected_model_name = PRO_MODEL
                logger.info(f"[MODEL_SELECT] Using PRO model (balance: ${user_balance:.2f})")
            else:
                downgrade_flag = True
                logger.warning(f"[MODEL_SELECT] Downgrading to FLASH (insufficient balance: ${user_balance:.2f})")
        
        elif user_role == 'guest':
            # Guests always use Flash (cost-aware)
            logger.info(f"[MODEL_SELECT] Guest user restricted to FLASH model")
        
        # 3. Assemble Main Prompt
        main_prompt = f"""{GEORGE_CONSTITUTION}

CONVERSATION HISTORY:
{chat_history_str}

RETRIEVED CONTEXT:
{context_str}

USER QUERY:
{rewritten_query}

Based only on the CONVERSATION HISTORY and RETRIEVED CONTEXT, provide a thoughtful response."""
        
        # 4. Get Draft Answer
        logger.info(f"[EXECUTION] Calling {selected_model_name} for response generation")
        result_dict = model_to_use.chat(main_prompt)
        draft_answer = result_dict['response']
        call_cost = result_dict.get('cost', 0.0)
        
        logger.info(f"[EXECUTION] Response received | cost=${call_cost:.6f}")

        # 5. Report Cost to Billing Server
        if call_cost > 0:
            job_id = f"chat-{uuid.uuid4()}"
            deduct_cost(user_id, job_id, call_cost, f"Chat: {intent} ({selected_model_name})")

        # --- CALL 3: GEORGEIFICATION POLISH ---
        
        downgrade_notice = ""
        if downgrade_flag:
            downgrade_notice = (
                "\n\nIMPORTANT: The user has limited credit. Add a gentle, friendly upsell after the response:\n"
                "'This is a complex question that would benefit from deeper analysis. "
                "A quick $5 top-up would let me engage my advanced reasoning module for an even better response!'"
            )
        
        polish_prompt = POLISH_PROMPT_TEMPLATE.format(
            downgrade_notice=downgrade_notice,
            draft_answer=draft_answer
        )
        
        logger.info("[POLISH] Calling Flash model for response polishing")
        polish_result = polish_client.chat(polish_prompt)
        final_answer = polish_result['response']
        polish_cost = polish_result.get('cost', 0.0)
        
        if polish_cost > 0:
            deduct_cost(user_id, f"chat-{uuid.uuid4()}", polish_cost, "Polish (Flash)")

        # --- SAVE & RESPOND ---
        session_manager.add_turn(project_id, user_id, user_query, final_answer)
        
        final_balance = get_user_balance(user_id)
        total_cost = call_cost + polish_cost
        
        logger.info(f"[RESPONSE] user={user_id} intent={intent} cost=${total_cost:.6f} balance=${final_balance:.2f}")
        
        return jsonify({
            "response": final_answer,
            "intent": intent,
            "cost": round(total_cost, 6),
            "model_used": selected_model_name,
            "downgraded": downgrade_flag,
            "balance_remaining": round(final_balance, 2),
            "balance_before": round(user_balance, 2)
        }), 200

    except Exception as e:
        logger.error(f"[CRITICAL] Unhandled error in /chat: {e}", exc_info=True)
        return jsonify({"error": "An internal server error occurred."}), 500


# --- Job Endpoints (for async operations) ---

@app.route('/jobs/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """Get the status of a specific job."""
    job = job_manager.get_job_status(job_id)
    if job is None:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(job)


@app.route('/project/<project_id>/jobs', methods=['GET'])
def get_all_project_jobs(project_id):
    """Get all jobs for a specific project."""
    jobs = job_manager.get_jobs_for_project(project_id)
    return jsonify(jobs)


def _run_wiki_generation_task(job_id, project_id, user_id):
    """Background task for wiki generation."""
    try:
        job_manager.update_job_status(job_id, status='running', progress=10, message='Initializing wiki generation...')
        
        job_manager.update_job_status(job_id, status='running', progress=50, message='Generating wiki content...')
        
        # Placeholder result
        result = {
            "files_created": 20,
            "graph_nodes": 150,
            "wiki_url": f"/project/{project_id}/wiki"
        }
        
        job_manager.update_job_status(
            job_id,
            status='completed',
            progress=100,
            message='Wiki generation complete!',
            result=result
        )
        
    except Exception as e:
        logger.error(f"Wiki generation failed: {e}", exc_info=True)
        job_manager.update_job_status(
            job_id,
            status='failed',
            progress=0,
            message=f'Error: {str(e)}'
        )


@app.route('/project/<project_id>/generate_wiki', methods=['POST'])
def generate_wiki(project_id):
    """Start asynchronous wiki generation for a project."""
    try:
        auth_data = _get_user_from_request(request)
        if not auth_data:
            return jsonify({"error": "Unauthorized"}), 401
        
        user_id = auth_data.get('user_id', 'anonymous')
        
        # 1. Create job receipt
        job_id = job_manager.create_job(
            project_id=project_id,
            user_id=user_id,
            job_type="wiki_generation"
        )
        
        # 2. Start background task
        job_manager.run_async(
            job_id,
            _run_wiki_generation_task,
            job_id,
            project_id,
            user_id
        )
        
        # 3. Return 202 Accepted
        return jsonify({
            "message": "Wiki generation has started.",
            "job_id": job_id,
            "status_url": f"/jobs/{job_id}"
        }), 202
        
    except Exception as e:
        logger.error(f"Wiki generation request failed: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    """
    George Backend - AI Router with Cost Governor
    
    Environment Variables Required:
    - GEMINI_API_KEY: Google Gemini API key
    - AUTH_SERVER_URL: Auth server URL (default: http://localhost:5005)
    - BILLING_SERVER_URL: Billing server URL (default: http://localhost:5004)
    - CHROMA_SERVER_URL: Chroma server URL (default: http://localhost:5002)
    """
    logger.info("=" * 70)
    logger.info("🚀 George Backend - AI Router with Cost Governor")
    logger.info("=" * 70)
    logger.info(f"Auth Server: {AUTH_SERVER_URL}")
    logger.info(f"Billing Server: {BILLING_SERVER_URL}")
    logger.info(f"Chroma Server: {CHROMA_SERVER_URL}")
    logger.info(f"Pro Model Threshold: ${PRO_MODEL_THRESHOLD}")
    logger.info("=" * 70)
    
    # Run Flask development server
    app.run(host='0.0.0.0', port=5001, debug=False, threaded=True)
