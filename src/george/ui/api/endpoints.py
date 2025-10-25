import os
import logging
import math
import re
import threading
import json
from pathlib import Path
from flask import Blueprint, jsonify, request, current_app, flash, redirect, url_for
from firebase_admin import auth, firestore
import firebase_admin

# --- Core Application Imports ---
# We assume these modules are in the correct path relative to 'src/george/ui/'
try:
    from ..auth.auth_client import verify_firebase_token
    from ...project_manager import ProjectManager
    from ...knowledge_extraction.orchestrator import KnowledgeExtractor
    from ...knowledge_extraction.query_analyzer import QueryAnalyzer
    from ...llm_integration import create_george_ai, GeorgeAI
    from ...parsers.parsers import read_manuscript_file
    from ...knowledge_base.structured_db import StructuredDB
except ImportError:
    # This fallback helps the app load, but logs a critical error
    logging.critical("FATAL ERROR: Could not import core backend modules in endpoints.py. Check your PYTHONPATH.")
    # Define dummy classes so the file can be parsed
    def verify_firebase_token():
        def decorator(f):
            def wrapper(*args, **kwargs): return jsonify({"error": "Auth decorator not loaded"}), 500
            wrapper.__name__ = f.__name__ + '_dummy_decorated'
            return wrapper
        return decorator
    class KnowledgeExtractor: pass
    class GeorgeAI: pass
    class ProjectManager: pass
    class StructuredDB: pass
    def create_george_ai(*args, **kwargs): pass
    def read_manuscript_file(*args, **kwargs): pass

# --- API Blueprint Setup ---
api_bp = Blueprint('api', __name__, url_prefix='/api')
logger = logging.getLogger(__name__)

# --- Initialize Managers ---
# These are initialized once when the blueprint is loaded.
try:
    project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    uploads_base_dir = project_root / 'src' / 'data' / 'uploads'
    pm = ProjectManager(base_dir=str(uploads_base_dir))
    
    # Use a single, central database
    db_path = project_root / 'src' / 'data' / 'george.db'
    db = StructuredDB(db_path=str(db_path))
    
    logger.info(f"ProjectManager and StructuredDB initialized in API.")
except Exception as init_e:
    logger.critical(f"Failed to initialize managers in endpoints.py: {init_e}", exc_info=True)
    pm = None 
    db = None

# --- Load Prompt Files ---
def load_prompt_file(filename: str) -> str:
    """Helper to load a prompt file from the /prompts directory."""
    try:
        current_dir = Path(__file__).parent.parent.parent # src/george/ui -> src/george
        prompt_path = current_dir.parent / "prompts" / filename
        if not prompt_path.exists():
            raise FileNotFoundError(f"{filename} not found at {prompt_path}")
        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt_text = f.read()
        if not prompt_text:
            raise ValueError(f"{filename} is empty.")
        logger.info(f"Successfully loaded prompt: {filename}")
        return prompt_text
    except Exception as e:
        logger.error(f"FATAL: Error loading prompt {filename}: {e}", exc_info=True)
        return f"ERROR: Could not load prompt {filename}."

GEORGEIFY_PROMPT = load_prompt_file("george_operational_protocol.txt")
STANDARD_CONTINUITY_PROMPT = load_prompt_file("standard_continuity_prompt.txt")
DEEP_CONTINUITY_PROMPT = load_prompt_file("deep_continuity_prompt.txt")
FOUNDATIONAL_CONSISTENCY_PROMPT = load_prompt_file("foundational_consistency_prompt.txt")

# --- Get Firestore Client ---
try:
    if not firebase_admin._apps:
        raise Exception("Firebase Admin SDK not initialized.")
    firestore_db = firestore.client()
    logger.info("Firestore client initialized successfully in API.")
except Exception as e:
    logger.critical(f"Failed to get Firestore client in endpoints.py: {e}")
    firestore_db = None

# === HELPER FUNCTIONS ==========================================

