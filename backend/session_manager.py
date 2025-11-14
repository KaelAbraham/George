import sqlite3
import json
import logging
import uuid
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)

class SessionManager:
    """
    Manages the short-term conversational memory for George.
    Stores linear chat logs in a lightweight SQLite database.
    """

    def __init__(self, db_path: str = "data/sessions.db"):
        """
        Initialize the session manager.
        
        Args:
            db_path (str): Path to the SQLite database file. 
                           Defaults to 'data/sessions.db' in the root.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        logger.info(f"SessionManager initialized. DB at {self.db_path}")

    def _get_conn(self) -> sqlite3.Connection:
        """Helper to get a new SQLite connection with row factory."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row  # Access columns by name
        return conn

    def _init_db(self):
        """Creates the chat_history, ingestion_queue, and bookmarks tables if they don't exist."""
        try:
            with self._get_conn() as conn:
                # 1. Main chat history table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS chat_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        message_id TEXT,
                        project_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        is_bookmarked INTEGER DEFAULT 0,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                # Create an index for fast retrieval by project/user
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_chat_history_lookup 
                    ON chat_history (project_id, user_id, timestamp DESC)
                """)
                # Index for message_id lookups
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_message_id 
                    ON chat_history (message_id)
                """)
                # Index for bookmarked messages
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_bookmarked 
                    ON chat_history (project_id, is_bookmarked, timestamp DESC)
                """)
                
                # 2. Ingestion queue table (for background worker)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS ingestion_queue (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        message_id TEXT NOT NULL UNIQUE,
                        project_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        status TEXT DEFAULT 'pending',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        processed_at DATETIME,
                        error_message TEXT
                    )
                """)
                # Index for fast queue processing
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_queue_pending 
                    ON ingestion_queue (status, created_at ASC)
                """)
                # Index for message lookups
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_queue_message 
                    ON ingestion_queue (message_id)
                """)
                
                conn.commit()
                logger.info("Database tables initialized: chat_history, ingestion_queue")
        except Exception as e:
            logger.critical(f"Failed to initialize SessionManager database: {e}", exc_info=True)
            raise

    def add_turn(self, project_id: str, user_id: str, user_message: str, george_response: str) -> str:
        """
        Saves a complete conversation turn (User Query + George Response).
        
        Args:
            project_id (str): The ID of the project being discussed.
            user_id (str): The ID of the user chatting.
            user_message (str): The text the user typed.
            george_response (str): The final text George replied with.
            
        Returns:
            str: The unique message_id for the AI response (used for feedback tracking)
        """
        try:
            # Generate a unique ID for the AI response message
            message_id = f"msg_{uuid.uuid4()}"
            
            with self._get_conn() as conn:
                # 1. Insert User Message (no message_id for user messages)
                conn.execute(
                    "INSERT INTO chat_history (project_id, user_id, role, content) VALUES (?, ?, ?, ?)",
                    (project_id, user_id, "user", user_message)
                )
                # 2. Insert George's Response with message_id
                conn.execute(
                    "INSERT INTO chat_history (message_id, project_id, user_id, role, content) VALUES (?, ?, ?, ?, ?)",
                    (message_id, project_id, user_id, "model", george_response)
                )
                conn.commit()
            logger.debug(f"Saved chat turn for user {user_id} in project {project_id} with message_id {message_id}")
            return message_id
        except Exception as e:
            logger.error(f"Failed to save chat turn: {e}", exc_info=True)
            raise

    def get_recent_history(self, project_id: str, user_id: str, limit: int = 6) -> List[Dict[str, str]]:
        """
        Retrieves the most recent messages for a project/user, formatted for the LLM.
        
        Args:
            project_id (str): The project context.
            user_id (str): The user context.
            limit (int): Number of individual messages to retrieve. 
                         Default 6 (3 user queries + 3 model responses).

        Returns:
            List[Dict]: A list of message dictionaries in the format:
                        [{"role": "user", "parts": [{"text": "..."}]}, ...]
                        The list is returned in CHRONOLOGICAL order (oldest -> newest).
        """
        try:
            with self._get_conn() as conn:
                # Fetch in reverse chronological order (newest first) to apply the limit
                cursor = conn.execute("""
                    SELECT role, content 
                    FROM chat_history 
                    WHERE project_id = ? AND user_id = ?
                    ORDER BY timestamp DESC 
                    LIMIT ?
                """, (project_id, user_id, limit))
                rows = cursor.fetchall()

            # Convert rows to Gemini-compatible format
            # Gemini expects "user" or "model" roles. Our DB stores "user" and "model" (or "assistant").
            history = []
            for row in rows:
                role = "user" if row["role"] == "user" else "model"
                history.append({
                    "role": role,
                    "parts": [{"text": row["content"]}]
                })

            # Reverse the list so it is chronological (Oldest -> Newest)
            return history[::-1]

        except Exception as e:
            logger.error(f"Failed to retrieve chat history: {e}", exc_info=True)
            return []

    def format_history_for_prompt(self, history: List[Dict[str, Any]]) -> str:
        """
        Helper to turn the history list into a readable string for the text prompt.
        Used for the "Georgeification" step or Context Rewriting step.
        """
        if not history:
            return ""
        
        formatted_lines = []
        for turn in history:
            role_label = "User" if turn['role'] == 'user' else "George"
            text = turn['parts'][0]['text']
            formatted_lines.append(f"{role_label}: {text}")
        
        return "\n".join(formatted_lines)

    def get_turn_by_id(self, message_id: str, user_id: str) -> Optional[Dict]:
        """
        Retrieves a single chat turn (query, response, project_id) by its unique message_id,
        ensuring the user has permission to access it.
        
        Args:
            message_id (str): The unique ID of the AI response message
            user_id (str): The user ID for security verification
            
        Returns:
            Optional[Dict]: Dictionary with keys 'project_id', 'user_query', 'ai_response'
                           or None if not found or user lacks permission
        """
        try:
            with self._get_conn() as conn:
                # Find the AI response message with this message_id
                cur = conn.execute(
                    """
                    SELECT id, project_id, user_id 
                    FROM chat_history 
                    WHERE message_id = ? AND user_id = ? AND role = 'model'
                    """,
                    (message_id, user_id)
                )
                response_row = cur.fetchone()
                
                if not response_row:
                    logger.warning(f"Message {message_id} not found for user {user_id}")
                    return None
                
                response_id = response_row[0]
                project_id = response_row[1]
                
                # Get the AI response content
                ai_response_content = response_row[2]
                
                # Find the preceding user message (the one right before this response)
                cur = conn.execute(
                    """
                    SELECT content 
                    FROM chat_history 
                    WHERE id < ? AND project_id = ? AND user_id = ? AND role = 'user'
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (response_id, project_id, user_id)
                )
                user_row = cur.fetchone()
                user_query_content = user_row[0] if user_row else ""
                
                # Fetch the actual response content again (fixing the logic above)
                cur = conn.execute(
                    "SELECT content FROM chat_history WHERE message_id = ? AND role = 'model'",
                    (message_id,)
                )
                ai_response_row = cur.fetchone()
                ai_response_content = ai_response_row[0] if ai_response_row else ""
                
                return {
                    "project_id": project_id,
                    "user_query": user_query_content,
                    "ai_response": ai_response_content
                }
        except Exception as e:
            logger.error(f"Failed to retrieve turn by message_id {message_id}: {e}", exc_info=True)
            return None

    def clear_history(self, project_id: str, user_id: str):
        """Clears chat history for a specific user/project context."""
        with self._get_conn() as conn:
            conn.execute(
                "DELETE FROM chat_history WHERE project_id = ? AND user_id = ?",
                (project_id, user_id)
            )
            conn.commit()
        logger.info(f"Cleared history for user {user_id} in project {project_id}")

    def add_to_ingestion_queue(self, message_id: str, project_id: str, user_id: str) -> bool:
        """
        Adds a message_id to the ingestion queue for background processing.
        The Ingestion Worker will pick this up and perform the File->Vector->Graph workflow.
        
        Args:
            message_id (str): The unique message ID to ingest
            project_id (str): The project context
            user_id (str): The user who sent the message
            
        Returns:
            bool: True if successfully queued, False if already in queue
        """
        try:
            with self._get_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO ingestion_queue (message_id, project_id, user_id, status)
                    VALUES (?, ?, ?, 'pending')
                    """,
                    (message_id, project_id, user_id)
                )
                conn.commit()
            logger.info(f"Added message {message_id} to ingestion queue")
            return True
        except sqlite3.IntegrityError:
            logger.warning(f"Message {message_id} already in ingestion queue (skipping duplicate)")
            return False
        except Exception as e:
            logger.error(f"Failed to add message {message_id} to ingestion queue: {e}", exc_info=True)
            return False

    def get_pending_ingestions(self, limit: int = 10) -> List[Dict]:
        """
        Retrieves pending messages from the ingestion queue for the background worker.
        
        Args:
            limit (int): Maximum number of messages to retrieve
            
        Returns:
            List[Dict]: List of pending ingestion records with keys:
                       message_id, project_id, user_id, id (queue record id)
        """
        try:
            with self._get_conn() as conn:
                cursor = conn.execute(
                    """
                    SELECT id, message_id, project_id, user_id
                    FROM ingestion_queue
                    WHERE status = 'pending'
                    ORDER BY created_at ASC
                    LIMIT ?
                    """,
                    (limit,)
                )
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to retrieve pending ingestions: {e}", exc_info=True)
            return []

    def mark_ingestion_complete(self, queue_id: int, status: str = 'complete', error_msg: str = None) -> bool:
        """
        Marks an ingestion queue record as processed.
        
        Args:
            queue_id (int): The ID of the queue record
            status (str): 'complete' or 'failed'
            error_msg (str): Error message if failed
            
        Returns:
            bool: True if updated successfully
        """
        try:
            with self._get_conn() as conn:
                conn.execute(
                    """
                    UPDATE ingestion_queue
                    SET status = ?, processed_at = CURRENT_TIMESTAMP, error_message = ?
                    WHERE id = ?
                    """,
                    (status, error_msg, queue_id)
                )
                conn.commit()
            logger.info(f"Marked ingestion queue record {queue_id} as {status}")
            return True
        except Exception as e:
            logger.error(f"Failed to update ingestion queue: {e}", exc_info=True)
            return False

    def toggle_bookmark(self, message_id: str, user_id: str, is_bookmarked: bool) -> bool:
        """
        Toggles the bookmark status for a chat message.
        
        Args:
            message_id (str): The unique message ID to bookmark
            user_id (str): The user ID (for security verification)
            is_bookmarked (bool): True to bookmark, False to unbookmark
            
        Returns:
            bool: True if successful, False if message not found
        """
        try:
            with self._get_conn() as conn:
                # Verify message belongs to user
                cur = conn.execute(
                    """
                    SELECT id FROM chat_history
                    WHERE message_id = ? AND user_id = ? AND role = 'model'
                    """,
                    (message_id, user_id)
                )
                if not cur.fetchone():
                    logger.warning(f"Cannot bookmark message {message_id}: not found or user mismatch")
                    return False
                
                # Update bookmark flag
                conn.execute(
                    """
                    UPDATE chat_history
                    SET is_bookmarked = ?
                    WHERE message_id = ? AND user_id = ?
                    """,
                    (1 if is_bookmarked else 0, message_id, user_id)
                )
                conn.commit()
            logger.info(f"Toggled bookmark for message {message_id}: is_bookmarked={is_bookmarked}")
            return True
        except Exception as e:
            logger.error(f"Failed to toggle bookmark for message {message_id}: {e}", exc_info=True)
            return False

    def get_bookmarks_for_project(self, project_id: str, user_id: str, limit: int = 50) -> List[Dict]:
        """
        Retrieves all bookmarked chat messages for a project (for the Notes section).
        
        Args:
            project_id (str): The project ID
            user_id (str): The user ID (for permission check)
            limit (int): Maximum number of bookmarks to retrieve
            
        Returns:
            List[Dict]: List of bookmarked messages with their context
        """
        try:
            with self._get_conn() as conn:
                cursor = conn.execute(
                    """
                    SELECT 
                        ch_response.message_id,
                        ch_response.content as ai_response,
                        ch_user.content as user_query,
                        ch_response.timestamp,
                        ch_response.id
                    FROM chat_history ch_response
                    LEFT JOIN chat_history ch_user ON 
                        ch_user.id = (
                            SELECT MAX(id) FROM chat_history
                            WHERE id < ch_response.id 
                            AND project_id = ? 
                            AND user_id = ? 
                            AND role = 'user'
                        )
                    WHERE ch_response.project_id = ? 
                    AND ch_response.user_id = ? 
                    AND ch_response.role = 'model'
                    AND ch_response.is_bookmarked = 1
                    ORDER BY ch_response.timestamp DESC
                    LIMIT ?
                    """,
                    (project_id, user_id, project_id, user_id, limit)
                )
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to retrieve bookmarks for project {project_id}: {e}", exc_info=True)
            return []