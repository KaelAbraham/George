"""
Demonstration of the hybrid knowledge base system
"""
import os
import sys
import logging
# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.knowledge_base.builder import KnowledgeBaseBuilder
from src.knowledge_base.vector_store import VectorStore
from src.knowledge_base.structured_db import StructuredDB
from src.knowledge_base.search import HybridSearchEngine
def setup_logging():
    """Set up basic logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
def main():
    """Demonstrate the knowledge base system functionality."""
    setup_logging()
    logger = logging.getLogger(__name__)
    try:
        print("=" * 60)
        print("HYBRID KNOWLEDGE BASE SYSTEM DEMONSTRATION")
        print("=" * 60)
        # Create data directory if it doesn't exist
        data_dir = os.path.join(os.getcwd(), "data")
        os.makedirs(data_dir, exist_ok=True)
        print("\n1. Initializing knowledge base system...")
        kb_builder = KnowledgeBaseBuilder(data_dir)
        print("   ✓ Knowledge base builder created")
        # Initialize knowledge base
        kb_builder.initialize_knowledge_base()
        print("   ✓ Knowledge base initialized")
        print("\n2. Sample data for demonstration...")
        # Sample entities data
        entities = [
            {
                "name": "John Doe",
                "type": "character",
                "description": "Main protagonist of the story",
                "source_file": "chapter1.txt",
                "mentions": [
                    {
                        "chapter": "Chapter 1",
                        "paragraph": 3,
                        "character_start": 45,
                        "character_end": 78,
                        "text": "John entered the dark forest cautiously"
                    }
                ]
            },
            {
                "name": "Mystic Forest",
                "type": "location",
                "description": "Enchanted woodland filled with magical creatures",
                "source_file": "chapter1.txt"
            }
        ]
        # Sample text chunks
        text_chunks = [
            {
                "text": "John entered the dark forest cautiously. The Mystic Forest was known for its unpredictable magic.",
                "source_file": "chapter1.txt",
                "chapter": "Chapter 1",
                "paragraph_start": 3,
                "paragraph_end": 3,
                "character_start": 45,
                "character_end": 135,
                "entities": [1, 2]  # IDs of entities mentioned in this chunk
            },
            {
                "text": "The ancient oak trees whispered secrets to those who knew how to listen. John felt a strange energy in the air.",
                "source_file": "chapter1.txt",
                "chapter": "Chapter 1",
                "paragraph_start": 4,
                "paragraph_end": 4,
                "character_start": 136,
                "character_end": 250,
                "entities": [1]  # ID of entity mentioned in this chunk
            }
        ]
        print("   Sample entities:")
        for entity in entities:
            print(f"     - {entity['name']} ({entity['type']})")
        print("   Sample text chunks:")
        for i, chunk in enumerate(text_chunks, 1):
            print(f"     - Chunk {i}: {chunk['text'][:50]}...")
        print("\n3. Building knowledge base with sample data...")
        kb_builder.build_knowledge_base(entities, text_chunks)
        print("   ✓ Knowledge base built successfully")
        print("\n4. Demonstrating query capabilities...")
        # Test structured database query
        print("   Structured entity search:")
        entity = kb_builder.structured_db.get_entity_by_name("John Doe")
        if entity:
            print(f"     Found entity: {entity['name']} - {entity['description']}")
        else:
            print("     Entity not found")
        # Test vector database query
        print("   Semantic search:")
        results = kb_builder.vector_store.search("magic forest", n_results=1)
        if results['ids'][0]:
            print(f"     Found relevant text: {results['documents'][0][0][:60]}...")
        else:
            print("     No relevant results found")
        # Test hybrid search
        print("   Hybrid search engine:")
        hybrid_engine = HybridSearchEngine(kb_builder.vector_store, kb_builder.structured_db)
        hybrid_results = hybrid_engine.hybrid_search("main character in magical forest")
        print(f"     Hybrid search completed with {len(hybrid_results['semantic_results']['ids'][0])} semantic results")
        # Close connections
        kb_builder.close()
        print("\n5. System demonstration completed successfully!")
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print("✓ Hybrid knowledge base system with vector and structured storage")
        print("✓ Entity storage with relationships and metadata tracking")
        print("✓ Text chunking with source attribution")
        print("✓ Semantic search capabilities")
        print("✓ Hybrid query interface combining both storage types")
        print("✓ Complete citation tracking system")
        print("=" * 60)
    except Exception as e:
        logger.error(f"Error in knowledge base demonstration: {e}")
        raise
if __name__ == "__main__":
    main()