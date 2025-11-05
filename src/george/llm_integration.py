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
    import os
    import sys
    from pathlib import Path
    import google.generativeai as genai
    import ollama
    import logging
    from dotenv import load_dotenv
    from typing import Dict, Any, Tuple # Added Tuple

    # Add parent to path if needed
    current_dir = Path(__file__).parent
    george_dir = current_dir
    if str(george_dir) not in sys.path:
        sys.path.insert(0, str(george_dir))

    # Setup logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)

    load_dotenv()

    DEFAULT_TIMEOUT = 30 

    class GeorgeAI:
        """Handles interactions with different LLM backends (local Ollama or cloud Gemini)."""

        def __init__(self, model: str = "phi3:mini:instruct", use_cloud: bool = False, api_key: str = None):
            self.model = model
            self.use_cloud = use_cloud
            self.gemini_model = None

            if use_cloud:
                key = api_key or os.getenv("GEMINI_API_KEY")
                if not key:
                    logger.error("❌ GEMINI_API_KEY not found.")
                else:
                    try:
                        genai.configure(api_key=key)
                        self.gemini_model = genai.GenerativeModel(model)
                        logger.info(f"☁️ Configured Google Gemini with model: {model}")
                    except Exception as e:
                        logger.error(f"❌ Failed to configure Google Gemini: {e}")
            else:
                try:
                    ollama.list()
                    logger.info(f"🤖 Configured local Ollama with model: {model}")
                except Exception as e:
                    logger.error(f"❌ Failed to connect to local Ollama service. Is it running? Error: {e}")

        def chat(self, prompt: str, project_context: str = "", temperature: float = 0.7, timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
            """
            Main chat method, routes to appropriate backend.
        
            Returns:
                Dict: {
                    'success': bool,
                    'response': str,
                    'error': str (if !success),
                    'input_tokens': int,
                    'output_tokens': int
                }
            """
            full_prompt = prompt
            if project_context:
                 full_prompt += f"\n\n--- Start Context ---\n{project_context}\n--- End Context ---"
        
            # Default error/empty response
            base_response = {
                'success': False,
                'response': None,
                'error': "Chat execution failed.",
                'input_tokens': 0,
                'output_tokens': 0
            }

            try:
                if self.use_cloud:
                    if not self.gemini_model:
                         base_response['error'] = "Gemini client not initialized. Check API key."
                         return base_response
                    return self._chat_with_gemini(full_prompt, temperature, timeout)
                else:
                    try:
                         ollama.list() 
                    except Exception as ollama_conn_e:
                         base_response['error'] = f"Cannot connect to Ollama: {ollama_conn_e}"
                         return base_response
                    return self._chat_with_ollama(full_prompt, temperature, timeout)
            except Exception as e:
                logger.error(f"❌ Unexpected error in chat method: {e}", exc_info=True)
                base_response['error'] = f"Unexpected error: {e}"
                return base_response

        def _chat_with_ollama(self, prompt: str, temperature: float, timeout: int) -> Dict[str, Any]:
            """Sends a prompt to the configured local Ollama model."""
            response_data = {
                'success': False,
                'response': None,
                'error': None,
                'input_tokens': 0,
                'output_tokens': 0
            }
            try:
                logger.info(f"🤖 Calling local Ollama model: {self.model}")
                # Note: Ollama library's 'timeout' is a request timeout, not a generation timeout
                response = ollama.chat(
                    model=self.model,
                    messages=[{'role': 'user', 'content': prompt}],
                    options={'temperature': temperature},
                )
            
                if not response or 'message' not in response or 'content' not in response['message'] or not response['message']['content']:
                     response_data['error'] = "Invalid or empty response from Ollama."
                     return response_data

                response_data['success'] = True
                response_data['response'] = response['message']['content']
                # --- Get Token Counts ---
                # 'prompt_eval_count' is input, 'eval_count' is output
                response_data['input_tokens'] = response.get('prompt_eval_count', 0)
                response_data['output_tokens'] = response.get('eval_count', 0)
            
                logger.info("  Ollama call successful.")
                return response_data
            
            except Exception as e:
                logger.error(f"❌ Error calling Ollama: {e}", exc_info=True)
                response_data['error'] = f"Ollama API call failed: {e}"
                return response_data

        def _chat_with_gemini(self, prompt: str, temperature: float, timeout: int) -> Dict[str, Any]:
            """Sends a prompt to the configured Google Gemini model."""
            response_data = {
                'success': False,
                'response': None,
                'error': None,
                'input_tokens': 0,
                'output_tokens': 0
            }
            try:
                logger.info(f"☁️ Calling Google Gemini model: {self.model} with timeout {timeout}s")
                response = self.gemini_model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(temperature=temperature),
                    request_options={'timeout': timeout}
                )

                # --- Get Token Counts (from usage_metadata) ---
                if response.usage_metadata:
                    response_data['input_tokens'] = response.usage_metadata.prompt_token_count
                    response_data['output_tokens'] = response.usage_metadata.candidates_token_count
            
                if not response.candidates:
                     block_reason = "Unknown safety block"
                     try:
                         if hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason:
                             block_reason = response.prompt_feedback.block_reason.name
                     except Exception:
                         pass
                     response_data['error'] = f"Content generation failed or was blocked by safety settings ({block_reason})."
                     return response_data

                response_data['success'] = True
                response_data['response'] = response.text
                logger.info("  Gemini call successful.")
                return response_data

            except Exception as e:
                logger.error(f"❌ Error calling Gemini: {e}", exc_info=True)
                response_data['error'] = f"Gemini API call failed: {e}"
                return response_data

    def create_george_ai(model: str = "phi3:mini:instruct", use_cloud: bool = False, api_key: str = None) -> GeorgeAI:
        """Factory function to create a GeorgeAI instance."""
        return GeorgeAI(model=model, use_cloud=use_cloud, api_key=api_key)

    # ... (Example usage remains the same) ...
    
    # Map friendly names to actual model IDs if needed
    if model.lower() == "gemini-pro":
        model_id = "gemini-1.0-pro" # Or the latest appropriate ID
        use_cloud = True
    elif model.lower() == "gemini-flash-lite":
        model_id = "gemini-2.0-flash-lite" # Fast lite model for routing
        use_cloud = True
    elif model.lower() == "gemini-2.0-flash":
        model_id = "gemini-2.0-flash-exp" # Gemini 2.0 Flash experimental
        use_cloud = True
    elif model.lower() == "gemini-2.5-pro":
        model_id = "gemini-exp-1206" # Correct experimental model name
        use_cloud = True
    else: # Assume it's an Ollama model
        model_id = model
        # Don't override use_cloud if explicitly set by caller
        # use_cloud stays as passed in
        
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