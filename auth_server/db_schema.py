"""
Database schema initialization for users.db
Manages users, invites, and project permissions.
"""

import sqlite3
from pathlib import Path
from datetime import datetime


def init_database(db_path: str = "users.db"):
    """
    Initialize the SQLite database with the required schema.
    
    Creates three tables:
    - invites: Stores invite codes with usage limits and role assignments
    - users: Stores user information and roles
    - project_permissions: Stores per-project access permissions for users
    
    Args:
        db_path: Path to the SQLite database file (defaults to users.db in current directory)
    """
    
    # Ensure the database directory exists
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Connect to the database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Create invites table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invites (
                code TEXT PRIMARY KEY,
                type TEXT NOT NULL CHECK(type IN ('single_use', 'ambassador')),
                uses_left INTEGER NOT NULL DEFAULT 1,
                associated_role TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT
            )
        """)
        
        # Create users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'guest')),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_login DATETIME
            )
        """)
        
        # Create project_permissions table
        cursor.execute("""
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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_invites_type ON invites(type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_permissions_project ON project_permissions(project_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_permissions_user ON project_permissions(user_id)")
        
        # Commit the changes
        conn.commit()
        print(f"✅ Database initialized successfully at {db_path}")
        
        # Print schema information
        print("\n📊 Schema Summary:")
        print("  - invites table: Stores invite codes and role assignments")
        print("  - users table: Stores user information and roles")
        print("  - project_permissions table: Stores per-project access permissions")
        
        return True
        
    except sqlite3.Error as e:
        print(f"❌ Database initialization error: {e}")
        conn.rollback()
        return False
        
    finally:
        conn.close()


def get_connection(db_path: str = "users.db") -> sqlite3.Connection:
    """
    Get a connection to the database.
    
    Args:
        db_path: Path to the SQLite database file
        
    Returns:
        sqlite3.Connection object
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Return rows as dictionaries
    return conn


def add_invite(db_path: str, code: str, invite_type: str, associated_role: str, created_by: str = None, uses: int = 1):
    """
    Add a new invite code to the database.
    
    Args:
        db_path: Path to the database
        code: Unique invite code (e.g., 'CAUDEX-BETA')
        invite_type: Either 'single_use' or 'ambassador'
        associated_role: The role to assign (e.g., 'author', 'editor')
        created_by: User ID of the person creating the invite
        uses: Number of uses (for single_use codes)
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO invites (code, type, uses_left, associated_role, created_by)
            VALUES (?, ?, ?, ?, ?)
        """, (code, invite_type, uses, associated_role, created_by))
        
        conn.commit()
        print(f"✅ Invite code '{code}' added successfully")
        return True
        
    except sqlite3.IntegrityError as e:
        print(f"❌ Invite code already exists or constraint violation: {e}")
        return False
        
    finally:
        conn.close()


def add_user(db_path: str, user_id: str, email: str, role: str = "guest"):
    """
    Add a new user to the database.
    
    Args:
        db_path: Path to the database
        user_id: Firebase UID
        email: User's email address
        role: Either 'admin' or 'guest' (defaults to 'guest')
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO users (user_id, email, role)
            VALUES (?, ?, ?)
        """, (user_id, email, role))
        
        conn.commit()
        print(f"✅ User '{email}' added successfully with role '{role}'")
        return True
        
    except sqlite3.IntegrityError as e:
        print(f"❌ User already exists or email conflict: {e}")
        return False
        
    finally:
        conn.close()


def grant_project_permission(db_path: str, project_id: str, user_id: str, permission_level: str, granted_by: str = None):
    """
    Grant a user permission to a project.
    
    Args:
        db_path: Path to the database
        project_id: ID of the project
        user_id: ID of the user
        permission_level: One of 'read', 'comment', 'edit', 'admin'
        granted_by: User ID of the person granting the permission
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO project_permissions 
            (project_id, user_id, permission_level, granted_by)
            VALUES (?, ?, ?, ?)
        """, (project_id, user_id, permission_level, granted_by))
        
        conn.commit()
        print(f"✅ Permission '{permission_level}' granted for project '{project_id}' to user '{user_id}'")
        return True
        
    except sqlite3.Error as e:
        print(f"❌ Failed to grant permission: {e}")
        return False
        
    finally:
        conn.close()


def get_user_permissions(db_path: str, user_id: str) -> list:
    """
    Get all project permissions for a user.
    
    Args:
        db_path: Path to the database
        user_id: ID of the user
        
    Returns:
        List of dictionaries with project_id and permission_level
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT project_id, permission_level, granted_at
            FROM project_permissions
            WHERE user_id = ?
            ORDER BY granted_at DESC
        """, (user_id,))
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
        
    finally:
        conn.close()


def get_invite_by_code(db_path: str, code: str) -> dict:
    """
    Get invite information by code.
    
    Args:
        db_path: Path to the database
        code: The invite code
        
    Returns:
        Dictionary with invite info, or None if not found
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT * FROM invites WHERE code = ?
        """, (code,))
        
        row = cursor.fetchone()
        return dict(row) if row else None
        
    finally:
        conn.close()


def use_invite(db_path: str, code: str) -> bool:
    """
    Decrement the uses_left counter for an invite code.
    
    Args:
        db_path: Path to the database
        code: The invite code
        
    Returns:
        True if successful, False otherwise
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE invites
            SET uses_left = uses_left - 1
            WHERE code = ? AND uses_left > 0
        """, (code,))
        
        if cursor.rowcount > 0:
            conn.commit()
            print(f"✅ Invite code '{code}' used (decremented)")
            return True
        else:
            print(f"❌ Invite code '{code}' not found or no uses left")
            return False
            
    except sqlite3.Error as e:
        print(f"❌ Failed to use invite: {e}")
        return False
        
    finally:
        conn.close()


if __name__ == "__main__":
    # Example usage
    db_path = "users.db"
    
    # Initialize database
    init_database(db_path)
    
    # Add sample data
    print("\n📝 Adding sample data...")
    add_invite(db_path, "CAUDEX-BETA", "ambassador", "author", created_by="admin_user_1")
    add_invite(db_path, "SINGLE-USE-001", "single_use", "editor", uses=3)
    
    add_user(db_path, "user_123", "author@example.com", "guest")
    add_user(db_path, "user_456", "editor@example.com", "admin")
    
    grant_project_permission(db_path, "project_1", "user_123", "read", granted_by="user_456")
    grant_project_permission(db_path, "project_1", "user_456", "admin", granted_by="user_456")
    
    # Test queries
    print("\n🔍 Testing queries...")
    permissions = get_user_permissions(db_path, "user_123")
    print(f"User 123 permissions: {permissions}")
    
    invite = get_invite_by_code(db_path, "CAUDEX-BETA")
    print(f"Invite info: {invite}")
