"""
Persistent Retry Queue for Billing Account Creation

This module provides a resilient queue for billing account creation during user registration.
When the billing_server is down during registration, instead of failing the user's signup,
we store the pending billing account creation in a persistent SQLite queue and retry later.

This ensures users can register and log in immediately, even if billing is temporarily unavailable.

Design Pattern:
1. User registers → Auth account created immediately
2. Try to create billing account
3. If fails → Queue for retry (user can still log in)
4. Background worker retries with exponential backoff
5. Eventually consistent: billing account created when service recovers

This prevents the "zombie user" problem where users are registered in Firebase
but can't use the app because billing account creation failed.
"""

import logging
import sqlite3
from typing import Optional, Dict, List
from pathlib import Path
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class BillingQueueStatus(Enum):
    """Status of a pending billing account creation."""
    PENDING = "pending"  # Not yet attempted or failed and waiting for retry
    RETRYING = "retrying"  # Currently being processed
    COMPLETED = "completed"  # Successfully created
    FAILED_PERMANENT = "failed_permanent"  # Max retries exceeded, manual intervention needed


class PendingBillingQueue:
    """
    Persistent queue for billing account creation with exponential backoff retry.
    
    When billing_server is down during registration, we:
    1. Create the user account in auth_server (so they can log in)
    2. Queue the billing account creation here
    3. Retry with exponential backoff until success
    
    This prevents failed registrations due to transient billing_server issues.
    
    Workflow:
    - enqueue(user_id, tier): Add new pending billing account
    - process_pending_items(): Retry all pending items (call from background worker)
    - get_user_billing_status(user_id): Check if user has pending billing account
    
    Retry Strategy:
    - Attempt 1: Immediately (during registration)
    - Attempt 2: 30 seconds later
    - Attempt 3: 2 minutes later
    - Attempt 4: 8 minutes later
    - Attempt 5: 32 minutes later
    - After 5 attempts: Mark as FAILED_PERMANENT, require manual intervention
    """
    
    def __init__(self, db_path: str = "data/pending_billing.db"):
        """
        Initialize the pending billing queue.
        
        Args:
            db_path: Path to SQLite database for persistent queue
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _get_conn(self) -> sqlite3.Connection:
        """Get a new SQLite connection with row factory."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")  # Better concurrency
        return conn
    
    def _init_db(self):
        """Initialize the pending billing queue table."""
        try:
            with self._get_conn() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS pending_billing (
                        user_id TEXT PRIMARY KEY,
                        tier TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_attempt_at TIMESTAMP,
                        next_retry_at TIMESTAMP,
                        retry_count INTEGER DEFAULT 0,
                        max_retries INTEGER DEFAULT 5,
                        last_error TEXT,
                        completed_at TIMESTAMP
                    )
                """)
                
                # Index for efficient queries
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_status_next_retry 
                    ON pending_billing(status, next_retry_at)
                """)
                
                conn.commit()
            logger.info("PendingBillingQueue database initialized successfully")
        except Exception as e:
            logger.critical(f"Failed to initialize PendingBillingQueue database: {e}", exc_info=True)
            raise
    
    def enqueue(self, user_id: str, tier: str, initial_error: Optional[str] = None) -> bool:
        """
        Add a user to the pending billing account creation queue.
        
        This is called when billing_server is unavailable during registration.
        The user is already created in auth_server, so they can log in,
        but we need to create their billing account later.
        
        Args:
            user_id: Firebase UID of the user
            tier: Billing tier ('admin', 'guest', etc.)
            initial_error: Error message from the first failed attempt
            
        Returns:
            True if successfully queued, False on error
        """
        try:
            with self._get_conn() as conn:
                # Calculate next retry time (30 seconds from now for first retry)
                next_retry = datetime.now() + timedelta(seconds=30)
                
                conn.execute("""
                    INSERT INTO pending_billing 
                    (user_id, tier, status, last_attempt_at, next_retry_at, retry_count, last_error)
                    VALUES (?, ?, 'pending', CURRENT_TIMESTAMP, ?, 1, ?)
                """, (user_id, tier, next_retry, initial_error))
                
                conn.commit()
            
            logger.warning(
                f"[BILLING-QUEUE] User {user_id} billing account queued for retry. "
                f"User can log in, but billing account will be created in background."
            )
            return True
            
        except sqlite3.IntegrityError:
            logger.warning(f"[BILLING-QUEUE] User {user_id} already in queue")
            return False
        except Exception as e:
            logger.error(f"[BILLING-QUEUE] Failed to enqueue {user_id}: {e}", exc_info=True)
            return False
    
    def get_pending_items(self) -> List[Dict]:
        """
        Get all pending billing account creations that are ready for retry.
        
        Returns items where:
        - status = 'pending'
        - next_retry_at <= now
        - retry_count < max_retries
        
        Returns:
            List of dicts with user_id, tier, retry_count, last_error
        """
        try:
            with self._get_conn() as conn:
                cursor = conn.execute("""
                    SELECT user_id, tier, retry_count, last_error, max_retries
                    FROM pending_billing
                    WHERE status = 'pending'
                    AND (next_retry_at IS NULL OR next_retry_at <= CURRENT_TIMESTAMP)
                    AND retry_count < max_retries
                    ORDER BY next_retry_at ASC
                """)
                
                items = [dict(row) for row in cursor.fetchall()]
                logger.info(f"[BILLING-QUEUE] Found {len(items)} pending billing accounts ready for retry")
                return items
                
        except Exception as e:
            logger.error(f"[BILLING-QUEUE] Failed to get pending items: {e}", exc_info=True)
            return []
    
    def mark_retry_attempt(self, user_id: str, success: bool, error_message: Optional[str] = None):
        """
        Record a retry attempt result.
        
        If successful: Mark as completed
        If failed: Increment retry count and schedule next retry with exponential backoff
        
        Args:
            user_id: Firebase UID
            success: True if billing account created successfully
            error_message: Error message if failed
        """
        try:
            with self._get_conn() as conn:
                if success:
                    # Success: Mark as completed
                    conn.execute("""
                        UPDATE pending_billing
                        SET status = 'completed',
                            completed_at = CURRENT_TIMESTAMP,
                            last_attempt_at = CURRENT_TIMESTAMP
                        WHERE user_id = ?
                    """, (user_id,))
                    
                    logger.info(f"[BILLING-QUEUE] ✓ Billing account created for {user_id}")
                
                else:
                    # Failed: Increment retry count and schedule next retry
                    # Get current retry count
                    cursor = conn.execute("""
                        SELECT retry_count, max_retries
                        FROM pending_billing
                        WHERE user_id = ?
                    """, (user_id,))
                    
                    row = cursor.fetchone()
                    if not row:
                        logger.error(f"[BILLING-QUEUE] User {user_id} not found in queue")
                        return
                    
                    retry_count = row['retry_count']
                    max_retries = row['max_retries']
                    
                    if retry_count >= max_retries:
                        # Max retries exceeded: Mark as permanently failed
                        conn.execute("""
                            UPDATE pending_billing
                            SET status = 'failed_permanent',
                                last_attempt_at = CURRENT_TIMESTAMP,
                                last_error = ?
                            WHERE user_id = ?
                        """, (error_message, user_id))
                        
                        logger.error(
                            f"[BILLING-QUEUE] ✗ User {user_id} billing account creation FAILED PERMANENTLY "
                            f"after {retry_count} attempts. Manual intervention required."
                        )
                    
                    else:
                        # Schedule next retry with exponential backoff
                        # Backoff: 30s, 2m, 8m, 32m, 128m (2h 8m)
                        backoff_seconds = 30 * (2 ** retry_count)
                        next_retry = datetime.now() + timedelta(seconds=backoff_seconds)
                        
                        conn.execute("""
                            UPDATE pending_billing
                            SET retry_count = retry_count + 1,
                                last_attempt_at = CURRENT_TIMESTAMP,
                                next_retry_at = ?,
                                last_error = ?
                            WHERE user_id = ?
                        """, (next_retry, error_message, user_id))
                        
                        logger.warning(
                            f"[BILLING-QUEUE] Retry {retry_count + 1}/{max_retries} failed for {user_id}. "
                            f"Next retry in {backoff_seconds}s at {next_retry.strftime('%H:%M:%S')}"
                        )
                
                conn.commit()
                
        except Exception as e:
            logger.error(f"[BILLING-QUEUE] Failed to mark retry attempt for {user_id}: {e}", exc_info=True)
    
    def get_user_status(self, user_id: str) -> Optional[Dict]:
        """
        Get the billing queue status for a specific user.
        
        Useful for:
        - Checking if a user has a pending billing account
        - Displaying status to user ("Your account is being set up...")
        - Admin dashboard monitoring
        
        Args:
            user_id: Firebase UID
            
        Returns:
            Dict with status info, or None if not in queue
        """
        try:
            with self._get_conn() as conn:
                cursor = conn.execute("""
                    SELECT user_id, tier, status, created_at, retry_count, 
                           last_error, completed_at, next_retry_at
                    FROM pending_billing
                    WHERE user_id = ?
                """, (user_id,))
                
                row = cursor.fetchone()
                return dict(row) if row else None
                
        except Exception as e:
            logger.error(f"[BILLING-QUEUE] Failed to get status for {user_id}: {e}", exc_info=True)
            return None
    
    def get_all_pending_count(self) -> int:
        """Get count of all pending billing accounts (for monitoring)."""
        try:
            with self._get_conn() as conn:
                cursor = conn.execute("""
                    SELECT COUNT(*) as count
                    FROM pending_billing
                    WHERE status = 'pending'
                """)
                return cursor.fetchone()['count']
        except Exception as e:
            logger.error(f"[BILLING-QUEUE] Failed to get pending count: {e}", exc_info=True)
            return 0
    
    def get_failed_permanent_count(self) -> int:
        """Get count of permanently failed billing accounts (for alerts)."""
        try:
            with self._get_conn() as conn:
                cursor = conn.execute("""
                    SELECT COUNT(*) as count
                    FROM pending_billing
                    WHERE status = 'failed_permanent'
                """)
                return cursor.fetchone()['count']
        except Exception as e:
            logger.error(f"[BILLING-QUEUE] Failed to get failed count: {e}", exc_info=True)
            return 0
