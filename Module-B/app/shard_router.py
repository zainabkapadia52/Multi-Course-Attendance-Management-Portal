# app/shard_router.py
"""
Query router for MySQL shards on 10.0.116.184 (Scalix team database).

Range-based partitioning on student_id (Team: Scalix):
    Shard 0  student_id 1-334    →  10.0.116.184:3307
    Shard 1  student_id 335-667  →  10.0.116.184:3308
    Shard 2  student_id 668-1000 →  10.0.116.184:3309
"""

import mysql.connector
from flask import g

SHARD_RANGES = {
    0: (12, 30),       # student_id 12-30 → Shard 0 (matches migrate.py)
    1: (31, 50),       # student_id 31-50 → Shard 1 (matches migrate.py)
    2: (51, 71),       # student_id 51-71 → Shard 2 (matches migrate.py)
}

SHARD_CONFIGS = {
    0: {"host": "10.0.116.184", "port": 3307,
        "database": "Scalix", "user": "Scalix", "password": "password@123"},
    1: {"host": "10.0.116.184", "port": 3308,
        "database": "Scalix", "user": "Scalix", "password": "password@123"},
    2: {"host": "10.0.116.184", "port": 3309,
        "database": "Scalix", "user": "Scalix", "password": "password@123"},
}

# ── Routing logic ─────────────────────────────────────────────────────────────

def get_shard_id(student_id: int) -> int:
    """Return shard index for a student_id. Returns -1 if out of range."""
    for shard_id, (lo, hi) in SHARD_RANGES.items():
        if lo <= student_id <= hi:
            return shard_id
    return -1   # student_id outside all shard ranges

def get_shards_for_range(min_id: int, max_id: int) -> list:
    """
    Return list of shard_ids whose range overlaps [min_id, max_id].
    Used for range queries that may span multiple shards.
    """
    result = []
    for shard_id, (lo, hi) in SHARD_RANGES.items():
        if lo <= max_id and hi >= min_id:
            result.append(shard_id)
    return result

# ── Connection management (one connection per shard per request) ───────────────

def get_shard_conn(shard_id: int):
    """
    Return a MySQL connection for the given shard.
    Connection is cached on Flask's g object for the lifetime of the request.
    """
    key = f"_shard_conn_{shard_id}"
    if not hasattr(g, key):
        cfg = SHARD_CONFIGS[shard_id]
        conn = mysql.connector.connect(**cfg)
        setattr(g, key, conn)
    return getattr(g, key)

def close_shard_connections(exception=None):
    """
    Call this from app teardown to close all shard connections.
    Register in app/__init__.py:
        app.teardown_appcontext(close_shard_connections)
    """
    for shard_id in SHARD_CONFIGS:
        key = f"_shard_conn_{shard_id}"
        conn = g.pop(key, None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

# ── High-level query helpers ───────────────────────────────────────────────────

def get_records_for_student(student_id: int) -> list:
    """
    LOOKUP QUERY — single shard.
    Returns all attendance_records rows for one student as list of dicts.
    """
    shard_id = get_shard_id(student_id)
    if shard_id == -1:
        return []

    conn   = get_shard_conn(shard_id)
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        f"SELECT * FROM shard_{shard_id}_attendance_records "
        "WHERE student_id = %s",
        (student_id,)
    )
    rows = cursor.fetchall()
    cursor.close()
    return rows


def get_records_for_session(att_session_id: int) -> list:
    """
    RANGE QUERY — all 3 shards (we don't know student_id up front).
    Returns merged attendance_records for one session across all shards.
    """
    rows = []
    for shard_id in SHARD_CONFIGS:
        conn   = get_shard_conn(shard_id)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            f"SELECT * FROM shard_{shard_id}_attendance_records "
            "WHERE att_session_id = %s",
            (att_session_id,)
        )
        rows.extend(cursor.fetchall())
        cursor.close()
    return rows


def update_record(record_id: int, new_status: str) -> bool:
    """
    UPDATE — scan all shards to find the record, then update it.
    Returns True if the record was found and updated.
    """
    for shard_id in SHARD_CONFIGS:
        conn   = get_shard_conn(shard_id)
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE shard_{shard_id}_attendance_records "
            "SET status = %s WHERE record_id = %s",
            (new_status, record_id)
        )
        conn.commit()
        affected = cursor.rowcount
        cursor.close()
        if affected > 0:
            return True   # found and updated — stop scanning
    return False          # not found in any shard


def insert_record(att_session_id: int, student_id: int,
                  status: str, record_id: int = None) -> bool:
    """
    INSERT — route to correct shard by student_id.
    Returns True on success, False if student_id is out of range.
    """
    shard_id = get_shard_id(student_id)
    if shard_id == -1:
        return False

    conn   = get_shard_conn(shard_id)
    cursor = conn.cursor()

    if record_id:
        cursor.execute(
            f"INSERT IGNORE INTO shard_{shard_id}_attendance_records "
            "(record_id, att_session_id, student_id, status) "
            "VALUES (%s, %s, %s, %s)",
            (record_id, att_session_id, student_id, status)
        )
    else:
        cursor.execute(
            f"INSERT INTO shard_{shard_id}_attendance_records "
            "(att_session_id, student_id, status) "
            "VALUES (%s, %s, %s)",
            (att_session_id, student_id, status)
        )
    conn.commit()
    cursor.close()
    return True