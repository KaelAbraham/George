from flask import Blueprint, jsonify, request, current_app
# --- ADD flash, redirect, url_for for the decorator ---
from flask import flash, redirect, url_for 
import os
import logging
from pathlib import Path
import json # Ensure json is imported

# --- ADD auth import for verifying token ---
from firebase_admin import auth 

# Assuming auth_client is one level up and then into auth folder
# Adjust relative import if your structure differs
try:
    from ..auth.auth_client import verify_firebase_token 
except ImportError:
     # Fallback if running script directly might cause issues
     try:
          from src.george.ui.auth.auth_client import verify_firebase_token
     except ImportError as e:
          logging.critical(f"Could not import verify_firebase_token decorator: {e}")
          # Define a dummy decorator if import fails, so app can load
          def verify_firebase_token():
              def decorator(f):
                  def wrapper(*args, **kwargs):
                      return jsonify({"error": "Auth decorator not loaded"}), 500
                  wrapper.__name__ = f.__name__ + '_dummy_decorated'
                  return wrapper
              return decorator


# Assuming knowledge_extraction and llm_integration are two levels up
try:
    from ...knowledge_extraction.orchestrator import KnowledgeExtractor
    from ...llm_integration import create_george_ai, GeorgeAI
    from ...project_manager import ProjectManager
    from ...parsers.parsers import read_manuscript_file # Needed by QueryAnalyzer if called directly
except ImportError as e:
     logging.critical(f"Could not import core backend modules: {e}")
     # Define dummy classes if import fails
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


api_bp = Blueprint('api', __name__, url_prefix='/api')
logger = logging.getLogger(__name__)

# Initialize Project Manager (Ensure path is correct relative to execution)
try:
     # Calculate base_dir relative to this file's location
     # endpoints.py -> api -> ui -> george -> src -> project_root
     project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
     uploads_base_dir = project_root / 'src' / 'data' / 'uploads'
     pm = ProjectManager(base_dir=str(uploads_base_dir))
     logger.info(f"ProjectManager initialized with base directory: {uploads_base_dir}")
except Exception as init_e:
     logger.critical(f"Failed to initialize ProjectManager: {init_e}", exc_info=True)
     # Define a dummy pm if initialization fails so the app can still load
     class DummyPM:
         def load_project(self, *args, **kwargs): return None
         def get_project_path(self, *args, **kwargs): return "."
         def update_project_status(self, *args, **kwargs): pass
     pm = DummyPM()


# --- Load Georgeification Prompt ---
GEORGEIFY_PROMPT = ""
try:
    current_dir = Path(__file__).parent.parent.parent # src/george/ui -> src/george -> src -> prompts
    prompt_path = current_dir.parent / "prompts" / "george_operational_protocol.txt"
    
    if not prompt_path.parent.exists():
         logger.warning(f"Prompts directory missing: {prompt_path.parent}. Creating.")
         prompt_path.parent.mkdir(parents=True, exist_ok=True)

    if not prompt_path.exists():
         logger.warning(f"Georgeification prompt not found at {prompt_path}. Creating placeholder.")
         with open(prompt_path, 'w', encoding='utf-8') as f:
             # Add a minimal placeholder based on user description
             f.write("""Core Protocol:
- Answer directly. No introductions.
- Use simple, declarative sentences.
- Append citations like $^{citation_source}$.""")
         GEORGEIFY_PROMPT = "ERROR: Default Georgeification prompt loaded." # Indicate placeholder
    else:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            GEORGEIFY_PROMPT = f.read()
        if not GEORGEIFY_PROMPT or GEORGEIFY_PROMPT.startswith("ERROR:"):
            raise ValueError("Georgeification prompt file is empty or contains placeholder error.")
        logger.info(f"Successfully loaded Georgeification prompt from {prompt_path}")

except Exception as e:
    logger.error(f"FATAL: Error loading Georgeification prompt file '{prompt_path}': {e}", exc_info=True)
    GEORGEIFY_PROMPT = "ERROR: Could not load Georgeification prompt."