def georgeify_response(original_question: str, raw_ai_answer: str, george_formatter_ai: GeorgeAI, sources: list = []) -> str:
    """Formats a raw AI response into George's voice using the operational protocol."""
    if GEORGEIFY_PROMPT.startswith("ERROR:"):
        logger.error("Georgeification cannot proceed because the protocol prompt failed to load.")
        return f"Error: Could not format response.\nRaw Answer: {raw_ai_answer}"

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
            return f"(Formatting Error: {error_msg})\nRaw Answer: {raw_ai_answer}"
    except Exception as e:
        logger.error(f"Error during Georgeification: {e}", exc_info=True)
        return f"(Formatting Exception)\nRaw Answer: {raw_ai_answer}"

def _save_chat_summary(user_id: str, project_id: str, question: str, response: str):
    """Summarizes and saves a chat exchange in a background thread."""
    try:
        if not db:
            logger.error("Cannot save chat summary: StructuredDB (db) is not initialized.")
            return
        logger.info(f"Starting background summary for user {user_id}, project {project_id}")
        ai_summarizer = create_george_ai(model="gemini-flash-lite", use_cloud=True)
        summary_prompt = f"""Summarize this Q&A into one concise sentence. Q: "{question}" A: "{response}" Summary:"""
        result = ai_summarizer.chat(summary_prompt, temperature=0.2, timeout=20)
        
        if result['success']:
            summary_text = result['response'].strip()
            # Must create a new DB connection for this thread
            thread_db_path = Path(__file__).resolve().parent.parent.parent.parent.parent / 'src' / 'data' / 'george.db'
            thread_db = StructuredDB(db_path=str(thread_db_path))
            with thread_db:
                thread_db.add_chat_summary(user_id, project_id, question, summary_text)
            logger.info(f"Successfully saved chat summary for user {user_id}.")
        else:
            logger.error(f"Failed to generate summary: {result.get('error')}")
    except Exception as e:
        logger.error(f"Error in background summary thread: {e}", exc_info=True)

def _parse_note_from_query(question: str) -> dict:
    """Parses a 'FUNC_KB_WRITE' query to extract the entity and note content."""
    match = re.search(r"note (to|for) ['\"]?(.+?)['\"]?:\s*(.+)", question, re.IGNORECASE)
    if match:
        return {"entity": match.group(2).strip(), "note": match.group(3).strip()}
    match = re.search(r"attach note to ['\"]?(.+?)['\"]?:\s*(.+)", question, re.IGNORECASE)
    if match:
        return {"entity": match.group(1).strip(), "note": match.group(2).strip()}
    return {}

def _batch_extract_facts(ai_model: GeorgeAI, chunks: list, entity_name: str) -> list:
    """Helper to run batch fact extraction for a list of chunks."""
    fact_timeline = []
    for chunk in chunks:
        fact_prompt = f"From the following text, extract all factual statements, actions, and motivations related ONLY to '{entity_name}'.\n\nText: \"{chunk['chunk_text']}\"\n\nFacts:"
        fact_result = ai_model.chat(fact_prompt, temperature=0.0, timeout=45)
        if fact_result['success']:
            fact_timeline.append(f"Source: {chunk['source_file']}, Location: approx. char {chunk['character_start']}\nFacts: {fact_result['response']}\n")
    return fact_timeline

def _extract_facts_from_kb_file(ai_model: GeorgeAI, file_path: str, concept_name: str) -> str:
    """Helper to read a KB file and use an AI to extract facts."""
    if not Path(file_path).exists():
        return f"No facts found for '{concept_name}' (file not found)."
    try:
        file_content = read_manuscript_file(file_path)
        fact_prompt = f"From the following knowledge base profile for '{concept_name}', extract all key factual statements.\n\nProfile:\n{file_content}"
        result = ai_model.chat(fact_prompt, temperature=0.0, timeout=45)
        return result['response'] if result['success'] else f"Fact extraction failed: {result.get('error')}"
    except Exception as e:
        return f"Error reading KB file: {e}"

# === API ENDPOINTS =============================================

