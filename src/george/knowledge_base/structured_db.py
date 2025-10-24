"""
Structured database for entity storage and relationships
"""
import os
import uuid
import logging
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, Tuple, ContextManager

logger = logging.getLogger(__name__)

class TransactionContext:
    """Context manager for database transactions."""
    def __init__(self, db: "StructuredDB"):
        self.db = db
        self._nested = False

    def __enter__(self) -> "TransactionContext":
        if self.db.conn.in_transaction:
            self._nested = True
            logger.debug("Nested transaction started")
            return self
        
        self.db.conn.execute("BEGIN")
        logger.debug("Transaction started")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._nested:
            logger.debug("Nested transaction ended")
            return
        
        if exc_type is None:
            self.db.conn.commit()
            logger.debug("Transaction committed")
        else:
            self.db.conn.rollback()
            logger.error("Transaction rolled back due to exception", exc_info=True)

class StructuredDB:
    """
    Manages the SQLite database for structured entity storage and relationships.
    
    - Provides ACID transactions via context manager
    - Enforces data integrity with unique constraints
    - Optimized for batch operations
    - Supports entity notes and chat summaries
    """
    def __init__(self, db_path: Union[str, Path] = None):
        """
        Initialize the structured database.
        
        Args:
            db_path: Path to the SQLite database file
        """
        if db_path is None:
            db_path = Path.cwd() / "data" / "entities.db"
        else:
            db_path = Path(db_path)
        
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self.conn = None
        
        try:
            # Disable auto-commit for transaction control
            self.conn = sqlite3.connect(
                str(db_path),
                isolation_level=None  # We manage transactions manually
            )
            self.conn.row_factory = sqlite3.Row
            self.initialize_database()
            logger.info(f"StructuredDB initialized at {db_path}")
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize database at {db_path}: {e}", exc_info=True)
            raise

    def initialize_database(self) -> None:
        """Create database tables if they don't exist."""
        if not self.conn:
            raise ConnectionError("Database connection not established")
        
        try:
            cursor = self.conn.cursor()
            
            # Entities table with unique constraint
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    type TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Entity mentions table
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
                    FOREIGN KEY (entity_id) REFERENCES entities (id) ON DELETE CASCADE
                )
            """)
            
            # Text chunks table
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
                    embedding_id TEXT UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Citations table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS citations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chunk_id INTEGER NOT NULL,
                    entity_id INTEGER NOT NULL,
                    relationship_type TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (chunk_id) REFERENCES text_chunks (id) ON DELETE CASCADE,
                    FOREIGN KEY (entity_id) REFERENCES entities (id) ON DELETE CASCADE,
                    UNIQUE(chunk_id, entity_id)  -- Prevent duplicate citations
                )
            """)
            
            # Entity notes table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entity_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    note_text TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (entity_id) REFERENCES entities (id) ON DELETE CASCADE
                )
            """)
            
            # Chat summaries table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    original_question TEXT,
                    summary_text TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Indexes
            cursor.executescript("""
                CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
                CREATE INDEX IF NOT EXISTS idx_mentions_entity ON entity_mentions(entity_id);
                CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON text_chunks(embedding_id);
                CREATE INDEX IF NOT EXISTS idx_citations_chunk ON citations(chunk_id);
                CREATE INDEX IF NOT EXISTS idx_citations_entity ON citations(entity_id);
                CREATE INDEX IF NOT EXISTS idx_entity_notes_entity ON entity_notes(entity_id);
                CREATE INDEX IF NOT EXISTS idx_chat_summaries_user ON chat_summaries(user_id);
                CREATE INDEX IF NOT EXISTS idx_chat_summaries_project ON chat_summaries(project_id);
            """)
            
            self.conn.commit()
            logger.debug("Database tables initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database tables: {e}", exc_info=True)
            self.conn.rollback()
            raise

    def transaction(self) -> TransactionContext:
        """Create a transaction context manager."""
        return TransactionContext(self)

    def insert_entity(
        self,
        name: str,
        entity_type: str,
        description: Optional[str] = None
    ) -> int:
        """Insert a new entity or get existing entity ID."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO entities (name, type, description)
                VALUES (?, ?, ?)
            """, (name, entity_type, description))
            
            if cursor.rowcount > 0:
                return cursor.lastrowid
            
            # Entity already exists
            cursor.execute("SELECT id FROM entities WHERE name = ?", (name,))
            return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Failed to insert entity {name}: {e}", exc_info=True)
            raise

    def insert_entity_mention(
        self,
        entity_id: int,
        source_file: str,
        chapter: Optional[str] = None,
        paragraph: Optional[int] = None,
        character_start: Optional[int] = None,
        character_end: Optional[int] = None,
        mention_text: Optional[str] = None
    ) -> int:
        """Insert a new entity mention."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO entity_mentions 
                (entity_id, source_file, chapter, paragraph, 
                 character_start, character_end, mention_text)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (entity_id, source_file, chapter, paragraph, 
                  character_start, character_end, mention_text))
            return cursor.lastrowid
        except Exception as e:
            logger.error("Failed to insert entity mention: %s", e, exc_info=True)
            raise

    def insert_text_chunk(
        self,
        chunk_text: str,
        source_file: str,
        chapter: Optional[str] = None,
        paragraph_start: Optional[int] = None,
        paragraph_end: Optional[int] = None,
        character_start: Optional[int] = None,
        character_end: Optional[int] = None,
        embedding_id: Optional[str] = None
    ) -> int:
        """Insert a new text chunk."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO text_chunks 
                (chunk_text, source_file, chapter, paragraph_start, paragraph_end, 
                 character_start, character_end, embedding_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (chunk_text, source_file, chapter, paragraph_start, paragraph_end,
                  character_start, character_end, embedding_id))
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Failed to insert text chunk: {e}", exc_info=True)
            raise

    def insert_citation(
        self,
        chunk_id: int,
        entity_id: int,
        relationship_type: Optional[str] = None
    ) -> int:
        """Insert a citation between chunk and entity."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO citations (chunk_id, entity_id, relationship_type)
                VALUES (?, ?, ?)
            """, (chunk_id, entity_id, relationship_type))
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Failed to insert citation: {e}", exc_info=True)
            raise

    def get_entity_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get entity by name."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM entities WHERE name = ?", (name,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to retrieve entity {name}: {e}", exc_info=True)
            raise

    def add_entity_note(
        self,
        entity_id: int,
        user_id: str,
        note_text: str
    ) -> int:
        """Add a user note to an entity."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO entity_notes (entity_id, user_id, note_text)
                VALUES (?, ?, ?)
            """, (entity_id, user_id, note_text))
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Failed to add note to entity {entity_id}: {e}", exc_info=True)
            raise

    def get_entity_notes(self, entity_id: int) -> List[Dict[str, Any]]:
        """Get all notes for an entity."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM entity_notes 
                WHERE entity_id = ? 
                ORDER BY created_at DESC
            """, (entity_id,))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to retrieve notes for entity {entity_id}: {e}", exc_info=True)
            raise

    def get_chunks_for_entity(self, entity_id: int) -> List[Dict[str, Any]]:
        """Retrieves all text chunks associated with a specific entity."""
        if not self.conn: raise ConnectionError("Database not connected")
        try:
            cursor = self.conn.cursor()
            # Find all chunk_ids linked to this entity_id in the citations table,
            # then join with the text_chunks table to get the text.
            cursor.execute("""
                SELECT t.* FROM text_chunks t
                JOIN citations c ON t.id = c.chunk_id
                WHERE c.entity_id = ?
                ORDER BY t.character_start
            """, (entity_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to retrieve chunks for entity {entity_id}: {e}", exc_info=True)
            raise

    def add_chat_summary(
        self,
        user_id: str,
        project_id: str,
        original_question: Optional[str],
        summary_text: str
    ) -> int:
        """Add a chat summary."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO chat_summaries 
                (user_id, project_id, original_question, summary_text)
                VALUES (?, ?, ?, ?)
            """, (user_id, project_id, original_question, summary_text))
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Failed to save chat summary: {e}", exc_info=True)
            raise

    def search_chat_summaries(
        self,
        user_id: str,
        project_id: Optional[str] = None,
        search_term: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search chat summaries."""
        try:
            query = """
                SELECT * FROM chat_summaries 
                WHERE user_id = ?
            """
            params = [user_id]
            
            if project_id:
                query += " AND project_id = ?"
                params.append(project_id)
            
            if search_term:
                query += " AND (summary_text LIKE ? OR original_question LIKE ?)"
                params.extend([f"%{search_term}%", f"%{search_term}%"])
            
            query += " ORDER BY created_at DESC"
            
            cursor = self.conn.cursor()
            cursor.execute(query, tuple(params))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to search chat summaries: {e}", exc_info=True)
            raise

    def get_entity_id_by_name(self, name: str) -> Optional[int]:
        """Helper function to get just the ID for a given entity name."""
        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT id FROM entities WHERE name = ?", (name,))
                row = cursor.fetchone()
                if row:
                    return row['id']
                return None
        except Exception as e:
            logger.error(f"Entity ID lookup failed for {name}: {e}", exc_info=True)
            raise

    def find_shared_chunks_by_entity_names(self, entity_names: List[str]) -> List[Dict[str, Any]]:
        """
        Finds all text chunks where all specified entities are mentioned together.
        
        Args:
            entity_names: A list of character names (e.g., ["Hugh", "Linda"])
        
        Returns:
            A list of text chunk records (dictionaries) that contain all specified entities.
        """
        if not entity_names or len(entity_names) < 2:
            raise ValueError("At least two entity names are required to find shared chunks.")
        
        logger.info(f"Finding shared chunks for entities: {entity_names}")
        
        try:
            # 1. Get the entity IDs for all names
            entity_ids = []
            with self.conn:
                for name in entity_names:
                    entity_id = self.get_entity_id_by_name(name)
                    if entity_id is None:
                        logger.warning(f"Entity '{name}' not found in database. Cannot complete relationship web.")
                        raise ValueError(f"Entity '{name}' not found.")
                    entity_ids.append(entity_id)

            # 2. Build the SQL query to find shared chunks
            # This query finds chunk_ids that are associated with ALL of the given entity_ids
            placeholder_list = ', '.join('?' for _ in entity_ids)
            sql_query = f"""
                SELECT
                    t.*
                FROM text_chunks t
                JOIN citations c ON t.id = c.chunk_id
                WHERE c.entity_id IN ({placeholder_list})
                GROUP BY
                    t.id
                HAVING
                    COUNT(DISTINCT c.entity_id) = ?
                ORDER BY
                    t.character_start;
            """
            
            params = tuple(entity_ids + [len(entity_ids)])
            
            # 3. Execute the query
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute(sql_query, params)
                rows = cursor.fetchall()
                # Use dict(row) to convert from sqlite3.Row
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Failed to find shared chunks: {e}", exc_info=True)
            raise
    def close(self) -> None:
        """Close the database connection."""
        if self.conn:
            try:
                self.conn.close()
                self.conn = None
                logger.info("StructuredDB connection closed")
            except Exception as e:
                logger.error(f"Error closing database connection: {e}", exc_info=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()