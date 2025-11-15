import os
import requests
import logging
import json
import uuid
import sqlite3
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify, make_response
from flask.views import MethodView
from dotenv import load_dotenv
from typing import Dict, Any, Optional, List, Tuple, Literal
from flask_smorest import Api, abort
from flask_cors import CORS
from neo4j import GraphDatabase
from pydantic import BaseModel, ValidationError

# --- Local Imports ---
# These are the new foundational services we just planned
from llm_client import GeminiClient, MultiModelCostAggregator
from session_manager import SessionManager
from job_manager import JobManager
from feedback_manager import FeedbackManager
# This is your premium report/wiki generator
try:
    from knowledge_extraction.orchestrator import KnowledgeExtractor as KnowledgeExtractionOrchestrator
except ImportError as e:
    logging.warning(f"Could not import KnowledgeExtractor: {e}")
    KnowledgeExtractionOrchestrator = None


# --- Load Config ---
load_dotenv()
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# --- Configuration for flask-smorest API documentation ---
app.config["API_TITLE"] = "Caudex Pro AI Router"
app.config["API_VERSION"] = "v1"
app.config["OPENAPI_VERSION"] = "3.0.2"
app.config["OPENAPI_URL_PREFIX"] = "/"
app.config["OPENAPI_SWAGGER_UI_PATH"] = "/api/docs"
app.config["OPENAPI_SWAGGER_UI_VERSION"] = "3.10.0"

api = Api(app)  # Initialize flask-smorest for advanced API documentation

# --- Flask-Smorest Blueprints ---
from flask_smorest import Blueprint

blp_chat = Blueprint(
    "chat",
    __name__,
    url_prefix="/",
    description="AI chat and query routing endpoints"
)

blp_jobs = Blueprint(
    "jobs",
    __name__,
    url_prefix="/",
    description="Background job management and tracking"
)

blp_admin = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin",
    description="Admin-only monitoring and statistics endpoints"
)

# Make sure data directory exists for job/session dbs
os.makedirs("data", exist_ok=True) 
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Service URLs (The "Hands") ---
# Internal service URLs (6000-series ports are reserved for internal services)
AUTH_SERVER_URL = os.environ.get("AUTH_SERVER_URL", "http://localhost:6001")
BILLING_SERVER_URL = os.environ.get("BILLING_SERVER_URL", "http://localhost:6004")
CHROMA_SERVER_URL = os.environ.get("CHROMA_SERVER_URL", "http://localhost:6003")
FILESYSTEM_SERVER_URL = os.environ.get("FILESYSTEM_SERVER_URL", "http://localhost:6002")
GIT_SERVER_URL = os.environ.get("GIT_SERVER_URL", "http://localhost:6005")
EXTERNAL_DATA_SERVER_URL = os.environ.get("EXTERNAL_DATA_SERVER_URL", "http://localhost:6006")
GRAPH_SERVER_URL = os.environ.get("GRAPH_SERVER_URL", "bolt://localhost:7687")


# --- Constants ---
# 100 Credits = 1 Cent ($0.01) | 10,000 Credits = $1.00
PRO_MODEL_THRESHOLD_CREDITS = 5000  # 5000 Credits ($0.50)
WIKI_JOB_MIN_BALANCE_CREDITS = 10000  # 10000 Credits ($1.00)

# --- Initialize Clients & Managers ---
try:
    # Initialize the aggregator to track all clients
    cost_aggregator = MultiModelCostAggregator()

    # We need multiple clients for the different steps in the 3-call loop
    triage_client = GeminiClient(model="gemini-1.5-flash-latest")
    cost_aggregator.register_client("triage_client", triage_client)
    
    answer_client_flash = GeminiClient(model="gemini-1.5-flash-latest")
    cost_aggregator.register_client("answer_flash_client", answer_client_flash)
    
    answer_client_pro = GeminiClient(model="gemini-1.5-pro-latest")
    cost_aggregator.register_client("answer_pro_client", answer_client_pro)
    
    polish_client = GeminiClient(model="gemini-1.5-flash-latest")
    cost_aggregator.register_client("polish_client", polish_client)
    
    # Initialize our new foundational services
    session_manager = SessionManager()
    job_manager = JobManager()
    feedback_manager = FeedbackManager()
    
    # Initialize orchestrator only if import succeeded AND all dependencies available
    if KnowledgeExtractionOrchestrator:
        try:
            # KnowledgeExtractor requires george_ai and project_path
            # Skip for now since GeorgeAI is not available
            orchestrator = None
            logging.warning("KnowledgeExtractor skipped - requires GeorgeAI (not available)")
        except Exception as e:
            orchestrator = None
            logging.warning(f"Could not initialize orchestrator: {e}")
    else:
        orchestrator = None
        logging.warning("KnowledgeExtractionOrchestrator not available - wiki generation disabled")
    
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


