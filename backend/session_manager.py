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
        """Creates the chat_history table if it doesn't exist."""
        try:
            with self._get_conn() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS chat_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        message_id TEXT,
                        project_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
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
                conn.commit()
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

    def clear_history(self, project_id: str, user_id: str):
        """Clears chat history for a specific user/project context."""
        with self._get_conn() as conn:
            conn.execute(
                "DELETE FROM chat_history WHERE project_id = ? AND user_id = ?",
                (project_id, user_id)
            )
            conn.commit()
        logger.info(f"Cleared history for user {user_id} in project {project_id}")