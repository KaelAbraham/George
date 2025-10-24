import os
import logging
import math
from pathlib import Path
from flask import Blueprint, jsonify, request, current_app, flash, redirect, url_for
from firebase_admin import auth, firestore
import firebase_admin
from ..auth.auth_client import verify_firebase_token
import threading  # <-- IMPORTED for background tasks
from itertools import combinations
from ...knowledge_extraction.query_analyzer import QueryAnalyzer
from ...parsers.parsers import read_manuscript_file

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

# --- NEW: Load Foundational Consistency Prompt ---
FOUNDATIONAL_CONSISTENCY_PROMPT = ""
try:
    current_dir = Path(__file__).parent.parent.parent # src/george/ui -> src/george
    prompt_path = current_dir.parent / "prompts" / "foundational_consistency_prompt.txt"
    with open(prompt_path, 'r', encoding='utf-8') as f:
        FOUNDATIONAL_CONSISTENCY_PROMPT = f.read()
    if not FOUNDATIONAL_CONSISTENCY_PROMPT:
        raise ValueError("Foundational Consistency prompt file is empty.")
    logger.info("Successfully loaded Foundational Consistency prompt.")
except Exception as e:
    logger.error(f"FATAL: Error loading Foundational Consistency prompt: {e}", exc_info=True)
    # The route will still be created, but will fail if called

# --- NEW: Load Report Prompts ---
STANDARD_CONTINUITY_PROMPT = ""
DEEP_CONTINUITY_PROMPT = ""
try:
    current_dir = Path(__file__).parent.parent.parent # src/george/ui -> src/george
    std_prompt_path = current_dir.parent / "prompts" / "standard_continuity_prompt.txt"
    deep_prompt_path = current_dir.parent / "prompts" / "deep_continuity_prompt.txt"
    
    with open(std_prompt_path, 'r', encoding='utf-8') as f:
        STANDARD_CONTINUITY_PROMPT = f.read()
    with open(deep_prompt_path, 'r', encoding='utf-8') as f:
        DEEP_CONTINUITY_PROMPT = f.read()
    
    if not STANDARD_CONTINUITY_PROMPT or not DEEP_CONTINUITY_PROMPT:
        raise ValueError("One or more report prompts are empty.")
    logger.info("Successfully loaded all report prompts.")
except Exception as e:
    logger.error(f"FATAL: Error loading report prompts: {e}", exc_info=True)
    # The routes will still be created, but will fail if called

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
    db = None

# --- Load Georgeification Prompt (No changes) ---
GEORGEIFY_PROMPT = ""
try:
    # ... (code to load prompt) ...
    current_dir = Path(__file__).parent.parent.parent # src/george/ui -> src/george
    prompt_path = current_dir.parent / "prompts" / "george_operational_protocol.txt"
    with open(prompt_path, 'r', encoding='utf-8') as f:
        GEORGEIFY_PROMPT = f.read()
    if not GEORGEIFY_PROMPT or GEORGEIFY_PROMPT.startswith("ERROR:"):
        raise ValueError("Georgeification prompt file is empty.")
    logger.info("Successfully loaded Georgeification prompt.")
except Exception as e:
    logger.error(f"FATAL: Error loading Georgeification prompt file: {e}", exc_info=True)
    GEORGEIFY_PROMPT = "ERROR: Could not load Georgeification prompt."


# --- Georgeify Function (No changes) ---
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


# --- NEW: Function to Save Chat Summary in Background ---
def _save_chat_summary(user_id: str, project_id: str, question: str, response: str):
    """
    Summarizes and saves a chat exchange in a background thread.
    """
    try:
        if not db:
            logger.error("Cannot save chat summary: Database (db) is not initialized.")
            return

        logger.info(f"Starting background summary for user {user_id}, project {project_id}")
        
        # 1. Create a summarizer AI (fast and cheap)
        ai_summarizer = create_george_ai(model="gemini-flash-lite", use_cloud=True)
        
        # 2. Create the summarization prompt
        summary_prompt = f"""
        Summarize the following question and answer exchange into a single, concise sentence 
        that captures the core insight or topic.

        Question: "{question}"
        Answer: "{response}"

        One-sentence Summary:
        """
        
        result = ai_summarizer.chat(summary_prompt, temperature=0.2, timeout=20)
        
        if result['success']:
            summary_text = result['response'].strip()
            
            # 3. Save to the StructuredDB
            # We must create a new DB instance *within this thread*
            # as SQLite connections are not thread-safe.
            thread_db_path = Path(__file__).resolve().parent.parent.parent.parent.parent / 'src' / 'data' / 'george.db'
            thread_db = StructuredDB(db_path=str(thread_db_path))
            with thread_db: # Use context manager to ensure connection is closed
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
        # Catch exceptions within the thread to prevent silent failures
        logger.error(f"Error in background summary thread: {e}", exc_info=True)