@api_bp.route('/health')
def health_check():
    """Health check endpoint."""
    return jsonify({'status': 'healthy', 'service': 'Standalone George UI API'})

# --- Project Management API ---

@api_bp.route('/projects', methods=['GET'])
@verify_firebase_token()
def list_projects():
    """List all projects for the authenticated user."""
    # Note: Our current PM is file-based and not user-specific.
    # This needs to be adapted for a multi-user environment.
    # For now, it lists all projects in the data folder.
    logger.info("API: Listing all projects")
    try:
        projects = pm.list_projects()
        return jsonify({"projects": projects})
    except Exception as e:
        logger.error(f"Error listing projects: {e}", exc_info=True)
        return jsonify({"error": f"Could not list projects: {e}"}), 500

@api_bp.route('/projects/<project_id>', methods=['GET'])
@verify_firebase_token()
def get_project(project_id):
    """Get details for a specific project."""
    logger.info(f"API: Getting project {project_id}")
    try:
        project = pm.load_project(project_id)
        if not project:
            return jsonify({"error": "Project not found"}), 404
        return jsonify(project)
    except Exception as e:
        logger.error(f"Error getting project {project_id}: {e}", exc_info=True)
        return jsonify({"error": f"Could not get project: {e}"}), 500

# --- Knowledge Base API ---

@api_bp.route('/projects/<project_id>/process', methods=['POST'])
@verify_firebase_token()
def process_manuscript(project_id):
    """Triggers the full AKG pipeline. Checks and deducts credits."""
    logger.info(f"API: Received request to generate KB for project: {project_id}")
    if not firestore_db or not db or not pm:
        return jsonify({"status": "error", "error": "Database/PM not configured."}), 500

    user_id = request.user_auth['uid']
    
    try:
        project_data = pm.load_project(project_id)
        if not project_data:
            return jsonify({'status': 'error', 'error': 'Project not found'}), 404
        manuscript_filenames = project_data.get('manuscript_files', [])
        if not manuscript_filenames:
            return jsonify({'status': 'error', 'error': 'No manuscript files. Please upload a file first.'}), 400

        manuscript_filename = manuscript_filenames[0]
        project_path_str = pm.get_project_path(project_id)
        manuscript_path = os.path.join(project_path_str, manuscript_filename)

        if not os.path.exists(manuscript_path):
             return jsonify({'status': 'error', 'error': f'Manuscript file {manuscript_filename} not found.'}), 404

        file_content = read_manuscript_file(str(manuscript_path))
        word_count = len(file_content.split())
        credits_needed = math.ceil(word_count / 10000)
        logger.info(f"Word count: {word_count}. Credits needed: {credits_needed}")

        customer_ref = firestore_db.collection('customers').document(user_id)
        
        @firestore.transactional
        def check_and_deduct_credits(transaction, customer_ref, amount_to_deduct):
            snapshot = customer_ref.get(transaction=transaction)
            if not snapshot.exists: raise Exception(f"Customer profile not found for user {user_id}.")
            current_balance = snapshot.get('creditBalance')
            if current_balance is None: raise Exception("Credit balance not found.")
            if current_balance < amount_to_deduct:
                raise ValueError(f"Insufficient credits. You need {amount_to_deduct}, but you only have {current_balance}.")
            
            new_balance = current_balance - amount_to_deduct
            transaction.update(customer_ref, {'creditBalance': new_balance})
            return new_balance

        transaction = firestore_db.transaction()
        new_balance = check_and_deduct_credits(transaction, customer_ref, credits_needed)

    except ValueError as ve: # Insufficient credits
        return jsonify({'status': 'error', 'error': str(ve)}), 403
    except Exception as e:
        return jsonify({"status": "error", "error": f"Credit check failed: {e}"}), 500

    try:
        ai_kb_generator = create_george_ai(model="gemini-2.5-pro-latest", use_cloud=True)
        pm.update_project_status(project_id, "processing")
        
        # We need to initialize the extractor with the correct AI and project path
        extractor = KnowledgeExtractor(ai_kb_generator, project_path=project_path_str)
        
        logger.info(f"Starting KB generation for {project_id}...")
        # Run the KB generation
        generation_result = extractor.generate_knowledge_base(manuscript_filename) 

        if generation_result.get('success'):
            pm.update_project_status(project_id, "ready") 
            message = f"{generation_result.get('entities_found', 0)} entities identified, {generation_result.get('files_created', 0)} files created."
            return jsonify({'status': 'success', 'message': message, 'new_credit_balance': new_balance})
        else:
            raise Exception(generation_result.get('error', 'Unknown generation error'))

    except Exception as e:
        logger.error(f"KB generation failed for {project_id}: {e}. Refunding credits.", exc_info=True)
        try:
            customer_ref.update({"creditBalance": firestore.Increment(credits_needed)})
            refund_message = "Credits have been refunded."
        except Exception as refund_e:
            logger.critical(f"FATAL: FAILED TO REFUND {credits_needed} CREDITS for user {user_id}: {refund_e}")
            refund_message = "CRITICAL: Credit refund failed."
        
        pm.update_project_status(project_id, "error")
        return jsonify({ 'status': 'error', 'error': f"KB generation failed: {e}. {refund_message}" }), 500

