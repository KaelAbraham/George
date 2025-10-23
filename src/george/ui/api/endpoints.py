import os
import logging
import math # <-- ADDED for ceiling function
from pathlib import Path
from flask import Blueprint, jsonify, request, current_app, flash, redirect, url_for
from firebase_admin import auth, firestore # <-- ADDED firestore
import firebase_admin # <-- ADDED
from ..auth.auth_client import verify_firebase_token

# --- Import backend modules ---
try:
    from ...knowledge_extraction.orchestrator import KnowledgeExtractor
    from ...llm_integration import create_george_ai, GeorgeAI
    from ...project_manager import ProjectManager
    from ...parsers.parsers import read_manuscript_file # <-- ADDED parser
except ImportError as e:
    logging.critical(f"FATAL: Could not import core backend modules in endpoints.py: {e}")
    # Define dummy classes if import fails to allow app to at least load
    class KnowledgeExtractor:
         def __init__(self, *args, **kwargs): pass
         def analyze_and_get_context(self, *args, **kwargs): return None, "Extractor module not loaded."
         def generate_knowledge_base(self, *args, **kwargs): return {'success': False, 'error': 'Extractor module not loaded.'}
    class GeorgeAI:
        def __init__(self, *args, **kwargs): self.model = "dummy"
        def chat(self, *args, **kwargs): return {'success': False, 'response': None, 'error': "LLM Integration module failed to load."}
    class ProjectManager:
        def __init__(self, *args, **kwargs): pass
        def list_projects(self, *args, **kwargs): return []
        def load_project(self, *args, **kwargs): return None
        def get_project_path(self, *args, **kwargs): return "."
        def add_manuscript_file(self, *args, **kwargs): pass
        def update_project_status(self, *args, **kwargs): pass
    def create_george_ai(*args, **kwargs): return GeorgeAI()
    def read_manuscript_file(*args, **kwargs): raise ImportError("Parsers module failed to load.")


api_bp = Blueprint('api', __name__, url_prefix='/api')
logger = logging.getLogger(__name__)

# --- Initialize Project Manager ---
try:
    project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    uploads_base_dir = project_root / 'src' / 'data' / 'uploads'
    pm = ProjectManager(base_dir=str(uploads_base_dir))
    logger.info(f"ProjectManager initialized with base directory: {uploads_base_dir}")
except Exception as init_e:
    logger.critical(f"Failed to initialize ProjectManager in endpoints.py: {init_e}", exc_info=True)
    class DummyPM: # Dummy class
        def load_project(self, *args, **kwargs): return None
        def get_project_path(self, *args, **kwargs): return "."
        def update_project_status(self, *args, **kwargs): pass
    pm = DummyPM()

# --- Load Georgeification Prompt ---
GEORGEIFY_PROMPT = ""
try:
    current_dir = Path(__file__).parent.parent.parent # src/george/ui -> src/george
    prompt_path = current_dir.parent / "prompts" / "george_operational_protocol.txt"
    with open(prompt_path, 'r', encoding='utf-8') as f:
        GEORGEIFY_PROMPT = f.read()
    if not GEORGEIFY_PROMPT or GEORGEIFY_PROMPT.startswith("ERROR:"):
        raise ValueError("Georgeification prompt file is empty or contains placeholder error.")
    logger.info("Successfully loaded Georgeification prompt.")
except Exception as e:
    logger.error(f"FATAL: Error loading Georgeification prompt file: {e}", exc_info=True)
    GEORGEIFY_PROMPT = "ERROR: Could not load Georgeification prompt."

# --- Get Firestore Client ---
try:
    if not firebase_admin._apps:
        raise Exception("Firebase Admin SDK not initialized.")
    db = firestore.client()
    logger.info("Firestore client initialized successfully.")
except Exception as e:
    logger.critical(f"Failed to get Firestore client in endpoints.py: {e}")
    db = None

