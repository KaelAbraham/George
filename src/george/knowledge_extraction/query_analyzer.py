"""
Query Analyzer - Determines user intent and identifies required resources using an AI router.
"""
import os
import sys
from pathlib import Path
from typing import List, Dict, Tuple
import json
import logging

# Add parent to path if needed
current_dir = Path(__file__).parent
george_dir = current_dir.parent
if str(george_dir) not in sys.path:
    sys.path.insert(0, str(george_dir))

from llm_integration import GeorgeAI

logger = logging.getLogger(__name__)

# --- AI Router System Instructions (v3) ---
# It's good practice to load this from a file, but for simplicity now, we embed it.
# TODO: Move this prompt to an external file (e.g., ai_router_prompt.txt)
AI_ROUTER_SYSTEM_PROMPT = """
You are a prompt classification router for the "George" AI writing assistant. Your purpose is twofold:
1. Classify the user's prompt by its intent (e.g., TIER_1, FUNC_HELP).
2. Identify the necessary knowledge base resources (files) required to answer the prompt.

You will respond only with a single JSON object. Do not add any other text.

JSON Output Format:
{
  "classification": "CLASSIFICATION_LABEL",
  "resources": ["file1.txt"]
}

Part 1: Classification Labels (Intent)
You must select one label from the two categories below.

A. Analysis Intents (Manuscript)
TIER_1 (Low Complexity / Factual Retrieval)
Trigger: Asks for a specific, discrete piece of data from the text.
Keywords: "Who," "What," "When," "Where," "Describe," "Why" (simple fact).
TIER_2 (Medium Complexity / Synthesis & Analysis)
Trigger: Requires synthesizing multiple data points or analyzing a literary pattern.
Keywords: "How," "Compare," "Analyze," "pacing," "character voice," "consistency."
TIER_3 (High Complexity / Subjective & Creative)
Trigger: Asks for an opinion, value judgment, or creative ideas.
Keywords: "What do you think," "Is this good," "Brainstorm," "Give me ideas."
TIER_4 (High Complexity / Emotional & Meta)
Trigger: Expresses user frustration, insecurity, or "stuckness."
Keywords: "I'm stuck," "frustrated," "banging my head," "doesn't feel right."

B. Functional Intents (Application)
FUNC_HELP
Trigger: Asks how to use the "George" application.
Keywords: "How do I," "What does this button do," "Help with..."
FUNC_ACCOUNT
Trigger: Asks about user account details, subscription, or login.
Keywords: "My account," "Password," "Subscription," "Billing," "Username."
FUNC_KB_WRITE
Trigger: Asks to add, delete, or modify information in a knowledge base file.
Keywords: "Add this," "Update file," "Change this detail," "Append to notes."
FUNC_MESSAGE
Trigger: Asks to send a message to another user on the platform.
Keywords: "Tell [User]," "Send a message to," "Ask [User]."
FUNC_PROJECT_MGMT
Trigger: Asks to manage projects, files, or folders.
Keywords: "Create new project," "Load file," "Delete project," "Save."
FUNC_CONVERSATION
Trigger: General social interaction, not a specific task.
Keywords: "Hello," "Hi," "Thanks," "Thank you," "How are you?"
FUNC_FEEDBACK
Trigger: Provides feedback on the AI's performance.
Keywords: "You were wrong," "Good job," "Bad answer," "I like this."

Part 2: Resource Analysis (Subject)
For TIER_ (Analysis) Prompts: Attach the relevant manuscript or character files (e.g., ["EAWAN.txt"]).
For FUNC_HELP: Attach the application knowledge base (e.g., ["George_KB.txt"]).
For FUNC_KB_WRITE: Attach the file to be modified (e.g., ["Captain_Eva.txt"]).
For all others (FUNC_ACCOUNT, FUNC_MESSAGE, etc.): The resources array should be empty ([]).
"""

