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
import logging

logger = logging.getLogger(__name__)

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
    Raises: mysql.connector.Error if connection fails
    """
    key = f"_shard_conn_{shard_id}"
    if not hasattr(g, key):
        cfg = SHARD_CONFIGS[shard_id]
        try:
            conn = mysql.connector.connect(
                host=cfg["host"],
                port=cfg["port"],
                user=cfg["user"],
                password=cfg["password"],
                database=cfg["database"],
                connection_timeout=10,
                autocommit=False
            )
            logger.info(f"✓ Connected to shard {shard_id} (port {cfg['port']})")
            setattr(g, key, conn)
        except mysql.connector.Error as e:
            logger.error(f"✗ FAILED to connect to shard {shard_id} (port {cfg['port']}): {str(e)}")
            raise
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
                logger.debug(f"✓ Closed shard {shard_id} connection")
            except Exception as e:
                logger.warning(f"⚠ Error closing shard {shard_id} connection: {str(e)}")

# ── High-level query helpers ───────────────────────────────────────────────────

def get_records_for_student(student_id: int) -> list:
    """
    LOOKUP QUERY — single shard.
    Returns all attendance_records rows for one student as list of dicts.
    Returns empty list if not found or on error.
    """
    shard_id = get_shard_id(student_id)
    if shard_id == -1:
        logger.warning(f"⚠ Student {student_id} out of shard range")
        return []

    try:
        conn   = get_shard_conn(shard_id)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            f"SELECT * FROM shard_{shard_id}_attendance_records "
            "WHERE student_id = %s",
            (student_id,)
        )
        rows = cursor.fetchall()
        cursor.close()
        logger.debug(f"✓ Retrieved {len(rows)} records for student {student_id} from shard {shard_id}")
        return rows
    except mysql.connector.Error as e:
        logger.error(f"✗ Query error for student {student_id} on shard {shard_id}: {str(e)}")
        return []
    except Exception as e:
        logger.error(f"✗ Unexpected error for student {student_id}: {str(e)}")
        return []


def get_records_for_session(att_session_id: int) -> list:
    """
    RANGE QUERY — queries shards intelligently based on session's student range.
    
    OPTIMIZATION: Instead of always querying all 3 shards, fetch the student_id
    range for this session from the main DB, then determine which shards to query.
    
    Note: Most sessions will still span all shards since students are distributed
    by ID, so this optimization provides limited benefit but is more correct.
    
    Returns merged attendance_records for one session across all shards.
    Returns partial results if shard fails; logs errors.
    """
    rows = []
    failed_shards = []
    
    # OPTIMIZATION: Determine relevant shards by checking which student_ids are in this session
    from flask import g
    try:
        db = g.get('db')
        if db:
            # Fetch min/max student_id for this session from main DB
            result = db.execute(
                "SELECT MIN(student_id) as min_id, MAX(student_id) as max_id "
                "FROM attendance_records WHERE att_session_id = ?",
                (att_session_id,)
            ).fetchone()
            
            if result and result['min_id'] is not None:
                min_id = result['min_id']
                max_id = result['max_id']
                relevant_shards = get_shards_for_range(min_id, max_id)
                logger.debug(f"  Session {att_session_id}: students {min_id}-{max_id} → shards {relevant_shards}")
            else:
                # No records in this session
                logger.debug(f"  Session {att_session_id}: no records in main DB")
                return []
        else:
            # No main DB available, query all shards (fallback)
            relevant_shards = list(SHARD_CONFIGS.keys())
            logger.debug(f"  Session {att_session_id}: no main DB, querying all shards")
    except Exception as e:
        # On any error, fall back to querying all shards
        logger.warning(f"  Session {att_session_id}: error determining relevant shards, querying all: {str(e)}")
        relevant_shards = list(SHARD_CONFIGS.keys())
    
    # Query only the relevant shards
    for shard_id in relevant_shards:
        try:
            conn   = get_shard_conn(shard_id)
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                f"SELECT * FROM shard_{shard_id}_attendance_records "
                "WHERE att_session_id = %s",
                (att_session_id,)
            )
            shard_rows = cursor.fetchall()
            rows.extend(shard_rows)
            cursor.close()
            logger.debug(f"✓ Retrieved {len(shard_rows)} records from shard {shard_id} for session {att_session_id}")
        except mysql.connector.Error as e:
            logger.error(f"✗ Query error on shard {shard_id} for session {att_session_id}: {str(e)}")
            failed_shards.append(shard_id)
        except Exception as e:
            logger.error(f"✗ Unexpected error on shard {shard_id}: {str(e)}")
            failed_shards.append(shard_id)
    
    if failed_shards:
        logger.warning(f"⚠ Partial results for session {att_session_id} (failed shards: {failed_shards})")
    
    return rows


def get_student_id_for_record(record_id: int) -> int:
    """
    HELPER: Fetch student_id for a given record_id across all shards.
    Scans all shards to find which one has this record_id.
    
    Returns student_id if found, -1 if not found.
    """
    try:
        for shard_id in SHARD_CONFIGS:
            try:
                conn   = get_shard_conn(shard_id)
                cursor = conn.cursor()
                cursor.execute(
                    f"SELECT student_id FROM shard_{shard_id}_attendance_records "
                    "WHERE record_id = %s LIMIT 1",
                    (record_id,)
                )
                row = cursor.fetchone()
                cursor.close()
                if row:
                    student_id = row[0]
                    logger.debug(f"  Found record {record_id} in shard {shard_id} with student_id={student_id}")
                    return student_id
            except Exception as e:
                logger.debug(f"  Shard {shard_id} scan for record: {str(e)}")
                continue
        
        logger.warning(f"⚠ Record {record_id} not found in any shard")
        return -1
    except Exception as e:
        logger.error(f"✗ Error fetching student_id for record {record_id}: {str(e)}")
        return -1


def update_record(record_id: int, new_status: str, student_id: int = None) -> bool:
    """
    UPDATE — route to correct shard using student_id if provided.
    If student_id provided: Route directly (OPTIMAL - single shard query)
    If student_id not provided: Scan all shards (FALLBACK - less efficient)
    
    Returns True if the record was found and updated, False otherwise.
    
    Args:
        record_id: ID of the attendance record to update
        new_status: New status value (present, absent, late)
        student_id: (Optional) Student ID to optimize routing. If provided, 
                   queries only the shard containing that student.
    """
    try:
        # OPTIMIZATION: If student_id provided, route directly to one shard
        if student_id is not None:
            shard_id = get_shard_id(student_id)
            if shard_id == -1:
                logger.warning(f"⚠ Cannot update: student_id {student_id} out of range")
                return False
            
            try:
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
                    logger.info(f"✓ Direct update: record {record_id} in shard {shard_id} to status={new_status}")
                    return True
                else:
                    logger.warning(f"⚠ Record {record_id} not found in shard {shard_id}")
                    return False
            except Exception as e:
                logger.error(f"✗ Direct update failed for record {record_id}: {str(e)}")
                return False
        
        # FALLBACK: No student_id provided, scan all shards (less efficient)
        logger.warning(f"⚠ Scanning all shards for record {record_id} (student_id not provided)")
        for shard_id in SHARD_CONFIGS:
            try:
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
                    logger.info(f"✓ Scan update: record {record_id} found in shard {shard_id} to status={new_status}")
                    return True
            except Exception as e:
                logger.debug(f"  Shard {shard_id} scan: {str(e)}")
                continue
        
        logger.warning(f"⚠ Record {record_id} not found in any shard")
        return False
        
    except Exception as e:
        logger.error(f"✗ Unexpected error updating record {record_id}: {str(e)}")
        return False


def insert_record(att_session_id: int, student_id: int,
                  status: str, record_id: int = None) -> bool:
    """
    INSERT — route to correct shard by student_id.
    Returns True on success, False if student_id is out of range or error.
    """
    shard_id = get_shard_id(student_id)
    if shard_id == -1:
        logger.warning(f"⚠ Cannot insert: student_id {student_id} out of range")
        return False

    try:
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
        affected = cursor.rowcount
        cursor.close()
        logger.debug(f"✓ Inserted {affected} record(s) for student {student_id} into shard {shard_id}")
        return True
    except mysql.connector.Error as e:
        logger.error(f"✗ Insert error for student {student_id}: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"✗ Unexpected error inserting record for student {student_id}: {str(e)}")
        return False


def delete_records_for_student(student_id: int) -> int:
    """
    CASCADE DELETE — delete all attendance_records for a student across all shards.
    Called when a student is deleted from the system.
    Returns count of records deleted.
    """
    shard_id = get_shard_id(student_id)
    if shard_id == -1:
        logger.warning(f"⚠ Cannot delete: student_id {student_id} out of range")
        return 0   # student_id out of range
    
    try:
        conn   = get_shard_conn(shard_id)
        cursor = conn.cursor()
        
        cursor.execute(
            f"DELETE FROM shard_{shard_id}_attendance_records "
            "WHERE student_id = %s",
            (student_id,)
        )
        deleted_count = cursor.rowcount
        conn.commit()
        cursor.close()
        logger.info(f"✓ Cascade deleted {deleted_count} attendance records for student {student_id} from shard {shard_id}")
        return deleted_count
    except mysql.connector.Error as e:
        logger.error(f"✗ Delete error for student {student_id}: {str(e)}")
        return 0
    except Exception as e:
        logger.error(f"✗ Unexpected error deleting records for student {student_id}: {str(e)}")
        return 0


def delete_records_for_session(att_session_id: int) -> int:
    """
    CASCADE DELETE — delete all attendance_records for a session across all shards.
    Called when an attendance session is deleted.
    Returns count of records deleted across all shards.
    """
    total_deleted = 0
    failed_shards = []
    
    for shard_id in SHARD_CONFIGS:
        try:
            conn   = get_shard_conn(shard_id)
            cursor = conn.cursor()
            
            cursor.execute(
                f"DELETE FROM shard_{shard_id}_attendance_records "
                "WHERE att_session_id = %s",
                (att_session_id,)
            )
            deleted_count = cursor.rowcount
            total_deleted += deleted_count
            conn.commit()
            cursor.close()
            logger.debug(f"✓ Deleted {deleted_count} records from shard {shard_id} for session {att_session_id}")
        except mysql.connector.Error as e:
            logger.error(f"✗ Delete error on shard {shard_id} for session {att_session_id}: {str(e)}")
            failed_shards.append(shard_id)
        except Exception as e:
            logger.error(f"✗ Unexpected error on shard {shard_id}: {str(e)}")
            failed_shards.append(shard_id)
    
    if failed_shards:
        logger.warning(f"⚠ Partial delete for session {att_session_id} (failed shards: {failed_shards})")
    
    logger.info(f"✓ Cascade deleted total {total_deleted} records for session {att_session_id}")
    return total_deleted


def delete_records_for_course(course_id: int, db) -> tuple:
    """
    CASCADE DELETE — delete all attendance_records for all sessions of a course
    across all shards. First deletes all sessions, then their records.
    Called when a course is deleted.
    Returns (sessions_deleted, records_deleted).
    """
    # Get all sessions for this course
    sessions = db.execute(
        "SELECT att_session_id FROM attendance_sessions WHERE course_id = ?",
        (course_id,)
    ).fetchall()
    
    records_deleted = 0
    for session in sessions:
        session_id = session["att_session_id"]
        records_deleted += delete_records_for_session(session_id)
    
    sessions_deleted = len(sessions)
    return (sessions_deleted, records_deleted)


def delete_records_for_student_in_course(student_id: int, course_id: int, db) -> int:
    """
    CASCADE DELETE — delete attendance_records for a specific student in a specific course
    across all shards (deletes records only for sessions in that course).
    Called when a student is unenrolled from a course.
    Returns count of records deleted.
    """
    try:
        # Get all sessions for this course
        sessions = db.execute(
            "SELECT att_session_id FROM attendance_sessions WHERE course_id = ?",
            (course_id,)
        ).fetchall()
        
        shard_id = get_shard_id(student_id)
        if shard_id == -1:
            logger.warning(f"⚠ Cannot delete: student_id {student_id} out of range")
            return 0   # student_id out of range
        
        conn   = get_shard_conn(shard_id)
        cursor = conn.cursor()
        
        total_deleted = 0
        for session in sessions:
            session_id = session["att_session_id"]
            cursor.execute(
                f"DELETE FROM shard_{shard_id}_attendance_records "
                "WHERE student_id = %s AND att_session_id = %s",
                (student_id, session_id)
            )
            total_deleted += cursor.rowcount
        
        conn.commit()
        cursor.close()
        
        logger.info(f"✓ Cascade deleted {total_deleted} records for student {student_id} from course {course_id}")
        return total_deleted
    except mysql.connector.Error as e:
        logger.error(f"✗ Delete error for student {student_id} in course {course_id}: {str(e)}")
        return 0
    except Exception as e:
        logger.error(f"✗ Unexpected error deleting records for student {student_id}: {str(e)}")
        return 0