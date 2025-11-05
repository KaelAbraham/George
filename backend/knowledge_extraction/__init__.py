"""
Knowledge Extraction - Package initialization
"""
# Import orchestrator and other modules from this package
from .orchestrator import KnowledgeExtractor
from .query_analyzer import QueryAnalyzer
from .profile_editor import ProfileEditor

# Import entity extractor from the akg module (needs to be in PYTHONPATH)
try:
    from akg.core.entity_extractor import EntityExtractor
except ImportError:
    # Fallback if akg is not available
    EntityExtractor = None

__all__ = [
    'EntityExtractor', 
    'QueryAnalyzer', 
    'ProfileEditor',
    'KnowledgeExtractor'
]