class QueryAnalyzer:
    """Analyzes user queries using an AI router to determine intent and required resources."""

    def __init__(self, george_ai_router: GeorgeAI, project_kb_path: str, app_help_path: str = "src/george/app_help_docs"):
        """
        Initialize query analyzer.

        Args:
            george_ai_router: AI instance specifically configured with a fast model (e.g., Flash Lite) for routing.
            project_kb_path: Directory where project-specific entity profiles are stored.
            app_help_path: Directory where application help documents are stored.
        """
        self.ai_router = george_ai_router
        self.project_kb_path = Path(project_kb_path)
        self.app_help_path = Path(app_help_path)
        self.available_project_files = self._scan_knowledge_base(self.project_kb_path)
        self.available_help_files = self._scan_knowledge_base(self.app_help_path, prefix_map={'help_': 'help'}) # Treat all as 'help' type


    def _scan_knowledge_base(self, kb_path: Path, prefix_map: Dict = None) -> Dict[str, List[str]]:
        """Scan a knowledge base directory to find all available resource files."""
        resources = {}
        if prefix_map is None:
            prefix_map = {
                'character_': 'characters',
                'location_': 'locations',
                'term_': 'terms'
            }

        if not kb_path.exists():
            logger.warning(f"Knowledge base path not found: {kb_path}")
            return resources

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

        logger.info(f"Scanned {kb_path}: Found {sum(len(v) for v in resources.values())} files across {len(resources)} categories.")
        return resources

    def analyze_query(self, user_question: str) -> Dict[str, any]:
        """
        Analyze user question using the AI Router.

        Args:
            user_question: The user's question

        Returns:
            Dictionary with 'classification' and 'resources' keys, or None if analysis fails.
            Example: {"classification": "TIER_1", "resources": ["character_Hugh.md"]}
        """
        logger.info(f"🔍 Analyzing query with AI Router: {user_question}")

        # Refresh available files (in case new ones were added)
        # In a production app, this might be triggered differently or cached
        self.available_project_files = self._scan_knowledge_base(self.project_kb_path)
        self.available_help_files = self._scan_knowledge_base(self.app_help_path, prefix_map={'help_': 'help'})

        # Construct the prompt for the AI Router
        prompt_context = f"User Prompt: \"{user_question}\"\n\n"
        prompt_context += "Available Project Knowledge Files:\n"
        for category, files in self.available_project_files.items():
            prompt_context += f"- {category}: {', '.join(files[:5])}{'...' if len(files) > 5 else ''}\n" # Show only first few

        prompt_context += "\nAvailable App Help Files:\n"
        for category, files in self.available_help_files.items():
            prompt_context += f"- {category}: {', '.join(files)}\n"

        full_prompt = f"{AI_ROUTER_SYSTEM_PROMPT}\n\n{prompt_context}"

        # Call the fast AI model designated for routing
        try:
            # Use a low temperature for deterministic classification
            result = self.ai_router.chat(full_prompt, project_context="", temperature=0.1)

            if result['success']:
                raw_response = result['response'].strip()
                logger.debug(f"  🤖 Raw Router Response: {raw_response}")

                # Attempt to parse the JSON response
                try:
                    # Clean potential markdown code block fences
                    if raw_response.startswith("```json"):
                        raw_response = raw_response[7:]
                    if raw_response.endswith("```"):
                        raw_response = raw_response[:-3]

                    analysis = json.loads(raw_response)
                    if "classification" in analysis and "resources" in analysis:
                        logger.info(f"  ✅ Router Analysis: Classification='{analysis['classification']}', Resources={analysis['resources']}")
                        return analysis
                    else:
                        logger.error("  ❌ Router Error: JSON missing required keys.")
                        return None
                except json.JSONDecodeError as json_e:
                    logger.error(f"  ❌ Router Error: Failed to parse JSON response: {json_e}")
                    logger.error(f"     Raw response was: {raw_response}")
                    # Attempt a fallback if possible (e.g., simple keyword check) - omitted for now
                    return None
            else:
                logger.error(f"  ❌ Router Error: AI call failed: {result.get('error')}")
                return None
        except Exception as e:
            logger.error(f"  ❌ Router Error: Unexpected exception during analysis: {e}")
            return None

    def load_context_files(self, analysis_result: Dict) -> str:
        """
        Load the content of the resource files identified by the router.

        Args:
            analysis_result: The JSON output from the analyze_query method.

        Returns:
            Combined content string, or an empty string if no relevant files.
        """
        if not analysis_result or not analysis_result.get("resources"):
            return ""

        content_parts = []
        classification = analysis_result.get("classification", "")
        resource_files = analysis_result.get("resources", [])

        # Determine which directory to load from based on classification
        base_path = self.project_kb_path if classification.startswith("TIER_") or classification == "FUNC_KB_WRITE" else self.app_help_path

        for filename in resource_files:
            # Basic security check: ensure filename doesn't try to escape the base path
            if ".." in filename or filename.startswith("/"):
                logger.warning(f"Skipping potentially unsafe resource file: {filename}")
                continue

            filepath = base_path / filename
            if filepath.exists() and filepath.is_file():
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        # Add a header indicating the source file
                        content_parts.append(f"--- START FILE: {filename} ---")
                        content_parts.append(f.read())
                        content_parts.append(f"--- END FILE: {filename} ---")
                except Exception as e:
                    logger.error(f"Error reading resource file {filepath}: {e}")
            else:
                logger.warning(f"Resource file not found or is not a file: {filepath}")

        if not content_parts:
            logger.warning(f"No valid content loaded for resources: {resource_files}")
            return "No specific context files available for this query."

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
            # Fallback if router fails: maybe just return basic project info or empty string
            return None, "Context analysis failed. Please try rephrasing your question."

        # Load the content of the identified files
        context_string = self.load_context_files(analysis)

        return analysis, context_string

