"""
LLM Integration Module for George - Multi-LLM Support (Ollama, OpenAI, Anthropic, etc.)
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
    """Client for cloud-based LLM APIs (OpenAI, Anthropic, Gemini, etc.)."""
    
    def __init__(self, api_key: str = None, model: str = "gpt-4o-mini", 
                 api_base: str = "https://api.openai.com/v1", api_type: str = "openai"):
        """
        Initialize cloud API client.
        
        Args:
            api_key: API key (or set OPENAI_API_KEY / ANTHROPIC_API_KEY / GEMINI_API_KEY env var)
            model: Model name (e.g., "gpt-4o-mini", "claude-3-haiku-20240307", "gemini-1.5-flash")
            api_base: API base URL
            api_type: "openai", "anthropic", or "gemini"
        """
        self.api_type = api_type
        self.model = model
        self.api_base = api_base
        
        # Get API key from parameter or environment
        if api_key is None:
            if api_type == "anthropic":
                api_key = os.getenv("ANTHROPIC_API_KEY")
            elif api_type == "gemini":
                api_key = os.getenv("GEMINI_API_KEY")
            else:
                api_key = os.getenv("OPENAI_API_KEY")
        
        if not api_key:
            raise ValueError(f"API key required. Set {api_type.upper()}_API_KEY environment variable or pass api_key parameter.")
        
        self.api_key = api_key
        self.session = requests.Session()
        
        # Set headers based on API type
        if api_type == "anthropic":
            self.session.headers.update({
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            })
        elif api_type == "gemini":
            # Gemini uses API key in URL, not headers
            self.session.headers.update({
                "Content-Type": "application/json"
            })
        else:  # openai
            self.session.headers.update({
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            })
    
    def is_available(self) -> bool:
        """Check if API is accessible."""
        try:
            # Simple check - assume available if key is set for cloud APIs
            return bool(self.api_key)
        except Exception as e:
            logger.warning(f"Cloud API availability check failed: {e}")
            return False
    
    def generate_response(self, prompt: str, context: str = "", temperature: float = 0.7) -> str:
        """Generate response using cloud API."""
        try:
            full_prompt = self._build_prompt(prompt, context)
            
            if self.api_type == "anthropic":
                return self._generate_anthropic(full_prompt, temperature)
            elif self.api_type == "gemini":
                return self._generate_gemini(full_prompt, temperature)
            else:
                return self._generate_openai(full_prompt, temperature)
                
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return f"Sorry, I encountered an error: {str(e)}"
    
    def _generate_openai(self, prompt: str, temperature: float) -> str:
        """Generate using OpenAI-compatible API."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are George, an AI assistant for authors and world-builders. Provide helpful, concise answers about writing, characters, plot, and world-building."},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": 1000
        }
        
        response = self.session.post(
            f"{self.api_base}/chat/completions",
            json=payload,
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            return result["choices"][0]["message"]["content"].strip()
        else:
            raise Exception(f"API error: {response.status_code} - {response.text}")
    
    def _generate_anthropic(self, prompt: str, temperature: float) -> str:
        """Generate using Anthropic API."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "system": "You are George, an AI assistant for authors and world-builders. Provide helpful, concise answers about writing, characters, plot, and world-building.",
            "temperature": temperature,
            "max_tokens": 1000
        }
        
        response = self.session.post(
            f"{self.api_base}/messages",
            json=payload,
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            return result["content"][0]["text"].strip()
        else:
            raise Exception(f"API error: {response.status_code} - {response.text}")
    
    def _generate_gemini(self, prompt: str, temperature: float) -> str:
        """Generate using Google Gemini API."""
        # Gemini API format
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": f"You are George, an AI assistant for authors and world-builders. Provide helpful, concise answers about writing, characters, plot, and world-building.\n\n{prompt}"
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 1000,
                "topP": 0.9,
                "topK": 40
            }
        }
        
        # Gemini uses API key in URL
        # Format: https://generativelanguage.googleapis.com/v1beta/models/MODEL_NAME:generateContent
        url = f"{self.api_base}/models/{self.model}:generateContent?key={self.api_key}"
        
        logger.info(f"Gemini API request URL: {url}")
        response = self.session.post(url, json=payload, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            return result["candidates"][0]["content"]["parts"][0]["text"].strip()
        else:
            raise Exception(f"Gemini API error: {response.status_code} - {response.text}")
    
    def _build_prompt(self, prompt: str, context: str) -> str:
        """Build full prompt with context."""
        if context:
            return f"Context about the story:\n{context}\n\nQuestion: {prompt}"
        return prompt

class OllamaClient:
    """Client for interacting with Ollama API."""
    
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "phi3:instruct"):
        """
        Initialize the Ollama client.
        
        Args:
            base_url: Ollama server URL
            model: Model name to use
        """
        self.base_url = base_url
        self.model = model
        self.session = requests.Session()
        
    def is_available(self) -> bool:
        """Check if Ollama server is running."""
        try:
            response = self.session.get(f"{self.base_url}/api/tags", timeout=10)
            return response.status_code == 200
        except requests.RequestException as e:
            logger.warning(f"Ollama availability check failed: {e}")
            return False
    
    def list_models(self) -> List[str]:
        """List available models."""
        try:
            response = self.session.get(f"{self.base_url}/api/tags")
            if response.status_code == 200:
                data = response.json()
                return [model['name'] for model in data.get('models', [])]
        except requests.RequestException as e:
            logger.error(f"Error listing models: {e}")
        return []
    
    def generate_response(self, prompt: str, context: str = "", temperature: float = 0.7) -> str:
        """
        Generate a response using the specified model.
        
        Args:
            prompt: User prompt
            context: Additional context about the story/world
            temperature: Response randomness (0.0-1.0)
            
        Returns:
            Generated response text
        """
        try:
            # Construct the full prompt with context
            full_prompt = self._build_prompt(prompt, context)
            
            payload = {
                "model": self.model,
                "prompt": full_prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "top_p": 0.9,
                    "top_k": 40,
                    "num_predict": 512,  # Limit response length
                }
            }
            
            logger.info(f"Sending request to Ollama with model: {self.model}")
            response = self.session.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=300  # 5 minute timeout for longer responses with larger models
            )
            
            if response.status_code == 200:
                result = response.json()
                generated_text = result.get('response', '').strip()
                logger.info(f"Successfully generated response of length: {len(generated_text)}")
                return generated_text
            else:
                error_msg = f"Ollama API error: {response.status_code} - {response.text}"
                logger.error(error_msg)
                return f"Sorry, I encountered an API error: {response.status_code}"
                
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout error calling Ollama API: {e}")
            return "Sorry, the AI is taking too long to respond. Please try a shorter question or try again."
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error calling Ollama API: {e}")
            return "Sorry, I can't connect to the AI service. Please check if Ollama is running."
        except requests.RequestException as e:
            logger.error(f"Error calling Ollama API: {e}")
            return "Sorry, I encountered a network error. Please try again."
        except Exception as e:
            logger.error(f"Unexpected error in generate_response: {e}")
            return "Sorry, I encountered an unexpected error. Please try again."
    
    def generate_streaming_response(self, prompt: str, context: str = "", temperature: float = 0.7):
        """
        Generate a streaming response using the specified model.
        
        Args:
            prompt: User prompt
            context: Additional context about the story/world
            temperature: Response randomness (0.0-1.0)
            
        Yields:
            Streaming response chunks
        """
        try:
            full_prompt = self._build_prompt(prompt, context)
            
            payload = {
                "model": self.model,
                "prompt": full_prompt,
                "stream": True,
                "options": {
                    "temperature": temperature,
                    "top_p": 0.9,
                    "top_k": 40,
                }
            }
            
            response = self.session.post(
                f"{self.base_url}/api/generate",
                json=payload,
                stream=True,
                timeout=300  # 5 minute timeout for streaming responses
            )
            
            if response.status_code == 200:
                for line in response.iter_lines():
                    if line:
                        try:
                            chunk = json.loads(line.decode('utf-8'))
                            if 'response' in chunk:
                                yield chunk['response']
                            if chunk.get('done', False):
                                break
                        except json.JSONDecodeError:
                            continue
            else:
                yield "Sorry, I encountered an error generating a response."
                
        except requests.RequestException as e:
            logger.error(f"Error calling Ollama API: {e}")
            yield "Sorry, I'm unable to connect to the AI service right now."
    
    def _build_prompt(self, user_prompt: str, context: str = "") -> str:
        """
        Build a comprehensive prompt with context for the AI.
        
        Args:
            user_prompt: User's question/prompt
            context: Story context from knowledge base
            
        Returns:
            Formatted prompt for the AI
        """
        system_prompt = """You are George, an AI writing assistant for authors. You help with storytelling, character development, world-building, and creative writing. Give SHORT, DIRECT answers. Be concise and helpful."""

        if context and len(context) > 0:
            # Truncate context if too long to avoid timeout (increased to 12000 to capture all main characters)
            truncated_context = context[:12000] + "..." if len(context) > 12000 else context
            prompt = f"""{system_prompt}

The user has uploaded their manuscript. Here is an excerpt from their story:

---MANUSCRIPT BEGINS---
{truncated_context}
---MANUSCRIPT ENDS---

User's question: {user_prompt}

Give a SHORT, DIRECT answer:"""
        else:
            prompt = f"""{system_prompt}

Question: {user_prompt}

Response:"""
        
        return prompt

class GeorgeAI:
    """Main AI interface for George application."""
    
    def __init__(self, model: str = "phi3:instruct", knowledge_base=None,
                 use_cloud: bool = False, api_key: str = None, api_type: str = "openai"):
        """
        Initialize George AI.
        
        Args:
            model: Model name (Ollama model or cloud model)
            knowledge_base: Knowledge base instance for context retrieval
            use_cloud: If True, use cloud API instead of Ollama
            api_key: API key for cloud service
            api_type: "openai", "anthropic", or "gemini"
        """
        self.use_cloud = use_cloud
        
        if use_cloud:
            # Set API base URL based on type
            if api_type == "gemini":
                # Use v1beta for newer models like gemini-1.5-flash
                api_base = "https://generativelanguage.googleapis.com/v1beta"
            elif api_type == "anthropic":
                api_base = "https://api.anthropic.com/v1"
            else:  # openai
                api_base = "https://api.openai.com/v1"
            
            self.llm_client = CloudAPIClient(api_key=api_key, model=model, api_base=api_base, api_type=api_type)
        else:
            self.llm_client = OllamaClient(model=model)
            self.ollama = self.llm_client  # Backwards compatibility
        
        self.knowledge_base = knowledge_base
        self.conversation_history: List[ChatMessage] = []
        
    def is_available(self) -> bool:
        """Check if AI services are available."""
        return self.llm_client.is_available()
    
    def chat(self, message: str, project_context: str = "") -> Dict[str, Any]:
        """
        Process a chat message and return a response.
        
        Args:
            message: User message
            project_context: Current project context
            
        Returns:
            Dictionary with response and metadata
        """
        try:
            # Add user message to history
            user_msg = ChatMessage(role="user", content=message)
            self.conversation_history.append(user_msg)
            
            # Get relevant context from knowledge base if available
            context = self._get_relevant_context(message, project_context)
            
            # Generate response
            response = self.llm_client.generate_response(message, context)
            
            # Add AI response to history
            ai_msg = ChatMessage(role="assistant", content=response)
            self.conversation_history.append(ai_msg)
            
            return {
                "response": response,
                "context_used": context,
                "model": self.llm_client.model,
                "success": True
            }
            
        except Exception as e:
            logger.error(f"Error in chat processing: {e}")
            return {
                "response": "Sorry, I encountered an error while processing your message.",
                "error": str(e),
                "success": False
            }
    
    def chat_streaming(self, message: str, project_context: str = ""):
        """
        Process a chat message and return a streaming response.
        
        Args:
            message: User message
            project_context: Current project context
            
        Yields:
            Response chunks
        """
        try:
            # Add user message to history
            user_msg = ChatMessage(role="user", content=message)
            self.conversation_history.append(user_msg)
            
            # Get relevant context from knowledge base if available
            context = self._get_relevant_context(message, project_context)
            
            # Generate streaming response
            response_parts = []
            for chunk in self.ollama.generate_streaming_response(message, context):
                response_parts.append(chunk)
                yield chunk
            
            # Add complete AI response to history
            full_response = "".join(response_parts)
            ai_msg = ChatMessage(role="assistant", content=full_response)
            self.conversation_history.append(ai_msg)
            
        except Exception as e:
            logger.error(f"Error in streaming chat: {e}")
            yield "Sorry, I encountered an error while processing your message."
    
    def _get_relevant_context(self, message: str, project_context: str = "") -> str:
        """
        Retrieve relevant context for the user's message.
        
        Args:
            message: User message
            project_context: Current project context
            
        Returns:
            Relevant context string
        """
        context_parts = []
        
        # Add project context if available
        if project_context:
            context_parts.append(f"Current Project: {project_context}")
        
        # Add knowledge base context if available
        if self.knowledge_base:
            try:
                # Search for relevant entities and content
                search_results = self.knowledge_base.search(message, limit=3)
                if search_results:
                    context_parts.append("Relevant Story Elements:")
                    for result in search_results:
                        context_parts.append(f"- {result}")
            except Exception as e:
                logger.warning(f"Error retrieving knowledge base context: {e}")
        
        # Add recent conversation context
        if len(self.conversation_history) > 0:
            recent_messages = self.conversation_history[-4:]  # Last 2 exchanges
            context_parts.append("Recent Conversation:")
            for msg in recent_messages:
                context_parts.append(f"{msg.role}: {msg.content[:200]}...")
        
        return "\n".join(context_parts) if context_parts else ""
    
    def clear_history(self):
        """Clear conversation history."""
        self.conversation_history = []
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the current model."""
        return {
            "model": self.ollama.model,
            "available": self.is_available(),
            "available_models": self.ollama.list_models()
        }

# Factory function for easy instantiation
def create_george_ai(model: str = "phi3:instruct", knowledge_base=None, 
                    use_cloud: bool = False, api_key: str = None, 
                    api_type: str = "openai") -> GeorgeAI:
    """
    Create and return a GeorgeAI instance.
    
    Args:
        model: Model name (e.g., "phi3:instruct" for Ollama, "gpt-4o-mini" for OpenAI, "claude-3-haiku-20240307" for Anthropic)
        knowledge_base: Knowledge base instance
        use_cloud: If True, use cloud API instead of Ollama
        api_key: API key for cloud service (or set OPENAI_API_KEY/ANTHROPIC_API_KEY env var)
        api_type: "openai" or "anthropic"
        
    Returns:
        GeorgeAI instance
    """
    if use_cloud:
        return GeorgeAI(model=model, knowledge_base=knowledge_base, use_cloud=True, 
                       api_key=api_key, api_type=api_type)
    else:
        return GeorgeAI(model=model, knowledge_base=knowledge_base)