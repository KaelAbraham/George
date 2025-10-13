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
    
    def extract_initial_entities(self, text: str) -> Dict[str, Entity]:
        """
        First pass: Extract all potential entities (proper nouns, repeated capitalized words).
        
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
