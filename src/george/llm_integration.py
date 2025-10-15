"""
LLM Integration Module for George - Multi-LLM Support (Ollama, OpenAI, Anthropic, etc.)
This version implements a tiered, multi-client routing system for Gemini models.
"""
import json
import logging
import requests
import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ChatMessage:
    """Represents a chat message."""
    role: str  # 'user', 'assistant', 'system'
    content: str
    timestamp: Optional[str] = None

class CloudAPIClient:
    """Client for cloud-based LLM APIs, primarily focused on Google Gemini."""
    
    def __init__(self, api_key: str, model: str, api_base: str = "https://generativelanguage.googleapis.com/v1beta"):
        """
        Initialize cloud API client for a specific Gemini model.
        """
        self.model = model
        self.api_base = api_base
        
        if not api_key:
            raise ValueError("A Google AI API key is required.")
        
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def is_available(self) -> bool:
        """Check if the API key is set."""
        return bool(self.api_key)
    
    def generate_response(self, prompt: str, system_prompt: str = None, temperature: float = 0.7) -> str:
        """Generate a response using the configured Gemini model."""
        url = f"{self.api_base}/models/{self.model}:generateContent?key={self.api_key}"
        
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 2048,
            }
        }
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        try:
            response = self.session.post(url, json=payload, timeout=120)
            response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
            result = response.json()
            return result["candidates"][0]["content"]["parts"][0]["text"].strip()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed for model {self.model}: {e}")
            raise Exception(f"API Error with {self.model}: {e}")
        except (KeyError, IndexError) as e:
            logger.error(f"Unexpected API response structure for model {self.model}: {response.text}")
            raise Exception(f"Invalid response from {self.model}: {e}")

class AIRouter:
    """
    Intelligently routes user queries to the appropriate Gemini model tier
    based on complexity and context requirements.
    """
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("API key is essential for the AI Router to function.")
            
        self.triage_client = CloudAPIClient(api_key=api_key, model="gemini-2.0-flash-lite")
        self.standard_client = CloudAPIClient(api_key=api_key, model="gemini-2.0-flash")
        self.pro_client = CloudAPIClient(api_key=api_key, model="gemini-2.5-pro")

    def triage_query(self, user_question: str) -> Dict[str, Any]:
        """
        Uses the fastest model to classify the query's complexity and context needs.
        """
        system_prompt = """You are a request triage agent. Analyze the user's question and determine two things:
1.  **complexity**: Classify the request as 'simple_lookup' (e.g., "who is Sarah?"), 'complex_analysis' (e.g., "compare Sarah's motivations to John's"), or 'creative_task' (e.g., "write a poem about their meeting").
2.  **needs_memory**: Determine if the question relies on unspoken context from the previous turn of conversation (e.g., using pronouns like "he", "she", "that", "it").

Respond with ONLY a valid JSON object in the format: {"complexity": "...", "needs_memory": boolean}"""

        try:
            response_text = self.triage_client.generate_response(user_question, system_prompt, temperature=0.0)
            return json.loads(response_text)
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Triage failed: {e}. Defaulting to complex analysis.")
            return {"complexity": "complex_analysis", "needs_memory": True} # Default safely

    def execute_and_polish(self, user_question: str, context: str, triage_result: Dict) -> Dict:
        """Routes to the correct model, gets a response, and polishes it."""
        complexity = triage_result.get("complexity", "complex_analysis")

        # 1. Select the appropriate client for execution
        if complexity == 'simple_lookup':
            execution_client = self.standard_client # Use Flash for simple lookups for quality
        else: # complex_analysis or creative_task
            execution_client = self.pro_client

        # 2. Generate the main, factual response
        main_prompt = f"Based on the following context, answer the user's question.\n\nContext:\n{context}\n\nQuestion:\n{user_question}"
        model_used = execution_client.model
        fallback_note = None

        try:
            main_response = execution_client.generate_response(
                main_prompt,
                system_prompt="You are a helpful AI assistant. Provide a direct, factual answer based on the context provided.",
            )
        except Exception as primary_error:
            logger.warning(
                "Primary model %s failed during execution: %s",
                execution_client.model,
                primary_error,
            )

            fallback_client = None
            if execution_client is self.pro_client:
                fallback_client = self.standard_client
            elif execution_client is self.standard_client:
                fallback_client = self.triage_client

            if fallback_client is None:
                raise

            try:
                main_response = fallback_client.generate_response(
                    main_prompt,
                    system_prompt="You are a helpful AI assistant. Provide a direct, factual answer based on the context provided.",
                )
                model_used = fallback_client.model
                fallback_note = f"primary_failed:{execution_client.model}"
                logger.info(
                    "Fallback model %s succeeded after %s failure",
                    fallback_client.model,
                    execution_client.model,
                )
            except Exception as secondary_error:
                logger.error(
                    "Fallback model %s also failed after %s: %s",
                    fallback_client.model,
                    execution_client.model,
                    secondary_error,
                )
                raise RuntimeError(
                    f"Primary model {execution_client.model} failed: {primary_error}; fallback {fallback_client.model} failed: {secondary_error}"
                ) from secondary_error

        # 3. "Georgeification" Layer: Polish the response for tone
        polish_prompt = f"Rephrase the following answer to have a natural, conversational, and friendly tone, as if you are 'George', an AI writing assistant. Do not add any new information. Answer:\n\n{main_response}"
        polish_model = self.standard_client.model

        try:
            final_response = self.standard_client.generate_response(polish_prompt, temperature=0.7)
        except Exception as polish_error:
            logger.warning(
                "Polish model %s failed: %s. Returning unpolished response.",
                self.standard_client.model,
                polish_error,
            )
            final_response = main_response
            polish_model = model_used

        return {
            "response": final_response,
            "model": model_used,  # Report the model that did the heavy lifting (or fallback)
            "polish_model": polish_model,
            "fallback_info": fallback_note,
        }

