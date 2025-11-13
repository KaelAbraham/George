import os
import requests
import logging
import json
import uuid
from pathlib import Path
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from typing import Dict, Any, Optional, List

# --- Local Imports ---
# These are the new foundational services we just planned
from llm_client import GeminiClient
from session_manager import SessionManager
from job_manager import JobManager
# This is your premium report/wiki generator
from knowledge_extraction.orchestrator import KnowledgeExtractionOrchestrator


# --- Load Config ---
load_dotenv()
app = Flask(__name__)
# Make sure data directory exists for job/session dbs
os.makedirs("data", exist_ok=True) 
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Service URLs (The "Hands") ---
AUTH_SERVER_URL = os.environ.get("AUTH_SERVER_URL", "http://localhost:5005")
BILLING_SERVER_URL = os.environ.get("BILLING_SERVER_URL", "http://localhost:5004")
CHROMA_SERVER_URL = os.environ.get("CHROMA_SERVER_URL", "http://localhost:5002")
FILESYSTEM_SERVER_URL = os.environ.get("FILESYSTEM_SERVER_URL", "http://localhost:5001")
GIT_SERVER_URL = os.environ.get("GIT_SERVER_URL", "http://localhost:5003")


# --- Constants ---
PRO_MODEL_THRESHOLD = 0.50  # 50 cents minimum balance to use Pro model

# --- Initialize Clients & Managers ---
try:
    # We need multiple clients for the different steps in the 3-call loop
    triage_client = GeminiClient(model="gemini-1.5-flash-latest")
    answer_client_flash = GeminiClient(model="gemini-1.5-flash-latest")
    answer_client_pro = GeminiClient(model="gemini-1.5-pro-latest")
    polish_client = GeminiClient(model="gemini-1.5-flash-latest")
    
    # Initialize our new foundational services
    session_manager = SessionManager()
    job_manager = JobManager()
    
    # orchestrator = KnowledgeExtractionOrchestrator() # Ready for premium jobs
    
    logging.info("AI Router initialized successfully.")
except Exception as e:
    logging.critical(f"Failed to initialize clients: {e}", exc_info=True)
    # In a real app, you'd exit here if core clients fail
    
