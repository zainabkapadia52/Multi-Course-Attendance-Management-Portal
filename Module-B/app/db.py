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
            timeout=30.0,  # Wait up to 30 seconds for DB lock
            check_same_thread=False  # Allow access from different threads
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA journal_mode = WAL")  # Write-Ahead Logging for concurrency
    
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