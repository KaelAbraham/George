"""
Knowledge Base Builder for constructing the hybrid knowledge base from processed entities and text
"""
import os
import logging
from typing import List, Dict, Any
from .vector_store import VectorStore
from .structured_db import StructuredDB
from .search import HybridSearchEngine
from ..preprocessing.text_chunker import TextChunker
logger = logging.getLogger(__name__)
class KnowledgeBaseBuilder:
    """
    Orchestrates the construction of the hybrid knowledge base from validated entities and text chunks.
    """
    def __init__(self, data_dir: str = None):
        """
        Initialize the knowledge base builder.
        Args:
            data_dir (str): Base directory for data storage
        """
        if data_dir is None:
            data_dir = os.path.join(os.getcwd(), "data")
        self.data_dir = data_dir
        self.vector_db_dir = os.path.join(data_dir, "vector_db")
        self.entities_db_path = os.path.join(data_dir, "entities.db")
        # Initialize storage components
        self.vector_store = VectorStore(self.vector_db_dir)
        self.structured_db = StructuredDB(self.entities_db_path)
        # Initialize search engine
        self.search_engine = HybridSearchEngine(self.vector_store, self.structured_db)
        # Initialize text chunker
        self.text_chunker = TextChunker()
        logger.info("KnowledgeBaseBuilder initialized")
    def initialize_knowledge_base(self, collection_name: str = "knowledge_base"):
        """
        Initialize the knowledge base collections and tables.
        Args:
            collection_name (str): Name for the vector collection
        """
        try:
            # Initialize vector store collection
            self.vector_store.create_collection(collection_name)
            # Structured DB is already initialized in constructor
            logger.info("Knowledge base initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize knowledge base: {e}")
            raise
    def add_entity(self, entity_data: Dict[str, Any]) -> int:
        """
        Add an entity to the structured database.
        Args:
            entity_data (dict): Entity information with keys:
                - name (str): Entity name
                - type (str): Entity type (character, location, etc.)
                - description (str, optional): Entity description
                - mentions (list, optional): List of mention data
                - source_file (str): Source file
                - chapter (str, optional): Chapter/section
                - paragraph (int, optional): Paragraph number
        Returns:
            int: ID of the inserted entity
        """
        try:
            # Insert entity
            entity_id = self.structured_db.insert_entity(
                entity_data["name"],
                entity_data["type"],
                entity_data.get("description")
            )
            # Insert mentions if provided
            if "mentions" in entity_data:
                for mention in entity_data["mentions"]:
                    self.structured_db.insert_entity_mention(
                        entity_id,
                        entity_data["source_file"],
                        mention.get("chapter"),
                        mention.get("paragraph"),
                        mention.get("character_start"),
                        mention.get("character_end"),
                        mention.get("text")
                    )
            logger.info(f"Added entity: {entity_data['name']} (ID: {entity_id})")
            return entity_id
        except Exception as e:
            logger.error(f"Failed to add entity {entity_data.get('name')}: {e}")
            raise
    def add_text_chunk(self, chunk_data: Dict[str, Any]) -> int:
        """
        Add a text chunk to both vector store and structured database.
        Args:
            chunk_data (dict): Chunk information with keys:
                - text (str): Text content
                - source_file (str): Source file
                - chapter (str, optional): Chapter/section
                - paragraph_start (int, optional): Starting paragraph
                - paragraph_end (int, optional): Ending paragraph
                - character_start (int, optional): Character start position
                - character_end (int, optional): Character end position
                - entities (list, optional): List of entity names in this chunk
        Returns:
            int: ID of the inserted chunk
        """
        try:
            # Generate a unique embedding ID
            import uuid
            embedding_id = str(uuid.uuid4())
            # Add to vector store
            self.vector_store.add_texts(
                [chunk_data["text"]],
                [{
                    "source_file": chunk_data["source_file"],
                    "chapter": chunk_data.get("chapter"),
                    "paragraph_start": chunk_data.get("paragraph_start"),
                    "paragraph_end": chunk_data.get("paragraph_end"),
                    "character_start": chunk_data.get("character_start"),
                    "character_end": chunk_data.get("character_end")
                }],
                [embedding_id]
            )
            # Add to structured database
            chunk_id = self.structured_db.insert_text_chunk(
                chunk_data["text"],
                chunk_data["source_file"],
                chunk_data.get("chapter"),
                chunk_data.get("paragraph_start"),
                chunk_data.get("paragraph_end"),
                chunk_data.get("character_start"),
                chunk_data.get("character_end"),
                embedding_id
            )
            # Add citations for entities if provided
            if "entities" in chunk_data and chunk_data["entities"]:
                for entity_name in chunk_data["entities"]:
                    # Get entity ID by name
                    entity = self.structured_db.get_entity_by_name(entity_name)
                    if entity:
                        self.structured_db.insert_citation(chunk_id, entity["id"])
            logger.info(f"Added text chunk from {chunk_data['source_file']} (ID: {chunk_id})")
            return chunk_id
        except Exception as e:
            logger.error(f"Failed to add text chunk: {e}")
            raise
    def process_document(self, text: str, source_file: str, entities: List[Dict] = None, 
                        chapter: str = None) -> List[int]:
        """
        Process a document by chunking it and adding chunks to the knowledge base.
        Args:
            text (str): Document text to process
            source_file (str): Source file identifier
            entities (List[Dict], optional): List of entity dictionaries with position info
            chapter (str, optional): Chapter/section name
        Returns:
            List[int]: List of chunk IDs that were added
        """
        try:
            # Chunk the text
            if entities:
                chunks = self.text_chunker.chunk_with_entity_detection(text, source_file, entities, chapter)
            else:
                chunks = self.text_chunker.chunk_text(text, source_file, chapter)
            # Add chunks to knowledge base
            chunk_ids = []
            for chunk in chunks:
                chunk_data = {
                    "text": chunk.text,
                    "source_file": chunk.source_file,
                    "chapter": chunk.chapter,
                    "paragraph_start": chunk.paragraph_start,
                    "paragraph_end": chunk.paragraph_end,
                    "character_start": chunk.character_start,
                    "character_end": chunk.character_end,
                    "entities": chunk.entities
                }
                chunk_id = self.add_text_chunk(chunk_data)
                chunk_ids.append(chunk_id)
            logger.info(f"Processed document {source_file} into {len(chunk_ids)} chunks")
            return chunk_ids
        except Exception as e:
            logger.error(f"Failed to process document {source_file}: {e}")
            raise
    def build_knowledge_base(self, entities: List[Dict], text_chunks: List[Dict]):
        """
        Build the complete knowledge base from entities and text chunks.
        Args:
            entities (list): List of entity data dictionaries
            text_chunks (list): List of text chunk data dictionaries
        """
        try:
            # Initialize the knowledge base
            self.initialize_knowledge_base()
            # Add entities
            entity_ids = []
            for entity in entities:
                entity_id = self.add_entity(entity)
                entity_ids.append(entity_id)
            # Add text chunks
            chunk_ids = []
            for chunk in text_chunks:
                chunk_id = self.add_text_chunk(chunk)
                chunk_ids.append(chunk_id)
            logger.info(f"Knowledge base built with {len(entity_ids)} entities and {len(chunk_ids)} chunks")
        except Exception as e:
            logger.error(f"Failed to build knowledge base: {e}")
            raise
    def close(self):
        """
        Close all database connections.
        """
        try:
            self.structured_db.close()
            logger.info("Knowledge base connections closed")
        except Exception as e:
            logger.error(f"Error closing connections: {e}")
if __name__ == "__main__":
    # Test the KnowledgeBaseBuilder
    import tempfile
    import shutil
    # Create a temporary directory for testing
    test_dir = tempfile.mkdtemp()
    try:
        # Test initialization
        builder = KnowledgeBaseBuilder(test_dir)
        print(f"✓ KnowledgeBaseBuilder initialized with data dir: {test_dir}")
        # Test sample data
        entities = [
            {
                "name": "John Doe",
                "type": "character",
                "description": "Main protagonist",
                "source_file": "chapter1.txt"
            }
        ]
        text_chunks = [
            {
                "text": "John entered the room cautiously.",
                "source_file": "chapter1.txt",
                "chapter": "Chapter 1",
                "paragraph_start": 5,
                "paragraph_end": 5,
                "character_start": 120,
                "character_end": 155
            }
        ]
        # Test building knowledge base
        builder.build_knowledge_base(entities, text_chunks)
        print("✓ Knowledge base built successfully")
        # Test search functionality
        entity_result = builder.search_engine.entity_search("John Doe")
        print(f"✓ Entity search result: {entity_result is not None}")
    finally:
        # Clean up
        builder.close()