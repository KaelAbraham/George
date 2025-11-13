"""
AuthManager - Encapsulates all authentication and authorization database logic.
Manages user roles, invite codes, and project permissions.
"""

import sqlite3
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class AuthManager:
    """
    Manages authentication, authorization, and user permissions.
    
    Handles:
    - Invite code validation and consumption
    - User account creation and role management
    - Project-level permissions (guest passes)
    """
    
    def __init__(self, db_path: str = "data/users.db"):
        """
        Initialize AuthManager with database connection.
        
        Args:
            db_path: Path to the SQLite database file (defaults to data/users.db)
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        logger.info(f"AuthManager initialized with database at {self.db_path}")

    def _get_conn(self) -> sqlite3.Connection:
        """
        Get a database connection with row factory set.
        
        Returns:
            sqlite3.Connection object
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initialize database tables if they don't exist."""
        with self._get_conn() as conn:
            # Invites table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS invites (
                    code TEXT PRIMARY KEY,
                    type TEXT NOT NULL CHECK(type IN ('single_use', 'ambassador')),
                    uses_left INTEGER DEFAULT 1,
                    associated_role TEXT DEFAULT 'guest',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT
                )
            """)
            
            # Users table (linked to Firebase UID)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('admin', 'guest')),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_login DATETIME
                )
            """)
            
            # Project Permissions (Guest Pass)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS project_permissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    permission_level TEXT NOT NULL CHECK(permission_level IN ('read', 'comment', 'edit', 'admin')),
                    granted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    granted_by TEXT,
                    UNIQUE(project_id, user_id),
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                )
            """)
            
            # Create indices for better query performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_invites_type ON invites(type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_permissions_project ON project_permissions(project_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_permissions_user ON project_permissions(user_id)")
            
            conn.commit()
            logger.info("Database tables initialized")

    # --- Invite System ---
    
    def create_invite(self, code: str, invite_type: str = 'single_use', uses: int = 1, 
                     associated_role: str = 'guest', created_by: str = None) -> bool:
        """
        Create a new invite code.
        
        Args:
            code: Unique invite code (e.g., 'CAUDEX-BETA')
            invite_type: Either 'single_use' or 'ambassador'
            uses: Number of uses for single_use codes
            associated_role: Role to assign (admin, guest, author, editor, etc.)
            created_by: User ID of the person creating the invite
            
        Returns:
            True if successful, False if code already exists
        """
        try:
            with self._get_conn() as conn:
                conn.execute(
                    """INSERT INTO invites (code, type, uses_left, associated_role, created_by)
                       VALUES (?, ?, ?, ?, ?)""",
                    (code, invite_type, uses, associated_role, created_by)
                )
                conn.commit()
            logger.info(f"Invite code '{code}' created (type={invite_type}, uses={uses})")
            return True
        except sqlite3.IntegrityError:
            logger.warning(f"Invite code '{code}' already exists")
            return False

    def validate_and_consume_invite(self, code: str) -> dict:
        """
        Check if an invite code is valid and not expired.
        Does NOT decrement uses yet (that happens on successful user creation).
        
        Args:
            code: The invite code to validate
            
        Returns:
            Dictionary with 'valid' (bool), 'role' (str), and optional 'error' (str)
        """
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT * FROM invites WHERE code = ?", (code,))
            invite = cursor.fetchone()
            
            if not invite:
                logger.warning(f"Invalid invite code attempted: {code}")
                return {"valid": False, "error": "Invalid code"}
            
            if invite['uses_left'] <= 0 and invite['type'] == 'single_use':
                logger.warning(f"Expired invite code attempted: {code}")
                return {"valid": False, "error": "Code expired"}
            
            logger.info(f"Invite code '{code}' validated successfully")
            return {
                "valid": True,
                "role": invite['associated_role'],
                "type": invite['type']
            }

    def decrement_invite(self, code: str) -> bool:
        """
        Decrement the uses_left counter for an invite code.
        Call this AFTER a user successfully creates a Firebase account.
        
        Args:
            code: The invite code to decrement
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with self._get_conn() as conn:
                cursor = conn.execute(
                    """UPDATE invites SET uses_left = uses_left - 1 
                       WHERE code = ? AND type = 'single_use'""",
                    (code,)
                )
                conn.commit()
            
            if cursor.rowcount > 0:
                logger.info(f"Invite code '{code}' decremented")
                return True
            else:
                logger.warning(f"Failed to decrement invite code '{code}' (not found or not single_use)")
                return False
        except sqlite3.Error as e:
            logger.error(f"Error decrementing invite code '{code}': {e}")
            return False

    def get_invite_info(self, code: str) -> dict:
        """
        Get detailed information about an invite code.
        
        Args:
            code: The invite code
            
        Returns:
            Dictionary with invite details, or None if not found
        """
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT * FROM invites WHERE code = ?", (code,))
            invite = cursor.fetchone()
            
            if not invite:
                return None
            
            return {
                "code": invite['code'],
                "type": invite['type'],
                "uses_left": invite['uses_left'],
                "associated_role": invite['associated_role'],
                "created_at": invite['created_at'],
                "created_by": invite['created_by']
            }

    # --- User Management ---
    
    def create_user(self, user_id: str, email: str, role: str = 'guest') -> bool:
        """
        Create a new user in the database.
        
        Args:
            user_id: Firebase UID
            email: User's email address
            role: Either 'admin' or 'guest' (defaults to 'guest')
            
        Returns:
            True if successful, False if user already exists
        """
        try:
            with self._get_conn() as conn:
                conn.execute(
                    """INSERT INTO users (user_id, email, role) VALUES (?, ?, ?)""",
                    (user_id, email, role)
                )
                conn.commit()
            logger.info(f"User created: {email} (id={user_id}, role={role})")
            return True
        except sqlite3.IntegrityError as e:
            logger.warning(f"Failed to create user {email}: {e}")
            return False

    def get_user_role(self, user_id: str) -> str:
        """
        Get a user's role.
        
        Args:
            user_id: The user's Firebase UID
            
        Returns:
            The user's role ('admin' or 'guest'), or 'guest' if not found
        """
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            role = row['role'] if row else 'guest'
            logger.debug(f"User {user_id} has role: {role}")
            return role

    def get_user_info(self, user_id: str) -> dict:
        """
        Get detailed information about a user.
        
        Args:
            user_id: The user's Firebase UID
            
        Returns:
            Dictionary with user details, or None if not found
        """
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            return {
                "user_id": row['user_id'],
                "email": row['email'],
                "role": row['role'],
                "created_at": row['created_at'],
                "updated_at": row['updated_at'],
                "last_login": row['last_login']
            }

    def update_last_login(self, user_id: str) -> bool:
        """
        Update the last_login timestamp for a user.
        
        Args:
            user_id: The user's Firebase UID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with self._get_conn() as conn:
                conn.execute(
                    """UPDATE users SET last_login = CURRENT_TIMESTAMP 
                       WHERE user_id = ?""",
                    (user_id,)
                )
                conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error updating last_login for user {user_id}: {e}")
            return False

    # --- Project Permissions (Guest Pass) ---
    
    def grant_project_access(self, project_id: str, user_id: str, 
                           permission_level: str = 'read', granted_by: str = None) -> bool:
        """
        Grant a user access to a project (guest pass).
        
        Args:
            project_id: The project ID
            user_id: The user's Firebase UID
            permission_level: One of 'read', 'comment', 'edit', 'admin'
            granted_by: User ID of the person granting access
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with self._get_conn() as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO project_permissions 
                       (project_id, user_id, permission_level, granted_by)
                       VALUES (?, ?, ?, ?)""",
                    (project_id, user_id, permission_level, granted_by)
                )
                conn.commit()
            logger.info(f"User {user_id} granted {permission_level} access to project {project_id}")
            return True
        except sqlite3.Error as e:
            logger.error(f"Error granting project access: {e}")
            return False

    def check_project_access(self, user_id: str, project_id: str) -> dict:
        """
        Check if a user has access to a project.
        Returns access details if user is a guest on this project.
        Note: Ownership (admin) logic usually lives in filesystem_server.
        
        Args:
            user_id: The user's Firebase UID
            project_id: The project ID
            
        Returns:
            Dictionary with 'has_access' (bool) and optional 'permission_level' (str)
        """
        with self._get_conn() as conn:
            cursor = conn.execute(
                """SELECT permission_level FROM project_permissions 
                   WHERE user_id = ? AND project_id = ?""",
                (user_id, project_id)
            )
            row = cursor.fetchone()
            
            if row:
                logger.info(f"User {user_id} has {row['permission_level']} access to project {project_id}")
                return {
                    "has_access": True,
                    "permission_level": row['permission_level']
                }
            
            logger.debug(f"User {user_id} has no guest access to project {project_id}")
            return {"has_access": False}

    def get_user_projects(self, user_id: str) -> list:
        """
        Get all projects a user has guest access to.
        
        Args:
            user_id: The user's Firebase UID
            
        Returns:
            List of dictionaries with project_id and permission_level
        """
        with self._get_conn() as conn:
            cursor = conn.execute(
                """SELECT project_id, permission_level, granted_at FROM project_permissions 
                   WHERE user_id = ? ORDER BY granted_at DESC""",
                (user_id,)
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def revoke_project_access(self, project_id: str, user_id: str) -> bool:
        """
        Revoke a user's access to a project.
        
        Args:
            project_id: The project ID
            user_id: The user's Firebase UID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with self._get_conn() as conn:
                conn.execute(
                    """DELETE FROM project_permissions 
                       WHERE project_id = ? AND user_id = ?""",
                    (project_id, user_id)
                )
                conn.commit()
            logger.info(f"Access revoked for user {user_id} to project {project_id}")
            return True
        except sqlite3.Error as e:
            logger.error(f"Error revoking project access: {e}")
            return False
