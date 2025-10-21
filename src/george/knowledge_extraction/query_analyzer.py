"""
Query Analyzer - Determines user intent and identifies required resources using an AI router.
"""
import os
import sys
from pathlib import Path
from typing import List, Dict, Tuple
import json
import logging
import time # For timeout handling

# Add parent to path if needed
current_dir = Path(__file__).parent
george_dir = current_dir.parent
if str(george_dir) not in sys.path:
    sys.path.insert(0, str(george_dir))

# Check if llm_integration can be imported before using it
try:
    from llm_integration import GeorgeAI, DEFAULT_TIMEOUT
    # --- ADD THIS IMPORT ---
    from parsers.parsers import read_manuscript_file 
except ImportError:
    logging.critical("FATAL: Could not import llm_integration. Ensure it's in the Python path.")
    # Define dummy classes/variables to prevent NameErrors later if needed for app structure
    DEFAULT_TIMEOUT = 30
    class GeorgeAI: # Dummy class
        def chat(self, *args, **kwargs):
             return {'success': False, 'response': None, 'error': "LLM Integration module failed to load."}
    def read_manuscript_file(*args, **kwargs): # Dummy function
          raise ImportError("Parsers module failed to load.")

logger = logging.getLogger(__name__)

# --- Load AI Router System Instructions from file ---
PROMPT_DIR = george_dir / "prompts"
AI_ROUTER_PROMPT_FILE = PROMPT_DIR / "ai_router_v3.txt"
AI_ROUTER_SYSTEM_PROMPT = ""
try:
    if not PROMPT_DIR.exists():
        logger.warning(f"Prompts directory not found at {PROMPT_DIR}. Creating it.")
        PROMPT_DIR.mkdir(parents=True, exist_ok=True)

    if not AI_ROUTER_PROMPT_FILE.exists():
         # If the file doesn't exist, create it with a placeholder message
         logger.warning(f"AI Router prompt file not found at {AI_ROUTER_PROMPT_FILE}. Creating placeholder.")
         with open(AI_ROUTER_PROMPT_FILE, 'w', encoding='utf-8') as f:
              f.write("ERROR: Default router prompt. Please replace this with the actual AI Router V3 instructions.")
         AI_ROUTER_SYSTEM_PROMPT = "ERROR: Default router prompt loaded."
    else:
        with open(AI_ROUTER_PROMPT_FILE, 'r', encoding='utf-8') as f:
            AI_ROUTER_SYSTEM_PROMPT = f.read()
        if not AI_ROUTER_SYSTEM_PROMPT or AI_ROUTER_SYSTEM_PROMPT.startswith("ERROR:"):
            raise ValueError("AI Router prompt file is empty or contains placeholder error.")
        logger.info(f"Successfully loaded AI Router prompt from {AI_ROUTER_PROMPT_FILE}")

except Exception as e:
    logger.error(f"FATAL: Error loading AI Router prompt file '{AI_ROUTER_PROMPT_FILE}': {e}")
    AI_ROUTER_SYSTEM_PROMPT = "ERROR: Could not load router prompt."


