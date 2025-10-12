"""
Main orchestrator for Standalone George - Local-first AI assistant for authors and world-builders.
This script integrates all components: manuscript import, entity extraction, knowledge base construction,
and conversational interface with citations.
"""
import os
import sys
import argparse
import logging
from pathlib import Path

# Import all required components
from george.parsers.document_parser import DocumentParser
from george.preprocessing.text_chunker import TextChunker
from george.akg.core.entity_extractor import EntityExtractor
from george.akg.validation.interface import ValidationInterface
from george.knowledge_base.builder import KnowledgeBaseBuilder
from george.knowledge_base.search import HybridSearchEngine
from george.ui.app import create_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class GeorgeOrchestrator:
    """Main orchestrator for the George application."""
    def __init__(self, project_path=None):
        """Initialize the George orchestrator."""
        self.project_path = project_path or os.getcwd()
        self.data_dir = os.path.join(self.project_path, 'data')
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Initialize components
        self.parser = DocumentParser()
        self.chunker = TextChunker()
        self.entity_extractor = EntityExtractor()
        self.validation_interface = ValidationInterface()
        self.kb_builder = KnowledgeBaseBuilder(self.data_dir)
        
        logger.info("George orchestrator initialized")
    
    def import_manuscript(self, file_path):
        """
        Import and process a manuscript file.
        Args:
            file_path (str): Path to the manuscript file
        Returns:
            dict: Processing results
        """
        logger.info(f"Importing manuscript: {file_path}")
        try:
            # Parse the document
            parsed_result = self.parser.parse(file_path)
            content = parsed_result['content']
            file_name = os.path.basename(file_path)
            logger.info(f"Parsed {file_name} ({parsed_result['format']}) - {len(content)} characters")
            
            # Chunk the text
            chunks = self.chunker.chunk_text(content, file_name)
            logger.info(f"Created {len(chunks)} text chunks")
            
            # Extract entities from each chunk
            entities = []
            for i, chunk in enumerate(chunks):
                # Debug: Check the type and content of chunk.content
                logger.info(f"Chunk {i}: chunk.content type = {type(chunk.content)}, content = {repr(chunk.content[:100])}")
                chunk_entities = self.entity_extractor.extract_entities(chunk.content)
                
                # Add chunk information to entities and convert format
                for entity in chunk_entities:
                    # Convert spaCy format to knowledge base format
                    kb_entity = {
                        'name': entity['text'],
                        'type': entity['label'],
                        'description': entity.get('sentence', ''),
                        'source_file': chunk.source_file,
                        'chunk_id': chunk.chunk_id
                    }
                    entities.append(kb_entity)
            
            logger.info(f"Extracted {len(entities)} candidate entities")
            
            return {
                'success': True,
                'file_name': file_name,
                'format': parsed_result['format'],
                'content_length': len(content),
                'chunks_count': len(chunks),
                'entities_count': len(entities),
                'content': content,
                'chunks': chunks,
                'entities': entities
            }
        except Exception as e:
            logger.error(f"Error importing manuscript {file_path}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def validate_entities(self, entities):
        """
        Validate extracted entities through user interface.
        Args:
            entities (list): List of entity candidates
        Returns:
            list: Validated entities
        """
        logger.info(f"Validating {len(entities)} entities")
        try:
            # In a real implementation, this would open the validation interface
            # For now, we'll simulate approval of all entities by accepting them all
            try:
                validated_entities = self.validation_interface.review_entities(entities)
                # If no entities were returned, accept all original entities
                if not validated_entities:
                    for entity in entities:
                        entity['status'] = 'accepted'
                    validated_entities = entities
                # Filter to only accepted entities
                accepted_entities = [e for e in validated_entities if e.get('status') == 'accepted']
                logger.info(f"Accepted {len(accepted_entities)} entities out of {len(entities)}")
                return accepted_entities
            except Exception as e:
                logger.warning(f"Validation interface error: {e}. Proceeding with all entities as accepted.")
                # Return all entities with accepted status
                for entity in entities:
                    entity['status'] = 'accepted'
                return entities
            
            logger.info(f"Validated {len(validated_entities)} entities")
            return validated_entities
        except Exception as e:
            logger.error(f"Error validating entities: {e}")
            return entities  # Return original entities if validation fails
    
    def build_knowledge_base(self, entities, chunks):
        """
        Build the hybrid knowledge base with entities and text chunks.
        Args:
            entities (list): Validated entities
            chunks (list): Processed text chunks
        Returns:
            bool: Success status
        """
        logger.info("Building knowledge base")
        try:
            # Initialize knowledge base
            self.kb_builder.initialize_knowledge_base()
            # Build knowledge base with entities and chunks
            self.kb_builder.build_knowledge_base(entities, [chunk.to_dict() for chunk in chunks])
            # Close connections
            self.kb_builder.close()
            logger.info("Knowledge base built successfully")
            return True
        except Exception as e:
            logger.error(f"Error building knowledge base: {e}")
            return False
    
    def start_chat_interface(self, host='0.0.0.0', port=5000, debug=False):
        """
        Start the chat interface web application.
        Args:
            host (str): Host address
            port (int): Port number
            debug (bool): Debug mode
        """
        logger.info(f"Starting chat interface on {host}:{port}")
        try:
            # Create and run the Flask app
            app = create_app()
            app.run(host=host, port=port, debug=debug)
        except Exception as e:
            logger.error(f"Error starting chat interface: {e}")
            raise
    
    def process_complete_workflow(self, file_path):
        """
        Process complete workflow: import -> extract -> validate -> build KB -> chat.
        Args:
            file_path (str): Path to the manuscript file
        """
        logger.info("Starting complete workflow")
        
        # 1. Import manuscript
        result = self.import_manuscript(file_path)
        if not result['success']:
            logger.error("Manuscript import failed")
            return False
        
        # 2. Validate entities
        validated_entities = self.validate_entities(result['entities'])
        
        # 3. Build knowledge base
        if not self.build_knowledge_base(validated_entities, result['chunks']):
            logger.error("Knowledge base building failed")
            return False
        
        logger.info("Complete workflow finished successfully")
        return True


def main():
    """Main entry point for the George application."""
    parser = argparse.ArgumentParser(description="Standalone George - Local-first AI assistant for authors")
    parser.add_argument('--mode', choices=['import', 'validate', 'build', 'chat', 'workflow'], 
                       default='workflow', help='Operation mode')
    parser.add_argument('--file', type=str, help='Path to manuscript file for import')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Host for chat interface')
    parser.add_argument('--port', type=int, default=5000, help='Port for chat interface')
    parser.add_argument('--project', type=str, help='Project directory path')
    
    args = parser.parse_args()
    
    # Initialize orchestrator
    orchestrator = GeorgeOrchestrator(args.project)
    
    try:
        if args.mode == 'import':
            if not args.file:
                logger.error("File path required for import mode")
                return 1
            result = orchestrator.import_manuscript(args.file)
            if result['success']:
                logger.info("Manuscript imported successfully")
                return 0
            else:
                logger.error(f"Import failed: {result['error']}")
                return 1
        elif args.mode == 'validate':
            logger.info("Starting entity validation interface")
            # This would normally open the validation UI
            logger.info("Validation interface would open here")
            return 0
        elif args.mode == 'build':
            logger.info("Building knowledge base")
            # This would require previously extracted entities and chunks
            logger.info("Knowledge base building would occur here")
            return 0
        elif args.mode == 'chat':
            logger.info("Starting chat interface")
            orchestrator.start_chat_interface(args.host, args.port)
            return 0
        elif args.mode == 'workflow':
            if not args.file:
                logger.error("File path required for complete workflow")
                return 1
            if orchestrator.process_complete_workflow(args.file):
                logger.info("Complete workflow finished successfully")
                return 0
            else:
                logger.error("Complete workflow failed")
                return 1
    except Exception as e:
        logger.error(f"Application error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())