# --- Chat API ---

@api_bp.route('/projects/<project_id>/chat', methods=['POST'])
@verify_firebase_token()
def project_chat(project_id):
    """Handles a chat message for a specific project."""
    data = request.get_json()
    question = data.get('question')
    user_auth_data = request.user_auth
    user_id = user_auth_data['uid']
    
    if not question: return jsonify({"error": "No question provided"}), 400
    if not db or not pm: return jsonify({"error": "Core services not available."}), 500
    
    try:
        router_model_name = "gemini-flash-lite"
        formatter_model_name = "gemini-flash-lite"
        default_response_model_name = "gemini-2.0-flash" 

        ai_router = create_george_ai(model=router_model_name, use_cloud=True)
        ai_formatter = create_george_ai(model=formatter_model_name, use_cloud=True)
        ai_responder = create_george_ai(model=default_response_model_name, use_cloud=True)
        
        project_root_path_str = pm.get_project_path(project_id)
        if not project_root_path_str:
            return jsonify({"error": f"Project '{project_id}' not found."}), 404
        
        analyzer = QueryAnalyzer(ai_router, project_path=project_root_path_str)
        analysis_result, context_str = analyzer.build_context_for_query(question)

        if analysis_result is None:
            final_answer = georgeify_response(question, context_str, ai_formatter)
            return jsonify({"answer": final_answer}) 

        classification = analysis_result.get("classification")
        sources = analysis_result.get("resources", [])
        
        if classification.startswith("FUNC_"):
            raw_answer = "This function is not yet implemented."
            
            if classification == "FUNC_KB_WRITE":
                note_data = _parse_note_from_query(question)
                entity_name = note_data.get('entity')
                note_text = note_data.get('note')
                
                if entity_name and note_text:
                    try:
                        with db:
                            entity = db.get_entity_by_name(entity_name)
                        if entity:
                            entity_id = entity['id']
                            with db:
                                db.add_entity_note(entity_id, user_id, note_text)
                            raw_answer = f"Note successfully added to '{entity_name}'."
                        else:
                            raw_answer = f"Sorry, I could not find an entity named '{entity_name}'."
                    except Exception as e:
                        raw_answer = f"An error occurred while trying to add the note: {e}"
                else:
                    raw_answer = "I couldn't parse the entity name and note content. Please use the format: 'Add a note to [Entity Name]: [Your note]'."
            
            elif classification == "FUNC_HELP":
                raw_answer = context_str if context_str else "Could not find relevant help information."
                sources = []
            
            elif classification == "FUNC_CONVERSATION":
                raw_answer = "Acknowledged."
            
            # ... (other FUNC handlers) ...

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
        
        if classification in ["TIER_2", "TIER_3", "TIER_4"]:
            summary_thread = threading.Thread(
                target=_save_chat_summary,
                args=(user_id, project_id, question, final_answer)
            )
            summary_thread.start()

        return jsonify({"answer": final_answer})

    except Exception as e:
        logger.error(f"Error in project_chat endpoint: {e}", exc_info=True)
        return jsonify({"error": f"An unexpected server error occurred: {e}"}), 500

