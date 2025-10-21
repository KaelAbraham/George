import os
import sys
from pathlib import Path
import google.generativeai as genai
import ollama
import logging
from dotenv import load_dotenv
from typing import Dict # Added for type hinting

# Add parent to path if needed to find local modules
current_dir = Path(__file__).parent
george_dir = current_dir # Assuming llm_integration is directly in src/george
if str(george_dir) not in sys.path:
    sys.path.insert(0, str(george_dir))

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables (like API key)
load_dotenv()

# --- NEW: Default timeout in seconds for AI calls ---
DEFAULT_TIMEOUT = 30 

class GeorgeAI:
    """Handles interactions with different LLM backends (local Ollama or cloud Gemini)."""

    def __init__(self, model: str = "phi3:mini:instruct", use_cloud: bool = False):
        """
        Initialize the AI client.

        Args:
            model (str): Name of the model to use (Ollama model name or Gemini model name).
            use_cloud (bool): If True, use Google Gemini API; otherwise, use local Ollama.
        """
        self.model = model
        self.use_cloud = use_cloud
        self.gemini_model = None

        if use_cloud:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                logger.error("❌ GEMINI_API_KEY not found in environment variables.")
                # Allow initialization but Gemini calls will fail
            else:
                try:
                    genai.configure(api_key=api_key)
                    self.gemini_model = genai.GenerativeModel(model)
                    logger.info(f"☁️ Configured Google Gemini with model: {model}")
                except Exception as e:
                    logger.error(f"❌ Failed to configure Google Gemini: {e}")
        else:
            try:
                # Check if Ollama service is running by listing local models
                ollama.list()
                logger.info(f"🤖 Configured local Ollama with model: {model}")
                # You might want to add a check here if self.model actually exists locally
            except Exception as e:
                logger.error(f"❌ Failed to connect to local Ollama service. Is it running? Error: {e}")
                # Allow initialization but Ollama calls will fail


    def chat(self, prompt: str, project_context: str = "", temperature: float = 0.7, timeout: int = DEFAULT_TIMEOUT) -> Dict:
        """
        Main chat method, routes to appropriate backend based on configuration.

        Args:
            prompt (str): The main user prompt or system instruction.
            project_context (str): Specific context from the project knowledge base.
            temperature (float): Controls randomness in generation.
            timeout (int): Maximum time in seconds to wait for a response.

        Returns:
            Dict: {'success': bool, 'response': str, 'error': str (if !success)}
        """
        # Combine prompt and context carefully
        full_prompt = prompt # Start with system prompt or main query
        if project_context:
             full_prompt += f"\n\n--- Start Context ---\n{project_context}\n--- End Context ---"
        #logger.debug(f"Full prompt being sent:\n{full_prompt[:500]}...") # Log beginning of prompt

        try:
            if self.use_cloud:
                if not self.gemini_model:
                     return {'success': False, 'response': None, 'error': "Gemini client not initialized. Check API key."}
                return self._chat_with_gemini(full_prompt, temperature, timeout)
            else:
                # Add check if ollama connection failed during init
                return self._chat_with_ollama(full_prompt, temperature, timeout)
        except Exception as e:
            logger.error(f"❌ Unexpected error in chat method: {e}", exc_info=True)
            return {'success': False, 'response': None, 'error': f"Unexpected error: {e}"}


    def _chat_with_ollama(self, prompt: str, temperature: float, timeout: int) -> Dict:
        """Sends a prompt to the configured local Ollama model."""
        # Note: Ollama library doesn't seem to support timeout directly in ollama.chat
        # We'll log a warning if the provided timeout isn't the default.
        if timeout != DEFAULT_TIMEOUT:
             logger.warning("Ollama API call does not directly support a custom timeout parameter via this library method.")

        try:
            logger.info(f"🤖 Calling local Ollama model: {self.model}")
            response = ollama.chat(
                model=self.model,
                messages=[{'role': 'user', 'content': prompt}],
                options={'temperature': temperature},
            )
            # Check for empty response content
            if not response or 'message' not in response or 'content' not in response['message']:
                 logger.error("❌ Ollama response structure invalid or content missing.")
                 return {'success': False, 'response': None, 'error': "Invalid or empty response from Ollama."}

            logger.info("  Ollama call successful.")
            return {'success': True, 'response': response['message']['content'], 'error': None}
        except Exception as e:
            logger.error(f"❌ Error calling Ollama: {e}", exc_info=True)
            return {'success': False, 'response': None, 'error': f"Ollama API call failed: {e}"}

    def _chat_with_gemini(self, prompt: str, temperature: float, timeout: int) -> Dict:
        """Sends a prompt to the configured Google Gemini model."""
        if not self.gemini_model:
            # This check is technically redundant due to the check in chat(), but good practice
            return {'success': False, 'response': None, 'error': "Gemini client not initialized."}

        try:
            logger.info(f"☁️ Calling Google Gemini model: {self.model} with timeout {timeout}s")
            # Use request_options for timeout
            response = self.gemini_model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(temperature=temperature),
                request_options={'timeout': timeout} # Pass timeout here
            )

            # --- Improved Safety Handling ---
            if not response.candidates:
                 block_reason = "Unknown safety block"
                 finish_reason = "Unknown finish reason"
                 try:
                     # Attempt to get more specific reasons if available
                     if hasattr(response, 'prompt_feedback') and hasattr(response.prompt_feedback, 'block_reason'):
                         block_reason = response.prompt_feedback.block_reason.name
                     # Sometimes the block reason is in the candidate's finish_reason
                     # (Need to access internal _result, which is fragile)
                     # Let's rely on prompt_feedback for now.
                 except Exception as fb_e:
                     logger.warning(f"Could not parse detailed block reason: {fb_e}")

                 logger.warning(f"  Gemini call potentially blocked. Block Reason: {block_reason}. Finish Reason: {finish_reason}")
                 # You might want to customize this error based on the reason
                 return {'success': False, 'response': None, 'error': f"Content generation failed or was blocked by safety settings ({block_reason})."}

            # Check candidate content (response.text is a shortcut but might raise)
            candidate_text = ""
            try:
                candidate_text = response.text # Use the safe shortcut if possible
            except ValueError:
                 logger.warning("  Gemini response candidate has no text content (potentially due to safety block on output).")
                 # Try to get finish reason from the candidate itself
                 finish_reason = "Unknown"
                 try:
                     if response.candidates[0].finish_reason:
                         finish_reason = response.candidates[0].finish_reason.name
                 except Exception:
                     pass
                 return {'success': False, 'response': None, 'error': f"Content generation failed ({finish_reason})."}
            except Exception as text_e:
                 logger.error(f"  Error accessing Gemini response text: {text_e}")
                 return {'success': False, 'response': None, 'error': f"Error accessing response text: {text_e}"}

            logger.info("  Gemini call successful.")
            return {'success': True, 'response': candidate_text, 'error': None}

        except Exception as e:
            # Catch potential timeout errors specifically if the library surfaces them
            # (Note: google-generativeai might wrap timeouts in a more generic error)
            error_str = str(e)
            if "Timeout" in error_str or "deadline exceeded" in error_str.lower():
                 logger.error(f"❌ Gemini API call timed out after {timeout} seconds: {e}")
                 return {'success': False, 'response': None, 'error': f"Gemini API call timed out ({timeout}s)."}
            else:
                 logger.error(f"❌ Error calling Gemini: {e}", exc_info=True)
                 return {'success': False, 'response': None, 'error': f"Gemini API call failed: {e}"}


