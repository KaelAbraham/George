import os
import logging
import math
import re # <-- ADDED for parsing notes
from pathlib import Path
from flask import Blueprint, jsonify, request, current_app, flash, redirect, url_for
from firebase_admin import auth, firestore
import firebase_admin
from ..auth.auth_client import verify_firebase_token
import threading

# --- Import backend modules ---
try:
    from ...knowledge_extraction.orchestrator import KnowledgeExtractor
    from ...llm_integration import create_george_ai, GeorgeAI
    from ...project_manager import ProjectManager
    from ...parsers.parsers import read_manuscript_file
    # --- IMPORT THE NEW STRUCTURED DB CLASS ---
    from ...knowledge_base.structured_db import StructuredDB 
except ImportError as e:
    logging.critical(f"FATAL: Could not import core backend modules in endpoints.py: {e}")
    # Define dummy classes
    class KnowledgeExtractor: pass
    class GeorgeAI: pass
    class ProjectManager: pass
    class StructuredDB: pass # Add dummy
    def create_george_ai(*args, **kwargs): pass
    def read_manuscript_file(*args, **kwargs): pass

api_bp = Blueprint('api', __name__, url_prefix='/api')
logger = logging.getLogger(__name__)

# --- Initialize Managers ---
try:
    project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    uploads_base_dir = project_root / 'src' / 'data' / 'uploads'
    pm = ProjectManager(base_dir=str(uploads_base_dir))
    
    # --- INITIALIZE STRUCTURED DB (Uses the new Option 2 class) ---
    # This assumes a single, central DB located in the data directory
    db_path = project_root / 'src' / 'data' / 'george.db'
    db = StructuredDB(db_path=str(db_path))
    
    logger.info(f"ProjectManager and StructuredDB initialized.")
except Exception as init_e:
    logger.critical(f"Failed to initialize managers in endpoints.py: {init_e}", exc_info=True)
    pm = None 
    db = None # Set db to None on failure

# --- Load Georgeification Prompt (No changes) ---
GEORGEIFY_PROMPT = ""
try:
    current_dir = Path(__file__).parent.parent.parent # src/george/ui -> src/george
    prompt_path = current_dir.parent / "prompts" / "george_operational_protocol.txt"
    with open(prompt_path, 'r', encoding='utf-8') as f:
        GEORGEIFY_PROMPT = f.read()
    if not GEORGEIFY_PROMPT: raise ValueError("Prompt file is empty.")
    logger.info("Successfully loaded Georgeification prompt.")
except Exception as e:
    logger.error(f"FATAL: Error loading Georgeification prompt file: {e}", exc_info=True)
    GEORGEIFY_PROMPT = "ERROR: Could not load Georgeification prompt."


# --- Georgeify Function (No changes) ---
def georgeify_response(original_question: str, raw_ai_answer: str, george_formatter_ai: GeorgeAI, sources: list = []) -> str:
    # ... (This function remains the same as before) ...
    if GEORGEIFY_PROMPT.startswith("ERROR:"):
        raw_output = f"Raw Answer: {raw_ai_answer}"
        if sources:
             raw_output += f"\n\n*Sources: {', '.join([f'$^{src}$' for src in sources])}*"
        return raw_output

    formatter_prompt = f"{GEORGEIFY_PROMPT}\n\nOriginal User Question: \"{original_question}\"\nRaw AI Answer to Format:\n---\n{raw_ai_answer}\n---\n\nFormatted Response:"
    
    try:
        result = george_formatter_ai.chat(formatter_prompt, temperature=0.1, timeout=15)
        if result['success']:
            formatted_text = result['response'].strip()
            if sources and "$^" not in formatted_text: 
                source_tags = [f"$^{src}$" for src in sources]
                formatted_text += f"\n\n*Sources: {', '.join(source_tags)}*"
            return formatted_text
        else:
            # ... (error handling) ...
            error_msg = result.get('error', 'Unknown formatting error')
            raw_output = f"(Formatting Error: {error_msg})\nRaw Answer: {raw_ai_answer}"
            if sources:
                 source_tags = [f"$^{src}$" for src in sources]
                 raw_output += f"\n\n*Sources: {', '.join([f'$^{src}$' for src in sources])}*"
            return raw_output
    except Exception as e:
        # ... (exception handling) ...
        raw_output = f"(Formatting Exception)\nRaw Answer: {raw_ai_answer}"
        if sources:
             source_tags = [f"$^{src}$" for src in sources]
             raw_output += f"\n\n*Sources: {', '.join([f'$^{src}$' for src in sources])}*"
        return raw_output


