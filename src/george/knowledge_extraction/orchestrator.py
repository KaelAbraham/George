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
from knowledge_extraction.profile_editor import ProfileEditor
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
        self.profile_editor = ProfileEditor(george_ai, str(self.kb_path))
        
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
        print(f"\n{'='*80}")
        print(f"🚀 AUTOMATIC KNOWLEDGE BASE GENERATOR")
        print(f"   Manuscript: {filename}")
        print(f"{'='*80}\n")
        
        # STEP 1: Identify ALL entities
        print(f"{'='*80}")
        print("STEP 1: IDENTIFICATION - Reading manuscript to identify entities")
        print(f"{'='*80}")
        entities = self.extractor.extract_initial_entities_ai(text, self.ai)
        
        self.entities = entities
        summary = self.extractor.get_summary()
        
        print(f"\n✅ STEP 1 COMPLETE - Identified:")
        print(f"   • {summary['character']} Characters")
        print(f"   • {summary['location']} Locations")
        print(f"   • {summary['term']} Terms/Concepts")
        print(f"   Total: {len(entities)} entities\n")
        
        # STEP 2: Create markdown files
        print(f"{'='*80}")
        print("STEP 2: PROFILE CREATION - Creating .md file for each entity")
        print(f"{'='*80}\n")
        
        total_entities = len(entities)
        current = 0
        
        # STEP 3: Detailed analysis (happens during profile building)
        print(f"{'='*80}")
        print("STEP 3: DEEP ANALYSIS - Reading manuscript for each entity")
        print(f"{'='*80}")
        
        # Build character profiles
        characters = self.extractor.get_entities_by_type('character')
        for i, entity in enumerate(characters, 1):
            current += 1
            print(f"\n[{current}/{total_entities}] Processing character: {entity.name}")
            try:
                self.profile_builder.build_character_profile(entity.name, text, entity)
            except Exception as e:
                print(f"  ⚠️  Error: {e}")
        
        # Build location profiles
        locations = self.extractor.get_entities_by_type('location')
        for i, entity in enumerate(locations, 1):
            current += 1
            print(f"\n[{current}/{total_entities}] Processing location: {entity.name}")
            try:
                self.profile_builder.build_location_profile(entity.name, text, entity)
            except Exception as e:
                print(f"  ⚠️  Error: {e}")
        
        # Build term profiles
        terms = self.extractor.get_entities_by_type('term')
        for i, entity in enumerate(terms, 1):
            current += 1
            print(f"\n[{current}/{total_entities}] Processing term: {entity.name}")
            try:
                self.profile_builder.build_term_profile(entity.name, text, entity)
            except Exception as e:
                print(f"  ⚠️  Error: {e}")
        
        self.processing_complete = True
        
        print(f"\n{'='*60}")
        print(f"✅ Knowledge extraction complete!")
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
    
    def edit_profile(self, user_instruction: str) -> Dict:
        """
        Edit a profile based on user instruction.
        
        This method detects edit commands like:
        - "Update Edie Ann: she has brown eyes"
        - "Add to Hugh's profile: he's an engineer"
        - "Remove from Linda: the part about Earth"
        - "Merge Carroll and Dad"
        
        Args:
            user_instruction: User's edit command
            
        Returns:
            Dict with success status and message
        """
        # Detect if this is an edit command
        command = self.profile_editor.detect_edit_command(user_instruction)
        
        if not command:
            return {
                'success': False,
                'is_edit_command': False,
                'message': "Not recognized as an edit command"
            }
        
        # Execute the edit
        result = self.profile_editor.execute_edit(command)
        result['is_edit_command'] = True
        
        return result
