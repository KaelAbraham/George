"""
Entity Extractor using spaCy for Named Entity Recognition
"""
try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False
    spacy = None

from typing import List, Dict, Tuple, Optional
from collections import defaultdict
import logging
logger = logging.getLogger(__name__)
class EntityExtractor:
    """
    Core entity extraction class using spaCy NER model.
    Extracts PERSON, ORG, GPE (locations) and custom proper nouns from text.
    """
    def __init__(self, model_name: str = "en_core_web_sm"):
        """
        Initialize the EntityExtractor with a spaCy model.
        Args:
            model_name (str): Name of the spaCy model to use (default: en_core_web_sm)
        """
        if not SPACY_AVAILABLE:
            logger.warning("spaCy is not available. Using basic fallback entity extraction.")
            self.nlp = None
            return
            
        try:
            self.nlp = spacy.load(model_name)
            logger.info(f"Successfully loaded spaCy model: {model_name}")
        except Exception as e:
            logger.warning(f"Failed to load spaCy model {model_name}: {e}. Using basic fallback.")
            self.nlp = None
    def extract_entities(self, text: str) -> List[Dict]:
        """
        Extract named entities from text using spaCy NER.
        Args:
            text (str): Input text to process
        Returns:
            List[Dict]: List of extracted entities with metadata
        """
        if self.nlp is None:
            return self._basic_extraction(text)
            
        doc = self.nlp(text)
        entities = []
        for ent in doc.ents:
            entity_data = {
                "text": ent.text,
                "label": ent.label_,
                "start": ent.start_char,
                "end": ent.end_char,
                "sentence": ent.sent.text.strip() if ent.sent else ""
            }
            entities.append(entity_data)
        return entities
    def extract_from_chunks(self, chunks: List[str]) -> List[Dict]:
        """
        Extract entities from a list of text chunks.
        Args:
            chunks (List[str]): List of text chunks to process
        Returns:
            List[Dict]: Combined list of extracted entities from all chunks
        """
        all_entities = []
        for i, chunk in enumerate(chunks):
            try:
                entities = self.extract_entities(chunk)
                # Add chunk information to entities
                for entity in entities:
                    entity["chunk_index"] = i
                all_entities.extend(entities)
            except Exception as e:
                logger.warning(f"Failed to process chunk {i}: {e}")
                continue
        return all_entities
    def get_entity_statistics(self, entities: List[Dict]) -> Dict:
        """
        Get statistics about extracted entities.
        Args:
            entities (List[Dict]): List of extracted entities
        Returns:
            Dict: Statistics about entity types and counts
        """
        stats = defaultdict(int)
        unique_entities = defaultdict(set)
        for entity in entities:
            label = entity["label"]
            text = entity["text"]
            stats[label] += 1
            unique_entities[label].add(text)
        return {
            "total_entities": len(entities),
            "unique_entities": {k: len(v) for k, v in unique_entities.items()},
            "entity_types": dict(stats)
        }
    
    def _basic_extraction(self, text: str) -> List[Dict]:
        """
        Basic entity extraction fallback when spaCy is not available.
        Args:
            text (str): Text to extract entities from
        Returns:
            List[Dict]: List of basic extracted entities
        """
        entities = []
        words = text.split()
        
        for i, word in enumerate(words):
            # Basic capitalized word detection
            if word[0].isupper() and len(word) > 2 and word.isalpha():
                # Get surrounding context
                start_idx = max(0, i-5)
                end_idx = min(len(words), i+6)
                sentence = ' '.join(words[start_idx:end_idx])
                
                entity = {
                    'text': word,
                    'label': 'ENTITY',
                    'start': start_idx,
                    'end': i+1,
                    'sentence': sentence
                }
                entities.append(entity)
        
        return entities
if __name__ == "__main__":
    # Simple test
    extractor = EntityExtractor()
    sample_text = "James Bond walked into the MI6 headquarters in London. He met with M and Q for a briefing."
    entities = extractor.extract_entities(sample_text)
    print(f"Extracted entities: {entities}")