# --- Updated Georgeify Function ---
def georgeify_response(original_question: str, raw_ai_answer: str, george_formatter_ai: GeorgeAI, sources: list = []) -> str:
    """Formats a raw AI response into George's voice using the operational protocol."""

    if GEORGEIFY_PROMPT.startswith("ERROR:"):
        logger.error("Georgeification cannot proceed because the protocol prompt failed to load.")
        # Return raw answer but add source info if available
        raw_output = f"Raw Answer: {raw_ai_answer}"
        if sources:
             source_tags = [f"$^{src}$" for src in sources]
             raw_output += f"\n\n*Sources: {', '.join(source_tags)}*"
        return raw_output

    # Construct the prompt for the formatting AI
    formatter_prompt = f"{GEORGEIFY_PROMPT}\n\n"
    formatter_prompt += f"Original User Question: \"{original_question}\"\n"
    formatter_prompt += f"Raw AI Answer to Format:\n---\n{raw_ai_answer}\n---\n\n"
    formatter_prompt += "Formatted Response:" # Ask the AI to provide the formatted response

    logger.debug(f"Georgeification Prompt (partial):\n{formatter_prompt[:500]}...")

    try:
        # Use a fast, cheap model for formatting
        result = george_formatter_ai.chat(
            formatter_prompt,
            temperature=0.1, # Low temperature for consistent formatting
            timeout=15 # Reasonable timeout for formatting
        )

        if result['success']:
            formatted_text = result['response'].strip()
            logger.debug(f"Georgeification successful. Formatted text (partial): {formatted_text[:100]}...")
            # Citations should ideally be handled BY the formatter based on the protocol.
            # If not, append them manually as a fallback.
            # Check if the formatted text already seems to include citations based on the protocol
            if sources and "$^" not in formatted_text: # Simple check
                logger.warning("Georgeification model did not seem to include citations; appending manually.")
                source_tags = [f"$^{src}$" for src in sources]
                formatted_text += f"\n\n*Sources: {', '.join(source_tags)}*"
            return formatted_text
        else:
            error_msg = result.get('error', 'Unknown formatting error')
            logger.error(f"Georgeification AI call failed: {error_msg}")
            # Fallback: return the raw answer with a warning and sources
            raw_output = f"(Formatting Error: {error_msg})\nRaw Answer: {raw_ai_answer}"
            if sources:
                 source_tags = [f"$^{src}$" for src in sources]
                 raw_output += f"\n\n*Sources: {', '.join(source_tags)}*"
            return raw_output

    except Exception as e:
        logger.error(f"Error during Georgeification: {e}", exc_info=True)
        # Fallback on exception
        raw_output = f"(Formatting Exception)\nRaw Answer: {raw_ai_answer}"
        if sources:
             source_tags = [f"$^{src}$" for src in sources]
             raw_output += f"\n\n*Sources: {', '.join(source_tags)}*"
        return raw_output