# --- Payment API ---

@api_bp.route('/credits/create-checkout-session', methods=['POST'])
@verify_firebase_token()
def create_credit_checkout():
    """Creates a Stripe Checkout session via the Firebase Extension."""
    logger.info("API: Received request to create credit checkout session.")
    user_id = request.user_auth['uid']
    
    if not firestore_db:
         return jsonify({"error": "Database connection is not configured."}), 500

    try:
        data = request.get_json()
        price_id = data.get('priceId')
        is_subscription = data.get('isSubscription', False)
        if not price_id:
            return jsonify({"error": "priceId is required."}), 400
        
        checkout_session_ref = firestore_db.collection('customers').document(user_id) \
                                 .collection('checkout_sessions').document()
        
        session_data = {
            "price": price_id,
            "mode": "subscription" if is_subscription else "payment",
            "success_url": request.host_url + url_for('project_manager.dashboard'), 
            "cancel_url": request.host_url + url_for('billing.billing_page'), 
        }
        checkout_session_ref.set(session_data)
        return jsonify({"sessionId": checkout_session_ref.id})
    except Exception as e:
        logger.error(f"Error creating checkout session for user {user_id}: {e}", exc_info=True)
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500

# --- Reports API ---

@api_bp.route('/projects/<project_id>/reports/relationship_web', methods=['POST'])
@verify_firebase_token()
def report_relationship_web(project_id):
    """Generates a relationship web report (no credits)."""
    if not db:
        return jsonify({"error": "Database connection is not configured."}), 500

    data = request.get_json()
    character_names = data.get('characters')
    if not character_names or len(character_names) < 2:
        return jsonify({"error": "Please provide at least two character names."}), 400

    try:
        from itertools import combinations
        links = []
        scene_list = {}
        with db:
            for (char_a, char_b) in list(combinations(character_names, 2)):
                shared_chunks = db.find_shared_chunks_by_entity_names([char_a, char_b])
                links.append({"source": char_a, "target": char_b, "value": len(shared_chunks)})
                for chunk in shared_chunks:
                    scene_list[chunk['id']] = chunk
        sorted_scenes = sorted(scene_list.values(), key=lambda x: x.get('character_start', 0))
        return jsonify({
            "status": "success",
            "report_data": {
                "nodes": [{"id": name} for name in character_names],
                "links": links,
                "scenes": sorted_scenes
            }
        })
    except Exception as e:
        logger.error(f"Failed to generate Relationship Web report: {e}", exc_info=True)
        return jsonify({"status": "error", "error": f"Failed to generate report: {e}"}), 500

@api_bp.route('/projects/<project_id>/reports/standard_continuity', methods=['POST'])
@verify_firebase_token()
def report_standard_continuity(project_id):
    """Runs a fast, surface-level continuity check (no credits)."""
    data = request.get_json()
    entity_name = data.get('entity_name')
    if not entity_name:
        return jsonify({"error": "entity_name is required."}), 400
    try:
        project_root_path_str = pm.get_project_path(project_id)
        temp_ai = create_george_ai(model="gemini-flash-lite", use_cloud=True)
        analyzer = QueryAnalyzer(temp_ai, project_path=project_root_path_str)
        kb_file_name = None
        for category, files in analyzer.available_kb_files.items():
            for f in files:
                if entity_name.lower() in f.lower().replace('_', ' '):
                    kb_file_name = f
                    break
            if kb_file_name: break
        if not kb_file_name:
            return jsonify({"error": f"Knowledge base file for '{entity_name}' not found."}), 404
        
        context_str = analyzer.load_context_files({"resources": [kb_file_name], "classification": "FUNC_KB_WRITE"})
        if not context_str:
            return jsonify({"error": f"Could not read content for '{kb_file_name}'."}), 500
        
        ai_flash = create_george_ai(model="gemini-2.0-flash", use_cloud=True)
        analysis_prompt = STANDARD_CONTINUITY_PROMPT.format(profile_text=context_str)
        result = ai_flash.chat(analysis_prompt, temperature=0.1)
        if not result['success']:
            return jsonify({"error": f"Analysis failed: {result['error']}"}), 500
        
        ai_formatter = create_george_ai(model="gemini-flash-lite", use_cloud=True)
        final_report = georgeify_response(
            original_question=f"Run a standard continuity check on {entity_name}",
            raw_ai_answer=result['response'],
            george_formatter_ai=ai_formatter
        )
        return jsonify({"status": "success", "report": final_report})
    except Exception as e:
        logger.error(f"Error in Standard Continuity Check: {e}", exc_info=True)
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500