# Example Usage (requires an initialized GeorgeAI instance)
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    try:
        # Example setup - replace with your actual AI setup
        from llm_integration import create_george_ai
        # IMPORTANT: Use a fast model for the router itself!
        ai_router_instance = create_george_ai(model="gemini-2.0-flash-lite", use_cloud=True) # Use Flash Lite for routing

        # Point to where your test knowledge base files are
        # For this example, assuming they are in 'src/data/uploads/projects/EAWAN_txt/knowledge_base'
        script_dir = Path(__file__).parent.parent # Should resolve to src/george
        example_kb_path = script_dir.parent / "data" / "uploads" / "projects" / "EAWAN_txt" / "knowledge_base"
        example_help_path = script_dir / "app_help_docs" # Create this folder

        # Create dummy help file if it doesn't exist
        example_help_path.mkdir(exist_ok=True)
        help_file = example_help_path / "help_general.md"
        if not help_file.exists():
            with open(help_file, "w") as f:
                f.write("# General Help\n\nAsk George questions about your manuscript.")

        analyzer = QueryAnalyzer(ai_router_instance, str(example_kb_path), str(example_help_path))

        test_queries = [
            "What is Hugh's personality like?",
            "Tell me about the Twist Drive", # Assuming term_Twist_Drive.md exists
            "How do I create a new project?",
            "Add a note to Linda's file: She seems conflicted.",
            "Thanks!",
            "Who paid for Edie Ann's Net?" # Test AI inference
        ]

        for query in test_queries:
            print(f"\n--- Testing Query: '{query}' ---")
            analysis_result, context_str = analyzer.build_context_for_query(query)
            if analysis_result:
                print(f"Analysis: {analysis_result}")
                print(f"Context Length: {len(context_str)} characters")
                print(f"Context Preview:\n{context_str[:300]}{'...' if len(context_str) > 300 else ''}")
            else:
                print("Analysis failed.")
            print("-" * (len(query) + 20))

    except ImportError:
        logger.error("Could not import llm_integration. Make sure it's in the Python path.")
    except Exception as e:
        logger.error(f"An error occurred during testing: {e}")