class QueryAnalyzer:
    """Analyzes user queries using an AI router to determine intent and required resources."""

    def __init__(self,
                 george_ai_router: GeorgeAI,
                 project_path: str, # CHANGED: Now takes the root project path
                 app_help_path: str = "src/george/app_help_docs",
                 default_router_timeout: int = 15): # Added default timeout
        """
        Initialize query analyzer.

        Args:
            george_ai_router: AI instance configured with a fast model for routing.
            project_path: Root directory path for the specific project.
            app_help_path: Directory where app help documents are stored.
            default_router_timeout: Default timeout in seconds for the router AI call.
        """
        self.ai_router = george_ai_router
        # --- Store project root path ---
        self.project_path = Path(project_path) 
        # --- Define KB path relative to project path ---
        self.project_kb_path = self.project_path / "knowledge_base" 
        self.app_help_path = Path(app_help_path)
        self.default_router_timeout = default_router_timeout # Store timeout
        # Initial scans
        self.available_manuscript_files = self._scan_manuscripts(self.project_path)
        self.available_project_files = self._scan_knowledge_base(self.project_kb_path)
        self.available_help_files = self._scan_knowledge_base(self.app_help_path, prefix_map={'help_': 'help'})


    # --- NEW: Function to scan for manuscript files ---
    def _scan_manuscripts(self, project_path: Path) -> List[str]:
        """Scan the project root for manuscript .md files."""
        manuscripts = []
        if not project_path.exists():
             logger.warning(f"Project path not found: {project_path}")
             return manuscripts
        try:
             # Look for .md files directly in the project root
             for file in project_path.glob('*.md'):
                  # Exclude files that might be part of the KB if structure changes
                  if file.is_file() and not str(file).startswith(str(self.project_kb_path)):
                       manuscripts.append(file.name)
             logger.info(f"Scanned {project_path}: Found {len(manuscripts)} manuscript files.")
        except Exception as e:
             logger.error(f"Error scanning manuscript files at {project_path}: {e}")
        return manuscripts


    def _scan_knowledge_base(self, kb_path: Path, prefix_map: Dict = None) -> Dict[str, List[str]]:
        """Scan a knowledge base directory to find all available resource files."""
        resources = {}
        if prefix_map is None:
            prefix_map = {
                'character_': 'characters',
                'location_': 'locations',
                'term_': 'terms'
                # Add more prefixes if needed
            }

        if not kb_path.exists():
            logger.warning(f"Knowledge base path not found: {kb_path}")
            return resources

        try:
            for file in kb_path.glob('*.md'):
                filename = file.stem
                found_prefix = False
                for prefix, category in prefix_map.items():
                    if filename.startswith(prefix):
                        if category not in resources:
                            resources[category] = []
                        # Store the actual filename for later retrieval
                        resources[category].append(file.name)
                        found_prefix = True
                        break
                if not found_prefix:
                    # Store files without a known prefix in a general category
                    if 'general' not in resources:
                        resources['general'] = []
                    resources['general'].append(file.name)
        except Exception as e:
             logger.error(f"Error scanning knowledge base at {kb_path}: {e}")
             return {} # Return empty on error

        logger.info(f"Scanned {kb_path}: Found {sum(len(v) for v in resources.values())} files across {len(resources)} categories.")
        return resources

    def analyze_query(self, user_question: str) -> Dict[str, any]:
        """
        Analyze user question using the AI Router.

        Args:
            user_question: The user's question

        Returns:
            Dictionary with 'classification' and 'resources' keys, or None if analysis fails.
        """
        if AI_ROUTER_SYSTEM_PROMPT.startswith("ERROR:"): # Check if prompt loaded correctly
             logger.error("AI Router cannot function because the system prompt failed to load.")
             return None

        logger.info(f"🔍 Analyzing query with AI Router: {user_question}")

        # Refresh files (consider caching later)
        # Add error handling for scan failures
        try:
             self.available_manuscript_files = self._scan_manuscripts(self.project_path)
             self.available_project_files = self._scan_knowledge_base(self.project_kb_path)
             self.available_help_files = self._scan_knowledge_base(self.app_help_path, prefix_map={'help_': 'help'})
        except Exception as scan_e:
             logger.error(f"Failed to refresh knowledge base files before analysis: {scan_e}")
             # Decide how to handle this - maybe proceed with old cache or return error?
             # For now, return error
             return None


        # Construct prompt - ADD MANUSCRIPT FILES
        prompt_context = f"User Prompt: \"{user_question}\"\n\n"
        prompt_context += "Available Manuscript Files:\n"
        if self.available_manuscript_files:
            prompt_context += f"- {', '.join(self.available_manuscript_files)}\n"
        else:
            prompt_context += "- (No manuscript files found)\n"

        prompt_context += "\nAvailable Project Knowledge Files:\n"
        if self.available_project_files:
            for category, files in self.available_project_files.items():
                prompt_context += f"- {category}: {', '.join(files[:5])}{'...' if len(files) > 5 else ''}\n"
        else:
             prompt_context += "- (No project files found or scanned)\n"

        prompt_context += "\nAvailable App Help Files:\n"
        if self.available_help_files:
            for category, files in self.available_help_files.items():
                 prompt_context += f"- {category}: {', '.join(files)}\n"
        else:
            prompt_context += "- (No help files found or scanned)\n"

        full_prompt = f"{AI_ROUTER_SYSTEM_PROMPT}\n\n{prompt_context}"

        # Call the fast AI model with timeout
        try:
            start_time = time.time()
            result = self.ai_router.chat(
                full_prompt,
                project_context="", # No project context needed for the router itself
                temperature=0.1,
                timeout=self.default_router_timeout # Use the timeout
            )
            elapsed_time = time.time() - start_time
            logger.debug(f"  Router AI call took {elapsed_time:.2f} seconds.")

            if result['success']:
                raw_response = result['response'].strip()
                logger.debug(f"  🤖 Raw Router Response: {raw_response}")
                # Attempt to parse the JSON response
                try:
                    # Clean potential markdown code block fences and other artifacts
                    cleaned_response = raw_response
                    if cleaned_response.startswith("```json"):
                        cleaned_response = cleaned_response[7:]
                    if cleaned_response.endswith("```"):
                        cleaned_response = cleaned_response[:-3]
                    cleaned_response = cleaned_response.strip() # Remove leading/trailing whitespace

                    analysis = json.loads(cleaned_response)
                    # Validate required keys
                    if isinstance(analysis, dict) and "classification" in analysis and "resources" in analysis:
                        # Further validate types if necessary
                        if isinstance(analysis["classification"], str) and isinstance(analysis["resources"], list):
                            logger.info(f"  ✅ Router Analysis: Classification='{analysis['classification']}', Resources={analysis['resources']}")
                            return analysis
                        else:
                             logger.error("  ❌ Router Error: JSON values have incorrect types.")
                             return None
                    else:
                        logger.error("  ❌ Router Error: JSON missing required keys ('classification', 'resources') or is not a dictionary.")
                        return None
                except json.JSONDecodeError as json_e:
                    logger.error(f"  ❌ Router Error: Failed to parse JSON response: {json_e}")
                    logger.error(f"     Raw response was: {raw_response}")
                    return None
            else:
                 # Check if the error was a timeout
                 error_msg = result.get('error', 'Unknown AI error')
                 if "timeout" in error_msg.lower() or "deadline exceeded" in error_msg.lower():
                     logger.error(f"  ❌ Router Error: AI call timed out after {self.default_router_timeout} seconds.")
                 else:
                     logger.error(f"  ❌ Router Error: AI call failed: {error_msg}")
                 return None
        except Exception as e:
            logger.error(f"  ❌ Router Error: Unexpected exception during analysis: {e}", exc_info=True)
            return None

    def load_context_files(self, analysis_result: Dict) -> str:
        """
        Load the content of the resource files identified by the router.

        Args:
            analysis_result: The JSON output from the analyze_query method.

        Returns:
            Combined content string, or an empty string if no relevant files.
        """
        if not analysis_result or not isinstance(analysis_result, dict) or not analysis_result.get("resources"):
            logger.debug("No resources specified by router, returning empty context.")
            return ""

        content_parts = []
        classification = analysis_result.get("classification", "")
        resource_files = analysis_result.get("resources", [])

        # Determine which directory to load from
        # Handle FUNC_KB_WRITE needing project path even if it's functional
        # --- UPDATED LOGIC TO DETERMINE BASE PATH ---
        base_path = None
        is_manuscript = False
        if classification.startswith("TIER_"):
             # For analysis, assume resources might be KB files OR manuscript files
             # We'll determine path file-by-file
             pass # Handled below
        elif classification == "FUNC_KB_WRITE":
             base_path = self.project_kb_path
        elif classification == "FUNC_HELP":
             base_path = self.app_help_path
        else:
             logger.debug(f"Classification '{classification}' requires no file context.")
             return ""


        for filename in resource_files:
             # --- Determine correct path for each file ---
             filepath = None
             current_base_path = base_path # Use specific path if set (e.g., for FUNC_KB_WRITE)

             if classification.startswith("TIER_"):
                 # Is it a manuscript file or a KB file?
                 if filename in self.available_manuscript_files:
                     current_base_path = self.project_path # Root project dir
                     is_manuscript = True
                 elif any(filename in file_list for file_list in self.available_project_files.values()):
                     current_base_path = self.project_kb_path
                     is_manuscript = False
                 else:
                     logger.warning(f"TIER query requested unknown resource: {filename}. Skipping.")
                     continue
             elif current_base_path is None: # Should only happen if logic above is flawed
                  logger.error(f"Could not determine base path for file '{filename}' with classification '{classification}'. Skipping.")
                  continue
             # Additional security checks
             if not isinstance(filename, str) or ".." in filename or filename.startswith("/") or filename.startswith("\\"):
                 logger.warning(f"Skipping potentially unsafe or invalid resource file name: {filename}")
                 continue

             try:
                 filepath = base_path / filename
                 # Ensure the file is actually within the intended directory (defense against symlinks etc.)
                 if not filepath.resolve().is_relative_to(base_path.resolve()):
                      logger.warning(f"Skipping file outside designated directory: {filepath}")
                      continue

                 if filepath.exists() and filepath.is_file():
                     try:
                         # --- Use read_manuscript_file for all types now ---
                         # It handles .md and .txt correctly
                         content = read_manuscript_file(str(filepath))
                         
                         content_parts.append(f"\n--- START CONTEXT FILE: {filename} ---\n")
                         content_parts.append(content)
                         content_parts.append(f"\n--- END CONTEXT FILE: {filename} ---\n")
                     except Exception as e:
                         logger.error(f"Error reading resource file {filepath}: {e}")
                 else:
                     logger.warning(f"Resource file not found or is not a file: {filepath}")
             except Exception as path_e:
                  logger.error(f"Error processing resource path '{filename}' relative to '{base_path}': {path_e}")


        if not content_parts:
            logger.warning(f"No valid content loaded for resources: {resource_files} in path {base_path}")
            # Return a specific message if files were expected but not found/loaded
            return f"Context files ({', '.join(resource_files)}) could not be loaded." if resource_files else ""

        # Join with double newline for clear separation
        return '\n\n'.join(content_parts)


    def build_context_for_query(self, user_question: str) -> Tuple[Dict, str]:
        """
        Build optimized context for answering a user query using the AI Router.

        Args:
            user_question: The user's question

        Returns:
            Tuple containing:
            - analysis_result (Dict): The raw analysis from the router (or None if failed).
            - context_string (str): Focused context string with relevant file content.
        """
        analysis = self.analyze_query(user_question)

        if analysis is None:
            logger.warning("Query analysis failed, returning empty context.")
            # Return the failed analysis object (None) and an error message string
            return None, "Context analysis failed. Please try rephrasing your question."

        # Load the content of the identified files
        context_string = self.load_context_files(analysis)

        return analysis, context_string