def create_george_ai(model: str = "phi3:mini:instruct", use_cloud: bool = False) -> GeorgeAI:
    """Factory function to create an instance of GeorgeAI."""
    # Determine model and cloud usage based on simple logic for now
    # In production, this might read from a config file
    
    # Map friendly names to actual model IDs if needed
    if model.lower() == "gemini-pro":
        model_id = "gemini-1.0-pro" # Or the latest appropriate ID
        use_cloud = True
    elif model.lower() == "gemini-flash-lite":
        model_id = "gemini-1.5-flash-latest" # Or specific version like gemini-2.0-flash-lite
        use_cloud = True
    elif model.lower() == "gemini-2.5-pro":
        model_id = "gemini-2.5-pro-latest" # Or specific version
        use_cloud = True
    else: # Assume it's an Ollama model
        model_id = model
        use_cloud = False
        
    logger.info(f"Creating GeorgeAI instance: Model='{model_id}', Cloud={use_cloud}")
    return GeorgeAI(model=model_id, use_cloud=use_cloud)

# Example usage
if __name__ == '__main__':
    # Test Ollama (make sure Ollama service is running)
    print("\n--- Testing Ollama ---")
    try:
        ollama_ai = create_george_ai(model="phi3:mini:instruct", use_cloud=False)
        # Test with a short timeout (Ollama might ignore it, but we test the flow)
        result_ollama = ollama_ai.chat("Explain quantum physics in one sentence.", timeout=5) 
        print(f"Ollama Result: {result_ollama}")
    except Exception as e:
        print(f"Ollama test failed: {e}")

    # Test Gemini (requires GEMINI_API_KEY in .env file or environment)
    print("\n--- Testing Gemini ---")
    try:
        gemini_ai = create_george_ai(model="gemini-flash-lite", use_cloud=True) # Use Flash Lite for testing
        # Test with a specific timeout
        result_gemini = gemini_ai.chat("Explain classical mechanics in one sentence.", timeout=10) 
        print(f"Gemini Result: {result_gemini}")
    except Exception as e:
        print(f"Gemini test failed: {e}")