class GeorgeAI:
    """Main AI interface for George application, now with routing."""
    
    def __init__(self, use_cloud: bool = True, api_key: str = None, api_type: str = "gemini"):
        if not use_cloud or api_type != "gemini":
            raise NotImplementedError("This version is optimized for the Gemini cloud API router.")
        
        # Resolve API key once - use provided key or fallback to environment variable
        resolved_api_key = api_key or os.getenv("GEMINI_API_KEY")
        
        self.router = AIRouter(api_key=resolved_api_key)
        self.knowledge_client = CloudAPIClient(api_key=resolved_api_key, model="gemini-2.5-pro")
        self.conversation_history: List[ChatMessage] = []
        
    def is_available(self) -> bool:
        """Check if AI services are available."""
        return self.router.triage_client.is_available()

    def chat(self, message: str, project_context: str = "") -> Dict[str, Any]:
        """Processes a chat message using the full routing and polishing pipeline."""
        try:
            # 1. Triage the query
            triage_result = self.router.triage_query(message)

            # 2. Gather resources
            context_parts = [project_context]
            if triage_result.get("needs_memory", False) and self.conversation_history:
                # Add last 3 exchanges (simplified for this example)
                recent_history = "\n".join([f"{msg.role}: {msg.content}" for msg in self.conversation_history[-3:]])
                context_parts.append(f"Recent Conversation History:\n{recent_history}")
            
            full_context = "\n\n".join(context_parts)

            # 3. Execute the routed query and get a polished response
            result = self.router.execute_and_polish(message, full_context, triage_result)

            # 4. Update history
            self.conversation_history.append(ChatMessage(role="user", content=message))
            self.conversation_history.append(ChatMessage(role="assistant", content=result['response']))
            
            return {
                "response": result['response'],
                "model": result['model'],
                "success": True
            }
        except Exception as e:
            logger.error(f"Error in chat processing: {e}")
            return {"response": f"Sorry, I encountered an error: {e}", "success": False}

    def get_knowledge_client(self) -> CloudAPIClient:
        """Provides direct access to the powerful Pro client for high-value tasks."""
        return self.knowledge_client

    def clear_history(self):
        """Clear conversation history."""
        self.conversation_history = []

def create_george_ai(api_key: str = None, api_type: str = "gemini") -> GeorgeAI:
    """Factory function to create a GeorgeAI instance with the routing logic."""
    return GeorgeAI(use_cloud=True, api_key=api_key, api_type=api_type)