# Example Usage (requires an initialized GeorgeAI instance and files)
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    try:
        from llm_integration import create_george_ai
        # Ensure API key is set for Gemini
        
        # Use Flash Lite for the router
        ai_router_instance = create_george_ai(model="gemini-flash-lite", use_cloud=True) 

        # Define paths (adjust if your structure differs)
        script_dir = Path(__file__).resolve().parent.parent # Should be src/george
        example_project_path = script_dir.parent / "data" / "uploads" / "projects" / "EAWAN_txt" # Root project path
        example_help_path = script_dir / "app_help_docs"

        # Create dummy manuscript if it doesn't exist in the project root
        manuscript_file = example_project_path / "EAWAN.md" # Assuming we want .md
        if not manuscript_file.exists():
             # Try to find EAWAN.txt and copy/convert it
             txt_file = script_dir.parent / "data" / "uploads" / "EAWAN.txt"
             if txt_file.exists():
                  with open(txt_file, 'r', encoding='utf-8') as f_in, open(manuscript_file, 'w', encoding='utf-8') as f_out:
                       f_out.write(f_in.read())
                  logger.info(f"Created dummy manuscript {manuscript_file.name} from {txt_file.name}")
             else:
                  with open(manuscript_file, "w", encoding='utf-8') as f:
                       f.write("# Sample Manuscript\n\nThis is the main text.")
                  logger.info(f"Created dummy manuscript {manuscript_file.name}")
                  
        # Ensure help dir exists
        example_help_path.mkdir(parents=True, exist_ok=True)
        help_file = example_help_path / "help_general.md" 
        if not help_file.exists():
            with open(help_file, "w", encoding='utf-8') as f:
                f.write("# General Application Help\n\nThis is where you find help about using George.")

        # --- Pass the root project path to QueryAnalyzer ---
        analyzer = QueryAnalyzer(ai_router_instance, str(example_project_path), str(example_help_path))

        test_queries = [
            "What is Hugh's personality like?", # Should use KB file
            "Analyze the pacing of the manuscript.", # Should request manuscript file
            "How do I create a new project?", # Should use help file
            "Add a note to Linda's file: She seems conflicted.", # Should request KB file
            "Thanks!", # No resources
            "Who paid for Edie Ann's Net?" # Should use KB file
        ]

        for query in test_queries:
            print(f"\n--- Testing Query: '{query}' ---")
            analysis_result, context_str = analyzer.build_context_for_query(query)
            if analysis_result:
                print(f"Analysis: {analysis_result}")
                print(f"Context Length: {len(context_str)} characters")
                print(f"Context Preview:\n{context_str[:500]}{'...' if len(context_str) > 500 else ''}")
            else:
                print(f"Analysis failed. Context returned: {context_str}")
            print("-" * (len(query) + 20))

    except ImportError as ie:
        logger.error(f"Could not import llm_integration: {ie}. Make sure it's in the Python path.")
    except Exception as e:
        logger.error(f"An error occurred during testing: {e}", exc_info=True)