@api_bp.route('/projects/<project_id>/reports/deep_continuity', methods=['POST'])
@verify_firebase_token()
def report_deep_continuity(project_id):
    """Runs a deep continuity check (1 credit)."""
    if not db or not firestore_db: return jsonify({"error": "DB not configured."}), 500
    user_id = request.user_auth['uid']
    data = request.get_json()
    entity_name = data.get('entity_name')
    if not entity_name: return jsonify({"error": "entity_name is required."}), 400
    credits_needed = 1
    customer_ref = firestore_db.collection('customers').document(user_id)
    try:
        @firestore.transactional
        def check_and_deduct_credits(transaction, ref, amount):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists: raise Exception("Customer profile not found.")
            balance = snapshot.get('creditBalance')
            if balance is None or balance < amount:
                raise ValueError(f"Insufficient credits. This report costs {amount} credit.")
            new_balance = balance - amount
            transaction.update(ref, {'creditBalance': new_balance})
            return new_balance
        new_balance = firestore_db.transaction().run(check_and_deduct_credits, customer_ref, credits_needed)
    except ValueError as ve:
        return jsonify({'status': 'error', 'error': str(ve)}), 4G03
    except Exception as e:
        return jsonify({"status": "error", "error": f"Credit check failed: {e}"}), 500

    try:
        with db:
            entity = db.get_entity_by_name(entity_name)
        if not entity: raise ValueError(f"Entity '{entity_name}' not found.")
        entity_id = entity['id']
        with db:
            chunks = db.get_chunks_for_entity(entity_id)
        if not chunks:
            return jsonify({"status": "success", "report": "No scenes found for this entity."})
        
        ai_pro = create_george_ai(model="gemini-2.5-pro-latest", use_cloud=True)
        fact_timeline = _batch_extract_facts(ai_pro, chunks, entity_name)
        if not fact_timeline:
            return jsonify({"status": "success", "report": "Could not extract any facts for this entity."})
        
        synthesis_prompt = DEEP_CONTINUITY_PROMPT.format(fact_timeline="\n---\n".join(fact_timeline))
        synthesis_result = ai_pro.chat(synthesis_prompt, temperature=0.2)
        if not synthesis_result['success']:
            raise Exception(f"Final analysis failed: {synthesis_result['error']}")
        
        ai_formatter = create_george_ai(model="gemini-flash-lite", use_cloud=True)
        final_report = georgeify_response(
            original_question=f"Run a deep continuity check on {entity_name}",
            raw_ai_answer=synthesis_result['response'],
            george_formatter_ai=ai_formatter
        )
        return jsonify({"status": "success", "report": final_report, "new_credit_balance": new_balance})
    except Exception as e:
        logger.error(f"Failed to generate Deep Continuity report: {e}", exc_info=True)
        try:
            customer_ref.update({"creditBalance": firestore.Increment(credits_needed)})
            logger.info(f"Credits refunded for user {user_id} due to report failure.")
        except Exception as refund_e:
            logger.critical(f"FATAL: FAILED TO REFUND 1 CREDIT for user {user_id}: {refund_e}")
        return jsonify({"status": "error", "error": f"Failed to generate report: {e}"}), 500