@api_bp.route('/projects/<project_id>/chat', methods=['POST'])
@verify_firebase_token()
def project_chat(project_id):
    """Handles a chat message for a specific project."""
    data = request.get_json()
    question = data.get('question')
    user_info = request.user # User info from decorator

    if not question:
        return jsonify({"error": "No question provided"}), 400

    logger.info(f"Received chat request for project '{project_id}': '{question[:50]}...'")

    try:
        # --- Initialize AI Instances ---
        # Consider making these part of the Flask app context (g) or using a factory
        router_model_name = "gemini-flash-lite"
        formatter_model_name = "gemini-flash-lite"
        default_response_model_name = "gemini-2.0-flash" 

        try:
             ai_router = create_george_ai(model=router_model_name, use_cloud=True)
             ai_formatter = create_george_ai(model=formatter_model_name, use_cloud=True)
             ai_responder = create_george_ai(model=default_response_model_name, use_cloud=True) # Default
        except Exception as ai_init_e:
             logger.critical(f"Failed to initialize AI models: {ai_init_e}", exc_info=True)
             return jsonify({"error": "AI service initialization failed."}), 500

        # --- Instantiate Orchestrator/QueryAnalyzer ---
        project_root_path_str = pm.get_project_path(project_id)
        if not project_root_path_str or not os.path.exists(project_root_path_str):
            logger.error(f"Project path not found for project {project_id}")
            return jsonify({"error": f"Project '{project_id}' not found or path invalid."}), 404
        
        project_kb_path = os.path.join(project_root_path_str, "knowledge_base")
        # Check if KB exists *before* initializing analyzer? Or let analyzer handle it?
        # Let's assume Analyzer needs project root path now
        try:
             # Assuming KnowledgeExtractor now takes ai_router and project_path
             # If KnowledgeExtractor wraps QueryAnalyzer, pass ai_router there
             # For now, let's assume we need QueryAnalyzer directly
             from ...knowledge_extraction.query_analyzer import QueryAnalyzer
             analyzer = QueryAnalyzer(ai_router, project_path=project_root_path_str)
        except Exception as analyzer_init_e:
             logger.critical(f"Failed to initialize QueryAnalyzer: {analyzer_init_e}", exc_info=True)
             return jsonify({"error": "Query analysis service failed to initialize."}), 500


        # --- Run the Full Workflow ---
        logger.debug("1. Analyzing intent and getting context...")
        analysis_result, context_str = analyzer.build_context_for_query(question)

        if analysis_result is None:
            logger.error(f"Query analysis failed for question: '{question[:50]}...'")
            # context_str contains the error message here
            # Apply Georgeification to the error message for consistent tone
            final_answer = georgeify_response(question, context_str, ai_formatter)
            return jsonify({"answer": final_answer}) # Return formatted error

        classification = analysis_result.get("classification")
        sources = analysis_result.get("resources", []) # Get source filenames
        logger.debug(f"  Router classified as '{classification}', resources: {sources}")

        # --- Handle Functional Intents directly ---
        if classification.startswith("FUNC_"):
            logger.info(f"Handling functional intent: {classification}")
            # --- Add specific handlers here ---
            if classification == "FUNC_CONVERSATION":
                raw_answer = "Acknowledged." # Simple canned response
            elif classification == "FUNC_ACCOUNT":
                # TODO: Implement account logic (e.g., fetch subscription from Firestore)
                raw_answer = "Account management features are currently under development."
            elif classification == "FUNC_HELP":
                # The context_str already contains the help file content
                # We can just pass this directly to the formatter
                raw_answer = context_str if context_str else "Could not find relevant help information."
                sources = [] # Don't cite help docs as manuscript sources
            elif classification == "FUNC_KB_WRITE":
                # TODO: Implement KB writing logic (securely update .md / DB / Firestore)
                # Requires extracting the element name and note content from the question
                raw_answer = "Ability to modify the knowledge base via chat is under development."
            elif classification == "FUNC_PROJECT_MGMT":
                 # TODO: Implement project management commands (create, delete etc.)
                 raw_answer = "Project management via chat is under development."
            elif classification == "FUNC_FEEDBACK":
                 # TODO: Log feedback appropriately
                 raw_answer = "Thank you for your feedback."
            else:
                 raw_answer = "This function is not yet implemented."

            # Apply Georgeification to the functional response
            final_answer = georgeify_response(question, raw_answer, ai_formatter)
            return jsonify({"answer": final_answer})


        # --- Proceed with Analysis Intents (TIER_*) ---
        # 2. Select Appropriate Model based on classification (Refined Logic)
        if classification in ["TIER_3", "TIER_4"]:
            response_model_name = "gemini-2.5-flash" # Use better model for complex/subjective
            logger.debug(f"Switching to model {response_model_name} for {classification}")
            try:
                 ai_responder = create_george_ai(model=response_model_name, use_cloud=True)
            except Exception as ai_switch_e:
                 logger.error(f"Failed to switch AI model to {response_model_name}: {ai_switch_e}")
                 # Fallback to default or return error? Fallback for now.
                 ai_responder = create_george_ai(model=default_response_model_name, use_cloud=True)
        # Else, the default ai_responder (2.0 Flash) is used for TIER_1, TIER_2

        # 3. Get Raw Answer from Responder AI
        logger.info(f"Calling responder model ({ai_responder.model}) for classification: {classification}")
        responder_result = ai_responder.chat(
            prompt=question, # Send original question for primary task
            project_context=context_str, # Send loaded context
            temperature=0.5 # Default temperature for analysis
        )

        if not responder_result['success']:
            error_msg = responder_result.get('error', 'Unknown responder error')
            logger.error(f"Responder AI ({ai_responder.model}) failed: {error_msg}")
            # Format the error message using Georgeification
            final_answer = georgeify_response(question, f"Error processing request: {error_msg}", ai_formatter)
            return jsonify({"answer": final_answer})

        raw_answer = responder_result['response']
        logger.debug(f"  Raw Answer Received (partial): {raw_answer[:100]}...")

        # 4. Apply the "Georgeification" Layer (using ai_formatter)
        logger.info("Applying Georgeification layer...")
        # Pass only filenames as sources, not full paths
        source_filenames = [Path(s).name for s in sources]
        final_answer = georgeify_response(question, raw_answer, ai_formatter, source_filenames)

        # 5. Return Final Answer
        logger.info(f"Successfully generated response for project '{project_id}'.")
        return jsonify({"answer": final_answer})

    except FileNotFoundError as fnf_error:
        # ... (File not found handling) ...
    except Exception as e:
        # ... (General exception handling) ...


