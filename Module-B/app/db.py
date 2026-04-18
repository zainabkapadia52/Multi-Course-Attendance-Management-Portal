import sqlite3
import click
from flask import g, current_app

from .shard import init_shards   # adjust import path to your structure
         

def get_db():
    """Get database connection with thread-safe locking"""
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DB_PATH"],
            detect_types=sqlite3.PARSE_DECLTYPES,
            timeout=60.0,  # Wait up to 60 seconds for DB lock (increased)
            check_same_thread=False,  # Allow access from different threads
            isolation_level=None  # Autocommit mode for better concurrency
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA busy_timeout = 60000")  # 60 second busy timeout
        
        # Try to set WAL mode, but don't fail if database is locked
        try:
            g.db.execute("PRAGMA journal_mode = WAL")  # Write-Ahead Logging for concurrency
            g.db.execute("PRAGMA synchronous = NORMAL")  # Faster writes with WAL
        except sqlite3.OperationalError:
            # WAL mode already set or database locked, continue anyway
            pass
    
    return g.db


def acquire_db_lock():
    """Acquire the thread lock for database operations - use auth as general lock"""
    if "db_lock" not in g:
        g.db_lock = current_app.config["THREAD_LOCKS"].get("auth")
    return g.db_lock


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_app(app):
    app.teardown_appcontext(close_db)
    from .shard import init_shards   # ← add this
    init_shards(app) 