# --- Chat Summary Function (No changes) ---
def _save_chat_summary(user_id: str, project_id: str, question: str, response: str):
    # ... (This function remains the same as before) ...
    try:
        # Re-initialize db connection *within the thread*
        db_path = Path(__file__).resolve().parent.parent.parent.parent.parent / 'src' / 'data' / 'george.db'
        thread_db = StructuredDB(db_path=str(db_path))
        
        if not thread_db.conn:
             logger.error("Cannot save chat summary: Thread DB connection failed.")
             return

        logger.info(f"Starting background summary for user {user_id}, project {project_id}")
        ai_summarizer = create_george_ai(model="gemini-flash-lite", use_cloud=True)
        summary_prompt = f"""Summarize this Q&A into one concise sentence. Q: "{question}" A: "{response}" Summary:"""
        result = ai_summarizer.chat(summary_prompt, temperature=0.2, timeout=20)
        
        if result['success']:
            summary_text = result['response'].strip()
            with thread_db: # Use context manager
                thread_db.add_chat_summary(
                    user_id=user_id,
                    project_id=project_id,
                    original_question=question,
                    summary_text=summary_text
                )
            logger.info(f"Successfully saved chat summary for user {user_id}.")
        else:
            logger.error(f"Failed to generate summary: {result.get('error')}")
    except Exception as e:
        logger.error(f"Error in background summary thread: {e}", exc_info=True)


# --- NEW: Helper function to parse note requests ---
def _parse_note_from_query(question: str) -> dict:
    """
    Parses a 'FUNC_KB_WRITE' query to extract the entity and note content.
    Example: "Add a note to Hugh: He seems anxious here."
    Returns: {'entity': 'Hugh', 'note': 'He seems anxious here.'}
    """
    # Regex to find patterns like "note to [Entity]: [Note]" or "note for [Entity]: [Note]"
    # This regex is more flexible with quotes around the entity name
    match = re.search(r"note (to|for) ['\"]?(.+?)['\"]?:\s*(.+)", question, re.IGNORECASE)
    
    if match:
        return {
            "entity": match.group(2).strip(), # The entity name
            "note": match.group(3).strip()  # The note content
        }
    
    # Fallback for "attach note to [Entity]: [Note]"
    match = re.search(r"attach this note to ['\"]?(.+?)['\"]?:\s*(.+)", question, re.IGNORECASE)
    if match:
        return {
            "entity": match.group(1).strip(),
            "note": match.group(2).strip()
        }
        
    logger.warning(f"Could not parse entity and note from query: {question}")
    return {}


