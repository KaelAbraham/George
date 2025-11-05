"""
George AI - Multi-Tier Routing System for Gemini API
Intelligently routes queries to appropriate model tiers for optimal cost and performance.
"""
import os
import json
import logging
import requests
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
        """Initialize cloud API client for a specific Gemini model."""
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
            response.raise_for_status()
            result = response.json()
            return result["candidates"][0]["content"]["parts"][0]["text"].strip()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed for model {self.model}: {e}")
            raise Exception(f"API Error with {self.model}: {e}")
        except (KeyError, IndexError) as e:
            logger.error(f"Unexpected API response structure for model {self.model}")
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
        """Uses the fastest model to classify the query's complexity and context needs."""
        system_prompt = """You are a request triage agent. Analyze the user's question and determine two things:
1. **complexity**: Classify as 'simple_lookup', 'complex_analysis', or 'creative_task'
2. **needs_memory**: Does it rely on unspoken context from previous conversation?

Respond with ONLY valid JSON: {"complexity": "...", "needs_memory": boolean}"""

        try:
            response_text = self.triage_client.generate_response(user_question, system_prompt, temperature=0.0)
            return json.loads(response_text)
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Triage failed: {e}. Defaulting to complex analysis.")
            return {"complexity": "complex_analysis", "needs_memory": True}

    def execute_and_polish(self, user_question: str, context: str, triage_result: Dict) -> Dict:
        """Routes to the correct model, gets a response, and polishes it."""
        complexity = triage_result.get("complexity", "complex_analysis")

        # 1. Select the appropriate client for execution
        if complexity == 'simple_lookup':
            execution_client = self.standard_client
        else:  # complex_analysis or creative_task
            execution_client = self.pro_client

        # 2. Generate the main, factual response
        main_prompt = f"Based on the following context, answer the user's question.\n\nContext:\n{context}\n\nQuestion:\n{user_question}"
        main_response = execution_client.generate_response(main_prompt, system_prompt="You are a helpful AI assistant. Provide a direct, factual answer based on the context provided.")

        # 3. "Georgeification" Layer: Polish the response for tone
        polish_prompt = f"Rephrase the following answer to have a natural, conversational, and friendly tone, as if you are 'George', an AI writing assistant. Do not add any new information. Answer:\n\n{main_response}"
        final_response = self.standard_client.generate_response(polish_prompt, temperature=0.5)

        return {
            "response": final_response,
            "model": execution_client.model,
        }