# --- UPDATED: Project Chat Endpoint ---
@api_bp.route('/projects/<project_id>/chat', methods=['POST'])
@verify_firebase_token()
def project_chat(project_id):
    """Handles a chat message for a specific project."""
    data = request.get_json()
    question = data.get('question')
    user_auth_data = request.user_auth # Auth info
    user_id = user_auth_data['uid'] # Get user ID
    
    if not question: 
        return jsonify({"error": "No question provided"}), 400
    
    logger.info(f"Received chat request for project '{project_id}' from user '{user_id}'")
    
    # Check if managers are initialized
    if not db or not pm:
         logger.critical("ProjectManager or StructuredDB not initialized.")
         return jsonify({"error": "Core services not available."}), 500
    
    try:
        # ... (AI instance creation logic remains the same) ...
        router_model_name = "gemini-flash-lite"
        formatter_model_name = "gemini-flash-lite"
        default_response_model_name = "gemini-2.0-flash" 

        ai_router = create_george_ai(model=router_model_name, use_cloud=True)
        ai_formatter = create_george_ai(model=formatter_model_name, use_cloud=True)
        ai_responder = create_george_ai(model=default_response_model_name, use_cloud=True)
        
        # ... (Analyzer instantiation remains the same) ...
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
        
        # --- Handle Functional Intents (No Summary) ---
        if classification.startswith("FUNC_"):
            # ... (Functional intent handling logic remains the same) ...
            raw_answer = "Functional intent recognized." # Placeholder
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
        
        # --- Proceed with Analysis Intents (TIER_*) ---
        
        # ... (Model selection logic remains the same) ...
        if classification in ["TIER_3", "TIER_4"]:
            response_model_name = "gemini-2.5-flash"
            ai_responder = create_george_ai(model=response_model_name, use_cloud=True)
        
        # ... (Responder AI call remains the same) ...
        responder_result = ai_responder.chat(prompt=question, project_context=context_str, temperature=0.5)

        if not responder_result['success']:
            error_msg = responder_result.get('error', 'Unknown responder error')
            final_answer = georgeify_response(question, f"Error processing request: {error_msg}", ai_formatter)
            return jsonify({"answer": final_answer})

        raw_answer = responder_result['response']
        
        # 4. Apply the "Georgeification" Layer
        source_filenames = [Path(s).name for s in sources]
        final_answer = georgeify_response(question, raw_answer, ai_formatter, source_filenames)
        
        # --- NEW: Trigger Chat Summary ---
        # Only save summaries for complex, non-functional queries
        if classification in ["TIER_2", "TIER_3", "TIER_4"]:
            logger.debug(f"Triggering background summary for classification: {classification}")
            # Run in a background thread so it doesn't block the user's response
            summary_thread = threading.Thread(
                target=_save_chat_summary,
                args=(user_id, project_id, question, final_answer)
            )
            summary_thread.start()
        # --- END NEW ---

        # 5. Return Final Answer
        return jsonify({"answer": final_answer})

    except Exception as e:
        logger.error(f"Error in project_chat endpoint: {e}", exc_info=True)
        # ... (Error handling remains the same) ...
        try:
             ai_formatter = create_george_ai(model="gemini-flash-lite", use_cloud=True)
             final_answer = georgeify_response(question, f"An unexpected server error occurred: {e}", ai_formatter)
             return jsonify({"answer": final_answer})
        except:
             return jsonify({"error": f"An unexpected server error occurred: {e}"}), 500