# --- UPDATED: Project Chat Endpoint ---
@api_bp.route('/projects/<project_id>/chat', methods=['POST'])
@verify_firebase_token()
def project_chat(project_id):
    """Handles a chat message for a specific project."""
    data = request.get_json()
    question = data.get('question')
    user_auth_data = request.user_auth
    user_id = user_auth_data['uid']
    
    if not question: 
        return jsonify({"error": "No question provided"}), 400
    
    if not db or not pm or not db.conn:
         logger.critical("ProjectManager or StructuredDB not initialized or connected.")
         return jsonify({"error": "Core services not available."}), 500
    
    try:
        # ... (AI instance creation) ...
        router_model_name = "gemini-flash-lite"
        formatter_model_name = "gemini-flash-lite"
        default_response_model_name = "gemini-2.0-flash" 

        ai_router = create_george_ai(model=router_model_name, use_cloud=True)
        ai_formatter = create_george_ai(model=formatter_model_name, use_cloud=True)
        ai_responder = create_george_ai(model=default_response_model_name, use_cloud=True)
        
        project_root_path_str = pm.get_project_path(project_id)
        if not project_root_path_str: # Check for None or empty
            return jsonify({"error": f"Project '{project_id}' not found."}), 404
        
        from ...knowledge_extraction.query_analyzer import QueryAnalyzer
        analyzer = QueryAnalyzer(ai_router, project_path=project_root_path_str)

        analysis_result, context_str = analyzer.build_context_for_query(question)

        if analysis_result is None:
            final_answer = georgeify_response(question, context_str, ai_formatter)
            return jsonify({"answer": final_answer}) 

        classification = analysis_result.get("classification")
        sources = analysis_result.get("resources", [])
        
        # --- Handle Functional Intents ---
        if classification.startswith("FUNC_"):
            logger.info(f"Handling functional intent: {classification}")
            raw_answer = "This function is not yet implemented." # Default
            
            # --- NEW: FUNC_KB_WRITE Logic ---
            if classification == "FUNC_KB_WRITE":
                note_data = _parse_note_from_query(question)
                entity_name = note_data.get('entity')
                note_text = note_data.get('note')
                
                if entity_name and note_text:
                    try:
                        # Find the entity's ID from the database
                        # Use the get_entity_id_by_name helper
                        entity_id_for_note = db.get_entity_id_by_name(entity_name)
                        
                        if entity_id_for_note:
                            # Add the note
                            db.add_entity_note(entity_id_for_note, user_id, note_text)
                            raw_answer = f"Note successfully added to '{entity_name}'."
                            logger.info(f"Added note to entity '{entity_name}' (ID: {entity_id_for_note}) for user {user_id}")
                        else:
                            raw_answer = f"Sorry, I could not find an entity named '{entity_name}' in your knowledge base."
                            logger.warning(f"FUNC_KB_WRITE: Entity '{entity_name}' not found.")
                    except Exception as e:
                        logger.error(f"Error during FUNC_KB_WRITE: {e}", exc_info=True)
                        raw_answer = f"An error occurred while trying to add the note: {e}"
                else:
                    raw_answer = "I understood you want to add a note, but I couldn't parse the entity name and note content. Please try again using the format: 'Add a note to [Entity Name]: [Your note]'."
            
            # --- Other Functional Intents (no change) ---
            elif classification == "FUNC_HELP":
                raw_answer = context_str if context_str else "Could not find relevant help information."
                sources = []
            elif classification == "FUNC_ACCOUNT":
                raw_answer = "Account management features are currently under development."
            # ... (other FUNC handlers) ...

            final_answer = georgeify_response(question, raw_answer, ai_formatter)
            return jsonify({"answer": final_answer})
        
        # --- Proceed with Analysis Intents (TIER_*) ---
        # ... (Model selection logic remains the same) ...
        if classification in ["TIER_3", "TIER_4"]: # Typo fixed
            response_model_name = "gemini-2.5-flash"
            ai_responder = create_george_ai(model=response_model_name, use_cloud=True)
        
        # ... (Responder AI call remains the same) ...
        responder_result = ai_responder.chat(prompt=question, project_context=context_str, temperature=0.5)

        if not responder_result['success']:
            error_msg = responder_result.get('error', 'Unknown responder error')
            final_answer = georgeify_response(question, f"Error processing request: {error_msg}", ai_formatter)
            return jsonify({"answer": final_answer})

        raw_answer = responder_result['response']
        
        # ... (Georgeification layer call) ...
        source_filenames = [Path(s).name for s in sources]
        final_answer = georgeify_response(question, raw_answer, ai_formatter, source_filenames)
        
        # --- Trigger Chat Summary (No change) ---
        if classification in ["TIER_2", "TIER_3", "TIER_4"]: # Typo fixed
            logger.debug(f"Triggering background summary for classification: {classification}")
            summary_thread = threading.Thread(
                target=_save_chat_summary,
                args=(user_id, project_id, question, final_answer) # Pass final_answer
            )
            summary_thread.start()

        # 5. Return Final Answer
        return jsonify({"answer": final_answer})

    except Exception as e:
        logger.error(f"Error in project_chat endpoint: {e}", exc_info=True)
        # ... (Error handling) ...
        return jsonify({"error": f"An unexpected server error occurred: {e}"}), 500


