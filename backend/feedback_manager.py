"""
Feedback Management System
Handles storage and retrieval of user feedback for chat messages.
"""

import sqlite3
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any


class FeedbackManager:
    """Manages user feedback for chat messages in a SQLite database."""

    def __init__(self, db_path: str = "data/feedback.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Helper to get a new SQLite connection."""
        return sqlite3.connect(str(self.db_path))

    def _init_db(self):
        """Creates the feedback table if it doesn't exist."""
        try:
            with self._get_conn() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS feedback (
                        feedback_id TEXT PRIMARY KEY,
                        message_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        rating INTEGER NOT NULL,
                        category TEXT,
                        comment TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                # Index for faster lookups
                conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_message_id ON feedback (message_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_user_id ON feedback (user_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_timestamp ON feedback (timestamp)")
                conn.commit()
        except Exception as e:
            raise Exception(f"Failed to initialize FeedbackManager database: {e}")

    def save_feedback(
        self,
        feedback_id: str,
        message_id: str,
        user_id: str,
        rating: int,
        category: Optional[str] = None,
        comment: Optional[str] = None
    ) -> bool:
        """
        Save feedback to the database.

        Args:
            feedback_id: Unique feedback identifier
            message_id: The ID of the message being rated
            user_id: The user submitting feedback
            rating: The rating value (e.g., 1 for good, -1 for bad)
            category: Optional category tag (e.g., "hallucination")
            comment: Optional free-text comment

        Returns:
            bool: True if saved successfully, False otherwise
        """
        try:
            with self._get_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO feedback (feedback_id, message_id, user_id, rating, category, comment)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (feedback_id, message_id, user_id, rating, category, comment)
                )
                conn.commit()
            return True
        except Exception as e:
            raise Exception(f"Failed to save feedback: {e}")

    def get_feedback_for_message(self, message_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve all feedback for a specific message.

        Args:
            message_id: The message ID to retrieve feedback for

        Returns:
            List of feedback records as dictionaries
        """
        try:
            with self._get_conn() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM feedback WHERE message_id = ? ORDER BY timestamp DESC",
                    (message_id,)
                )
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            raise Exception(f"Failed to retrieve feedback: {e}")

    def get_feedback_for_user(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve all feedback submitted by a specific user.

        Args:
            user_id: The user ID to retrieve feedback for

        Returns:
            List of feedback records as dictionaries
        """
        try:
            with self._get_conn() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM feedback WHERE user_id = ? ORDER BY timestamp DESC",
                    (user_id,)
                )
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            raise Exception(f"Failed to retrieve user feedback: {e}")

    def get_feedback_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all feedback (for admin/analytics).

        Returns:
            Dictionary with summary statistics
        """
        try:
            with self._get_conn() as conn:
                # Total feedback count
                total_count = conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]

                # Average rating
                avg_rating = conn.execute("SELECT AVG(rating) FROM feedback").fetchone()[0]

                # Feedback by category
                category_stats = conn.execute(
                    "SELECT category, COUNT(*) as count FROM feedback GROUP BY category"
                ).fetchall()

                # Recent feedback (last 24 hours)
                recent_count = conn.execute(
                    "SELECT COUNT(*) FROM feedback WHERE timestamp > datetime('now', '-1 day')"
                ).fetchone()[0]

                return {
                    "total_feedback": total_count,
                    "average_rating": avg_rating or 0.0,
                    "category_breakdown": dict(category_stats or []),
                    "recent_24h": recent_count
                }
        except Exception as e:
            raise Exception(f"Failed to get feedback summary: {e}")