# --- NEW: Relationship Web Report Endpoint (No Credit Check) ---
@api_bp.route('/projects/<project_id>/reports/relationship_web', methods=['POST'])
@verify_firebase_token()
def report_relationship_web(project_id):
    """
    Generates a relationship web report for a list of characters.
    This is an included feature and does not cost credits.
    """
    if not db:
        return jsonify({"error": "Database connection is not configured."}), 500

    user_id = request.user_auth['uid']
    data = request.get_json()
    character_names = data.get('characters') # Expect a list: ["Hugh", "Linda"]

    if not character_names or not isinstance(character_names, list) or len(character_names) < 2:
        return jsonify({"error": "Please provide a list of at least two character names."}), 400

    logger.info(f"Generating Relationship Web for project {project_id}, user {user_id}, characters: {character_names}")

    # --- Generate Report Data ---
    try:
        # This will be the data for the graph: {"source": "Name1", "target": "Name2", "value": X}
        links = []
        
        # Get all unique pairs of characters
        from itertools import combinations
        character_pairs = list(combinations(character_names, 2))

        # This will be the list of all scenes found
        scene_list = {} # Use a dict to avoid duplicate scenes

        with db: # Use the database context manager
            for (char_a, char_b) in character_pairs:
                shared_chunks = db.find_shared_chunks_by_entity_names([char_a, char_b])
                
                # Add to our link data for the graph
                links.append({"source": char_a, "target": char_b, "value": len(shared_chunks)})
                
                # Add the scenes to our list
                for chunk in shared_chunks:
                    scene_list[chunk['id']] = chunk # Store by ID to deduplicate

        # Convert scene_list dict to a sorted list
        sorted_scenes = sorted(scene_list.values(), key=lambda x: x.get('character_start', 0))

        # --- Return the data ---
        return jsonify({
            "status": "success",
            "report_data": {
                "nodes": [{"id": name} for name in character_names], # Nodes for the graph
                "links": links, # Links for the graph
                "scenes": sorted_scenes # List of scenes
            }
        })
    
    except ValueError as ve: # Catch errors like "Entity not found"
        logger.warning(f"Failed to generate Relationship Web: {ve}")
        return jsonify({"status": "error", "error": str(ve)}), 400
    except Exception as e:
        logger.error(f"Failed to generate Relationship Web report: {e}", exc_info=True)
        return jsonify({"status": "error", "error": f"Failed to generate report: {e}"}), 500


