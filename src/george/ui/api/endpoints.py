from flask import Blueprint, jsonify, request, current_app # Added current_app
from ..auth.auth_client import verify_firebase_token
from ...knowledge_extraction.orchestrator import KnowledgeExtractor
from ...knowledge_extraction.query_analyzer import QueryAnalyzer
from ...llm_integration import create_george_ai, GeorgeAI # Import GeorgeAI class
import os
import logging # Added logging
from pathlib import Path # Added Path

api_bp = Blueprint('api', __name__, url_prefix='/api')
logger = logging.getLogger(__name__) # Added logger

# --- Load Georgeification Prompt ---
GEORGEIFY_PROMPT = ""
try:
    # Construct the path relative to the current file's location
    current_dir = Path(__file__).parent
    prompt_path = current_dir.parent.parent / "prompts" / "george_operational_protocol.txt"
    if not prompt_path.exists():
         # Attempt to create the file with a placeholder if it doesn't exist
         logger.warning(f"Georgeification prompt not found at {prompt_path}. Creating placeholder.")
         prompt_path.parent.mkdir(parents=True, exist_ok=True)
         with open(prompt_path, 'w', encoding='utf-8') as f:
             f.write("ERROR: Default Georgeification prompt. Please replace with George Operational Protocol.")
         GEORGEIFY_PROMPT = "ERROR: Default Georgeification prompt loaded."
    else:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            GEORGEIFY_PROMPT = f.read()
        if not GEORGEIFY_PROMPT or GEORGEIFY_PROMPT.startswith("ERROR:"):
            raise ValueError("Georgeification prompt file is empty or contains placeholder error.")
        logger.info(f"Successfully loaded Georgeification prompt from {prompt_path}")
except Exception as e:
    logger.error(f"FATAL: Error loading Georgeification prompt file '{prompt_path}': {e}")
    GEORGEIFY_PROMPT = "ERROR: Could not load Georgeification prompt."

# --- Updated Georgeify Function ---
def georgeify_response(original_question: str, raw_ai_answer: str, george_formatter_ai: GeorgeAI, sources: list = []) -> str:
    """Formats a raw AI response into George's voice using the operational protocol."""

    if GEORGEIFY_PROMPT.startswith("ERROR:"):
        logger.error("Georgeification cannot proceed because the protocol prompt failed to load.")
        return f"Error: Could not format response.\nRaw Answer: {raw_ai_answer}" # Return raw answer with error

    # Construct the prompt for the formatting AI
    formatter_prompt = f"{GEORGEIFY_PROMPT}\n\n"
    formatter_prompt += f"Original User Question: \"{original_question}\"\n"
    formatter_prompt += f"Raw AI Answer to Format:\n---\n{raw_ai_answer}\n---\n\n"
    formatter_prompt += "Important: Remove all LaTeX citation markers like $^{\\text{citation\\_source}}$ and replace them with simple superscript numbers [1], [2], etc.\n"
    formatter_prompt += "Formatted Response:"

    try:
        # Use a fast, cheap model for formatting
        result = george_formatter_ai.chat(
            formatter_prompt,
            temperature=0.1, # Low temperature for consistent formatting
            timeout=15 # Reasonable timeout for formatting
        )

        if result['success']:
            formatted_text = result['response'].strip()
            
            # Clean up any remaining LaTeX artifacts
            import re
            # Remove LaTeX citation markers
            formatted_text = re.sub(r'\$\^\{\\text\{citation\\_source\}\}\$', '', formatted_text)
            # Remove other LaTeX artifacts
            formatted_text = re.sub(r'\$\^([^$]+)\$', r'[\1]', formatted_text)
            
            # Clean up the sources section if it exists
            if "*Sources:" in formatted_text:
                # Extract and clean the sources line
                formatted_text = re.sub(r'\*Sources:\s*\$\^([^$]+)\$\*', r'*Source: \1*', formatted_text)
            elif sources:
                # Add clean source list
                source_list = ', '.join(sources)
                formatted_text += f"\n\n*Sources: {source_list}*"
                
            return formatted_text
        else:
            logger.error(f"Georgeification AI call failed: {result.get('error')}")
            # Fallback: return the raw answer with a warning
            return f"(Formatting Error)\nRaw Answer: {raw_ai_answer}"

    except Exception as e:
        logger.error(f"Error during Georgeification: {e}", exc_info=True)
        return f"(Formatting Exception)\nRaw Answer: {raw_ai_answer}"


