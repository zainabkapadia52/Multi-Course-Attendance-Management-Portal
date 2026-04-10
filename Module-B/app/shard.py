# shard.py
import sqlite3
import os
from flask import g, current_app

NUM_SHARDS = 3
SHARD_SIZE = 20  # student_ids per shard


def get_shard_id(student_id: int) -> int:
    """Range-based: student_id 1-20 → 0, 21-40 → 1, 41-60 → 2"""
    return (student_id - 1) // SHARD_SIZE


def get_shard_path(shard_id: int) -> str:
    base = os.path.dirname(current_app.config["DB_PATH"])
    return os.path.join(base, f"shard_{shard_id}.db")


def get_shard_db(student_id: int):
    """Get the shard DB connection for a given student_id."""
    shard_id = get_shard_id(student_id)
    key = f"shard_db_{shard_id}"

    if key not in g:
        conn = sqlite3.connect(
            get_shard_path(shard_id),
            detect_types=sqlite3.PARSE_DECLTYPES,
            timeout=30.0,
            check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        g[key] = conn

    return g[key]


def get_all_shard_dbs():
    """Returns connections to all shards — used for cross-shard queries."""
    dbs = []
    for shard_id in range(NUM_SHARDS):
        key = f"shard_db_{shard_id}"
        if key not in g:
            conn = sqlite3.connect(
                get_shard_path(shard_id),
                detect_types=sqlite3.PARSE_DECLTYPES,
                timeout=30.0,
                check_same_thread=False
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            g[key] = conn
        dbs.append((shard_id, g[key]))
    return dbs


def close_shard_dbs(e=None):
    for shard_id in range(NUM_SHARDS):
        key = f"shard_db_{shard_id}"
        conn = g.pop(key, None)
        if conn:
            conn.close()


def init_shards(app):
    """Register teardown and create shard schema on first run."""
    app.teardown_appcontext(close_shard_dbs)