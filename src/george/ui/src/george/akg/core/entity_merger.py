"""
Entity Merger for deduplicating similar entities and suggesting merges
"""
from typing import List, Dict, Tuple
from difflib import SequenceMatcher
import re
class EntityMerger:
    """
    Handles entity deduplication and suggests merges for similar entities.
    """
    def __init__(self, similarity_threshold: float = 0.8):
        """
        Initialize the entity merger.
        Args:
            similarity_threshold (float): Threshold for considering entities similar
        """
        self.similarity_threshold = similarity_threshold
    def find_merge_candidates(self, entities: List[Dict]) -> List[Dict]:
        """
        Find potential merge candidates among entities.
        Args:
            entities (List[Dict]): List of entity candidates
        Returns:
            List[Dict]: Entities with merge suggestions
        """
        # Add merge suggestions to entities
        enriched_entities = []
        for i, entity in enumerate(entities):
            entity_copy = entity.copy()
            # Find similar entities
            similar_entities = self._find_similar_entities(entity, entities, i)
            # Add merge suggestions if any
            if similar_entities:
                entity_copy["merge_suggestions"] = similar_entities
                entity_copy["needs_review"] = True
            else:
                entity_copy["needs_review"] = False
            enriched_entities.append(entity_copy)
        return enriched_entities
    def _find_similar_entities(self, target_entity: Dict, all_entities: List[Dict], target_index: int) -> List[Dict]:
        """
        Find entities similar to the target entity.
        Args:
            target_entity (Dict): Entity to compare against
            all_entities (List[Dict]): All entities to check
            target_index (int): Index of target entity to avoid self-comparison
        Returns:
            List[Dict]: Similar entities with similarity scores
        """
        similar = []
        target_text = target_entity.get("text", "").lower()
        for i, entity in enumerate(all_entities):
            # Skip self and already processed entities
            if i <= target_index:
                continue
            entity_text = entity.get("text", "").lower()
            # Check various similarity conditions
            similarity_score = self._calculate_similarity(target_text, entity_text)
            if similarity_score >= self.similarity_threshold:
                suggestion = entity.copy()
                suggestion["similarity_score"] = round(similarity_score, 3)
                similar.append(suggestion)
        return similar
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate similarity between two entity names.
        Args:
            text1 (str): First text
            text2 (str): Second text
        Returns:
            float: Similarity score (0-1)
        """
        # Handle exact matches
        if text1 == text2:
            return 1.0
        # Handle nickname patterns (Jim/James, Liz/Elizabeth, etc.)
        if self._is_nickname_variant(text1, text2):
            return 0.9
        # Handle abbreviation patterns (J. Smith/John Smith)
        if self._is_abbreviation_variant(text1, text2):
            return 0.85
        # Use sequence matcher for general similarity
        similarity = SequenceMatcher(None, text1, text2).ratio()
        return similarity
    def _is_nickname_variant(self, text1: str, text2: str) -> bool:
        """
        Check if texts are likely nickname variants.
        Args:
            text1 (str): First text
            text2 (str): Second text
        Returns:
            bool: True if likely nickname variants
        """
        # Common nickname mappings
        nicknames = {
            "jim": "james",
            "jimmy": "james",
            "tom": "thomas",
            "tommy": "thomas",
            "dick": "richard",
            "bob": "robert",
            "bobby": "robert",
            "bill": "william",
            "jack": "john",
            "jane": "janet",
            "liz": "elizabeth",
            "beth": "elizabeth",
            "ann": "anne",
            "sue": "susan"
        }
        t1_norm = text1.lower().split()[0]  # First name only
        t2_norm = text2.lower().split()[0]  # First name only
        # Check direct mappings
        if (t1_norm in nicknames and nicknames[t1_norm] == t2_norm) or \
           (t2_norm in nicknames and nicknames[t2_norm] == t1_norm):
            return True
        return False
    def _is_abbreviation_variant(self, text1: str, text2: str) -> bool:
        """
        Check if texts are abbreviation variants.
        Args:
            text1 (str): First text
            text2 (str): Second text
        Returns:
            bool: True if likely abbreviation variants
        """
        # Simple check for initials vs full names
        words1 = text1.split()
        words2 = text2.split()
        if len(words1) != len(words2):
            return False
        for w1, w2 in zip(words1, words2):
            # Check if one is an initial of the other
            if (len(w1) == 1 and w1[0] == w2[0].lower()) or \
               (len(w2) == 1 and w2[0] == w1[0].lower()):
                continue
            elif w1 != w2:
                return False
        return True
    def merge_entities(self, entities: List[Dict], merge_actions: List[Tuple[int, int]]) -> List[Dict]:
        """
        Apply merge actions to entities.
        Args:
            entities (List[Dict]): List of entities
            merge_actions (List[Tuple[int, int]]): List of (keep_index, remove_index) pairs
        Returns:
            List[Dict]: Merged entities
        """
        # Sort actions by remove_index descending to maintain indices
        sorted_actions = sorted(merge_actions, key=lambda x: x[1], reverse=True)
        # Make a copy to avoid modifying original
        merged_entities = entities.copy()
        for keep_index, remove_index in sorted_actions:
            if keep_index < len(merged_entities) and remove_index < len(merged_entities):
                # Merge metadata (e.g., combine mentions, sources)
                keep_entity = merged_entities[keep_index]
                remove_entity = merged_entities[remove_index]
                # Update mention count
                keep_entity["mention_count"] = keep_entity.get("mention_count", 1) + \
                                              remove_entity.get("mention_count", 1)
                # Combine sources if they exist
                if "sources" in keep_entity and "sources" in remove_entity:
                    combined_sources = list(set(keep_entity["sources"] + remove_entity["sources"]))
                    keep_entity["sources"] = combined_sources
                elif "sources" in remove_entity:
                    keep_entity["sources"] = remove_entity["sources"]
                # Update confidence if needed (take maximum)
                if remove_entity.get("confidence", 0) > keep_entity.get("confidence", 0):
                    keep_entity["confidence"] = remove_entity["confidence"]
                # Remove the entity to be merged
                merged_entities.pop(remove_index)
        return merged_entities
if __name__ == "__main__":
    # Simple test
    merger = EntityMerger()
    sample_entities = [
        {"text": "James Bond", "confidence": 0.95, "mention_count": 3},
        {"text": "James", "confidence": 0.8, "mention_count": 2},
        {"text": "Bond", "confidence": 0.7, "mention_count": 1}
    ]
    enriched = merger.find_merge_candidates(sample_entities)
    print(f"Entities with merge suggestions: {enriched}")