# --- process_manuscript Endpoint ---
@api_bp.route('/projects/<project_id>/process', methods=['POST'])
@verify_firebase_token()
def process_manuscript(project_id):
    """
    Triggers the full Knowledge Base Generation (AKG) pipeline for a project.
    """
    logger.info(f"Received request to generate KB for project: {project_id}")
    user_info = request.user 

    try:
        # 1. Load project details
        project_data = pm.load_project(project_id)
        # ... (Checks for project_data and manuscript_filenames remain the same) ...
        manuscript_filenames = project_data.get('manuscript_files', [])
        if not manuscript_filenames:
             return jsonify({'status': 'error', 'error': 'No manuscript files found. Please upload a file first.'}), 400

        # For MVP, process only the first file.
        manuscript_filename = manuscript_filenames[0]
        project_path_str = pm.get_project_path(project_id)
        project_path = Path(project_path_str)
        manuscript_path = project_path / manuscript_filename
        knowledge_base_path = project_path / "knowledge_base" # Ensure KB path exists

        if not manuscript_path.exists():
             logger.error(f"Manuscript file not found at path: {manuscript_path}")
             return jsonify({'status': 'error', 'error': f'Manuscript file {manuscript_filename} not found.'}), 404
        
        # Ensure KB directory exists before generation
        knowledge_base_path.mkdir(parents=True, exist_ok=True)

        # 2. Initialize AI Instances needed for KB Generation
        # Use Pro for KB generation as planned
        try:
             # Make sure the model name is correct for Gemini API
             ai_kb_generator = create_george_ai(model="gemini-2.5-pro-latest", use_cloud=True) 
        except Exception as ai_init_e:
             logger.critical(f"Failed to initialize AI model for KB generation: {ai_init_e}", exc_info=True)
             return jsonify({"error": "AI service initialization failed."}), 500

        # Update project status to 'processing' before starting
        try:
             pm.update_project_status(project_id, "processing")
             logger.info(f"Project status updated to 'processing' for {project_id}")
        except Exception as status_e:
             logger.error(f"Could not update project status before generation: {status_e}")
             # Decide whether to proceed or fail here. Let's proceed but log warning.


        # 3. Instantiate and run the Knowledge Extractor's generation process
        # Assuming KnowledgeExtractor needs the AI instance and the project root path
        try:
             extractor = KnowledgeExtractor(ai_kb_generator, project_path=project_path_str) 
        except Exception as extractor_init_e:
             logger.critical(f"Failed to initialize KnowledgeExtractor: {extractor_init_e}", exc_info=True)
             pm.update_project_status(project_id, "error") # Set status back to error
             return jsonify({"error": "Knowledge extraction service failed to initialize."}), 500
        
        logger.info(f"Starting KB generation for {project_id} using {manuscript_filename}...")
        
        # --- THIS IS THE CORE CALL ---
        # Make sure generate_knowledge_base takes the filename relative to project_path
        generation_result = extractor.generate_knowledge_base(manuscript_filename) 

        if generation_result.get('success'):
            logger.info(f"KB generation successful for {project_id}.")
            pm.update_project_status(project_id, "ready") 
            
            entity_count = generation_result.get('entities_found', 0)
            files_created = generation_result.get('files_created', 0)
            message = f"{entity_count} entities identified, {files_created} knowledge files created."

            return jsonify({
                'status': 'success', # Indicate completion
                'message': message
            })
        else:
            error_msg = generation_result.get('error', 'Unknown error during generation')
            logger.error(f"KB generation failed for {project_id}: {error_msg}")
            pm.update_project_status(project_id, "error")
            return jsonify({
                'status': 'error',
                'error': f"Knowledge base generation failed: {error_msg}"
            }), 500 # Return 500 for server-side failure

    except FileNotFoundError as fnf_error:
        # ... (File not found handling) ...
    except Exception as e:
        # ... (General exception handling, ensure status is set to error) ...
        try:
             pm.update_project_status(project_id, "error")
        except:
             pass 
        return jsonify({"error": f"An unexpected server error occurred: {e}"}), 500


# --- Health Check (keep as is) ---
@api_bp.route('/health')
def health_check():
    # ...
    pass

# --- Remove Mock Endpoints ---
# Remove or comment out list_projects, get_project, get_job_status if not needed