# --- Failed Transaction Logger (Billing Resilience) ---
class FailedTransactionLogger:
    """
    Manages a persistent queue of failed billing deductions.
    Ensures no charges are lost if the billing server is down or unreachable.
    
    The reconciliation service will periodically read from this DB and retry.
    """
    def __init__(self, db_path: str = "data/failed_transactions.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Helper to get a new SQLite connection."""
        return sqlite3.connect(str(self.db_path))

    def _init_db(self):
        """Creates the 'failed_transactions' table if it doesn't exist."""
        try:
            with self._get_conn() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS failed_transactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        job_id TEXT,
                        cost REAL NOT NULL,
                        description TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        status TEXT DEFAULT 'PENDING'
                    )
                """)
                # Index for faster lookup during reconciliation
                conn.execute("CREATE INDEX IF NOT EXISTS idx_failed_tx_status ON failed_transactions (status)")
                conn.commit()
            logging.info("FailedTransactionLogger initialized successfully.")
        except Exception as e:
            logging.critical(f"Failed to initialize FailedTransactionLogger database: {e}", exc_info=True)
            raise

    def log_failure(self, user_id: str, job_id: str, cost: float, description: str):
        """Logs a failed deduction to the database for later reconciliation."""
        try:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT INTO failed_transactions (user_id, job_id, cost, description) VALUES (?, ?, ?, ?)",
                    (user_id, job_id, cost, description)
                )
                conn.commit()
            logging.info(f"[FAILED-TX] Logged failed transaction for user {user_id}, cost ${cost:.6f}.")
        except Exception as e:
            # This is a critical error, as we are failing to log a failure
            logging.critical(f"!!! CRITICAL: FAILED TO LOG FAILED TRANSACTION: {e}", exc_info=True)
            # Note: We log but don't raise, to prevent blocking the user


# --- Initialize Failed Transaction Logger (global) ---
failed_tx_logger = FailedTransactionLogger()  # For billing reconciliation on service failures


# Load all critical prompts on startup
GEORGE_CONSTITUTION = load_prompt('george_operational_protocol.txt')
AI_ROUTER_PROMPT_v4 = load_prompt('ai_router_v3.txt')  # Use v3 as fallback
COREF_RESOLUTION_PROMPT = load_prompt('query_rewriter.txt')  # Use query_rewriter as coreference resolution
POLISH_PROMPT = load_prompt('georgeification_polish.txt')  # Correct filename

# --- Pydantic Models for Type-Safe LLM Output Validation ---

class TriageData(BaseModel):
    """
    Pydantic model to validate the output from the Triage LLM (Call 1).
    Ensures the output is predictable and type-safe.
    
    Fields:
        intent: The detected intent (e.g., "craft_guidance", "complex_analysis", "app_support")
        knowledge_source: Which knowledge base to query (e.g., "PROJECT_KB", "CAUDEX_SUPPORT_KB", "NONE")
        requires_memory: Whether the query needs chat history context for coreference resolution
    """
    intent: str
    knowledge_source: str
    requires_memory: bool

# --- Marshmallow Schemas for Request/Response Validation ---
import marshmallow as ma

class ChatRequestSchema(ma.Schema):
    """Request schema for POST /chat endpoint."""
    query = ma.fields.Str(required=True)
    project_id = ma.fields.Str(required=True)

class ChatResponseSchema(ma.Schema):
    """Response schema for successful chat responses."""
    message_id = ma.fields.Str()
    response = ma.fields.Str()
    intent = ma.fields.Str()
    cost = ma.fields.Float()
    downgraded = ma.fields.Bool()
    balance = ma.fields.Float(allow_none=True)

class JobStatusSchema(ma.Schema):
    """Schema for job status response."""
    job_id = ma.fields.Str()
    project_id = ma.fields.Str()
    user_id = ma.fields.Str()
    status = ma.fields.Str()
    job_type = ma.fields.Str()
    created_at = ma.fields.DateTime()
    result = ma.fields.Raw(allow_none=True)

class JobsListSchema(ma.Schema):
    """Schema for list of jobs."""
    jobs = ma.fields.List(ma.fields.Nested(JobStatusSchema))

class CostSummarySchema(ma.Schema):
    """Schema for admin cost summary."""
    total_tokens = ma.fields.Int()
    total_cost = ma.fields.Float()
    clients = ma.fields.Raw()

class WikiGenerationRequestSchema(ma.Schema):
    """Request schema for wiki generation (empty body, admin-only)."""
    pass

class WikiGenerationResponseSchema(ma.Schema):
    """Response schema for wiki generation job creation."""
    message = ma.fields.Str()
    job_id = ma.fields.Str()
    status_url = ma.fields.Str()

class FeedbackRequestSchema(ma.Schema):
    """Request schema for POST /feedback endpoint."""
    message_id = ma.fields.Str(required=True)
    rating = ma.fields.Int(required=True)
    category = ma.fields.Str(allow_none=True)
    comment = ma.fields.Str(allow_none=True)

class FeedbackResponseSchema(ma.Schema):
    """Response schema for successful feedback submission."""
    status = ma.fields.Str()
    feedback_id = ma.fields.Str()

class SaveNoteResponseSchema(ma.Schema):
    """Response schema for successful note saving."""
    status = ma.fields.Str()
    note_path = ma.fields.Str()
    ingest_status = ma.fields.Str()

class BookmarkRequestSchema(ma.Schema):
    """Request schema for bookmarking a chat message."""
    is_bookmarked = ma.fields.Bool(required=True)

class BookmarkResponseSchema(ma.Schema):
    """Response schema for bookmark operations."""
    status = ma.fields.Str()
    message_id = ma.fields.Str()
    is_bookmarked = ma.fields.Bool()

class BookmarkListSchema(ma.Schema):
    """Schema for a bookmarked message in the list."""
    message_id = ma.fields.Str()
    user_query = ma.fields.Str()
    ai_response = ma.fields.Str()
    timestamp = ma.fields.Str()
    id = ma.fields.Int()

class ProjectBookmarksSchema(ma.Schema):
    """Response schema for getting all bookmarks in a project."""
    bookmarks = ma.fields.List(ma.fields.Nested(BookmarkListSchema))

# --- Authentication Proxy Routes (Gatekeeper Pattern) ---

@app.route('/v1/api/auth/login', methods=['POST'])
def proxy_login():
    """
    Proxies the login request to the Auth Server.
    If successful, it receives the token and sets it in a secure, HttpOnly cookie.
    """
    try:
        # 1. Forward login credentials to Auth Server
        data = request.get_json()
        resp = requests.post(
            f"{AUTH_SERVER_URL}/login",
            json=data,
            timeout=5
        )
        resp.raise_for_status()  # Raise an error for bad responses (401, 500, etc.)

        # 2. On success, get the token from the response
        token_data = resp.json()
        token = token_data.get('token')

        # 3. Create a response and set the secure cookie
        response_data = {"success": True, "user": token_data.get('user')}
        response = make_response(jsonify(response_data))

        response.set_cookie(
            'auth_token',
            value=token,
            httponly=True,   # <-- CRITICAL: Makes it inaccessible to JavaScript
            secure=True,     # <-- CRITICAL: Only send over HTTPS (in prod)
            samesite='Lax'   # <-- Good security practice
        )
        return response

    except requests.exceptions.HTTPError as e:
        # Forward the auth server's error (e.g., "Invalid password")
        return jsonify(e.response.json()), e.response.status_code
    except Exception as e:
        logger.error(f"Error in /login proxy: {e}", exc_info=True)
        return jsonify({"error": "Login service is unavailable"}), 503


@app.route('/v1/api/auth/register', methods=['POST'])
def proxy_register():
    """
    Proxies the registration request to the Auth Server.
    Does not log the user in; just creates the account.
    
    Expected payload:
    {
        "email": "user@example.com",
        "password": "secure_password",
        "invite_code": "VALID_INVITE_CODE"
    }
    
    Returns:
        201 on success with user data
        400 on validation error (e.g., email already exists, invalid invite)
        503 if auth service is unavailable
    """
    try:
        # 1. Forward registration data to Auth Server
        data = request.get_json()
        resp = requests.post(
            f"{AUTH_SERVER_URL}/register",  # Calls the /register route on the auth hand
            json=data,
            timeout=5
        )
        resp.raise_for_status()  # Raise an error for bad responses (400, 500, etc.)

        # 2. On success, just return the success message (no login needed)
        return resp.json(), resp.status_code

    except requests.exceptions.HTTPError as e:
        # Forward the auth server's error (e.g., "Email already in use", "Invalid invite code")
        return jsonify(e.response.json()), e.response.status_code
    except Exception as e:
        logger.error(f"Error in /register proxy: {e}", exc_info=True)
        return jsonify({"error": "Registration service is unavailable"}), 503


@app.route('/v1/api/auth/logout', methods=['POST'])
def proxy_logout():
    """
    Logs the user out by clearing the secure cookie.
    """
    response = make_response(jsonify({"success": True, "message": "Logged out"}))
    response.set_cookie('auth_token', '', expires=0, httponly=True)  # Clear the cookie
    return response


@app.route('/v1/api/auth/check', methods=['GET'])
def check_auth_status():
    """
    Checks if the user is currently authenticated by verifying the token in their cookie.
    This is called by the frontend on page load.
    """
    # _get_user_from_request is now modified to read from the cookie
    user_data = _get_user_from_request(request)

    if user_data and user_data.get('valid'):
        return jsonify({"isAuthenticated": True, "user": user_data}), 200
    else:
        return jsonify({"isAuthenticated": False, "user": None}), 401


# --- File Content Proxy Route ---

@app.route('/v1/api/project/<project_id>/file/<file_name>', methods=['GET'])
def get_file_content(project_id, file_name):
    """
    [AUTH] Proxies a request to the filesystem_server to get raw file content.
    """
    # 1. AUTHENTICATION (User must be logged in)
    auth_data = _get_user_from_request(request)
    if not auth_data or not auth_data.get('valid'):
        return jsonify({"error": "Invalid or missing token"}), 401

    # 2. PERMISSION CHECK (User must own this project)
    # (You can add your project access logic here if needed)

    try:
        # 3. PROXY REQUEST to filesystem_server with user_id header
        resp = requests.get(
            f"{FILESYSTEM_SERVER_URL}/file/{project_id}/{file_name}",
            headers={'X-User-ID': auth_data.get('user_id', '')},
            timeout=10
        )
        resp.raise_for_status()  # Raise error for 404, 500, etc.

        # 4. RETURN FILE CONTENT
        # We return the raw text content directly
        return resp.text, 200, {'Content-Type': resp.headers.get('Content-Type', 'text/plain')}

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return jsonify({"error": "File not found"}), 404
        return jsonify({"error": "Filesystem service error"}), 503
    except Exception as e:
        logger.error(f"Error in /get_file_content proxy: {e}", exc_info=True)
        return jsonify({"error": "File service is unavailable"}), 503

# --- File Upload Proxy Route ---

@app.route('/v1/api/project/<project_id>/upload', methods=['POST'])
def proxy_file_upload(project_id):
    """
    [AUTH] Proxies a file upload to the filesystem_server.
    Receives a file from the frontend and forwards it to the internal filesystem_server.
    The filesystem_server handles saving the original and creating markdown conversion.
    """
    # 1. AUTHENTICATION (User must be logged in)
    auth_data = _get_user_from_request(request)
    if not auth_data or not auth_data.get('valid'):
        return jsonify({"error": "Invalid or missing token"}), 401

    # 2. PERMISSION CHECK (User must own this project)
    # (You can add your project access logic here if needed)
    
    if 'file' not in request.files:
        return jsonify({"error": "No file provided in request"}), 400
    
    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    try:
        # 3. FORWARD THE FILE to filesystem_server with user_id header
        # Stream the file to the internal service
        files = {'file': (file.filename, file.stream, file.content_type)}
        
        resp = requests.post(
            f"{FILESYSTEM_SERVER_URL}/projects/{project_id}/upload",
            files=files,
            headers={'X-User-ID': auth_data.get('user_id', '')},
            timeout=30
        )
        resp.raise_for_status()

        # 4. RETURN RESPONSE FROM FILESYSTEM_SERVER
        return resp.json(), resp.status_code

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return jsonify({"error": "Project not found"}), 404
        elif e.response.status_code == 400:
            return jsonify({"error": "Invalid file or project ID"}), 400
        logger.error(f"Filesystem service error: {e.response.text if e.response else str(e)}")
        return jsonify({"error": "File upload service error"}), 503
    except Exception as e:
        logger.error(f"Error in /upload proxy: {e}", exc_info=True)
        return jsonify({"error": "File upload service is unavailable"}), 503

# --- Core Chat Endpoint (Migrated to flask-smorest) ---

@blp_chat.route('/chat')
class Chat(MethodView):
    """Main stateless chat endpoint using the 3-call loop."""

    @blp_chat.doc(
        description="Main endpoint for all user-facing chat interactions. Requires an Authorization token.",
        summary="Send a query to the AI chat router."
    )
    @blp_chat.arguments(ChatRequestSchema, location="json")
    @blp_chat.response(200, ChatResponseSchema)
    def post(self, data):
        """
        Main stateless chat endpoint using the 3-call loop.
        
        Accepts a JSON payload with `query` and `project_id`.
        The backend handles intent routing, knowledge retrieval, and cost management.
        """
        # 1. AUTHENTICATION (The "Gatekeeper")
        auth_data = _get_user_from_request(request)
        if not auth_data or not auth_data['valid']:
            abort(401, message="Invalid or missing token")
        
        user_id = auth_data['user_id']
        user_role = auth_data['role']
        
        # data is automatically validated by ChatRequestSchema
        user_query = data['query']
        project_id = data['project_id']
        
        # 2. PERMISSION CHECK
        if not _check_project_access(auth_data, project_id):
            logging.warning(f"User {user_id} (role: {user_role}) denied access to {project_id}.")
            abort(403, message="You do not have permission to access this project.")

        try:
            # --- CALL 1: TRIAGE ---
            triage_data = get_triage_data(user_query, project_id)
            intent = triage_data.intent
            
            # --- GUARDRAILS ---
            if intent == "creative_task":
                logging.warning(f"User {user_id} triggered creative guardrail.")
                response_text = "I see you're working on a creative task! My role is to be your diagnostic partner, not a co-writer. If you write a draft, I'd be happy to analyze it for you."
                session_manager.add_turn(project_id, user_id, user_query, response_text)
                return {"response": response_text}
            
            if intent == "emotional_support":
                logging.info(f"User {user_id} triggered emotional support.")
                response_text = "It sounds like you're stuck. That's a normal part of the creative process! Take a short break, or try approaching the scene from a different character's perspective."
                session_manager.add_turn(project_id, user_id, user_query, response_text)
                return {"response": response_text}

            # --- CALL 1.5: MEMORY & REWRITE ---
            rewritten_query, chat_history_str, history_list = resolve_memory(triage_data, user_query, user_id, project_id)

            # --- RESOURCE GATHERING (RAG) ---
            kb_name = ""
            if triage_data.knowledge_source == "PROJECT_KB":
                kb_name = f"project_{project_id}"
            elif triage_data.knowledge_source == "CAUDEX_SUPPORT_KB":
                kb_name = "george_craft_library"  # Your static craft guides
            # Add future "EXTERNAL_API" logic here
            
            # Get context from vector database (Chroma)
            chroma_context, chroma_success = get_chroma_context(rewritten_query, kb_name)
            
            # RESILIENCE CHECK: If Chroma failed, abort gracefully with 503
            if not chroma_success:
                logger.error(f"[RESILIENCE] Aborting chat for user {user_id} due to Chroma failure.")
                abort(503, message="Your knowledge base is temporarily unavailable. Please try again in a moment.")
            
            # Get context from knowledge graph (Neo4j) - graceful degradation if unavailable
            graph_context, graph_success = get_graph_context(rewritten_query, project_id)
            if not graph_success:
                logger.warning(f"[GRACEFUL] Graph context unavailable, continuing with Chroma context only.")
            
            # Combine contexts: vector DB + relationship graph
            context_str = chroma_context
            if graph_context:
                context_str = f"{chroma_context}\n\n{graph_context}" if chroma_context else graph_context
            
            logging.debug(f"[RAG] Combined context: {len(context_str)} chars from Chroma + {len(graph_context)} chars from Graph")

            # --- CALL 2: EXECUTION & COST GOVERNOR ---
            
            # 1. Check Balance
            user_balance_or_none = get_user_balance(user_id)
            billing_server_failed = (user_balance_or_none is None)
            
            # Default to 0.0 for calculations, but we use the None for logic
            user_balance = user_balance_or_none if not billing_server_failed else 0.0

            if billing_server_failed:
                logger.warning(f"[FAIL-OPEN] Billing server failed for user {user_id}. Allowing Pro model.")

            # 2. Select Model based on Governor
            model_to_use = answer_client_flash
            downgrade_flag = False
            
            if intent == 'complex_analysis' and user_role == 'admin':  # Guests can't use Pro
                
                # Use Pro model if:
                # A) Billing server failed (fail-open principle)
                # B) Billing server succeeded AND balance is sufficient
                
                if billing_server_failed or user_balance >= PRO_MODEL_THRESHOLD_CREDITS:
                    model_to_use = answer_client_pro
                    if billing_server_failed:
                        logger.info(f"User {user_id}: Using PRO model (Billing server failed, fail-open).")
                    else:
                        logger.info(f"User {user_id} has {user_balance} Credits. Using PRO model.")
                else:
                    # This 'else' block now only runs if billing succeeded AND balance is low
                    downgrade_flag = True
                    logger.info(f"User {user_id} has {user_balance} Credits. Downgrading to FLASH.")
            elif user_role == 'guest' and intent == 'complex_analysis':
                 downgrade_flag = True  # Guests are always "downgraded" for complex tasks
                 logger.info(f"User {user_id} is a GUEST. Forcing FLASH model for complex task.")

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
            
            # --- NEW: FINAL GUARDRAIL CHECK ---
            # Check if the polish model detected a violation from Call 2
            if "[COMPLIANCE_ERROR]" in final_answer:
                logging.warning(f"CRITICAL: Call 2 (Answer) failed protocol. Call 3 (Polish) caught the violation. Aborting.")
                # We log the specific error but return a generic, safe message to the user
                return jsonify({"error": "I was unable to process that request in a way that aligns with my operational protocol."}), 500

            # --- SAVE & RESPOND ---
            message_id = session_manager.add_turn(project_id, user_id, user_query, final_answer)
            
            # --- QUEUE FOR ASYNC INGESTION ---
            # Add to ingestion queue so the background worker will:
            # - Save as markdown file to filesystem
            # - Index in Chroma for semantic search
            # - Commit to Git for versioning
            # This keeps the chat fast while ensuring the Story Bible is eventually consistent
            session_manager.add_to_ingestion_queue(message_id, project_id, user_id)
            logger.info(f"Message {message_id} queued for async ingestion (file→vector→graph)")
            
            # Convert dollar cost to Credits
            call_cost_credits = int(call_cost * 10000)
            
            # Calculate final balance, handling billing server failure
            final_balance_credits = None
            if not billing_server_failed:
                # user_balance is already in Credits
                final_balance_credits = user_balance - call_cost_credits
                
            # Return dict; flask-smorest handles JSON serialization via ChatResponseSchema
            return {
                "message_id": message_id,
                "response": final_answer,
                "intent": intent,
                "cost": call_cost_credits,      # Now in Credits
                "downgraded": downgrade_flag,
                "balance": final_balance_credits # Now in Credits (or null)
            }

        except Exception as e:
            logging.error(f"Critical error in /chat: {e}", exc_info=True)
            abort(500, message="An internal server error occurred.")

# --- Feedback Endpoint ---

@blp_chat.route('/feedback')
class Feedback(MethodView):
    """Submit feedback for a specific chat message."""

    @blp_chat.doc(
        description="Allows a user to submit feedback (good/bad, category, comment) for a specific chat message.",
        summary="Submit chat feedback."
    )
    @blp_chat.arguments(FeedbackRequestSchema, location="json")
    @blp_chat.response(201, FeedbackResponseSchema)
    def post(self, data):
        """Submit feedback for a chat message."""

        # 1. AUTHENTICATION
        auth_data = _get_user_from_request(request)
        if not auth_data or not auth_data['valid']:
            abort(401, message="Invalid or missing token")

        user_id = auth_data['user_id']
        feedback_id = f"fbk_{uuid.uuid4()}"

        try:
            # 2. SAVE FEEDBACK
            feedback_manager.save_feedback(
                feedback_id=feedback_id,
                message_id=data['message_id'],
                user_id=user_id,
                rating=data['rating'],
                category=data.get('category'),
                comment=data.get('comment')
            )

            logger.info(f"Feedback {feedback_id} received from user {user_id} for message {data['message_id']}.")

            return {
                "status": "success",
                "feedback_id": feedback_id
            }

        except Exception as e:
            logging.error(f"Critical error in /feedback: {e}", exc_info=True)
            abort(500, message="An internal server error occurred while saving feedback.")


@blp_chat.route('/chat/<string:message_id>/save_as_note')
@blp_chat.route('/chat/<string:message_id>/bookmark')
class BookmarkChat(MethodView):
    """Bookmarks a specific chat message for the Notes section."""

    @blp_chat.doc(
        description="Toggles the bookmark status for a specific chat message. Bookmarked messages appear in the Story Bible Notes section.",
        summary="Bookmark or unbookmark a chat message."
    )
    @blp_chat.arguments(BookmarkRequestSchema, location="json")
    @blp_chat.response(200, BookmarkResponseSchema)
    def post(self, data, message_id):
        """Toggle bookmark status for a chat message."""
        
        # 1. AUTHENTICATION
        auth_data = _get_user_from_request(request)
        if not auth_data or not auth_data['valid']:
            abort(401, message="Invalid or missing token")
        
        user_id = auth_data['user_id']
        is_bookmarked = data['is_bookmarked']
        
        try:
            # 2. UPDATE THE BOOKMARK FLAG IN THE DATABASE
            success = session_manager.toggle_bookmark(
                message_id=message_id,
                user_id=user_id,
                is_bookmarked=is_bookmarked
            )
            
            if not success:
                abort(404, message="Message not found or you do not have permission to bookmark it.")
            
            logger.info(f"User {user_id} bookmarked message {message_id}: {is_bookmarked}")
            
            return {
                "status": "updated",
                "message_id": message_id,
                "is_bookmarked": is_bookmarked
            }, 200
        
        except Exception as e:
            logging.error(f"Failed to bookmark message {message_id}: {e}", exc_info=True)
            abort(500, message="Failed to update bookmark status.")

# --- Project Bookmarks Endpoint ---

@blp_chat.route('/project/<string:project_id>/bookmarks')
class ProjectBookmarks(MethodView):
    """Retrieves all bookmarked chat messages for a project (for the Story Bible Notes section)."""

    @blp_chat.doc(
        description="Returns all bookmarked chat messages for a project, ordered by recency. These appear in the Story Bible's Notes tab.",
        summary="Get all bookmarked messages for a project."
    )
    @blp_chat.response(200, ProjectBookmarksSchema)
    def get(self, project_id):
        """Get all bookmarked messages for a project."""
        
        # 1. AUTHENTICATION
        auth_data = _get_user_from_request(request)
        if not auth_data or not auth_data['valid']:
            abort(401, message="Invalid or missing token")
        
        user_id = auth_data['user_id']
        
        # 2. CHECK PERMISSION
        if not _check_project_access(auth_data, project_id):
            abort(403, message="You do not have permission to access this project.")
        
        try:
            # 3. FETCH BOOKMARKS FROM SESSION MANAGER
            bookmarks = session_manager.get_bookmarks_for_project(project_id, user_id)
            
            logger.info(f"User {user_id} retrieved {len(bookmarks)} bookmarks for project {project_id}")
            
            return {
                "bookmarks": bookmarks
            }, 200
        
        except Exception as e:
            logging.error(f"Failed to retrieve bookmarks for project {project_id}: {e}", exc_info=True)
            abort(500, message="Failed to retrieve bookmarks.")

# --- Job/Report Endpoints ---

@blp_jobs.route('/jobs/<string:job_id>')
class JobStatus(MethodView):
    """Get the status of a background job."""

    @blp_jobs.doc(
        description="Get the status of a background job (e.g., wiki generation). Jobs are user-scoped.",
        summary="Retrieve job status and progress."
    )
    @blp_jobs.response(200, JobStatusSchema)
    def get(self, job_id):
        """Get the status of a background job."""
        # 1. AUTHENTICATION
        auth_data = _get_user_from_request(request)
        if not auth_data or not auth_data.get('valid'):
            abort(401, message="Invalid or missing token")
        
        user_id = auth_data.get('user_id')
        
        # 2. Get Job (now securely scoped by the JobManager)
        job = job_manager.get_job(job_id, user_id)
        
        if not job:
            # This now correctly returns 404 if the job doesn't exist OR if the user doesn't own it
            abort(404, message="Job not found")
        
        return job


@blp_jobs.route('/project/<string:project_id>/jobs')
class ProjectJobs(MethodView):
    """Get all jobs for a specific project."""

    @blp_jobs.doc(
        description="Returns a list of all background jobs for the specified project, scoped to the authenticated user.",
        summary="List all jobs for a project."
    )
    @blp_jobs.response(200, JobsListSchema)
    def get(self, project_id):
        """Get all jobs for a specific project."""
        # 1. AUTHENTICATION
        auth_data = _get_user_from_request(request)
        if not auth_data or not auth_data.get('valid'):
            abort(401, message="Invalid or missing token")
        
        user_id = auth_data.get('user_id')
        
        # 2. Get Jobs (now securely scoped to this user)
        jobs = job_manager.get_jobs_for_project(project_id, user_id)
        
        logger.info(f"User {user_id} retrieved {len(jobs)} jobs for project {project_id}")
        
        return {"project_id": project_id, "jobs": jobs}

# --- Graph Database Helper Functions ---

def _get_graph_driver():
    """
    Get a Neo4j driver instance.
    Returns None if connection fails (error is logged).
    """
    try:
        driver = GraphDatabase.driver(GRAPH_SERVER_URL, auth=None)
        return driver
    except Exception as e:
        logging.error(f"[GRAPH] Failed to connect to Neo4j at {GRAPH_SERVER_URL}: {e}")
        return None

def _save_relationships_to_graph(project_id: str, relationships: List[Tuple[str, str, str]]) -> bool:
    """
    Save extracted relationships to Neo4j graph database.
    
    Args:
        project_id: Project identifier for scoping nodes
        relationships: List of (entity1, relationship_type, entity2) tuples
    
    Returns:
        True if successful, False otherwise
    """
    if not relationships:
        logging.info(f"[GRAPH] No relationships to save for project {project_id}")
        return True
    
    driver = _get_graph_driver()
    if not driver:
        logging.error("[GRAPH] Could not establish Neo4j connection")
        return False
    
    try:
        with driver.session() as session:
            for entity1, rel_type, entity2 in relationships:
                # Create nodes with project scope
                cypher = f"""
                    MERGE (n1:Entity {{name: $entity1, project_id: $project_id}})
                    MERGE (n2:Entity {{name: $entity2, project_id: $project_id}})
                    MERGE (n1)-[r:{rel_type}]->(n2)
                    SET r.project_id = $project_id
                """
                session.run(
                    cypher,
                    entity1=entity1,
                    entity2=entity2,
                    project_id=project_id
                )
                logging.debug(f"[GRAPH] Stored: ({entity1}, {rel_type}, {entity2})")
        
        logging.info(f"[GRAPH] Successfully saved {len(relationships)} relationships to Neo4j")
        return True
    except Exception as e:
        logging.error(f"[GRAPH] Failed to save relationships: {e}")
        return False
    finally:
        driver.close()

# --- WIKI Generation Task Helper Function ---
def _run_wiki_generation_task(project_id: str, user_id: str) -> Dict:
    """
    The actual heavy-lifting for the wiki job.
    
    Steps:
    1. Get all chunks from chroma_server
    2. Call KnowledgeExtractionOrchestrator to generate wiki files
    3. Extract relationships from documents
    4. Save relationships to Neo4j graph database
    5. Save files using filesystem_server
    6. Create Git snapshot
    """
    logging.info(f"[WIKI] Starting wiki generation for project {project_id}")
    collection_name = f"project_{project_id}"

    # Step 1: Get all chunks from chroma_server
    logging.info(f"[WIKI] Step 1: Fetching all documents from {collection_name}...")
    try:
        resp = requests.post(
            f"{CHROMA_SERVER_URL}/get_all_data",
            json={"collection_name": collection_name},
            timeout=30
        )
        resp.raise_for_status()
        all_docs = resp.json().get('documents', [])
        if not all_docs:
            raise Exception("No documents found in knowledge base.")
        logging.info(f"[WIKI] Step 1 SUCCESS: Retrieved {len(all_docs)} documents.")
    except Exception as e:
        logging.error(f"[WIKI] Step 1 FAILED: {e}")
        raise Exception(f"Failed to fetch knowledge base data: {e}")

    # Step 2: Call KnowledgeExtractionOrchestrator
    logging.info(f"[WIKI] Step 2: Calling orchestrator to generate wiki files...")
    try:
        # Orchestrator generates markdown files from documents
        generated_files = orchestrator.generate_wiki_files(all_docs)
        if not generated_files:
            raise Exception("Orchestrator returned no files.")
        logging.info(f"[WIKI] Step 2 SUCCESS: Generated {len(generated_files)} files.")
    except Exception as e:
        logging.error(f"[WIKI] Step 2 FAILED: {e}")
        raise Exception(f"Failed to generate wiki files: {e}")

    # Step 3: Extract relationships from documents for knowledge graph
    logging.info(f"[WIKI] Step 3: Extracting relationships from documents...")
    relationships = []
    try:
        # Combine all document text for relationship extraction
        combined_text = "\n\n".join(all_docs[:10])  # Use first 10 docs to avoid token limits
        
        if orchestrator:
            relationships = orchestrator.extract_relationships(combined_text)
            logging.info(f"[WIKI] Step 3 SUCCESS: Extracted {len(relationships)} relationships.")
        else:
            logging.warning(f"[WIKI] Step 3 SKIPPED: Orchestrator not available for relationship extraction.")
    except Exception as e:
        logging.warning(f"[WIKI] Step 3 WARNING: Relationship extraction failed: {e}. Continuing without graph data.")

    # Step 4: Save relationships to Neo4j graph database
    logging.info(f"[WIKI] Step 4: Saving relationships to graph database...")
    try:
        if relationships:
            graph_success = _save_relationships_to_graph(project_id, relationships)
            if graph_success:
                logging.info(f"[WIKI] Step 4 SUCCESS: Graph database updated with {len(relationships)} relationships.")
            else:
                logging.warning(f"[WIKI] Step 4 WARNING: Graph database update failed. Continuing.")
        else:
            logging.info(f"[WIKI] Step 4 SKIPPED: No relationships to store.")
    except Exception as e:
        logging.warning(f"[WIKI] Step 4 WARNING: Graph storage failed: {e}. Continuing.")

    # Step 5: Save files using filesystem_server
    logging.info(f"[WIKI] Step 5: Saving files via filesystem_server...")
    saved_count = 0
    try:
        for file_data in generated_files:
            save_payload = {
                "project_id": project_id,
                "file_path": f"wiki/{file_data.get('filename', 'unknown.md')}",
                "content": file_data.get('content', '')
            }
            save_resp = requests.post(
                f"{FILESYSTEM_SERVER_URL}/save_file",
                json=save_payload,
                headers={'X-User-ID': user_id},
                timeout=10
            )
            if save_resp.status_code == 200:
                saved_count += 1
                logging.debug(f"[WIKI] Saved {file_data.get('filename', 'unknown')}")
        
        logging.info(f"[WIKI] Step 5 SUCCESS: Saved {saved_count}/{len(generated_files)} files.")
    except Exception as e:
        logging.error(f"[WIKI] Step 5 FAILED: {e}")
        raise Exception(f"Failed to save generated files: {e}")

    # Step 6: Create Git snapshot
    logging.info(f"[WIKI] Step 6: Creating Git snapshot...")
    try:
        git_resp = requests.post(
            f"{GIT_SERVER_URL}/snapshot/{project_id}",
            json={
                "user_id": user_id,
                "message": f"Auto-generated wiki with {saved_count} files and {len(relationships)} relationships."
            },
            timeout=15
        )
        git_resp.raise_for_status()
        snapshot_id = git_resp.json().get('snapshot_id', 'N/A')
        logging.info(f"[WIKI] Step 6 SUCCESS: Snapshot created: {snapshot_id}")
    except Exception as e:
        # This step failing is not critical; we log but don't fail the whole job
        logging.warning(f"[WIKI] Step 6 WARNING: Git snapshot failed: {e}. Continuing.")

    # Success!
    logging.info(f"[WIKI] Wiki generation completed for project {project_id}")
    return {
        "files_created": saved_count,
        "relationships_extracted": len(relationships),
        "entities_processed": len(generated_files),
        "message": f"Successfully generated {saved_count} wiki files with {len(relationships)} relationship triples."
    }


# --- WIKI Generation Endpoint ---

@blp_jobs.route('/project/<string:project_id>/generate_wiki')
class GenerateWiki(MethodView):
    """Start a background wiki/report generation job."""

    @blp_jobs.doc(
        description="Initiates a background job to generate a comprehensive wiki report. Admin-only, requires $1.00 minimum balance.",
        summary="Generate a comprehensive wiki report for a project."
    )
    @blp_jobs.response(202, WikiGenerationResponseSchema)
    def post(self, project_id):
        """Start a background wiki/report generation job."""
        auth_data = _get_user_from_request(request)
        if not auth_data or auth_data['role'] != 'admin':
            abort(403, message="Only project admins can run reports.")
        
        user_id = auth_data['user_id']
        
        # 1. Check API pool balance BEFORE starting the job
        user_balance_credits = get_user_balance(user_id)  # Now returns Credits
        
        if user_balance_credits is None or user_balance_credits < WIKI_JOB_MIN_BALANCE_CREDITS:
            actual_balance = user_balance_credits if user_balance_credits is not None else 0
            logger.warning(f"User {user_id} tried to start wiki job with insufficient balance ({actual_balance} Credits).")
            abort(402, message=f"Insufficient balance. This report requires a minimum balance of {WIKI_JOB_MIN_BALANCE_CREDITS} Credits.")
        
        # 2. Create the job "receipt"
        job_id = job_manager.create_job(
            project_id=project_id, 
            user_id=user_id, 
            job_type="wiki_generation"
        )
        
        logger.info(f"[WIKI] Job {job_id} created for project {project_id} by user {user_id}")
        
        # 3. Start the background task
        job_manager.run_async(
            job_id, 
            _run_wiki_generation_task, 
            project_id, 
            user_id
        )
        
        # 4. Return immediately with 202 Accepted
        return {
            "message": "Wiki generation has started.",
            "job_id": job_id,
            "status_url": f"/jobs/{job_id}"
        }


# --- Admin & Monitoring Endpoints ---

@blp_admin.route('/costs')
class AdminCosts(MethodView):
    """Get aggregate LLM cost summary."""

    @blp_admin.doc(
        description="Admin-only endpoint that returns a real-time aggregate cost summary across all LLM client instances.",
        summary="Get aggregate LLM cost summary."
    )
    @blp_admin.response(200, CostSummarySchema)
    def get(self):
        """Get aggregate LLM cost summary."""
        # 1. AUTHENTICATION (Must be an admin)
        auth_data = _get_user_from_request(request)
        if not auth_data or not auth_data['valid'] or auth_data['role'] != 'admin':
            logging.warning(f"Failed admin cost summary access attempt.")
            abort(403, message="You do not have permission to access this resource.")

        # 2. Get Summary from the Aggregator
        summary = cost_aggregator.get_aggregate_cost()
        
        return summary


# *** NOW register blueprints after ALL routes are defined ***
api.register_blueprint(blp_chat)
api.register_blueprint(blp_jobs)
api.register_blueprint(blp_admin)

# --- Helper Functions ---

def get_user_id_from_request(req):
    """
    Extract and verify user ID from request.
    
    First tries to get Bearer token from Authorization header,
    then verifies it with the auth server.
    Falls back to DEV_MOCK_USER_ID in development mode.
    
    Returns:
        str: User ID if authenticated
        None: If authentication fails or no valid token
    """
    # 1. Try Bearer token from Authorization header
    auth_header = req.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        try:
            resp = requests.post(
                f"{AUTH_SERVER_URL}/verify_token",
                json={"token": token},
                timeout=3
            )
            if resp.ok:
                user_data = resp.json()
                return user_data.get("user_id")
            return None
        except requests.RequestException:
            return None
    
    # 2. Try auth_token from cookie (for browser requests)
    token = req.cookies.get('auth_token')
    if token:
        try:
            auth_header = f"Bearer {token}"
            resp = requests.post(
                f"{AUTH_SERVER_URL}/verify_token",
                headers={"Authorization": auth_header},
                timeout=3
            )
            if resp.ok:
                user_data = resp.json()
                return user_data.get("user_id")
            return None
        except requests.RequestException:
            return None
    
    # 3. Development fallback - only if no auth header or cookie
    if os.getenv('DEV_MODE') == 'true':
        mock_user_id = os.getenv('DEV_MOCK_USER_ID', 'dev-mock-user-1')
        logging.debug(f"Dev mode: using mock user {mock_user_id}")
        return mock_user_id
    
    return None

def _get_user_from_request(request) -> Optional[Dict[str, Any]]:
    """
    Helper to call the Auth Server and verify the user's token,
    which is now stored in a secure HttpOnly cookie or Bearer token.
    
    In development mode (when DEV_MODE=true), uses a fixed mock user ID
    to preserve job ownership across requests.
    
    Returns full user data dict for permission checks.
    """
    user_id = get_user_id_from_request(request)
    if not user_id:
        return None
    
    # For now, return a basic user dict with the user_id
    # If we need role info, we'd fetch it from the auth server
    return {
        'user_id': user_id,
        'valid': True,
        'role': 'admin' if user_id.startswith('dev-') else 'user',
        'guest_projects': []
    }

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

def get_user_balance(user_id: str) -> Optional[int]:
    """
    Gets the user's current API pool balance in Credits.
    
    Returns:
        int: The user's balance in Credits on success.
        None: On any failure (e.g., connection error, non-200 status).
              This signals the frontend and internal logic to fail-open.
    """
    try:
        resp = requests.get(
            f"{BILLING_SERVER_URL}/balance/{user_id}",
            timeout=5
        )
        if resp.status_code == 200:
            dollar_balance = float(resp.json().get('balance', 0.0))
            # Convert dollars to Credits (10,000 Credits = $1.00)
            return int(dollar_balance * 10000)
        
        # Log non-200 status as a warning
        logging.warning(f"Billing server returned non-200 status ({resp.status_code}) for user {user_id}: {resp.text}")
    
    except Exception as e:
        # Log connection errors, timeouts, etc.
        logging.error(f"Failed to connect to billing server for user {user_id}: {e}", exc_info=True)
    
    return None  # Return None on any failure (fail-open signal)

def deduct_cost(user_id: str, job_id: str, cost: float, description: str):
    """Tells the billing server to log a transaction and deduct cost."""
    try:
        resp = requests.post(f"{BILLING_SERVER_URL}/deduct", json={
            "user_id": user_id,
            "cost": cost,
            "job_id": job_id,
            "description": description
        }, timeout=2.0)
        if resp.status_code != 200:
            raise Exception(f"Billing server returned {resp.status_code}")
    except Exception as e:
        logging.error(f"Failed to deduct cost for {user_id}: {e}. Logging for reconciliation.")
        failed_tx_logger.log_failure(user_id, job_id, cost, description)

def get_triage_data(user_query: str, project_id: str) -> TriageData:
    """
    Call 1: Triage. Determines intent, knowledge source, and memory needs.
    
    Uses Pydantic validation to ensure the LLM output is type-safe and complete.
    
    Args:
        user_query: The user's natural language query
        project_id: Project identifier for context
    
    Returns:
        TriageData object with validated intent, knowledge_source, and requires_memory
    
    Raises:
        Returns safe defaults on any validation or API error
    """
    # Safe fallback object
    fallback_data = TriageData(
        intent="app_support",
        knowledge_source="CAUDEX_SUPPORT_KB",
        requires_memory=False
    )
    
    prompt = AI_ROUTER_PROMPT_v4.format(user_query=user_query, project_id=project_id)
    
    try:
        result_dict = triage_client.chat(prompt)
        response_text = result_dict.get('response', '').strip()
        
        # 1. Try to validate the raw JSON string using Pydantic
        data = TriageData.model_validate_json(response_text)
        logging.info(f"✓ Triage validated: intent={data.intent}, source={data.knowledge_source}, memory={data.requires_memory}")
        return data
        
    except ValidationError as e:
        # 2. The LLM's JSON was malformed (e.g., missing required key, wrong type)
        logging.warning(f"[TRIAGE] Pydantic validation failed: {e}. Defaulting to safe fallback.")
        logging.debug(f"[TRIAGE] Raw response was: {response_text[:200]}")
        return fallback_data
    
    except Exception as e:
        # 3. A different error occurred (API call failure, etc.)
        logging.error(f"[TRIAGE] Unexpected error during triage: {e}. Defaulting to safe fallback.", exc_info=True)
        return fallback_data

def resolve_memory(triage_data: TriageData, user_query: str, user_id: str, project_id: str) -> Tuple[str, str, List[Dict]]:
    """
    Handles Step 1.5 (Memory & Rewrite).
    
    Args:
        triage_data: Validated TriageData from Call 1
        user_query: Original user query
        user_id: User identifier
        project_id: Project identifier
    
    Returns:
        (rewritten_query, chat_history_for_prompt, chat_history_for_llm)
    """
    if not triage_data.requires_memory:
        return user_query, "", []  # No rewrite needed, no history list

    logging.info(f"Query '{user_query}' requires memory. Fetching history...")
    history_list = session_manager.get_recent_history(project_id, user_id)
    chat_history_str = session_manager.format_history_for_prompt(history_list)
    
    # Call 1.5: Rewrite query using coreference resolution
    rewrite_prompt = COREF_RESOLUTION_PROMPT.format(
        chat_history=chat_history_str,
        user_query=user_query
    )
    result = triage_client.chat(rewrite_prompt)  # Use the cheap client
    
    rewritten_query = result['response'].strip()
    logging.info(f"Query rewritten: '{user_query}' -> '{rewritten_query}'")
    
    # Return all three formats
    return rewritten_query, chat_history_str, history_list

def get_chroma_context(query: str, collection_name: str) -> Tuple[Optional[str], bool]:
    """
    Calls the Chroma server to get RAG context.
    
    Returns:
        (context_str, True) on success with context.
        ("", True) if no context was needed.
        (None, False) on failure.
    """
    if not collection_name or collection_name == "NONE":
        return "", True  # Success, but no context needed
    
    try:
        resp = requests.post(
            f"{CHROMA_SERVER_URL}/query",
            json={"collection_name": collection_name, "query_texts": [query], "n_results": 5},
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
            return context_str, True  # Success with context
        else:
            # Handle non-200 status codes
            logging.warning(f"Chroma server returned non-200 status: {resp.status_code} {resp.text}")
            return None, False  # Failure
    except Exception as e:
        logging.error(f"Failed to get context from Chroma: {e}")
        return None, False  # Failure

def _generate_cypher_query(user_query: str) -> Optional[str]:
    """
    Use AI to generate a Cypher query from a natural language question.
    This allows semantic understanding of graph patterns.
    
    Args:
        user_query: Natural language question from the user
    
    Returns:
        Cypher query string, or None if generation fails
    """
    prompt = f"""You are a Neo4j Cypher query expert. Convert the user's natural language question into a Cypher query.