@api_bp.route('/projects/<project_id>/chat', methods=['POST'])
@verify_firebase_token()
def project_chat(project_id):
    """Handles a chat message for a specific project."""
    logger.info(f"=" * 60)
    logger.info(f"CHAT REQUEST RECEIVED for project: {project_id}")
    logger.info(f"=" * 60)
    
    data = request.get_json()
    question = data.get('question')
    user_info = request.user # User info from decorator
    
    logger.info(f"Question: {question}")

    if not question:
        return jsonify({"error": "No question provided"}), 400

    try:
        # Check if API key is set
        import os
        api_key = os.environ.get('GEMINI_API_KEY')
        logger.info(f"API Key present: {bool(api_key)}")
        if api_key:
            logger.info(f"API Key length: {len(api_key)}")
        else:
            logger.error("GEMINI_API_KEY is not set!")
            return jsonify({"answer": "Configuration error: API key is missing. Please contact support."}), 200
        
        logger.info("Initializing AI instances...")
        # --- Initialize AI Instances ---
        # Get model choices based on user tier or request type (future enhancement)
        # For now, hardcode based on our plan
        router_model_name = "gemini-flash-lite" # Use Flash Lite for routing
        formatter_model_name = "gemini-flash-lite" # Use Flash Lite for formatting
        # Default response model (can be overridden by router later)
        default_response_model_name = "gemini-2.0-flash" 

        # Create AI instances (Consider managing these globally in Flask app context)
        ai_router = create_george_ai(model=router_model_name, use_cloud=True)
        ai_formatter = create_george_ai(model=formatter_model_name, use_cloud=True)
        ai_responder = create_george_ai(model=default_response_model_name, use_cloud=True) # Default

        # --- Get project path using ProjectManager ---
        pm = current_app.project_manager
        project_path = pm.get_project_path(project_id)
        if not project_path or not os.path.exists(project_path):
            logger.error(f"Project not found: {project_id}")
            return jsonify({"error": f"Project '{project_id}' not found."}), 404
            
        project_kb_path = os.path.join(project_path, "knowledge_base")
        if not os.path.exists(project_kb_path):
             # Handle case where KB hasn't been generated yet
             logger.warning(f"Knowledge base not found for project {project_id} at {project_kb_path}")
             # Optionally, trigger KB generation or return a specific message
             return jsonify({"answer": f"The knowledge base for project '{project_id}' has not been generated yet. Please process the manuscript first."})
        
        # Create QueryAnalyzer to analyze the query and load context
        query_analyzer = QueryAnalyzer(ai_router, project_kb_path) 

        # --- Run the Full Workflow ---
        # 1. Analyze Intent & Get Context (using ai_router via QueryAnalyzer)
        logger.info(f"Analyzing query: {question}")
        analysis_result, context_str = query_analyzer.build_context_for_query(question)

        if analysis_result is None:
            # Handle analysis failure - context_str contains error message
            logger.error(f"Query analysis failed: {context_str}")
            return jsonify({"answer": f"I'm having trouble understanding your question. {context_str}"}), 200

        classification = analysis_result.get("classification")

        # 2. Select Appropriate Model based on classification (Example Logic)
        if classification.startswith("TIER_3") or classification.startswith("TIER_4"):
            # Use a more powerful model for complex/subjective analysis if needed
             response_model_name = "gemini-2.5-flash" # Upgrade model
             ai_responder = create_george_ai(model=response_model_name, use_cloud=True)
        # Add more logic here for FUNC_ types that might need specific handling or models

        # --- Handle Functional Intents directly if they don't need context/responder AI ---
        if classification == "FUNC_CONVERSATION":
             # Simple canned response for conversation, skip main AI call
             # Apply Georgeification for consistency
             final_answer = georgeify_response(question, "Acknowledged.", ai_formatter)
             return jsonify({"answer": final_answer})
        elif classification == "FUNC_ACCOUNT":
             # TODO: Implement account logic (e.g., fetch from Firestore)
             final_answer = georgeify_response(question, "Account features are not yet implemented.", ai_formatter)
             return jsonify({"answer": final_answer})
        # Add handlers for FUNC_HELP, FUNC_KB_WRITE, FUNC_PROJECT_MGMT, FUNC_FEEDBACK etc.


        # --- Proceed with Analysis Intents (TIER_*) ---
        # 3. Get Raw Answer from Responder AI
        logger.info(f"Calling responder model ({ai_responder.model}) for classification: {classification}")
        responder_result = ai_responder.chat(
            prompt=question, # Send original question for primary task
            project_context=context_str, # Send loaded context
            temperature=0.5 # Allow some flexibility for analysis
        )

        if not responder_result['success']:
            logger.error(f"Responder AI failed: {responder_result.get('error')}")
            return jsonify({"error": f"Failed to get response: {responder_result.get('error')}"}), 500

        raw_answer = responder_result['response']
        sources = analysis_result.get("resources", []) # Get sources identified by router

        # 4. Apply the "Georgeification" Layer (using ai_formatter)
        logger.info("Applying Georgeification layer...")
        final_answer = georgeify_response(question, raw_answer, ai_formatter, sources)

        # 5. Return Final Answer
        return jsonify({"answer": final_answer})

    except FileNotFoundError as fnf_error:
        logger.error(f"File not found during chat processing: {fnf_error}")
        return jsonify({"error": "A required file or directory was not found. Has the knowledge base been generated?"}), 500
    except Exception as e:
        logger.error(f"Error in project_chat endpoint: {e}", exc_info=True)
        return jsonify({"error": f"An unexpected server error occurred: {e}"}), 500