# --- Georgeify Function (No Changes) ---
def georgeify_response(original_question: str, raw_ai_answer: str, george_formatter_ai: GeorgeAI, sources: list = []) -> str:
    # ... (This function remains the same as before) ...
    if GEORGEIFY_PROMPT.startswith("ERROR:"):
        logger.error("Georgeification cannot proceed because the protocol prompt failed to load.")
        raw_output = f"Raw Answer: {raw_ai_answer}"
        if sources:
             source_tags = [f"$^{src}$" for src in sources]
             raw_output += f"\n\n*Sources: {', '.join(source_tags)}*"
        return raw_output

    formatter_prompt = f"{GEORGEIFY_PROMPT}\n\n"
    formatter_prompt += f"Original User Question: \"{original_question}\"\n"
    formatter_prompt += f"Raw AI Answer to Format:\n---\n{raw_ai_answer}\n---\n\n"
    formatter_prompt += "Formatted Response:"

    try:
        result = george_formatter_ai.chat(formatter_prompt, temperature=0.1, timeout=15)
        if result['success']:
            formatted_text = result['response'].strip()
            if sources and "$^" not in formatted_text: 
                source_tags = [f"$^{src}$" for src in sources]
                formatted_text += f"\n\n*Sources: {', '.join(source_tags)}*"
            return formatted_text
        else:
            error_msg = result.get('error', 'Unknown formatting error')
            logger.error(f"Georgeification AI call failed: {error_msg}")
            raw_output = f"(Formatting Error: {error_msg})\nRaw Answer: {raw_ai_answer}"
            if sources:
                 source_tags = [f"$^{src}$" for src in sources]
                 raw_output += f"\n\n*Sources: {', '.join(source_tags)}*"
            return raw_output
    except Exception as e:
        logger.error(f"Error during Georgeification: {e}", exc_info=True)
        raw_output = f"(Formatting Exception)\nRaw Answer: {raw_ai_answer}"
        if sources:
             source_tags = [f"$^{src}$" for src in sources]
             raw_output += f"\n\n*Sources: {', '.join(source_tags)}*"
        return raw_output

# --- Project Chat Endpoint (No Changes) ---
@api_bp.route('/projects/<project_id>/chat', methods=['POST'])
@verify_firebase_token()
def project_chat(project_id):
    # ... (This function remains the same as before) ...
    data = request.get_json()
    question = data.get('question')
    user_info = request.user 
    if not question: return jsonify({"error": "No question provided"}), 400
    logger.info(f"Received chat request for project '{project_id}'")
    try:
        router_model_name = "gemini-flash-lite"
        formatter_model_name = "gemini-flash-lite"
        default_response_model_name = "gemini-2.0-flash" 
        ai_router = create_george_ai(model=router_model_name, use_cloud=True)
        ai_formatter = create_george_ai(model=formatter_model_name, use_cloud=True)
        ai_responder = create_george_ai(model=default_response_model_name, use_cloud=True)
        project_root_path_str = pm.get_project_path(project_id)
        if not project_root_path_str or not os.path.exists(project_root_path_str):
            return jsonify({"error": f"Project '{project_id}' not found."}), 404
        from ...knowledge_extraction.query_analyzer import QueryAnalyzer
        analyzer = QueryAnalyzer(ai_router, project_path=project_root_path_str)
        analysis_result, context_str = analyzer.build_context_for_query(question)
        if analysis_result is None:
            final_answer = georgeify_response(question, context_str, ai_formatter)
            return jsonify({"answer": final_answer}) 
        classification = analysis_result.get("classification")
        sources = analysis_result.get("resources", [])
        if classification.startswith("FUNC_"):
            raw_answer = "Functional intent recognized." 
            if classification == "FUNC_HELP":
                raw_answer = context_str if context_str else "Could not find relevant help information."
                sources = []
            elif classification == "FUNC_ACCOUNT":
                raw_answer = "Account management features are currently under development."
            elif classification == "FUNC_KB_WRITE":
                raw_answer = "Ability to modify the knowledge base via chat is under development."
            elif classification == "FUNC_PROJECT_MGMT":
                 raw_answer = "Project management via chat is under development."
            elif classification == "FUNC_FEEDBACK":
                 raw_answer = "Thank you for your feedback."
            else:
                 raw_answer = "This function is not yet implemented."
            final_answer = georgeify_response(question, raw_answer, ai_formatter)
            return jsonify({"answer": final_answer})
        if classification in ["TIER_3", "TIER_4"]:
            response_model_name = "gemini-2.5-flash"
            ai_responder = create_george_ai(model=response_model_name, use_cloud=True)
        responder_result = ai_responder.chat(prompt=question, project_context=context_str, temperature=0.5)
        if not responder_result['success']:
            error_msg = responder_result.get('error', 'Unknown responder error')
            final_answer = georgeify_response(question, f"Error processing request: {error_msg}", ai_formatter)
            return jsonify({"answer": final_answer})
        raw_answer = responder_result['response']
        source_filenames = [Path(s).name for s in sources]
        final_answer = georgeify_response(question, raw_answer, ai_formatter, source_filenames)
        return jsonify({"answer": final_answer})
    except Exception as e:
        logger.error(f"Error in project_chat endpoint: {e}", exc_info=True)
        try:
             ai_formatter = create_george_ai(model="gemini-flash-lite", use_cloud=True)
             final_answer = georgeify_response(question, f"An unexpected server error occurred: {e}", ai_formatter)
             return jsonify({"answer": final_answer})
        except:
             return jsonify({"error": f"An unexpected server error occurred: {e}"}), 500

