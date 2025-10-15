"""
Query Analyzer - Determines what entities a user question is asking about
"""
import os
import sys
from pathlib import Path
from typing import List, Dict

# Add parent to path if needed
current_dir = Path(__file__).parent
george_dir = current_dir.parent
if str(george_dir) not in sys.path:
    sys.path.insert(0, str(george_dir))

from llm_integration import GeorgeAI

class QueryAnalyzer:
    """Analyzes user queries to determine relevant entities."""
    
    def __init__(self, george_ai: GeorgeAI, knowledge_base_path: str):
        """
        Initialize query analyzer.
        
        Args:
            george_ai: AI instance for analysis
            knowledge_base_path: Directory where entity profiles are stored
        """
        self.ai = george_ai
        self.kb_path = Path(knowledge_base_path)
        self.available_entities = self._scan_knowledge_base()
    
    def _scan_knowledge_base(self) -> Dict[str, List[str]]:
        """Scan knowledge base directory to find all available entity profiles."""
        entities = {
            'characters': [],
            'locations': [],
            'terms': []
        }
        
        if not self.kb_path.exists():
            return entities
        
        for file in self.kb_path.glob('*.md'):
            filename = file.stem
            if filename.startswith('character_'):
                entities['characters'].append(filename.replace('character_', '').replace('_', ' '))
            elif filename.startswith('location_'):
                entities['locations'].append(filename.replace('location_', '').replace('_', ' '))
            elif filename.startswith('term_'):
                entities['terms'].append(filename.replace('term_', '').replace('_', ' '))
        
        return entities
    
    def analyze_query(self, user_question: str) -> Dict[str, any]:
        """
        Analyze user question to determine what they're asking about.
        
        Args:
            user_question: The user's question
            
        Returns:
            Dictionary with:
            - query_type: 'character', 'location', 'plot', 'general', etc.
            - entities: List of relevant entity names
            - needs_full_text: Boolean if query needs access to full manuscript
        """
        print(f"[ANALYZE] Analyzing query: {user_question}")
        
        # Refresh entity list
        self.available_entities = self._scan_knowledge_base()
        
        # Simple keyword detection first
        query_lower = user_question.lower()
        
        # Check for character-related queries
        character_keywords = ['character', 'who is', 'who are', 'protagonist', 'antagonist', 'people', 'who did', 'who paid']
        is_character_query = any(keyword in query_lower for keyword in character_keywords)
        
        # Check for location queries
        location_keywords = ['where', 'location', 'setting', 'place', 'happens']
        is_location_query = any(keyword in query_lower for keyword in location_keywords)
        
        # Check if asking about specific entities
        mentioned_characters = [
            char for char in self.available_entities['characters']
            if char.lower() in query_lower
        ]
        mentioned_locations = [
            loc for loc in self.available_entities['locations']
            if loc.lower() in query_lower
        ]
        mentioned_terms = [
            term for term in self.available_entities['terms']
            if term.lower() in query_lower
        ]
        
        # Use AI to intelligently map queries to entities
        if not mentioned_characters and not mentioned_locations and not mentioned_terms:
            # Ask AI which entities might be relevant
            ai_prompt = f"""Given this question: "{user_question}"

Available characters: {', '.join(self.available_entities['characters'])}
Available locations: {', '.join(self.available_entities['locations'])}
Available terms: {', '.join(self.available_entities['terms'])}

Which entities from the above lists are most relevant to answering this question?
Respond with ONLY a comma-separated list of entity names, or "NONE" if none are relevant.
If the question seems to be about actions/events (like surgery, payment, operations), consider which CHARACTER might be involved."""
            
            try:
                ai_response = self.ai.chat(ai_prompt, project_context="")
                ai_text = ai_response.get('response') if isinstance(ai_response, dict) else str(ai_response)
                print(f"  [AI] AI entity detection: {ai_text}")

                if ai_text and ai_text.strip().upper() != "NONE":
                    # Parse AI response
                    suggested_entities = [e.strip() for e in ai_text.split(',')]
                    # Match to actual entity names
                    for entity in suggested_entities:
                        entity_lower = entity.lower()
                        for char in self.available_entities['characters']:
                            if char.lower() in entity_lower or entity_lower in char.lower():
                                mentioned_characters.append(char)
                        for loc in self.available_entities['locations']:
                            if loc.lower() in entity_lower or entity_lower in loc.lower():
                                mentioned_locations.append(loc)
                        for term in self.available_entities['terms']:
                            if term.lower() in entity_lower or entity_lower in term.lower():
                                mentioned_terms.append(term)
            except Exception as e:
                print(f"  [WARN] AI analysis failed: {e}")
        
        # Determine query type and relevant entities
        result = {
            'query_type': 'general',
            'entities': [],
            'needs_full_text': False
        }
        
        # Specific entity mentioned
        if mentioned_characters:
            result['query_type'] = 'character'
            result['entities'] = mentioned_characters
            result['needs_full_text'] = False
        elif mentioned_locations:
            result['query_type'] = 'location'
            result['entities'] = mentioned_locations
            result['needs_full_text'] = False
        elif mentioned_terms:
            result['query_type'] = 'term'
            result['entities'] = mentioned_terms
            result['needs_full_text'] = False
        # General character query (list all characters, etc.)
        elif is_character_query:
            result['query_type'] = 'character'
            result['entities'] = self.available_entities['characters']
            result['needs_full_text'] = False
        elif is_location_query:
            result['query_type'] = 'location'
            result['entities'] = self.available_entities['locations']
            result['needs_full_text'] = False
        else:
            # Might need plot summary or full text
            result['query_type'] = 'general'
            result['needs_full_text'] = True
        
        print(f"  Query type: {result['query_type']}")
        print(f"  Relevant entities: {result['entities']}")
        
        return result
    
    def load_entity_profiles(self, entity_names: List[str], entity_type: str = None) -> str:
        """
        Load the markdown profiles for specified entities.
        
        Args:
            entity_names: List of entity names
            entity_type: 'character', 'location', or 'term' (if known)
            
        Returns:
            Combined markdown content
        """
        content = []
        
        for name in entity_names:
            # Try different prefixes if type not specified
            prefixes = []
            if entity_type:
                prefixes = [entity_type]
            else:
                prefixes = ['character', 'location', 'term']
            
            for prefix in prefixes:
                filename = f"{prefix}_{name.replace(' ', '_')}.md"
                filepath = self.kb_path / filename
                
                if filepath.exists():
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content.append(f.read())
                    break
        
        return '\n\n---\n\n'.join(content)
    
    def build_context_for_query(self, user_question: str) -> str:
        """
        Build optimized context for answering a user query.
        
        Args:
            user_question: The user's question
            
        Returns:
            Focused context string with only relevant entity profiles
        """
        analysis = self.analyze_query(user_question)
        
        if not analysis['entities']:
            return "No specific entity profiles available for this query."
        
        # Load relevant profiles
        context = self.load_entity_profiles(analysis['entities'])
        
        return f"""Relevant entity information:

{context}

Answer based on the above information."""