@api_bp.route('/projects/<project_id>/process', methods=['POST'])
@verify_firebase_token()
def process_manuscript(project_id):
    """
    Triggers the full Knowledge Base Generation (AKG) pipeline for a project.
    """
    logger.info(f"Received request to generate KB for project: {project_id}")
    user_info = request.user # Get user info if needed later

    try:
        # 1. Load project details to find the manuscript file(s)
        pm = current_app.project_manager
        project_data = pm.load_project(project_id)
        if not project_data:
            logger.error(f"Project not found: {project_id}")
            return jsonify({'status': 'error', 'error': 'Project not found'}), 404

        manuscript_filenames = project_data.get('manuscripts', [])
        if not manuscript_filenames:
            logger.error(f"No manuscript files found for project: {project_id}")
            return jsonify({'status': 'error', 'error': 'No manuscript files found for this project. Please upload a file first.'}), 400

        # For MVP, process only the first file. Future: Loop or combine.
        manuscript_filename = manuscript_filenames[0]
        project_path = pm.get_project_path(project_id)
        manuscript_path = os.path.join(project_path, "manuscripts", manuscript_filename)
        knowledge_base_path = os.path.join(project_path, "knowledge_base")

        if not os.path.exists(manuscript_path):
             logger.error(f"Manuscript file not found at path: {manuscript_path}")
             return jsonify({'status': 'error', 'error': f'Manuscript file {manuscript_filename} not found.'}), 404

        # 2. Initialize AI Instances needed for KB Generation
        # Use Pro for KB generation as planned
        ai_responder = create_george_ai(model="gemini-2.5-pro", use_cloud=True)
        # Router might not be needed here unless generate_knowledge_base uses it internally
        
        # 3. Read the manuscript file with fallback encoding handling
        try:
            with open(manuscript_path, 'r', encoding='utf-8') as f:
                manuscript_text = f.read()
        except UnicodeDecodeError:
            # Try Windows-1252 encoding if UTF-8 fails
            logger.warning(f"UTF-8 decoding failed for {manuscript_filename}, trying Windows-1252")
            with open(manuscript_path, 'r', encoding='windows-1252') as f:
                manuscript_text = f.read()
        
        # 4. Instantiate and run the Knowledge Extractor's generation process
        # Pass the AI instance needed by the extractor/profile_builder
        extractor = KnowledgeExtractor(ai_responder, project_path=project_path) 
        
        logger.info(f"Starting KB generation for {project_id} using {manuscript_filename}...")
        
        # --- THIS IS THE CORE CALL ---
        # process_manuscript extracts entities, runs pipeline, saves MD files
        generation_result = extractor.process_manuscript(manuscript_text, manuscript_filename) 

        # Check if processing was successful
        logger.info(f"KB generation successful for {project_id}.")
        # Update project status (e.g., in project JSON or future DB)
        pm.update_project_status(project_id, "ready") 
        
        # Construct a more informative message from the result
        entity_count = len(generation_result.get('entities', {}))
        message = f"Knowledge base generated successfully! {entity_count} entities extracted."

        return jsonify({
            'status': 'success',
            'message': message
        })

    except FileNotFoundError as fnf_error:
        logger.error(f"File not found during KB generation setup for {project_id}: {fnf_error}")
        return jsonify({"error": f"Configuration error: {fnf_error}"}), 500
    except Exception as e:
        logger.error(f"Unexpected error during KB generation for {project_id}: {e}", exc_info=True)
        # Attempt to update status even on unexpected failure
        try:
             pm.update_project_status(project_id, "error")
        except:
             pass # Ignore error during error handling
        return jsonify({"error": f"An unexpected server error occurred: {e}"}), 500


# --- Other API endpoints remain below ---
# ... (health_check, list_projects, get_project, get_job_status) ...