# --- UPDATED: process_manuscript Endpoint ---
@api_bp.route('/projects/<project_id>/process', methods=['POST'])
@verify_firebase_token()
def process_manuscript(project_id):
    """
    Triggers the full Knowledge Base Generation (AKG) pipeline for a project.
    Checks and deducts credits before starting.
    """
    logger.info(f"Received request to generate KB for project: {project_id}")
    
    if not db:
        logger.critical("Firestore client (db) is not initialized in endpoints.py.")
        return jsonify({"status": "error", "error": "Database connection is not configured."}), 500

    # Get user ID from the auth token, and customer profile from the request context
    user_auth_data = request.user_auth # From decorator
    customer_profile = request.user   # From decorator
    user_id = user_auth_data['uid']
    
    try:
        # 1. Load Project & Manuscript
        project_data = pm.load_project(project_id)
        if not project_data:
            return jsonify({'status': 'error', 'error': 'Project not found'}), 404

        manuscript_filenames = project_data.get('manuscript_files', [])
        if not manuscript_filenames:
            return jsonify({'status': 'error', 'error': 'No manuscript files found. Please upload a file first.'}), 400

        manuscript_filename = manuscript_filenames[0] # Process first file
        project_path_str = pm.get_project_path(project_id)
        manuscript_path = os.path.join(project_path_str, manuscript_filename)

        if not os.path.exists(manuscript_path):
             return jsonify({'status': 'error', 'error': f'Manuscript file {manuscript_filename} not found.'}), 404

        # 2. Calculate Word Count & Credit Cost
        logger.info(f"Calculating word count for: {manuscript_path}")
        file_content = read_manuscript_file(str(manuscript_path))
        word_count = len(file_content.split())
        # Calculate credits: 1 per 10,000 words
        credits_needed = math.ceil(word_count / 10000)
        logger.info(f"Word count: {word_count}. Credits needed: {credits_needed}")

        # 3. Check and Deduct Credits Atomically
        customer_ref = db.collection('customers').document(user_id)
        
        @firestore.transactional
        def check_and_deduct_credits(transaction, customer_ref, amount_to_deduct):
            snapshot = customer_ref.get(transaction=transaction)
            if not snapshot.exists:
                raise Exception(f"Customer profile not found for user {user_id}.")
            
            current_balance = snapshot.get('creditBalance')
            if current_balance is None:
                raise Exception("Credit balance not found in customer profile.")

            if current_balance < amount_to_deduct:
                # Raise a specific error for insufficient credits
                raise ValueError(f"Insufficient credits. You need {amount_to_deduct}, but you only have {current_balance}.")
            
            # Sufficient credits, proceed with deduction
            new_balance = current_balance - amount_to_deduct
            transaction.update(customer_ref, {
                'creditBalance': new_balance
            })
            logger.info(f"Successfully deducted {amount_to_deduct} credits for user {user_id}. New balance: {new_balance}")
            return new_balance

        logger.info(f"Attempting to deduct {credits_needed} credits for user {user_id}...")
        transaction = db.transaction()
        new_balance = check_and_deduct_credits(transaction, customer_ref, credits_needed)

    except ValueError as ve: # Catch insufficient credits
        logger.warning(f"Insufficient credits for user {user_id}: {ve}")
        return jsonify({'status': 'error', 'error': str(ve)}), 403 # 403 Forbidden
    except Exception as e:
        logger.error(f"Error during credit check/deduction for {project_id}: {e}", exc_info=True)
        return jsonify({"status": "error", "error": f"An error occurred during credit check: {e}"}), 500

    # --- 4. Proceed with KB Generation (If credits were successfully deducted) ---
    try:
        project_path = Path(project_path_str)
        knowledge_base_path = project_path / "knowledge_base"
        knowledge_base_path.mkdir(parents=True, exist_ok=True)
        
        ai_kb_generator = create_george_ai(model="gemini-2.5-pro-latest", use_cloud=True) 
        
        pm.update_project_status(project_id, "processing")
        
        extractor = KnowledgeExtractor(ai_kb_generator, project_path=project_path_str)
        
        logger.info(f"Starting KB generation for {project_id} using {manuscript_filename}...")
        generation_result = extractor.generate_knowledge_base(manuscript_filename) 

        if generation_result.get('success'):
            logger.info(f"KB generation successful for {project_id}.")
            pm.update_project_status(project_id, "ready") 
            
            entity_count = generation_result.get('entities_found', 0)
            files_created = generation_result.get('files_created', 0)
            message = f"{entity_count} entities identified, {files_created} knowledge files created."

            return jsonify({
                'status': 'success', 
                'message': message,
                'new_credit_balance': new_balance
            })
        else:
            raise Exception(generation_result.get('error', 'Unknown generation error'))

    except Exception as e:
        # --- 5. Rollback Credits on Failure ---
        logger.error(f"KB generation failed for {project_id}: {e}. Refunding credits.", exc_info=True)
        try:
            customer_ref.update({"creditBalance": firestore.Increment(credits_needed)})
            logger.info(f"Credits refunded for user {user_id}. Amount: {credits_needed}")
            refund_message = "Credits have been refunded."
        except Exception as refund_e:
            logger.critical(f"FATAL: FAILED TO REFUND {credits_needed} CREDITS for user {user_id}: {refund_e}")
            refund_message = "CRITICAL: Credit refund failed. Please contact support."
        
        pm.update_project_status(project_id, "error")
        return jsonify({ 
            'status': 'error', 
            'error': f"KB generation failed: {e}. {refund_message}" 
        }), 500