# --- Prompt Loading (Helper) ---
PROMPT_DIR = Path("prompts")
def load_prompt(filename: str) -> str:
    """Loads a prompt from the backend/prompts/ directory."""
    try:
        with open(PROMPT_DIR / filename, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        logging.error(f"CRITICAL: Prompt file '{filename}' not found.")
        return ""

# Load all critical prompts on startup
GEORGE_CONSTITUTION = load_prompt('george_operational_protocol.txt')
AI_ROUTER_PROMPT_v4 = load_prompt('ai_router_v4.txt') 
COREF_RESOLUTION_PROMPT = load_prompt('coreference_resolution.txt')
POLISH_PROMPT = load_prompt('george_polish.txt')

# --- Helper Functions ---

def _get_user_from_request(request) -> Optional[Dict[str, Any]]:
    """Helper to call the Auth Server and verify the user's token."""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return None
    try:
        # This call verifies the Firebase token AND gets our internal role/permissions
        resp = requests.post(f"{AUTH_SERVER_URL}/verify_token", headers={"Authorization": auth_header})
        if resp.status_code == 200:
            return resp.json()
        logging.warning(f"Auth verification failed with status {resp.status_code}: {resp.text}")
        return None
    except Exception as e:
        logging.error(f"Auth verification call failed: {e}")
        return None

def _check_project_access(auth_data: Dict, project_id: str) -> bool:
    """Checks if user is admin OR has guest access to the project."""
    if not auth_data:
        return False
    # Admins own their projects. We assume they own the project they are querying.
    # A more robust check would involve a project_owner_id check here.
    if auth_data.get('role') == 'admin':
        return True
    # Guests must have an explicit entry in their guest_projects list
    if auth_data.get('role') == 'guest' and project_id in auth_data.get('guest_projects', []):
        return True
    return False

def get_user_balance(user_id: str) -> float:
    """Gets the user's current API pool balance."""
    try:
        resp = requests.get(f"{BILLING_SERVER_URL}/balance/{user_id}")
        if resp.status_code == 200:
            return float(resp.json().get('balance', 0.0))
    except Exception as e:
        logging.error(f"Failed to get balance for {user_id}: {e}")
    return 0.0

def deduct_cost(user_id: str, job_id: str, cost: float, description: str):
    """Tells the billing server to log a transaction and deduct cost."""
    try:
        requests.post(f"{BILLING_SERVER_URL}/deduct", json={
            "user_id": user_id,
            "cost": cost,
            "job_id": job_id,
            "description": description
        })
    except Exception as e:
        logging.error(f"Failed to deduct cost for {user_id}: {e}")

def get_triage_data(user_query: str, project_id: str) -> Dict[str, Any]:
    """Call 1: Triage. Determines intent, knowledge source, and memory needs."""
    prompt = AI_ROUTER_PROMPT_v4.format(user_query=user_query, project_id=project_id)
    result = triage_client.chat(prompt)
    try:
        # The prompt asks for minified JSON
        data = json.loads(result['response'])
        return data
    except Exception as e:
        logging.error(f"Failed to parse triage JSON: {e}. Defaulting to craft.")
        # Fallback to a safe, known state
        return {"intent": "app_support", "knowledge_source": "CAUDEX_SUPPORT_KB", "requires_memory": False}

def resolve_memory(triage_data: Dict, user_id: str, project_id: str) -> (str, str, List[Dict]):
    """
    Handles Step 1.5 (Memory & Rewrite).
    Returns: (rewritten_query, chat_history_for_prompt, chat_history_for_llm)
    """
    user_query = triage_data['original_query']
    if not triage_data.get('requires_memory', False):
        return user_query, "", [] # No rewrite needed, no history list

    logging.info(f"Query '{user_query}' requires memory. Fetching history...")
    history_list = session_manager.get_recent_history(project_id, user_id)
    chat_history_str = session_manager.format_history_for_prompt(history_list)
    
    # Call 1.5: Rewrite query
    rewrite_prompt = COREF_RESOLUTION_PROMPT.format(
        chat_history=chat_history_str,
        user_query=user_query
    )
    result = triage_client.chat(rewrite_prompt) # Use the cheap client
    
    rewritten_query = result['response'].strip()
    logging.info(f"Query rewritten: '{user_query}' -> '{rewritten_query}'")
    
    # Return all three formats
    return rewritten_query, chat_history_str, history_list

def get_chroma_context(query: str, collection_name: str) -> str:
    """Calls the Chroma server to get RAG context."""
    if not collection_name or collection_name == "NONE":
        return ""
    try:
        resp = requests.post(
            f"{CHROMA_SERVER_URL}/query",
            json={"collection_name": collection_name, "query_texts": [query], "n_results": 5}
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
        logging.error(f"Failed to get context from Chroma: {e}")
    return "Error: Could not retrieve knowledge base."

# --- Core Chat Endpoint ---

@app.route('/chat', methods=['POST'])
def chat():
    """
    Main stateless chat endpoint using the 3-call loop.
    """
    # 1. AUTHENTICATION (The "Gatekeeper")
    auth_data = _get_user_from_request(request)
    if not auth_data or not auth_data['valid']:
        return jsonify({"error": "Invalid or missing token"}), 401
    
    user_id = auth_data['user_id']
    user_role = auth_data['role']
    
    data = request.get_json()
    user_query = data.get('query')
    project_id = data.get('project_id')

    if not user_query or not project_id:
        return jsonify({"error": "query and project_id are required"}), 400
    
    # 2. PERMISSION CHECK
    if not _check_project_access(auth_data, project_id):
        logging.warning(f"User {user_id} (role: {user_role}) denied access to {project_id}.")
        return jsonify({"error": "You do not have permission to access this project."}), 403

    try:
        # --- CALL 1: TRIAGE ---
        triage_data = get_triage_data(user_query, project_id)
        triage_data['original_query'] = user_query
        intent = triage_data.get('intent')
        
        # --- GUARDRAILS ---
        if intent == "creative_task":
            logging.warning(f"User {user_id} triggered creative guardrail.")
            response_text = "I see you're working on a creative task! My role is to be your diagnostic partner, not a co-writer. If you write a draft, I'd be happy to analyze it for you."
            session_manager.add_turn(project_id, user_id, user_query, response_text)
            return jsonify({"response": response_text}), 200
        
        if intent == "emotional_support":
            logging.info(f"User {user_id} triggered emotional support.")
            response_text = "It sounds like you're stuck. That's a normal part of the creative process! Take a short break, or try approaching the scene from a different character's perspective."
            session_manager.add_turn(project_id, user_id, user_query, response_text)
            return jsonify({"response": response_text}), 200

        # --- CALL 1.5: MEMORY & REWRITE ---
        rewritten_query, chat_history_str, history_list = resolve_memory(triage_data, user_id, project_id)

        # --- RESOURCE GATHERING ---
        kb_name = ""
        if triage_data.get('knowledge_source') == "PROJECT_KB":
            kb_name = f"project_{project_id}"
        elif triage_data.get('knowledge_source') == "CAUDEX_SUPPORT_KB":
            kb_name = "george_craft_library" # Your static craft guides
        # Add future "EXTERNAL_API" logic here
        
        context_str = get_chroma_context(rewritten_query, kb_name)

        # --- CALL 2: EXECUTION & COST GOVERNOR ---
        
        # 1. Check Balance
        user_balance = get_user_balance(user_id)
        
        # 2. Select Model based on Governor
        model_to_use = answer_client_flash
        downgrade_flag = False
        
        if intent == 'complex_analysis' and user_role == 'admin': # Guests can't use Pro
            if user_balance >= PRO_MODEL_THRESHOLD:
                model_to_use = answer_client_pro
                logging.info(f"User {user_id} has ${user_balance}. Using PRO model.")
            else:
                downgrade_flag = True
                logging.info(f"User {user_id} has ${user_balance}. Downgrading to FLASH.")
        elif user_role == 'guest' and intent == 'complex_analysis':
             downgrade_flag = True # Guests are always "downgraded" for complex tasks
             logging.info(f"User {user_id} is a GUEST. Forcing FLASH model for complex task.")

        # 3. Assemble Main Prompt
        main_prompt = f"""
        {GEORGE_CONSTITUTION}

        USER QUERY:
        {user_query}

        ---
        RETRIEVED CONTEXT (Vetted Sources):
        {context_str}
        ---

        Based *only* on the RETRIEVED CONTEXT, answer the USER QUERY.
        """
        
        # 4. Get Draft Answer
        # We pass the history_list (Gemini-formatted) to the chat() method
        result_dict = model_to_use.chat(main_prompt, history=history_list)
        draft_answer = result_dict['response']
        call_cost = result_dict.get('cost', 0.0)

        # 5. Report Cost to Billing Server
        if call_cost > 0:
            deduct_cost(user_id, f"chat-{uuid.uuid4()}", call_cost, f"Chat: {intent}")

        # --- CALL 3: "GEORGEIFICATION" POLISH ---
        
        polish_instructions = "Rephrase the DRAFT ANSWER to be natural, helpful, and consistent with your persona."
        
        if downgrade_flag:
            polish_instructions = (
                "You must also add a gentle, friendly upsell. Explain that this is a complex question "
                "and you could provide a much deeper analysis with a 'pick-me-up' (a $5 coffee) to "
                "activate your advanced reasoning module."
            )

        polish_prompt = POLISH_PROMPT.format(
            polish_instructions=polish_instructions,
            draft_answer=draft_answer
        )
        
        polish_result = polish_client.chat(polish_prompt)
        final_answer = polish_result['response']
        
        # --- SAVE & RESPOND ---
        session_manager.add_turn(project_id, user_id, user_query, final_answer)
        
        return jsonify({
            "response": final_answer,
            "intent": intent,
            "cost": call_cost,
            "downgraded": downgrade_flag,
            "balance": user_balance - call_cost
        })

    except Exception as e:
        logging.error(f"Critical error in /chat: {e}", exc_info=True)
        return jsonify({"error": "An internal server error occurred."}), 500

# --- Job/Report Endpoints ---

@app.route('/jobs/<job_id>', methods=['GET'])
def get_job_status(job_id):
    # TODO: Add auth check: user must own this job
    job = job_manager.get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)

@app.route('/project/<project_id>/jobs', methods=['GET'])
def get_project_jobs(project_id):
    # TODO: Add auth check: user must own this project
    jobs = job_manager.get_jobs_for_project(project_id)
    return jsonify({"project_id": project_id, "jobs": jobs})

# --- EXAMPLE: Async "Wiki Generation" Endpoint ---
def _run_wiki_generation_task(project_id: str, user_id: str) -> Dict:
    """The actual heavy-lifting for the wiki job."""
    logging.info(f"Starting WIKI job for {project_id}")
    # 1. Get all chunks from chroma_server
    # 2. Get graph data from chroma_server
    # 3. Call KnowledgeExtractionOrchestrator
    # 4. Save files using filesystem_server
    # 5. Snapshot with git_server
    import time
    time.sleep(10) # Simulate 10 seconds of work
    logging.info(f"Finished WIKI job for {project_id}")
    return {"files_created": 15, "entities_found": 42}


@app.route('/project/<project_id>/generate_wiki', methods=['POST'])
def generate_wiki(project_id):
    auth_data = _get_user_from_request(request)
    if not auth_data or auth_data['role'] != 'admin':
        return jsonify({"error": "Only project admins can run reports."}), 403
    
    user_id = auth_data['user_id']
    
    # TODO: Check API pool balance before starting!
    
    # 1. Create the job "receipt"
    job_id = job_manager.create_job(
        project_id=project_id, 
        user_id=user_id, 
        job_type="wiki_generation"
    )
    
    # 2. Start the background task
    job_manager.run_async(
        job_id, 
        _run_wiki_generation_task, 
        project_id, 
        user_id
    )
    
    # 3. Return immediately
    return jsonify({
        "message": "Wiki generation has started.",
        "job_id": job_id,
        "status_url": f"/jobs/{job_id}"
    }), 202 # "Accepted"

if __name__ == '__main__':
    print("--- Caudex Pro AI Router (The Brain) ---")
    print("Ensure all microservices (Auth, Billing, Chroma, Filesystem, Git) are running.")
    print("Running on http://localhost:5000")
    app.run(debug=True, port=5000)