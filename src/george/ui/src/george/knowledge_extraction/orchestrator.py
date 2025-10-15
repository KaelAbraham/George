"""
Knowledge Extraction Orchestrator - Main workflow controller
"""
import os
import sys
from pathlib import Path
from typing import Dict

# Add parent to path if needed
current_dir = Path(__file__).parent
george_dir = current_dir.parent
if str(george_dir) not in sys.path:
    sys.path.insert(0, str(george_dir))

from knowledge_extraction.entity_extractor import EntityExtractor
from knowledge_extraction.profile_builder import ProfileBuilder
from knowledge_extraction.query_analyzer import QueryAnalyzer
from llm_integration import GeorgeAI

class KnowledgeExtractor:
    """Main orchestrator for knowledge extraction and retrieval."""
    
    def __init__(self, george_ai: GeorgeAI, project_path: str):
        """
        Initialize knowledge extractor.
        
        Args:
            george_ai: AI instance for analysis
            project_path: Base path for storing knowledge base
        """
        self.ai = george_ai
        self.project_path = Path(project_path)
        self.kb_path = self.project_path / 'knowledge_base'
        self.kb_path.mkdir(parents=True, exist_ok=True)
        
        self.extractor = EntityExtractor()
        self.profile_builder = ProfileBuilder(george_ai, str(self.kb_path))
        self.query_analyzer = QueryAnalyzer(george_ai, str(self.kb_path))
        
        self.entities = {}
        self.processing_complete = False
    
    def process_manuscript(self, text: str, filename: str) -> Dict:
        """
        Full processing pipeline for uploaded manuscript.
        
        This takes time but only runs once per upload.
        
        Args:
            text: Full manuscript text
            filename: Original filename
            
        Returns:
            Processing summary with entity counts
        """
        print(f"\n{'='*60}")
        print(f"[START] Starting knowledge extraction for: {filename}")
        print(f"{'='*60}\n")
        
        # Phase 1: Extract entities
        print("Phase 1: Extracting entities...")
        entities = self.extractor.extract_initial_entities(text)
        print(f"  Found {len(entities)} potential entities")
        
        # Phase 2: Classify entities
        print("\nPhase 2: Classifying entities...")
        self.entities = self.extractor.classify_entities(text)
        summary = self.extractor.get_summary()
        print(f"  Characters: {summary['character']}")
        print(f"  Locations: {summary['location']}")
        print(f"  Terms: {summary['term']}")
        
        # Phase 3: Build detailed profiles
        print("\nPhase 3: Building detailed profiles (this may take a while)...")
        
        # Build character profiles
        characters = self.extractor.get_entities_by_type('character')
        for entity in characters:
            try:
                self.profile_builder.build_character_profile(entity.name, text, entity)
            except Exception as e:
                print(f"  [WARN] Error building profile for {entity.name}: {e}")
        
        # Build location profiles
        locations = self.extractor.get_entities_by_type('location')
        for entity in locations:
            try:
                self.profile_builder.build_location_profile(entity.name, text, entity)
            except Exception as e:
                print(f"  [WARN] Error building profile for {entity.name}: {e}")
        
        # Build term profiles
        terms = self.extractor.get_entities_by_type('term')
        for entity in terms[:5]:  # Limit to top 5 most mentioned terms
            try:
                self.profile_builder.build_term_profile(entity.name, text, entity)
            except Exception as e:
                print(f"  [WARN] Error building profile for {entity.name}: {e}")
        
        self.processing_complete = True
        
        print(f"\n{'='*60}")
        print(f"[OK] Knowledge extraction complete!")
        print(f"{'='*60}\n")
        
        return {
            'total_entities': len(self.entities),
            'characters': summary['character'],
            'locations': summary['location'],
            'terms': summary['term'],
            'kb_path': str(self.kb_path)
        }
    
    def answer_query(self, user_question: str) -> Dict:
        """
        Answer user query using extracted knowledge.
        
        Args:
            user_question: User's question
            
        Returns:
            Dictionary with response and metadata
        """
        if not self.processing_complete:
            return {
                'success': False,
                'error': 'Knowledge base not ready. Please upload and process a manuscript first.'
            }
        
        # Analyze query and build focused context
        context = self.query_analyzer.build_context_for_query(user_question)
        
        # Send to AI with focused context
        result = self.ai.chat(user_question, context)
        
        if result['success']:
            return {
                'success': True,
                'response': result['response'],
                'model': result['model'],
                'context_used': len(context)
            }
        else:
            return {
                'success': False,
                'error': result.get('error', 'Unknown error')
            }
    
    def get_knowledge_base_summary(self) -> Dict:
        """Get summary of current knowledge base."""
        return {
            'processing_complete': self.processing_complete,
            'entities': self.extractor.get_summary(),
            'total_profiles': len(list(self.kb_path.glob('*.md'))),
            'kb_path': str(self.kb_path)
        }
