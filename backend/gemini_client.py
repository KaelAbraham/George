"""
Gemini API Client
Handles all communication with Google's Gemini API for the George Knowledge Extractor.
"""
import os
import requests
from typing import Optional


class GeminiClient:
    """Client for interacting with Google's Gemini API using REST."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the Gemini client.
        
        Args:
            api_key: Gemini API key. If not provided, will look for GEMINI_API_KEY env var.
        """
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("Gemini API key not provided. Set GEMINI_API_KEY environment variable.")
        
        # Use Gemini 2.0 Flash for fast, efficient responses
        self.model_name = 'gemini-2.0-flash'
        self.api_url = f'https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent'
        
    def generate_text(self, prompt: str, context: str = "") -> str:
        """
        Generate text using Gemini API.
        
        Args:
            prompt: The prompt to send to the model
            context: Optional context to include before the prompt
            
        Returns:
            Generated text response
        """
        try:
            # Combine context and prompt
            full_prompt = f"{context}\n\n{prompt}" if context else prompt
            
            # Prepare request payload
            payload = {
                "contents": [{
                    "parts": [{
                        "text": full_prompt
                    }]
                }]
            }
            
            # Make API request
            response = requests.post(
                f"{self.api_url}?key={self.api_key}",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=60
            )
            
            if response.status_code != 200:
                return f"Error: Gemini API returned status {response.status_code}"
            
            # Extract text from response
            data = response.json()
            return data['candidates'][0]['content']['parts'][0]['text']
            
        except Exception as e:
            return f"Error generating response: {str(e)}"
    
    def extract_entities(self, text: str) -> dict:
        """
        Extract entities (characters, locations, terms) from text.
        
        Args:
            text: The text to analyze
            
        Returns:
            Dictionary with extracted entities
        """
        prompt = f"""Analyze this text and extract:
1. Characters (people in the story)
2. Locations (places mentioned)
3. Important terms/concepts

Text:
{text[:10000]}

Respond in this exact format:
CHARACTERS: [list names separated by commas]
LOCATIONS: [list places separated by commas]
TERMS: [list important terms separated by commas]"""

        try:
            response_text = self.generate_text(prompt)
            result = self._parse_entity_response(response_text)
            return result
        except Exception as e:
            return {
                'characters': [],
                'locations': [],
                'terms': [],
                'error': str(e)
            }
    
    def build_profile(self, entity_name: str, entity_type: str, text: str) -> str:
        """
        Build a detailed profile for an entity.
        
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
            return self.generate_text(prompt)
        except Exception as e:
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
