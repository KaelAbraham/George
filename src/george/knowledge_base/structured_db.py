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
            # Default path, e.g., in a user-specific app data directory
            # For now, let's keep it in the data folder
            data_dir = os.path.join(os.getcwd(), "data") # Adjust as needed
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "entities.db")
        
        # Ensure the directory for the DB exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        self.db_path = db_path
        self.conn = None
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row # Access results by column name
            self.initialize_database()
            logger.info(f"StructuredDB initialized at {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize database at {self.db_path}: {e}", exc_info=True)
            raise

    def initialize_database(self):
        """
        Create the database tables if they don't exist.
        """
        if not self.conn:
            logger.error("Database connection not established.")
            return

        try:
            cursor = self.conn.cursor()
            
            # --- Entities Table (No changes) ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    type TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # --- Entity Mentions Table (No changes) ---
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
            
            # --- Text Chunks Table (No changes) ---
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
            
            # --- Citations Table (No changes) ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS citations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chunk_id INTEGER NOT NULL,
                    entity_id INTEGER NOT NULL,
                    relationship_type TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (chunk_id) REFERENCES text_chunks (id) ON DELETE CASCADE,
                    FOREIGN KEY (entity_id) REFERENCES entities (id) ON DELETE CASCADE
                )
            """)

            # --- NEW: Entity Notes Table ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entity_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL, -- The Firebase Auth UID
                    note_text TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (entity_id) REFERENCES entities (id) ON DELETE CASCADE
                )
            """)

            # --- NEW: Chat Summaries Table ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL, -- The Firebase Auth UID
                    project_id TEXT NOT NULL, -- The project this chat was in
                    original_question TEXT,
                    summary_text TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # --- Indexes (Added new ones) ---
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mentions_entity ON entity_mentions(entity_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON text_chunks(embedding_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_citations_chunk ON citations(chunk_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_citations_entity ON citations(entity_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_entity_notes_entity ON entity_notes(entity_id)") # NEW
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_summaries_user ON chat_summaries(user_id)") # NEW
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_summaries_project ON chat_summaries(project_id)") # NEW

            self.conn.commit()
            logger.info("Database tables, including entity_notes and chat_summaries, initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database tables: {e}", exc_info=True)
            if self.conn:
                self.conn.rollback() # Rollback changes on error
            raise

    # --- (insert_entity, insert_entity_mention, insert_text_chunk, insert_citation, get_entity_by_name remain the same) ---
    
    def insert_entity(self, name: str, entity_type: str, description: str = None) -> int:
        if not self.conn: raise ConnectionError("Database not connected")
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO entities (name, type, description)
                VALUES (?, ?, ?)
            """, (name, entity_type, description))
            self.conn.commit()
            if cursor.lastrowid > 0:
                logger.info(f"Inserted entity: {name} (ID: {cursor.lastrowid})")
                return cursor.lastrowid
            # If IGNORE was triggered, fetch existing ID
            cursor.execute("SELECT id FROM entities WHERE name = ?", (name,))
            result = cursor.fetchone()
            entity_id = result[0] if result else None
            if entity_id:
                 logger.warning(f"Entity '{name}' already exists with ID: {entity_id}.")
                 # Optionally update description/type if needed
                 # cursor.execute("UPDATE entities SET type = ?, description = ? WHERE id = ?", (entity_type, description, entity_id))
                 # self.conn.commit()
            return entity_id
        except Exception as e:
            logger.error(f"Failed to insert entity {name}: {e}", exc_info=True)
            self.conn.rollback()
            raise

    def insert_entity_mention(self, entity_id: int, source_file: str, chapter: str = None, 
                             paragraph: int = None, character_start: int = None, 
                             character_end: int = None, mention_text: str = None) -> int:
        if not self.conn: raise ConnectionError("Database not connected")
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO entity_mentions 
                (entity_id, source_file, chapter, paragraph, character_start, character_end, mention_text)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (entity_id, source_file, chapter, paragraph, character_start, character_end, mention_text))
            self.conn.commit()
            mention_id = cursor.lastrowid
            logger.debug(f"Inserted entity mention for entity ID {entity_id}")
            return mention_id
        except Exception as e:
            logger.error(f"Failed to insert entity mention: {e}", exc_info=True)
            self.conn.rollback()
            raise

    def insert_text_chunk(self, chunk_text: str, source_file: str, chapter: str = None,
                         paragraph_start: int = None, paragraph_end: int = None,
                         character_start: int = None, character_end: int = None,
                         embedding_id: str = None) -> int:
        if not self.conn: raise ConnectionError("Database not connected")
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
            logger.debug(f"Inserted text chunk from {source_file}")
            return chunk_id
        except Exception as e:
            logger.error(f"Failed to insert text chunk: {e}", exc_info=True)
            self.conn.rollback()
            raise

    def insert_citation(self, chunk_id: int, entity_id: int, relationship_type: str = None) -> int:
        if not self.conn: raise ConnectionError("Database not connected")
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO citations (chunk_id, entity_id, relationship_type)
                VALUES (?, ?, ?)
            """, (chunk_id, entity_id, relationship_type))
            self.conn.commit()
            citation_id = cursor.lastrowid # Note: will be 0 if IGNORE triggered
            logger.debug(f"Inserted citation linking chunk {chunk_id} to entity {entity_id}")
            return citation_id
        except Exception as e:
            logger.error(f"Failed to insert citation: {e}", exc_info=True)
            self.conn.rollback()
            raise

    def get_entity_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        if not self.conn: raise ConnectionError("Database not connected")
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM entities WHERE name = ?", (name,))
            row = cursor.fetchone()
            if row:
                # Convert sqlite3.Row object to a standard dict
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"Failed to retrieve entity {name}: {e}", exc_info=True)
            raise

    # --- NEW: Functions for Notes and Summaries ---
    
    def add_entity_note(self, entity_id: int, user_id: str, note_text: str) -> int:
        """Adds a user-authored note to a specific entity."""
        if not self.conn: raise ConnectionError("Database not connected")
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO entity_notes (entity_id, user_id, note_text)
                VALUES (?, ?, ?)
            """, (entity_id, user_id, note_text))
            self.conn.commit()
            note_id = cursor.lastrowid
            logger.info(f"Added note (ID: {note_id}) to entity {entity_id} by user {user_id}")
            return note_id
        except Exception as e:
            logger.error(f"Failed to add note to entity {entity_id}: {e}", exc_info=True)
            self.conn.rollback()
            raise

    def get_entity_notes(self, entity_id: int) -> List[Dict[str, Any]]:
        """Retrieves all notes for a specific entity."""
        if not self.conn: raise ConnectionError("Database not connected")
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM entity_notes WHERE entity_id = ? ORDER BY created_at DESC", (entity_id,))
            rows = cursor.fetchall()
            # Convert list of sqlite3.Row objects to list of dicts
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to retrieve notes for entity {entity_id}: {e}", exc_info=True)
            raise

    def add_chat_summary(self, user_id: str, project_id: str, original_question: str, summary_text: str) -> int:
        """Saves a chat summary to the database."""
        if not self.conn: raise ConnectionError("Database not connected")
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO chat_summaries (user_id, project_id, original_question, summary_text)
                VALUES (?, ?, ?, ?)
            """, (user_id, project_id, original_question, summary_text))
            self.conn.commit()
            summary_id = cursor.lastrowid
            logger.info(f"Saved chat summary (ID: {summary_id}) for user {user_id}")
            return summary_id
        except Exception as e:
            logger.error(f"Failed to save chat summary for user {user_id}: {e}", exc_info=True)
            self.conn.rollback()
            raise

    def search_chat_summaries(self, user_id: str, project_id: str = None, search_term: str = None) -> List[Dict[str, Any]]:
        """Searches chat summaries for a user, optionally by project and search term."""
        if not self.conn: raise ConnectionError("Database not connected")
        try:
            cursor = self.conn.cursor()
            query = "SELECT * FROM chat_summaries WHERE user_id = ?"
            params = [user_id]
            
            if project_id:
                query += " AND project_id = ?"
                params.append(project_id)
            
            if search_term:
                # Basic full-text search on summary and question
                query += " AND (summary_text LIKE ? OR original_question LIKE ?)"
                params.extend([f"%{search_term}%", f"%{search_term}%"])
                
            query += " ORDER BY created_at DESC"
            
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to search chat summaries for user {user_id}: {e}", exc_info=True)
            raise

    def close(self):
        """
        Close the database connection.
        """
        if self.conn:
            try:
                self.conn.close()
                self.conn = None
                logger.info("Database connection closed")
            except Exception as e:
                logger.error(f"Error closing database connection: {e}", exc_info=True)

    def __del__(self):
        # Ensure connection is closed when object is destroyed
        self.close()

if __name__ == "__main__":
    # Test the updated StructuredDB initialization
    import tempfile
    import shutil
    test_dir = tempfile.mkdtemp()
    try:
        db_path = os.path.join(test_dir, "test_entities_v2.db")
        db = StructuredDB(db_path)
        print(f"✓ StructuredDB initialized at {db_path}")
        
        # Test inserting an entity
        entity_id = db.insert_entity("John Doe", "character", "Main protagonist")
        print(f"✓ Inserted entity with ID: {entity_id}")
        
        # --- Test New Features ---
        print("\nTesting new features...")
        # Test adding a note
        note_id = db.add_entity_note(entity_id, "user_123", "This is a test note.")
        print(f"✓ Added entity note with ID: {note_id}")
        
        # Test retrieving notes
        notes = db.get_entity_notes(entity_id)
        print(f"✓ Retrieved {len(notes)} note(s):")
        for note in notes:
            print(f"  - {note['note_text']} (by {note['user_id']})")
        assert len(notes) == 1
        assert notes[0]['note_text'] == "This is a test note."

        # Test adding a summary
        summary_id = db.add_chat_summary("user_123", "project_abc", "What's the deal with John?", "John is the main character.")
        print(f"✓ Added chat summary with ID: {summary_id}")

        # Test searching summaries
        summaries = db.search_chat_summaries("user_123", project_id="project_abc")
        print(f"✓ Retrieved {len(summaries)} summary(s) for project:")
        assert len(summaries) == 1
        assert summaries[0]['summary_text'] == "John is the main character."
        
        summaries_search = db.search_chat_summaries("user_123", search_term="main character")
        print(f"✓ Retrieved {len(summaries_search)} summary(s) via search:")
        assert len(summaries_search) == 1
        
        print("\n✓ All database tests passed!")

    except Exception as e:
        print(f"\n❌ Test failed: {e}", exc_info=True)
    finally:
        # Clean up
        if 'db' in locals() and db.conn:
            db.close()
        shutil.rmtree(test_dir)
        print(f"✓ Cleaned up test directory: {test_dir}")