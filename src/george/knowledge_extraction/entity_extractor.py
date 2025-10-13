"""
Entity Extractor - Identifies characters, locations, and unique terms from manuscripts
"""
import re
from typing import Dict, List, Set
from dataclasses import dataclass, field

@dataclass
class Entity:
    """Represents an extracted entity from the manuscript."""
    name: str
    entity_type: str  # 'character', 'location', 'term'
    first_mention: int  # Character position in text
    mention_count: int = 1
    contexts: List[str] = field(default_factory=list)  # Surrounding text snippets

class EntityExtractor:
    """Extract entities from manuscript text."""
    
    def __init__(self):
        self.entities: Dict[str, Entity] = {}
        # Common words to exclude from entity extraction
        self.common_words = {
            'The', 'And', 'But', 'Or', 'In', 'On', 'At', 'To', 'For', 'Of', 'With', 
            'By', 'From', 'Up', 'About', 'Into', 'Through', 'During', 'Before', 
            'After', 'Above', 'Below', 'Between', 'Under', 'Again', 'Further', 
            'Then', 'Once', 'Here', 'There', 'When', 'Where', 'Why', 'How', 'All',
            'Each', 'Other', 'Some', 'Such', 'No', 'Nor', 'Not', 'Only', 'Own',
            'Same', 'So', 'Than', 'Too', 'Very', 'Can', 'Will', 'Just', 'Should',
            'Now', 'I', 'You', 'He', 'She', 'It', 'We', 'They', 'What', 'Which',
            'This', 'That', 'These', 'Those', 'Am', 'Is', 'Are', 'Was', 'Were',
            'Be', 'Been', 'Being', 'Have', 'Has', 'Had', 'Do', 'Does', 'Did',
            'A', 'An', 'As', 'If', 'Because', 'While', 'My', 'Your', 'His', 'Her',
            'Its', 'Our', 'Their', 'Me', 'Him', 'Us', 'Them'
        }
    
    def extract_initial_entities_ai(self, text: str, ai_instance) -> Dict[str, Entity]:
        """
        COMPREHENSIVE AI entity extraction - reads entire manuscript to identify EVERYTHING.
        This takes time but ensures we don't miss anything.
        
        Args:
            text: Full manuscript text
            ai_instance: GeorgeAI instance for AI analysis
            
        Returns:
            Dictionary of entity name -> Entity object
        """
        print("🔍 Step 1: Comprehensive Entity Identification")
        print("   Reading manuscript to identify ALL characters, settings, and proper names...")
        
        # Process in large chunks to cover the ENTIRE manuscript
        chunk_size = 20000  # Larger chunks to see more context
        chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
        
        all_entities = {
            'characters': set(),
            'locations': set(),
            'terms': set()
        }
        
        # Analyze each chunk
        for i, chunk in enumerate(chunks):
            print(f"   Analyzing chunk {i+1}/{len(chunks)}...")
            
            prompt = f"""Read this story segment carefully and identify EVERY:

1. CHARACTER NAMES - Full proper names of people/beings (e.g., "Edie Ann", "Hugh Sinclair", NOT "Dad" or "Mom")
2. LOCATION NAMES - Specific place names (e.g., "Akkadia Station", "Workshop", NOT generic words)
3. PROPER NOUNS - Named objects, organizations, concepts (e.g., "The Partigiana", specific ship/technology names)

Story segment:
{chunk}

IMPORTANT RULES:
- Use FULL NAMES when characters are introduced (e.g., "Edie Ann" not just "Edie")
- ONLY proper names, NOT generic terms like "Everything", "Maybe", "Dad", "Mom"
- ONLY names that appear in the text, don't invent anything

Format your response EXACTLY like this:
CHARACTERS: name1, name2, name3
LOCATIONS: place1, place2, place3
TERMS: term1, term2, term3

If none found in a category, write "none"."""

            try:
                result = ai_instance.chat(prompt, project_context="")
                if result['success']:
                    response_text = result['response']
                    self._accumulate_entities(response_text, all_entities)
                else:
                    print(f"   ⚠️ Chunk {i+1} AI call failed")
            except Exception as e:
                print(f"   ⚠️ Chunk {i+1} analysis failed: {e}")
                continue
        
        # Convert sets to Entity objects
        print(f"\n   ✅ Found {len(all_entities['characters'])} characters")
        print(f"   ✅ Found {len(all_entities['locations'])} locations")
        print(f"   ✅ Found {len(all_entities['terms'])} terms")
        
        entities = {}
        for name in all_entities['characters']:
            pos = text.find(name)
            if pos >= 0:
                entities[name] = Entity(
                    name=name,
                    entity_type='character',
                    first_mention=pos,
                    mention_count=text.count(name)
                )
        
        for name in all_entities['locations']:
            pos = text.find(name)
            if pos >= 0:
                entities[name] = Entity(
                    name=name,
                    entity_type='location',
                    first_mention=pos,
                    mention_count=text.count(name)
                )
        
        for name in all_entities['terms']:
            pos = text.find(name)
            if pos >= 0:
                entities[name] = Entity(
                    name=name,
                    entity_type='term',
                    first_mention=pos,
                    mention_count=text.count(name)
                )
        
        # Update extractor's entities dict
        self.entities = entities
        
        return entities
    
    def _accumulate_entities(self, response: str, all_entities: dict):
        """Add entities from AI response to accumulator."""
        # Words to exclude (common words, generic terms)
        exclude_words = {
            'Everything', 'Maybe', 'Dad', 'Mom', 'Papa', 'Mama', 'Grandma', 'Grandpa',
            'Sir', 'Madam', 'Mr', 'Mrs', 'Miss', 'Ms', 'Doctor', 'Professor',
            'Eventually', 'Suddenly', 'Then', 'Now', 'Here', 'There', 'Sorry',
            'Please', 'Thank', 'Yes', 'No', 'Okay', 'Hello', 'Goodbye',
            'Tell', 'Wants', 'Isn', 'Net', 'Michael'  # Added based on your false positives
        }
        
        lines = response.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if line.startswith('CHARACTERS:'):
                names = line.replace('CHARACTERS:', '').strip()
                if names.lower() != 'none':
                    for name in names.split(','):
                        name = name.strip()
                        # Filter out common words and single words that aren't proper names
                        if name and len(name) > 1 and name not in exclude_words:
                            all_entities['characters'].add(name)
            
            elif line.startswith('LOCATIONS:'):
                places = line.replace('LOCATIONS:', '').strip()
                if places.lower() != 'none':
                    for place in places.split(','):
                        place = place.strip()
                        if place and len(place) > 1 and place not in exclude_words:
                            all_entities['locations'].add(place)
            
            elif line.startswith('TERMS:'):
                terms = line.replace('TERMS:', '').strip()
                if terms.lower() != 'none':
                    for term in terms.split(','):
                        term = term.strip()
                        if term and len(term) > 1 and term not in exclude_words:
                            all_entities['terms'].add(term)
    
    def _parse_ai_entity_response(self, response: str, full_text: str) -> Dict[str, Entity]:
        """Parse AI response and create Entity objects."""
        entities = {}
        lines = response.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if line.startswith('CHARACTERS:'):
                names = line.replace('CHARACTERS:', '').strip().split(',')
                for name in names:
                    name = name.strip()
                    if name and len(name) > 1:
                        # Find first occurrence in text
                        pos = full_text.find(name)
                        if pos >= 0:
                            entities[name] = Entity(
                                name=name,
                                entity_type='character',
                                first_mention=pos,
                                mention_count=full_text.count(name)
                            )
            elif line.startswith('LOCATIONS:'):
                places = line.replace('LOCATIONS:', '').strip().split(',')
                for place in places:
                    place = place.strip()
                    if place and len(place) > 1 and place.lower() != 'none':
                        pos = full_text.find(place)
                        if pos >= 0:
                            entities[place] = Entity(
                                name=place,
                                entity_type='location',
                                first_mention=pos,
                                mention_count=full_text.count(place)
                            )
            elif line.startswith('TERMS:'):
                terms = line.replace('TERMS:', '').strip().split(',')
                for term in terms:
                    term = term.strip()
                    if term and len(term) > 1 and term.lower() != 'none':
                        pos = full_text.find(term)
                        if pos >= 0:
                            entities[term] = Entity(
                                name=term,
                                entity_type='term',
                                first_mention=pos,
                                mention_count=full_text.count(term)
                            )
        
        return entities
    
    def extract_initial_entities(self, text: str) -> Dict[str, Entity]:
        """
        FALLBACK: First pass using regex (used if AI extraction fails).
        Extract all potential entities (proper nouns, repeated capitalized words).
        
        Args:
            text: Full manuscript text
            
        Returns:
            Dictionary of entity name -> Entity object
        """
        # Find all capitalized words (potential proper nouns)
        capitalized_pattern = r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b'
        matches = re.finditer(capitalized_pattern, text)
        
        entity_candidates = {}
        
        for match in matches:
            name = match.group()
            position = match.start()
            
            # Skip common words
            if name in self.common_words:
                continue
            
            # Get context (100 chars before and after)
            context_start = max(0, position - 100)
            context_end = min(len(text), position + len(name) + 100)
            context = text[context_start:context_end]
            
            if name in entity_candidates:
                entity_candidates[name].mention_count += 1
                entity_candidates[name].contexts.append(context)
            else:
                entity_candidates[name] = Entity(
                    name=name,
                    entity_type='unknown',  # Will classify later
                    first_mention=position,
                    mention_count=1,
                    contexts=[context]
                )
        
        # Filter: Only keep entities mentioned 2+ times (likely important)
        self.entities = {
            name: entity for name, entity in entity_candidates.items()
            if entity.mention_count >= 2
        }
        
        return self.entities
    
    def classify_entities(self, text: str) -> Dict[str, Entity]:
        """
        Second pass: Classify entities as characters, locations, or terms.
        
        Uses heuristics:
        - Characters: Appear with dialogue, action verbs, pronouns
        - Locations: Appear with prepositions (in, at, near)
        - Terms: Everything else (objects, concepts, etc.)
        """
        # Dialogue patterns (character indicators)
        dialogue_pattern = r'[""]([^"""]+)[""],?\s+(\w+)\s+(?:said|asked|replied|told|shouted|whispered|announced)'
        
        # Find all characters speaking
        dialogue_matches = re.finditer(dialogue_pattern, text)
        speaking_characters = set()
        for match in dialogue_matches:
            speaker = match.group(2)
            speaking_characters.add(speaker)
        
        # Classify based on patterns
        for name, entity in self.entities.items():
            # Check if they speak (strong character indicator)
            if name in speaking_characters:
                entity.entity_type = 'character'
                continue
            
            # Check contexts for location indicators
            location_indicators = ['in', 'at', 'near', 'from', 'to', 'toward', 'around']
            is_location = any(
                any(f' {indicator} {name}' in context.lower() for indicator in location_indicators)
                for context in entity.contexts
            )
            if is_location:
                entity.entity_type = 'location'
                continue
            
            # Check for character action verbs
            action_verbs = ['walked', 'ran', 'said', 'looked', 'smiled', 'thought', 'felt', 'went']
            is_character = any(
                any(f'{name} {verb}' in context for verb in action_verbs)
                for context in entity.contexts
            )
            if is_character:
                entity.entity_type = 'character'
                continue
            
            # Default to term
            entity.entity_type = 'term'
        
        return self.entities
    
    def extract_dialogue_contexts(self, text: str, character_name: str) -> List[str]:
        """Extract all dialogue snippets for a specific character."""
        # Pattern: "dialogue", Character said/asked/etc.
        pattern = f'[""]([^"""]+)[""],?\\s+{character_name}\\s+(?:said|asked|replied|told|shouted|whispered|announced)'
        matches = re.findall(pattern, text, re.IGNORECASE)
        return matches
    
    def get_entities_by_type(self, entity_type: str) -> List[Entity]:
        """Get all entities of a specific type."""
        return [entity for entity in self.entities.values() if entity.entity_type == entity_type]
    
    def get_summary(self) -> Dict[str, int]:
        """Get count of entities by type."""
        summary = {'character': 0, 'location': 0, 'term': 0, 'unknown': 0}
        for entity in self.entities.values():
            summary[entity.entity_type] = summary.get(entity.entity_type, 0) + 1
        return summary