class GeminiClient:
    """
    Main AI interface with multi-tier routing for optimal cost and performance.
    Backwards compatible with the old GeminiClient interface.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize the Gemini client with routing capabilities."""
        resolved_api_key = api_key or os.getenv('GEMINI_API_KEY')
        if not resolved_api_key:
            raise ValueError("Gemini API key not provided. Set GEMINI_API_KEY environment variable.")
        
        self.api_key = resolved_api_key
        self.router = AIRouter(api_key=resolved_api_key)
        self.knowledge_client = CloudAPIClient(api_key=resolved_api_key, model="gemini-2.5-pro")
        self.conversation_history: List[ChatMessage] = []
        
        # Backwards compatibility
        self.model_name = 'gemini-2.0-flash'
        self.api_url = f'https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent'
    
    def is_available(self) -> bool:
        """Check if AI services are available."""
        return self.router.triage_client.is_available()
    
    def generate_text(self, prompt: str, context: str = "") -> str:
        """
        Generate text using intelligent routing (backwards compatible method).
        
        Args:
            prompt: The prompt to send to the model
            context: Optional context to include before the prompt
            
        Returns:
            Generated text response
        """
        try:
            # Use the routing system
            triage_result = self.router.triage_query(prompt)
            full_context = context if context else ""
            result = self.router.execute_and_polish(prompt, full_context, triage_result)
            return result['response']
        except Exception as e:
            logger.error(f"Error in generate_text: {e}")
            return f"Error: {str(e)}"
    
    def chat(self, message: str, project_context: str = "") -> Dict[str, Any]:
        """Process a chat message using the full routing and polishing pipeline."""
        try:
            # 1. Triage the query
            triage_result = self.router.triage_query(message)

            # 2. Gather resources
            context_parts = [project_context] if project_context else []
            if triage_result.get("needs_memory", False) and self.conversation_history:
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
    
    def extract_entities(self, text: str) -> dict:
        """
        Extract entities (characters, locations, terms) from text using Pro model.
        
        Args:
            text: The text to analyze
            
        Returns:
            Dictionary with extracted entities
        """
        prompt = f"""Analyze this text and extract:
1. Characters (people in the story) - use FULL NAMES
2. Locations (places mentioned)
3. Important terms/concepts

Text:
{text[:10000]}

Respond in this exact format:
CHARACTERS: [list names separated by commas]
LOCATIONS: [list places separated by commas]
TERMS: [list important terms separated by commas]"""

        try:
            # Use Pro client for entity extraction (high-value task)
            response_text = self.knowledge_client.generate_response(prompt, temperature=0.2)
            result = self._parse_entity_response(response_text)
            return result
        except Exception as e:
            logger.error(f"Entity extraction failed: {e}")
            return {
                'characters': [],
                'locations': [],
                'terms': [],
                'error': str(e)
            }
    
    def build_profile(self, entity_name: str, entity_type: str, text: str) -> str:
        """
        Build a detailed profile for an entity using Pro model.
        
        Args:
            entity_name: Name of the entity (character, location, etc.)
            entity_type: Type of entity ('character', 'location', 'term')
            text: The source text to analyze
            
        Returns:
            Markdown-formatted profile
        """
        # Limit text size for API
        text_preview = text[:15000] if len(text) > 15000 else text
        
        if entity_type == 'character':
            prompt = f"""Create a detailed character profile for "{entity_name}" based on this text.

Include:
- Physical description
- Personality traits
- Relationships with other characters
- Key actions and moments
- Character development

Text:
{text_preview}

Format as markdown with clear sections."""

        elif entity_type == 'location':
            prompt = f"""Create a detailed location profile for "{entity_name}" based on this text.

Include:
- Physical description
- Atmosphere/mood
- Events that happen here
- Significance to the story

Text:
{text_preview}

Format as markdown with clear sections."""

        else:  # term
            prompt = f"""Explain the term/concept "{entity_name}" based on this text.

Include:
- Definition/meaning
- How it's used in the story
- Significance
- Related concepts

Text:
{text_preview}

Format as markdown with clear sections."""

        try:
            # Use Pro client for profile building (high-value, detailed task)
            return self.knowledge_client.generate_response(prompt, temperature=0.3)
        except Exception as e:
            logger.error(f"Profile building failed for {entity_name}: {e}")
            return f"# {entity_type.title()} Profile: {entity_name}\n\nError: {str(e)}"
    
    def answer_query(self, question: str, context: str) -> str:
        """
        Answer a question using provided context.
        
        Args:
            question: The user's question
            context: Relevant context (entity profiles, etc.)
            
        Returns:
            Answer to the question
        """
        prompt = f"""Based on the following context, answer this question:

Question: {question}

Context:
{context}

Provide a clear, detailed answer based only on the information in the context."""

        return self.generate_text(prompt)
    
    def _parse_entity_response(self, response: str) -> dict:
        """Parse the entity extraction response into structured data."""
        result = {
            'characters': [],
            'locations': [],
            'terms': []
        }
        
        lines = response.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('CHARACTERS:'):
                chars = line.replace('CHARACTERS:', '').strip()
                if chars and chars.lower() != 'none':
                    result['characters'] = [c.strip() for c in chars.split(',') if c.strip()]
            elif line.startswith('LOCATIONS:'):
                locs = line.replace('LOCATIONS:', '').strip()
                if locs and locs.lower() != 'none':
                    result['locations'] = [l.strip() for l in locs.split(',') if l.strip()]
            elif line.startswith('TERMS:'):
                terms = line.replace('TERMS:', '').strip()
                if terms and terms.lower() != 'none':
                    result['terms'] = [t.strip() for t in terms.split(',') if t.strip()]
        
        return result