User Question: {user_query}

Return ONLY the Cypher query, nothing else. Example format:
MATCH (e1:Entity)-[r]->(e2:Entity) WHERE e1.name CONTAINS 'keyword' RETURN e1.name, r.type, e2.name

Your Cypher query:"""
    
    try:
        result = triage_client.chat(prompt)
        cypher_query = result.get('response', '').strip()
        if cypher_query:
            logging.debug(f"[GRAPH] Generated Cypher: {cypher_query}")
            return cypher_query
    except Exception as e:
        logging.warning(f"[GRAPH] Failed to generate Cypher query: {e}")
    
    return None

def get_graph_context(user_query: str, project_id: str) -> Tuple[str, bool]:
    """
    Query the Neo4j graph database for relationship-based context.
    
    Args:
        user_query: User's natural language question
        project_id: Project ID for scoping graph queries
    
    Returns:
        (context_str, True) on success (even if empty)
        (context_str, False) on connection failure (still returns empty string for graceful degradation)
    """
    driver = _get_graph_driver()
    if not driver:
        logging.warning("[GRAPH] Graph database unavailable, skipping graph context.")
        return "", True  # Graceful degradation: return empty but mark as "success"
    
    try:
        # Generate a Cypher query from the user's question
        cypher_query = _generate_cypher_query(user_query)
        if not cypher_query:
            logging.debug("[GRAPH] No Cypher query generated.")
            return "", True
        
        # Add project scoping to the query if not already present
        if "project_id" not in cypher_query:
            cypher_query += f" WHERE (e1.project_id = '{project_id}' OR e2.project_id = '{project_id}')"
        
        with driver.session() as session:
            results = session.run(cypher_query)
            records = results.data()
            
            if not records:
                logging.debug(f"[GRAPH] Query returned no results: {cypher_query}")
                return "", True
            
            # Format results as readable context
            context_lines = ["[Knowledge Graph Relationships:]\n"]
            for record in records[:10]:  # Limit to 10 results
                # Records are dictionaries; convert to readable format
                line = " → ".join(str(v) for v in record.values())
                context_lines.append(f"  • {line}")
            
            graph_context = "\n".join(context_lines)
            logging.info(f"[GRAPH] Retrieved {len(records)} relationship records.")
            return graph_context, True
            
    except Exception as e:
        logging.warning(f"[GRAPH] Failed to query graph: {e}")
        return "", True  # Graceful degradation
    finally:
        driver.close()

# --- Core Chat Endpoint ---

# NOTE: The /chat endpoint below is currently using @app.route with flasgger documentation.
# Flask-smorest integration (blp_chat.route, MethodView) is prepared via blueprints (blp_chat, blp_jobs, blp_admin)
# and Marshmallow schemas (ChatRequestSchema, ChatResponseSchema, etc.) defined above.
# 
# Migration Path:
# 1. Test the new Marshmallow schemas by using them in @blp_chat.route endpoints


if __name__ == '__main__':
    import os
    if os.getenv('FLASK_ENV') == 'development':
        print("--- Caudex Pro AI Router (The Brain) ---")
        print("Ensure all microservices (Auth, Billing, Chroma, Filesystem, Git) are running.")
        print("Running on http://localhost:5000")
        app.run(debug=True, port=5000)
    else:
        print("Use gunicorn for production: gunicorn -w 4 -b 0.0.0.0:5000 backend.app:app")