# --- process_manuscript Endpoint (No Changes) ---
@api_bp.route('/projects/<project_id>/process', methods=['POST'])
@verify_firebase_token()
def process_manuscript(project_id):
    # ... (This function remains the same as before) ...
    # (Includes credit check, KB generation, and credit rollback)
    logger.info(f"Received request to generate KB for project: {project_id}")
    if not db:
        return jsonify({"status": "error", "error": "Database connection is not configured."}), 500
    user_auth_data = request.user_auth 
    customer_profile = request.user   
    user_id = user_auth_data['uid']
    try:
        project_data = pm.load_project(project_id)
        if not project_data:
            return jsonify({'status': 'error', 'error': 'Project not found'}), 404
        manuscript_filenames = project_data.get('manuscript_files', [])
        if not manuscript_filenames:
            return jsonify({'status': 'error', 'error': 'No manuscript files found. Please upload a file first.'}), 400
        manuscript_filename = manuscript_filenames[0]
        project_path_str = pm.get_project_path(project_id)
        manuscript_path = os.path.join(project_path_str, manuscript_filename)
        if not os.path.exists(manuscript_path):
             return jsonify({'status': 'error', 'error': f'Manuscript file {manuscript_filename} not found.'}), 404

        file_content = read_manuscript_file(str(manuscript_path))
        word_count = len(file_content.split())
        credits_needed = math.ceil(word_count / 10000)
        logger.info(f"Word count: {word_count}. Credits needed: {credits_needed}")

        customer_ref = db.collection('customers').document(user_id)
        
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

        transaction = db.transaction()
        new_balance = check_and_deduct_credits(transaction, customer_ref, credits_needed)
    except ValueError as ve: 
        return jsonify({'status': 'error', 'error': str(ve)}), 403 
    except Exception as e:
        return jsonify({"status": "error", "error": f"An error occurred during credit check: {e}"}), 500

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
            customer_ref.update({"creditBalance": firestore.Increment(credits_needed)})
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
    if not db: return jsonify({"error": "Database connection is not configured."}), 500
    try:
        data = request.get_json()
        price_id = data.get('priceId') 
        is_subscription = data.get('isSubscription', False) # Check for subscription flag
        if not price_id:
            return jsonify({"error": "priceId is required."}), 400
        
        checkout_session_ref = db.collection('customers').document(user_id) \
                                 .collection('checkout_sessions').document()
        
        session_data = {
            "price": price_id,
            "mode": "subscription" if is_subscription else "payment", # Set mode
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
# --- NEW: Helper function for batch fact extraction (to avoid code duplication) ---
def _batch_extract_facts(ai_model: GeorgeAI, chunks: list, entity_name: str) -> list:
    """Helper to run batch fact extraction for a list of chunks."""
    fact_timeline = []
    # In a real implementation, we would batch chunks *together* into single API calls
    # For MVP, we do one call per chunk (which is less efficient but simpler)
    for chunk in chunks:
        fact_prompt = f"From the following text, extract all factual statements, definitions, or interpretations related ONLY to the concept '{entity_name}'.\n\nText: \"{chunk['chunk_text']}\"\n\nFacts:"
        fact_result = ai_model.chat(fact_prompt, temperature=0.0, timeout=45)
        if fact_result['success']:
            fact_timeline.append(f"Source: {chunk['source_file']}, Location: approx. char {chunk['character_start']}\nFacts: {fact_result['response']}\n")
    return fact_timeline

# --- NEW: Foundational Consistency Check (Pro Report) ---
@api_bp.route('/projects/<project_id>/reports/foundational_consistency', methods=['POST'])
@verify_firebase_token()
def report_foundational_consistency(project_id):
    """
    Runs a deep consistency check on a concept by comparing
    the WIP against the Established Lore. Costs 1 credit per concept.
    """
    if not db:
        return jsonify({"error": "Database connection is not configured."}), 500

    user_id = request.user_auth['uid']
    data = request.get_json()
    concept_name = data.get('concept_name')
    if not concept_name:
        return jsonify({"error": "concept_name is required."}), 400

    credits_needed = 1 # This report costs 1 credit per concept
    
    # --- 1. Check and Deduct Credits ---
    customer_ref = db.collection('customers').document(user_id)
    try:
        @firestore.transactional
        def check_and_deduct_credits(transaction, customer_ref, amount):
            snapshot = customer_ref.get(transaction=transaction)
            if not snapshot.exists: raise Exception("Customer profile not found.")
            current_balance = snapshot.get('creditBalance')
            if current_balance is None or current_balance < amount:
                raise ValueError(f"Insufficient credits. This report costs {amount} credit.")
            
            new_balance = current_balance - amount
            transaction.update(customer_ref, {'creditBalance': new_balance})
            return new_balance

        transaction = db.transaction()
        new_balance = check_and_deduct_credits(transaction, customer_ref, credits_needed)
        logger.info(f"Deducted {credits_needed} credit for Foundational Consistency report. New balance: {new_balance}")

    except ValueError as ve: # Insufficient credits
        return jsonify({'status': 'error', 'error': str(ve)}), 403 # 403 Forbidden
    except Exception as e:
        return jsonify({"status": "error", "error": f"Credit check failed: {e}"}), 500

    # --- 2. Generate Report Data (if credits successful) ---
    try:
        # 2a. Get project info
        wip_project_data = pm.load_project(project_id)
        if not wip_project_data:
            raise Exception("WIP project not found.")
        
        # --- This is the key logic for a Universe-aware feature ---
        # We need to find the "Established Lore" project(s)
        # For now, we'll assume a simple structure where the user tells us the lore project ID
        # TODO: This needs to be replaced with logic to find associated Lore projects in the Universe
        lore_project_id = wip_project_data.get('associated_lore_project_id') # This field needs to be added to your project data
        if not lore_project_id:
             raise Exception("This project is not part of a Universe or has no Established Lore project linked.")
        
        # 2b. Initialize DBs for both projects
        wip_db_path = Path(pm.get_project_path(project_id)) / "george.db"
        lore_db_path = Path(pm.get_project_path(lore_project_id)) / "george.db"
        
        wip_db = StructuredDB(db_path=str(wip_db_path))
        lore_db = StructuredDB(db_path=str(lore_db_path))

        # 2c. Get Entity IDs and Chunks from both DBs
        with wip_db:
            wip_entity_id = wip_db.get_entity_id_by_name(concept_name)
            wip_chunks = wip_db.get_chunks_for_entity(wip_entity_id) if wip_entity_id else []
        
        with lore_db:
            lore_entity_id = lore_db.get_entity_id_by_name(concept_name)
            lore_chunks = lore_db.get_chunks_for_entity(lore_entity_id) if lore_entity_id else []

        if not lore_chunks:
            return jsonify({
                "status": "success",
                "report": f"No information found for the concept '{concept_name}' in the Established Lore.",
                "new_credit_balance": new_balance
            })

        # 2d. Initialize Pro model for analysis
        ai_pro = create_george_ai(model="gemini-2.5-pro-latest", use_cloud=True)
        
        # 2e. Batch extract facts from both
        logger.info(f"Extracting facts from {len(lore_chunks)} lore chunks...")
        foundational_facts_list = _batch_extract_facts(ai_pro, lore_chunks, concept_name)
        
        logger.info(f"Extracting facts from {len(wip_chunks)} WIP chunks...")
        wip_facts_list = _batch_extract_facts(ai_pro, wip_chunks, concept_name)

        if not wip_facts_list:
            return jsonify({
                "status": "success",
                "report": f"The concept '{concept_name}' was found in the Established Lore, but no mentions were found in the current Work in Progress.",
                "new_credit_balance": new_balance
            })

        # 2f. Final Synthesis
        logger.info("Running final synthesis...")
        synthesis_prompt = FOUNDATIONAL_CONSISTENCY_PROMPT.format(
            foundational_facts="\n---\n".join(foundational_facts_list),
            wip_facts="\n---\n".join(wip_facts_list)
        )
        
        synthesis_result = ai_pro.chat(synthesis_prompt, temperature=0.2)

        if not synthesis_result['success']:
            raise Exception(f"Final analysis failed: {synthesis_result['error']}")

        # 3. Georgeify and return
        ai_formatter = create_george_ai(model="gemini-flash-lite", use_cloud=True)
        final_report = georgeify_response(
            original_question=f"Run a foundational consistency check on '{concept_name}'",
            raw_ai_answer=synthesis_result['response'],
            george_formatter_ai=ai_formatter
        )
        return jsonify({"status": "success", "report": final_report, "new_credit_balance": new_balance})

    except Exception as e:
        logger.error(f"Failed to generate Foundational Consistency report: {e}", exc_info=True)
        # --- ROLLBACK CREDITS on failure ---
        try:
            customer_ref.update({"creditBalance": firestore.Increment(credits_needed)})
            logger.info(f"Credits refunded for user {user_id} due to report failure.")
        except Exception as refund_e:
            logger.critical(f"FATAL: FAILED TO REFUND 1 CREDIT for user {user_id}: {refund_e}")
        
        return jsonify({"status": "error", "error": f"Failed to generate report: {e}"}), 500
# --- NEW: Standard Continuity Check (No Credit) ---
@api_bp.route('/projects/<project_id>/reports/standard_continuity', methods=['POST'])
@verify_firebase_token()
def report_standard_continuity(project_id):
    """
    Runs a fast, surface-level continuity check on a single entity's
    generated Knowledge Base file. This report is INCLUDED (no credits).
    """
    data = request.get_json()
    entity_name = data.get('entity_name')
    if not entity_name:
        return jsonify({"error": "entity_name is required."}), 400

    logger.info(f"Running Standard Continuity Check for: {entity_name} in project {project_id}")

    try:
        # 1. Get the path to the .md file
        # We use the analyzer's helpers to find the file
        project_root_path_str = pm.get_project_path(project_id)
        # We need an AI instance, but we're not using it for the router, just to pass to QueryAnalyzer
        temp_ai = create_george_ai(model="gemini-flash-lite", use_cloud=True)
        analyzer = QueryAnalyzer(temp_ai, project_path=project_root_path_str)
        
        # Manually find the resource file
        kb_file_name = None
        for category, files in analyzer.available_kb_files.items():
            for f in files:
                if entity_name.lower() in f.lower():
                    kb_file_name = f
                    break
            if kb_file_name: break
        
        if not kb_file_name:
            return jsonify({"error": f"Knowledge base file for '{entity_name}' not found."}), 404

        # 2. Load the file content
        context_str = analyzer.load_context_files({"resources": [kb_file_name], "classification": "FUNC_KB_WRITE"})
        if not context_str:
            return jsonify({"error": f"Could not read content for '{kb_file_name}'."}), 500

        # 3. Call the Flash model for analysis
        ai_flash = create_george_ai(model="gemini-2.0-flash", use_cloud=True)
        analysis_prompt = STANDARD_CONTINUITY_PROMPT.format(profile_text=context_str)
        
        result = ai_flash.chat(analysis_prompt, temperature=0.1)
        if not result['success']:
            return jsonify({"error": f"Analysis failed: {result['error']}"}), 500
        
        # 4. Georgeify and return the result
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

# --- NEW: Deep Continuity Check (Pro Report) ---
@api_bp.route('/projects/<project_id>/reports/deep_continuity', methods=['POST'])
@verify_firebase_token()
def report_deep_continuity(project_id):
    """
    Runs a deep, multi-pass continuity check on a single entity
    by analyzing all its mentions in the manuscript. Costs 1 credit.
    """
    if not db:
        return jsonify({"error": "Database connection is not configured."}), 500

    user_id = request.user_auth['uid']
    data = request.get_json()
    entity_name = data.get('entity_name')
    if not entity_name:
        return jsonify({"error": "entity_name is required."}), 400

    credits_needed = 1 # This report costs 1 credit
    
    # --- 1. Check and Deduct Credits ---
    customer_ref = db.collection('customers').document(user_id)
    try:
        @firestore.transactional
        def check_and_deduct_credits(transaction, customer_ref, amount):
            snapshot = customer_ref.get(transaction=transaction)
            if not snapshot.exists: raise Exception("Customer profile not found.")
            current_balance = snapshot.get('creditBalance')
            if current_balance is None or current_balance < amount:
                raise ValueError(f"Insufficient credits. This report costs {amount} credit.")
            new_balance = current_balance - amount
            transaction.update(customer_ref, {'creditBalance': new_balance})
            return new_balance

        transaction = db.transaction()
        new_balance = check_and_deduct_credits(transaction, customer_ref, credits_needed)
        logger.info(f"Deducted {credits_needed} credit for Deep Continuity report. New balance: {new_balance}")

    except ValueError as ve: # Insufficient credits
        return jsonify({'status': 'error', 'error': str(ve)}), 403 # 403 Forbidden
    except Exception as e:
        return jsonify({"status": "error", "error": f"Credit check failed: {e}"}), 500

    # --- 2. Generate Report Data (if credits successful) ---
    try:
        # 2a. Get the entity ID
        with db:
            entity = db.get_entity_by_name(entity_name)
        if not entity:
            raise ValueError(f"Entity '{entity_name}' not found in the database.")
        entity_id = entity['id']

        # 2b. Get all text chunks for this entity
        with db:
            chunks = db.get_chunks_for_entity(entity_id)
        if not chunks:
            return jsonify({"status": "success", "report": "No scenes found for this entity."})
        
        # 2c. Batch process chunks to extract facts (as planned)
        ai_pro = create_george_ai(model="gemini-2.5-pro-latest", use_cloud=True)
        fact_timeline = []
        
        # We can optimize this by batching text, not just one call per chunk
        # For now, a simple loop:
        for chunk in chunks:
            fact_prompt = f"From the following text, extract all factual statements, actions, and motivations related ONLY to '{entity_name}'.\n\nText: \"{chunk['chunk_text']}\"\n\nFacts:"
            fact_result = ai_pro.chat(fact_prompt, temperature=0.0, timeout=45)
            if fact_result['success']:
                fact_timeline.append(f"Source: {chunk['source_file']}, Location: approx. char {chunk['character_start']}\nFacts: {fact_result['response']}\n")
        
        if not fact_timeline:
             return jsonify({"status": "success", "report": "Could not extract any facts for this entity."})

        # 2d. Final Synthesis
        synthesis_prompt = DEEP_CONTINUITY_PROMPT.format(fact_timeline="\n---\n".join(fact_timeline))
        synthesis_result = ai_pro.chat(synthesis_prompt, temperature=0.2)

        if not synthesis_result['success']:
            raise Exception(f"Final analysis failed: {synthesis_result['error']}")

        # 3. Georgeify and return
        ai_formatter = create_george_ai(model="gemini-flash-lite", use_cloud=True)
        final_report = georgeify_response(
            original_question=f"Run a deep continuity check on {entity_name}",
            raw_ai_answer=synthesis_result['response'],
            george_formatter_ai=ai_formatter
        )
        return jsonify({"status": "success", "report": final_report, "new_credit_balance": new_balance})

    except Exception as e:
        logger.error(f"Failed to generate Deep Continuity report: {e}", exc_info=True)
        # --- ROLLBACK CREDITS on failure ---
        try:
            customer_ref.update({"creditBalance": firestore.Increment(credits_needed)})
            logger.info(f"Credits refunded for user {user_id} due to report failure.")
        except Exception as refund_e:
            logger.critical(f"FATAL: FAILED TO REFUND 1 CREDIT for user {user_id}: {refund_e}")
        
        return jsonify({"status": "error", "error": f"Failed to generate report: {e}"}), 500
    # ... (This function remains the same as before) ...
    return jsonify({'status': 'healthy', 'service': 'Standalone George UI API'})