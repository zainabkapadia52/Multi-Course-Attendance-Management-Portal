"""
Fix for Missing Sessions Table
================================
This script adds the missing 'sessions' table to the database.
Run this if you get: sqlite3.OperationalError: no such table: sessions
"""

import sqlite3
import sys

DB_PATH = "module_b.db"

def fix_missing_sessions_table():
    """Add missing sessions table to database"""
    print("="*80)
    print("FIXING: Missing Sessions Table")
    print("="*80)

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Enable foreign keys
        cursor.execute("PRAGMA foreign_keys = ON")

        # Create sessions table with IF NOT EXISTS (safe to run multiple times)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT    PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                mac        TEXT    NOT NULL,
                created_at TEXT    DEFAULT (datetime('now')),
                expires_at TEXT    NOT NULL
            )
        """)

        # Create index for performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_user_id
            ON sessions(user_id)
        """)

        conn.commit()

        print("\n[OK] Sessions table created successfully!")

        # Verify table structure
        print("\nTable structure verified:")
        cursor.execute("""
            SELECT sql FROM sqlite_master
            WHERE type='table' AND name='sessions'
        """)
        schema = cursor.fetchone()
        if schema:
            print(schema[0])

        # Check index
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index' AND name='idx_sessions_user_id'
        """)
        index = cursor.fetchone()
        if index:
            print(f"\n[OK] Index created: {index[0]}")

        # List all tables
        print("\nAll tables in database:")
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table'
            ORDER BY name
        """)
        tables = cursor.fetchall()
        for table in tables:
            print(f"  - {table[0]}")

        conn.close()

        print("\n" + "="*80)
        print("SUCCESS: Database fixed and ready to use!")
        print("="*80)
        print("\nYou can now run the Flask application:")
        print("  python run.py")
        print("\n")

        return True

    except sqlite3.OperationalError as e:
        print(f"\n[ERROR] SQLite error: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure you're in the /Module-B directory")
        print("2. Make sure module_b.db exists")
        print("3. Make sure the database is not locked by another process")
        return False
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        return False

def main():
    print(f"\nDatabase: {DB_PATH}")
    print(f"Location: {DB_PATH}\n")

    # Check if database exists
    import os
    if not os.path.exists(DB_PATH):
        print(f"[ERROR] Database file not found: {DB_PATH}")
        print("\nPlease run this script from the /Module-B directory")
        print("or initialize the database first:")
        print("  python init_db.py")
        return False

    # Apply the fix
    success = fix_missing_sessions_table()
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
