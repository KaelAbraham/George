"""
Entity validation interface for manual review and correction of extracted entities.
"""
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

class ValidationInterface:
    """Interface for validating and correcting extracted entities."""
    
    def __init__(self):
        """Initialize the validation interface."""
        logger.info("ValidationInterface initialized")
    
    def review_entities(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Review and validate extracted entities.
        
        Args:
            entities (List[Dict]): List of extracted entities to validate
            
        Returns:
            List[Dict]: List of validated entities with status
        """
        validated_entities = []
        
        for entity in entities:
            # For now, automatically accept all entities
            # In a real implementation, this would present a UI for manual review
            validated_entity = entity.copy()
            validated_entity['status'] = 'accepted'
            validated_entities.append(validated_entity)
        
        logger.info(f"Validated {len(validated_entities)} entities")
        return validated_entities
    
    def get_entity_stats(self, entities: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Get statistics about validated entities.
        
        Args:
            entities (List[Dict]): List of validated entities
            
        Returns:
            Dict[str, int]: Statistics about entity status
        """
        stats = {
            'total': len(entities),
            'accepted': 0,
            'rejected': 0,
            'pending': 0
        }
        
        for entity in entities:
            status = entity.get('status', 'pending')
            if status in stats:
                stats[status] += 1
        
        return stats