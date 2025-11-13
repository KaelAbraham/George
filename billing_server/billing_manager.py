import sqlite3
import uuid
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict

logger = logging.getLogger(__name__)

class BillingManager:
    """
    Manages user accounts, API usage pools, and transaction ledgers.
    This is the 'Bank' of the Caudex Pro platform.
    """

    def __init__(self, db_path: str = "data/billing.db"):
        """
        Initialize the Billing Manager.
        
        Args:
            db_path (str): Path to the SQLite database.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        logger.info(f"BillingManager initialized. DB at {self.db_path}")

    def _get_conn(self) -> sqlite3.Connection:
        """Helper to get a new SQLite connection with row factory."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Creates the accounts and ledger tables if they don't exist."""
        try:
            with self._get_conn() as conn:
                # 1. Accounts Table: Stores current state
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS accounts (
                        user_id TEXT PRIMARY KEY,
                        tier TEXT NOT NULL DEFAULT 'guest',
                        balance REAL NOT NULL DEFAULT 0.0,
                        stripe_customer_id TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 2. Ledger Table: Stores every single transaction (history)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS ledger (
                        transaction_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        amount REAL NOT NULL,  -- Negative for spend, Positive for top-up
                        description TEXT,
                        job_id TEXT,           -- Optional link to a JobManager job
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(user_id) REFERENCES accounts(user_id)
                    )
                """)
                
                # Index for faster history lookups
                conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_user ON ledger (user_id, timestamp DESC)")
                conn.commit()
        except Exception as e:
            logger.critical(f"Failed to initialize Billing database: {e}", exc_info=True)
            raise

    def create_account(self, user_id: str, tier: str = 'guest', initial_balance: float = 0.0) -> bool:
        """
        Creates a new billing account for a user.
        
        Returns:
            bool: True if created, False if already exists.
        """
        try:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT INTO accounts (user_id, tier, balance) VALUES (?, ?, ?)",
                    (user_id, tier, initial_balance)
                )
                # Log the initial grant if there is one
                if initial_balance > 0:
                    self._log_transaction(conn, user_id, initial_balance, "Initial Account Grant")
                
                conn.commit()
            logger.info(f"Created billing account for {user_id} (Tier: {tier})")
            return True
        except sqlite3.IntegrityError:
            logger.warning(f"Billing account for {user_id} already exists.")
            return False
        except Exception as e:
            logger.error(f"Error creating account: {e}", exc_info=True)
            raise

    def get_account(self, user_id: str) -> Optional[Dict]:
        """Retrieves the current account status."""
        try:
            with self._get_conn() as conn:
                cursor = conn.execute("SELECT * FROM accounts WHERE user_id = ?", (user_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error fetching account for {user_id}: {e}")
            return None

    def deduct_funds(self, user_id: str, cost: float, description: str, job_id: str = None) -> bool:
        """
        Attempt to subtract funds for usage.
        
        Args:
            user_id: The user spending money.
            cost: The POSITIVE amount to subtract (e.g., 0.004).
            description: What they bought (e.g. "Chat: Analysis").
            job_id: Optional ID for the async job.

        Returns:
            bool: True if successful, False if insufficient funds.
        """
        if cost < 0:
            raise ValueError("Cost must be a positive number.")

        try:
            with self._get_conn() as conn:
                # 1. Check Balance
                cursor = conn.execute("SELECT balance FROM accounts WHERE user_id = ?", (user_id,))
                row = cursor.fetchone()
                
                if not row:
                    logger.error(f"User {user_id} not found during deduction.")
                    return False
                
                current_balance = row['balance']
                
                # Strict check: Balance cannot go negative
                if current_balance < cost:
                    logger.info(f"Insufficient funds for {user_id}: Has ${current_balance:.4f}, needs ${cost:.4f}")
                    return False

                # 2. Update Account Balance
                new_balance = current_balance - cost
                conn.execute(
                    "UPDATE accounts SET balance = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?", 
                    (new_balance, user_id)
                )
                
                # 3. Write to Ledger (Negative Amount)
                self._log_transaction(conn, user_id, -cost, description, job_id)
                
                conn.commit()
                logger.debug(f"Deducted ${cost:.4f} from {user_id}. New Balance: ${new_balance:.4f}")
                return True
                
        except Exception as e:
            logger.error(f"Transaction failed for {user_id}: {e}", exc_info=True)
            return False

    def add_funds(self, user_id: str, amount: float, description: str, source: str = "system") -> bool:
        """
        Adds funds to an account (e.g. monthly subscription refresh, coffee top-up).
        
        Args:
            amount: POSITIVE dollar amount to add.
        """
        if amount <= 0:
            raise ValueError("Top-up amount must be positive.")

        try:
            with self._get_conn() as conn:
                # Update Balance
                conn.execute(
                    "UPDATE accounts SET balance = balance + ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?", 
                    (amount, user_id)
                )
                # Write to Ledger (Positive Amount)
                self._log_transaction(conn, user_id, amount, description)
                
                conn.commit()
                logger.info(f"Added ${amount:.2f} to {user_id} ({description})")
                return True
        except Exception as e:
            logger.error(f"Top-up failed for {user_id}: {e}", exc_info=True)
            return False

    def _log_transaction(self, conn: sqlite3.Connection, user_id: str, amount: float, description: str, job_id: str = None):
        """Internal helper to write a row to the ledger table."""
        transaction_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO ledger (transaction_id, user_id, amount, description, job_id) 
               VALUES (?, ?, ?, ?, ?)""",
            (transaction_id, user_id, amount, description, job_id)
        )