@api_bp.route('/projects/<project_id>/reports/foundational_consistency', methods=['POST'])
@verify_firebase_token()
def report_foundational_consistency(project_id):
    """Runs a foundational consistency check (1 credit per concept)."""
    if not db or not firestore_db: return jsonify({"error": "DB not configured."}), 500
    user_id = request.user_auth['uid']
    data = request.get_json()
    concept_name = data.get('concept_name')
    lore_project_id = data.get('lore_project_id')
    if not concept_name: return jsonify({"error": "concept_name is required."}), 400
    if not lore_project_id: return jsonify({"error": "lore_project_id is required."}), 400
    credits_needed = 1
    customer_ref = firestore_db.collection('customers').document(user_id)
    try:
        @firestore.transactional
        def check_and_deduct_credits(transaction, ref, amount):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists: raise Exception("Customer profile not found.")
            balance = snapshot.get('creditBalance')
            if balance is None or balance < amount:
                raise ValueError(f"Insufficient credits. This report costs {amount} credit.")
            new_balance = balance - amount
            transaction.update(ref, {'creditBalance': new_balance})
            return new_balance
        new_balance = firestore_db.transaction().run(check_and_deduct_credits, customer_ref, credits_needed)
    except ValueError as ve:
        return jsonify({'status': 'error', 'error': str(ve)}), 403
    except Exception as e:
        return jsonify({"status": "error", "error": f"Credit check failed: {e}"}), 500

    try:
        wip_project_path = pm.get_project_path(project_id)
        lore_project_path = pm.get_project_path(lore_project_id)
        if not wip_project_path or not lore_project_path:
            raise Exception("One or both projects could not be found.")
        
        def find_kb_file(kb_path, concept):
            for prefix in ['term_', 'character_', 'location_']:
                file_path = Path(kb_path) / f"{prefix}{concept.replace(' ', '_')}.md"
                if file_path.exists(): return str(file_path)
            return None

        wip_file_path = find_kb_file(Path(wip_project_path) / "knowledge_base", concept_name)
        lore_file_path = find_kb_file(Path(lore_project_path) / "knowledge_base", concept_name)
        if not lore_file_path: raise ValueError(f"'{concept_name}' not found in Established Lore.")
        if not wip_file_path: raise ValueError(f"'{concept_name}' not found in Work in Progress.")
        
        ai_pro = create_george_ai(model="gemini-2.5-pro-latest", use_cloud=True)
        foundational_facts = _extract_facts_from_kb_file(ai_pro, lore_file_path, concept_name)
        wip_facts = _extract_facts_from_kb_file(ai_pro, wip_file_path, concept_name)
        
        synthesis_prompt = FOUNDATIONAL_CONSISTENCY_PROMPT.format(foundational_facts=foundational_facts, wip_facts=wip_facts)
        synthesis_result = ai_pro.chat(synthesis_prompt, temperature=0.2)
        if not synthesis_result['success']:
            raise Exception(f"Final analysis failed: {synthesis_result['error']}")
        
        ai_formatter = create_george_ai(model="gemini-flash-lite", use_cloud=True)
        final_report = georgeify_response(
            original_question=f"Run a foundational consistency check on '{concept_name}'",
            raw_ai_answer=synthesis_result['response'],
            george_formatter_ai=ai_formatter
        )
        return jsonify({"status": "success", "report": final_report, "new_credit_balance": new_balance})
    except Exception as e:
        logger.error(f"Failed to generate Foundational Consistency report: {e}", exc_info=True)
        try:
            customer_ref.update({"creditBalance": firestore.Increment(credits_needed)})
            logger.info(f"Credits refunded for user {user_id} due to report failure.")
        except Exception as refund_e:
            logger.critical(f"FATAL: FAILED TO REFUND 1 CREDIT for user {user_id}: {refund_e}")
        return jsonify({"status": "error", "error": f"Failed to generate report: {e}"}), 500