# --- NEW: Endpoint for creating credit purchase sessions ---
@api_bp.route('/credits/create-checkout-session', methods=['POST'])
@verify_firebase_token()
def create_credit_checkout():
    """
    Creates a Stripe Checkout session by writing a document to Firestore
    that the 'Run Payments with Stripe' extension is listening to.
    """
    logger.info("Received request to create credit checkout session.")
    user_id = request.user_auth['uid'] # Get user ID from decorator
    
    if not db:
         return jsonify({"error": "Database connection is not configured."}), 500

    try:
        data = request.get_json()
        price_id = data.get('priceId') 
        if not price_id:
            return jsonify({"error": "priceId is required."}), 400
        
        # This is the path the Stripe Extension listens to:
        # customers/{uid}/checkout_sessions
        checkout_session_ref = db.collection('customers').document(user_id) \
                                 .collection('checkout_sessions').document()
        
        # Write the document to trigger the extension
        checkout_session_ref.set({
            "price": price_id,
            "mode": "payment", # 'payment' for one-time purchases
            "success_url": request.host_url + url_for('project_manager.dashboard'), # Redirect to dashboard
            "cancel_url": request.host_url + url_for('billing.billing_page'), # Return to billing page
        })

        # The extension will now asynchronously update this document
        # with a 'url' or 'error' field.
        # We return the ID of this document so the frontend can listen to it.
        return jsonify({"sessionId": checkout_session_ref.id})

    except Exception as e:
        logger.error(f"Error creating checkout session for user {user_id}: {e}", exc_info=True)
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500

# --- Health Check (keep as is) ---
@api_bp.route('/health')
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'Standalone George UI API'
    })