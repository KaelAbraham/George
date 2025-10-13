"""
Structured Database Module using SQLite for entity storage and relationships
"""
import sqlite3
import os
import logging
from typing import List, Dict, Any, Optional
logger = logging.getLogger(__name__)
class StructuredDB:
    """
    Manages the SQLite database for structured entity storage and relationships.
    """
    def __init__(self, db_path: str = None):
        """
        Initialize the structured database.
        Args:
            db_path (str): Path to the SQLite database file
        """
        if db_path is None:
            db_path = os.path.join(os.getcwd(), "data", "entities.db")
        # Create the directory if it doesn't exist
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.conn = None
        self.initialize_database()
        logger.info(f"StructuredDB initialized at {db_path}")
    def initialize_database(self):
        """
        Create the database tables if they don't exist.
        """
        try:
            self.conn = sqlite3.connect(self.db_path)
            cursor = self.conn.cursor()
            # Create entities table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    type TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Create entity_mentions table for tracking where entities appear
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entity_mentions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id INTEGER NOT NULL,
                    source_file TEXT NOT NULL,
                    chapter TEXT,
                    paragraph INTEGER,
                    character_start INTEGER,
                    character_end INTEGER,
                    mention_text TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (entity_id) REFERENCES entities (id)
                )
            """)
            # Create text_chunks table for storing processed text segments
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS text_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chunk_text TEXT NOT NULL,
                    source_file TEXT NOT NULL,
                    chapter TEXT,
                    paragraph_start INTEGER,
                    paragraph_end INTEGER,
                    character_start INTEGER,
                    character_end INTEGER,
                    embedding_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Create citations table for tracking relationships between chunks and entities
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS citations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chunk_id INTEGER NOT NULL,
                    entity_id INTEGER NOT NULL,
                    relationship_type TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (chunk_id) REFERENCES text_chunks (id),
                    FOREIGN KEY (entity_id) REFERENCES entities (id)
                )
            """)
            # Create indexes for better query performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mentions_entity ON entity_mentions(entity_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON text_chunks(embedding_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_citations_chunk ON citations(chunk_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_citations_entity ON citations(entity_id)")
            self.conn.commit()
            logger.info("Database tables initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    def insert_entity(self, name: str, type: str, description: str = None) -> int:
        """
        Insert a new entity into the database.
        Args:
            name (str): Name of the entity
            type (str): Type of the entity (character, location, etc.)
            description (str, optional): Description of the entity
        Returns:
            int: ID of the inserted entity
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO entities (name, type, description)
                VALUES (?, ?, ?)
            """, (name, type, description))
            self.conn.commit()
            # Get the entity ID
            cursor.execute("SELECT id FROM entities WHERE name = ?", (name,))
            result = cursor.fetchone()
            entity_id = result[0] if result else None
            logger.info(f"Inserted entity: {name} (ID: {entity_id})")
            return entity_id
        except Exception as e:
            logger.error(f"Failed to insert entity {name}: {e}")
            raise
    def insert_entity_mention(self, entity_id: int, source_file: str, chapter: str = None, 
                             paragraph: int = None, character_start: int = None, 
                             character_end: int = None, mention_text: str = None) -> int:
        """
        Insert a new entity mention into the database.
        Args:
            entity_id (int): ID of the entity
            source_file (str): Source file where entity was mentioned
            chapter (str, optional): Chapter/section name
            paragraph (int, optional): Paragraph number
            character_start (int, optional): Character start position
            character_end (int, optional): Character end position
            mention_text (str, optional): Text of the mention
        Returns:
            int: ID of the inserted mention
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO entity_mentions 
                (entity_id, source_file, chapter, paragraph, character_start, character_end, mention_text)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (entity_id, source_file, chapter, paragraph, character_start, character_end, mention_text))
            self.conn.commit()
            mention_id = cursor.lastrowid
            logger.info(f"Inserted entity mention for entity ID {entity_id}")
            return mention_id
        except Exception as e:
            logger.error(f"Failed to insert entity mention: {e}")
            raise
    def insert_text_chunk(self, chunk_text: str, source_file: str, chapter: str = None,
                         paragraph_start: int = None, paragraph_end: int = None,
                         character_start: int = None, character_end: int = None,
                         embedding_id: str = None) -> int:
        """
        Insert a new text chunk into the database.
        Args:
            chunk_text (str): Text content of the chunk
            source_file (str): Source file of the chunk
            chapter (str, optional): Chapter/section name
            paragraph_start (int, optional): Starting paragraph number
            paragraph_end (int, optional): Ending paragraph number
            character_start (int, optional): Character start position
            character_end (int, optional): Character end position
            embedding_id (str, optional): ID linking to vector store
        Returns:
            int: ID of the inserted chunk
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO text_chunks 
                (chunk_text, source_file, chapter, paragraph_start, paragraph_end, 
                 character_start, character_end, embedding_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (chunk_text, source_file, chapter, paragraph_start, paragraph_end,
                  character_start, character_end, embedding_id))
            self.conn.commit()
            chunk_id = cursor.lastrowid
            logger.info(f"Inserted text chunk from {source_file}")
            return chunk_id
        except Exception as e:
            logger.error(f"Failed to insert text chunk: {e}")
            raise
    def insert_citation(self, chunk_id: int, entity_id: int, relationship_type: str = None) -> int:
        """
        Insert a new citation linking a text chunk to an entity.
        Args:
            chunk_id (int): ID of the text chunk
            entity_id (int): ID of the entity
            relationship_type (str, optional): Type of relationship
        Returns:
            int: ID of the inserted citation
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO citations (chunk_id, entity_id, relationship_type)
                VALUES (?, ?, ?)
            """, (chunk_id, entity_id, relationship_type))
            self.conn.commit()
            # Get the citation ID
            cursor.execute("""
                SELECT id FROM citations 
                WHERE chunk_id = ? AND entity_id = ?
            """, (chunk_id, entity_id))
            result = cursor.fetchone()
            citation_id = result[0] if result else None
            logger.info(f"Inserted citation linking chunk {chunk_id} to entity {entity_id}")
            return citation_id
        except Exception as e:
            logger.error(f"Failed to insert citation: {e}")
            raise
    def get_entity_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve an entity by name.
        Args:
            name (str): Name of the entity
        Returns:
            dict: Entity data or None if not found
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM entities WHERE name = ?", (name,))
            row = cursor.fetchone()
            if row:
                columns = [description[0] for description in cursor.description]
                return dict(zip(columns, row))
            return None
        except Exception as e:
            logger.error(f"Failed to retrieve entity {name}: {e}")
            raise
    def close(self):
        """
        Close the database connection.
        """
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
if __name__ == "__main__":
    # Test the StructuredDB initialization
    import tempfile
    import shutil
    # Create a temporary directory for testing
    test_dir = tempfile.mkdtemp()
    try:
        db_path = os.path.join(test_dir, "test_entities.db")
        # Test initialization
        db = StructuredDB(db_path)
        print(f"✓ StructuredDB initialized at {db_path}")
        # Test inserting an entity
        entity_id = db.insert_entity("John Doe", "character", "Main protagonist")
        print(f"✓ Inserted entity with ID: {entity_id}")
        # Test inserting an entity mention
        mention_id = db.insert_entity_mention(
            entity_id, "chapter1.txt", "Chapter 1", 5, 120, 150, "John entered the room"
        )
        print(f"✓ Inserted mention with ID: {mention_id}")
        # Test inserting a text chunk
        chunk_id = db.insert_text_chunk(
            "John entered the room cautiously.", "chapter1.txt", "Chapter 1", 5, 5, 120, 155, "emb_123"
        )
        print(f"✓ Inserted chunk with ID: {chunk_id}")
        # Test inserting a citation
        citation_id = db.insert_citation(chunk_id, entity_id, "appearance")
        print(f"✓ Inserted citation with ID: {citation_id}")
        # Test retrieving an entity
        entity = db.get_entity_by_name("John Doe")
        print(f"✓ Retrieved entity: {entity}")
    finally:
        # Clean up
        db.close()
        shutil.rmtree(test_dir)