# --- process_manuscript Endpoint (No Changes) ---
@api_bp.route('/projects/<project_id>/process', methods=['POST'])
@verify_firebase_token()
def process_manuscript(project_id):
    # ... (This function remains the same as before) ...
    logger.info(f"Received request to generate KB for project: {project_id}")
    if not db: return jsonify({"status": "error", "error": "Database connection not configured."}), 500
    user_auth_data = request.user_auth 
    user_id = user_auth_data['uid']
    try:
        project_data = pm.load_project(project_id)
        if not project_data: return jsonify({'status': 'error', 'error': 'Project not found'}), 404
        manuscript_filenames = project_data.get('manuscript_files', [])
        if not manuscript_filenames: return jsonify({'status': 'error', 'error': 'No manuscript files found. Please upload a file first.'}), 400
        manuscript_filename = manuscript_filenames[0]
        project_path_str = pm.get_project_path(project_id)
        manuscript_path = os.path.join(project_path_str, manuscript_filename)
        if not os.path.exists(manuscript_path):
             return jsonify({'status': 'error', 'error': f'Manuscript file {manuscript_filename} not found.'}), 404

        file_content = read_manuscript_file(str(manuscript_path))
        word_count = len(file_content.split())
        credits_needed = math.ceil(word_count / 10000)
        logger.info(f"Word count: {word_count}. Credits needed: {credits_needed}")

        customer_ref = firestore_db.collection('customers').document(user_id) # Use firestore_db
        
        @firestore.transactional
        def check_and_deduct_credits(transaction, customer_ref, amount_to_deduct):
            snapshot = customer_ref.get(transaction=transaction)
            if not snapshot.exists: raise Exception(f"Customer profile not found for user {user_id}.")
            current_balance = snapshot.get('creditBalance')
            if current_balance is None: raise Exception("Credit balance not found in customer profile.")
            if current_balance < amount_to_deduct:
                raise ValueError(f"Insufficient credits. You need {amount_to_deduct}, but you only have {current_balance}.")
            new_balance = current_balance - amount_to_deduct
            transaction.update(customer_ref, {'creditBalance': new_balance})
            return new_balance

        transaction = firestore_db.transaction() # Use firestore_db
        new_balance = check_and_deduct_credits(transaction, customer_ref, credits_needed)
    except ValueError as ve: 
        return jsonify({'status': 'error', 'error': str(ve)}), 403 
    except Exception as e:
        return jsonify({"status": "error", "error": f"An error occurred during credit check: {e}"}), 500
    
    # ... (Rest of KB Generation and Rollback logic remains the same) ...
    try:
        project_path = Path(project_path_str)
        knowledge_base_path = project_path / "knowledge_base"
        knowledge_base_path.mkdir(parents=True, exist_ok=True)
        ai_kb_generator = create_george_ai(model="gemini-2.5-pro-latest", use_cloud=True) 
        pm.update_project_status(project_id, "processing")
        extractor = KnowledgeExtractor(ai_kb_generator, project_path=project_path_str)
        generation_result = extractor.generate_knowledge_base(manuscript_filename) 

        if generation_result.get('success'):
            pm.update_project_status(project_id, "ready") 
            message = f"{generation_result.get('entities_found', 0)} entities identified, {generation_result.get('files_created', 0)} knowledge files created."
            return jsonify({'status': 'success', 'message': message, 'new_credit_balance': new_balance})
        else:
            raise Exception(generation_result.get('error', 'Unknown generation error'))
    except Exception as e:
        logger.error(f"KB generation failed for {project_id}: {e}. Refunding credits.", exc_info=True)
        try:
            customer_ref.update({"creditBalance": firestore.Increment(credits_needed)}) # Use firestore.Increment
            refund_message = "Credits have been refunded."
        except Exception as refund_e:
            logger.critical(f"FATAL: FAILED TO REFUND {credits_needed} CREDITS for user {user_id}: {refund_e}")
            refund_message = "CRITICAL: Credit refund failed. Please contact support."
        pm.update_project_status(project_id, "error")
        return jsonify({ 'status': 'error', 'error': f"KB generation failed: {e}. {refund_message}" }), 500


# --- Credit Checkout Endpoint (No Changes) ---
@api_bp.route('/credits/create-checkout-session', methods=['POST'])
@verify_firebase_token()
def create_credit_checkout():
    # ... (This function remains the same as before) ...
    logger.info("Received request to create credit checkout session.")
    user_id = request.user_auth['uid']
    if not firestore_db: return jsonify({"error": "Database connection is not configured."}), 500 # Use firestore_db
    try:
        data = request.get_json()
        price_id = data.get('priceId') 
        is_subscription = data.get('isSubscription', False)
        if not price_id: return jsonify({"error": "priceId is required."}), 400
        checkout_session_ref = firestore_db.collection('customers').document(user_id) \
                                 .collection('checkout_sessions').document() # Use firestore_db
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


# --- Health Check (No Changes) ---
@api_bp.route('/health')
def health_check():
    # ... (This function remains the same as before) ...
    return jsonify({'status': 'healthy', 'service': 'Standalone George UI API'})

# --- Relationship Web Endpoint (No Changes) ---
@api_bp.route('/projects/<project_id>/reports/relationship_web', methods=['POST'])
@verify_firebase_token()
def report_relationship_web(project_id):
    # ... (This function remains the same as before) ...
    if not db: return jsonify({"error": "Database connection is not configured."}), 500
    data = request.get_json()
    character_names = data.get('characters')
    if not character_names or len(character_names) < 2:
        return jsonify({"error": "Please provide at least two character names."}), 400
    logger.info(f"Generating Relationship Web for project {project_id}, characters: {character_names}")
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
    except ValueError as ve:
        return jsonify({"status": "error", "error": str(ve)}), 400
    except Exception as e:
        logger.error(f"Failed to generate Relationship Web report: {e}", exc_info=True)
        return jsonify({"status": "error", "error": f"Failed to generate report: {e}"}), 500