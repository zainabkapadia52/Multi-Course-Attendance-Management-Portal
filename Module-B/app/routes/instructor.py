from flask import Blueprint, request, jsonify, g   # fixed: was 'afrom'
from ..db import get_db
from ..middleware import require_role, thread_safe_db
from ..logger import audit_log
from ..events import broadcast
import time

bp = Blueprint("instructor", __name__)

@bp.get("/courses")
@require_role("instructor")
@thread_safe_db("courses")
def my_courses():
    db  = get_db()
    sem = db.execute("SELECT semester_id FROM semesters WHERE is_active=1 LIMIT 1").fetchone()
    if not sem:
        return jsonify([])
    rows = db.execute(
        """SELECT c.course_id, c.name, c.code, s.name AS semester
           FROM courses c
           JOIN course_instructors ci ON ci.course_id=c.course_id
           JOIN semesters s ON s.semester_id=c.semester_id
           WHERE ci.instructor_id=? AND c.semester_id=?""",
        (g.user["user_id"], sem["semester_id"])
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@bp.get("/courses/<int:cid>/students")
@require_role("instructor")
@thread_safe_db("courses", "enrollments")
def course_students(cid):
    db = get_db()
    if not db.execute("SELECT 1 FROM course_instructors WHERE course_id=? AND instructor_id=?",
                      (cid, g.user["user_id"])).fetchone():
        return jsonify({"error": "Forbidden"}), 403
    rows = db.execute(
        """SELECT u.user_id, u.username,
                  p.roll_no, p.program, p.batch
           FROM users u
           JOIN course_enrollments ce ON ce.student_id=u.user_id
           LEFT JOIN user_profiles p ON p.user_id=u.user_id
           WHERE ce.course_id=?
           ORDER BY u.username""", (cid,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@bp.post("/attendance-sessions")
@require_role("instructor")
@thread_safe_db("attendance", "courses")
def create_session():
    d            = request.json or {}
    course_id    = d.get("course_id")
    session_date = d.get("session_date")
    topic        = d.get("topic","")
    records      = d.get("records",[])
    if not course_id or not session_date:
        return jsonify({"error": "course_id and session_date required"}), 400
    db = get_db()
    if not db.execute("SELECT 1 FROM course_instructors WHERE course_id=? AND instructor_id=?",
                      (course_id, g.user["user_id"])).fetchone():
        return jsonify({"error": "Forbidden"}), 403
    cur = db.execute(
        "INSERT INTO attendance_sessions (course_id,session_date,topic,created_by) VALUES (?,?,?,?)",
        (course_id, session_date, topic, g.user["user_id"])
    )
    sid = cur.lastrowid
    inserted_records = []
    
    # INSERT — route each record to correct shard by student_id
    from ..shard_router import insert_record as shard_insert
    for rec in records:
        s, st = rec.get("student_id"), rec.get("status","absent")
        if s and st in ("present","absent","late"):
            shard_insert(
                att_session_id = sid,
                student_id     = s,
                status         = st
            )
            inserted_records.append({"student_id": s, "status": st})

    db.commit()  # CRITICAL: Commit attendance_sessions to SQLite so students can join

    broadcast("attendance_session_created", {
        "course_id":      course_id,
        "att_session_id": sid,
        "session_date":   session_date,
    })
    audit_log(
        "CREATE_ATT_SESSION",
        "/api/instructor/attendance-sessions",
        g.user["user_id"],
        details=f"att_session_id={sid}",
        old_value=None,
        new_value={
            "att_session_id": sid,
            "course_id":      course_id,
            "session_date":   session_date,
            "topic":          topic,
            "records":        inserted_records
        }
    )
    return jsonify({"message": "Session created", "att_session_id": sid}), 201

@bp.get("/attendance-sessions")
@require_role("instructor")
@thread_safe_db("attendance", "courses")
def list_sessions():
    db  = get_db()
    sem = db.execute("SELECT semester_id FROM semesters WHERE is_active=1 LIMIT 1").fetchone()
    if not sem:
        return jsonify([])
    rows = db.execute(
        """SELECT att.*, c.name AS course_name
           FROM attendance_sessions att
           JOIN courses c ON c.course_id=att.course_id
           JOIN course_instructors ci ON ci.course_id=att.course_id
           WHERE ci.instructor_id=? AND c.semester_id=?
           ORDER BY att.session_date DESC""",
        (g.user["user_id"], sem["semester_id"])
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@bp.get("/attendance-sessions/<int:sid>/records")
@require_role("instructor")
@thread_safe_db("attendance")
def session_records(sid):
    db = get_db()
    if not db.execute(
        """SELECT 1 FROM attendance_sessions att
           JOIN course_instructors ci ON ci.course_id=att.course_id
           WHERE att.att_session_id=? AND ci.instructor_id=?""",
        (sid, g.user["user_id"])
    ).fetchone():
        return jsonify({"error": "Forbidden"}), 403
    
    # RANGE QUERY — fan-out across all 3 shards, merge results
    from ..shard_router import get_records_for_session
    shard_rows = get_records_for_session(sid)   # list of dicts from MySQL
    
    # Enrich with profile data from main SQLite db
    result = []
    for row in shard_rows:
        profile = db.execute(
            """SELECT u.username, p.roll_no, p.program, p.batch
               FROM users u
               LEFT JOIN user_profiles p ON p.user_id = u.user_id
               WHERE u.user_id = ?""",
            (row["student_id"],)
        ).fetchone()
        
        result.append({
            "record_id":  row["record_id"],
            "student_id": row["student_id"],
            "status":     row["status"],
            "username":   profile["username"] if profile else "—",
            "roll_no":    profile["roll_no"]  if profile else "—",
            "program":    profile["program"]  if profile else "—",
            "batch":      profile["batch"]    if profile else "—",
        })
    
    return jsonify(result)

@bp.get("/corrections")
@require_role("instructor")
@thread_safe_db("corrections", "courses", "attendance")
def list_corrections():
    db  = get_db()
    sem = db.execute("SELECT semester_id FROM semesters WHERE is_active=1 LIMIT 1").fetchone()
    if not sem:
        return jsonify([])
    
    # Get instructor's courses in active semester
    instructor_courses = db.execute(
        """SELECT c.course_id
           FROM courses c
           JOIN course_instructors ci ON ci.course_id=c.course_id
           WHERE ci.instructor_id=? AND c.semester_id=?""",
        (g.user["user_id"], sem["semester_id"])
    ).fetchall()
    
    if not instructor_courses:
        return jsonify([])
    
    course_ids = [row["course_id"] for row in instructor_courses]
    
    # Get correction requests from MySQL shards for these courses
    from ..shard_router import get_pending_corrections_for_course
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    all_corrections = []
    
    # Query all courses in parallel
    with ThreadPoolExecutor(max_workers=len(course_ids)) as executor:
        # Get all corrections (not just pending) by querying shards directly
        futures = {}
        for course_id in course_ids:
            future = executor.submit(_get_all_corrections_for_course, course_id)
            futures[future] = course_id
        
        for future in as_completed(futures):
            try:
                corrections = future.result(timeout=10)
                all_corrections.extend(corrections)
            except Exception as e:
                pass
    
    # Enrich with user and session data from SQLite
    result = []
    for cr in all_corrections:
        user = db.execute("SELECT username FROM users WHERE user_id = ?", (cr["student_id"],)).fetchone()
        course = db.execute("SELECT name FROM courses WHERE course_id = ?", (cr["course_id"],)).fetchone()
        session = db.execute(
            "SELECT session_date, topic FROM attendance_sessions WHERE att_session_id = ?",
            (cr["att_session_id"],)
        ).fetchone()
        
        result.append({
            "req_id": cr["req_id"],
            "student_id": cr["student_id"],
            "course_id": cr["course_id"],
            "att_session_id": cr["att_session_id"],
            "reason": cr["reason"],
            "proof_url": cr.get("proof_url"),
            "status": cr["status"],
            "created_at": cr["created_at"],
            "student_name": user["username"] if user else "Unknown",
            "course_name": course["name"] if course else "Unknown",
            "session_date": session["session_date"] if session else None,
            "topic": session["topic"] if session else None,
        })
    
    # Sort: pending first (False < True), then by created_at DESC within each group
    result.sort(key=lambda x: (x["status"] != "pending", x["created_at"]), reverse=False)
    # Reverse the created_at within groups
    pending_items = [x for x in result if x["status"] == "pending"]
    other_items = [x for x in result if x["status"] != "pending"]
    pending_items.sort(key=lambda x: x["created_at"], reverse=True)
    other_items.sort(key=lambda x: x["created_at"], reverse=True)
    result = pending_items + other_items
    
    return jsonify(result)


def _get_all_corrections_for_course(course_id):
    """Helper function to get all correction requests for a course from shards."""
    import mysql.connector
    from ..shard_router import SHARD_CONFIGS
    
    rows = []
    for shard_id in SHARD_CONFIGS:
        try:
            cfg = SHARD_CONFIGS[shard_id]
            conn = mysql.connector.connect(
                host=cfg["host"], port=cfg["port"],
                user=cfg["user"], password=cfg["password"],
                database=cfg["database"],
                connection_timeout=10, autocommit=False
            )
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                f"SELECT * FROM shard_{shard_id}_correction_requests "
                "WHERE course_id = %s "
                "ORDER BY created_at DESC",
                (course_id,)
            )
            shard_rows = cursor.fetchall()
            cursor.close()
            conn.close()
            rows.extend(shard_rows)
        except Exception:
            continue
    
    return rows

@bp.put("/records/<int:rid>")
@require_role("instructor")
@thread_safe_db("attendance")
def update_record(rid):
    status = (request.json or {}).get("status")
    if status not in ("present", "absent", "late"):
        return jsonify({"error": "Invalid status"}), 400
    
    # UPDATE — optimize by fetching student_id first, then routing directly
    from ..shard_router import update_record as shard_update, get_student_id_for_record
    student_id = get_student_id_for_record(rid)
    if student_id == -1:
        return jsonify({"error": "Record not found in any shard"}), 404
    
    found = shard_update(rid, status, student_id)  # Pass student_id for direct routing
    
    if not found:
        return jsonify({"error": "Update failed"}), 500
    
    # BROADCAST: Notify all students viewing this session's records
    broadcast("attendance_updated", {
        "record_id": rid,
        "student_id": student_id,
        "status": status,
        "timestamp": time.time()
    })
    audit_log("INSTRUCTOR_UPDATE_ATT", f"/api/instructor/records/{rid}",
              g.user["user_id"], f"status={status}")
    return jsonify({"message": "Record updated"})

@bp.post("/corrections/<int:req_id>/accept")
@require_role("instructor")
@thread_safe_db("corrections", "attendance", "courses")
def accept_correction(req_id):
    db = get_db()
    
    # Get correction request from MySQL shard
    from ..shard_router import (
        get_correction_request_by_id,
        get_records_for_student,
        update_record as shard_update,
        update_correction_request_status
    )
    
    req = get_correction_request_by_id(req_id)
    if not req:
        return jsonify({"error": "Not found"}), 404
    
    # Verify this instructor teaches this course
    instructor_check = db.execute(
        """SELECT 1 FROM course_instructors ci
           WHERE ci.course_id=? AND ci.instructor_id=?""",
        (req["course_id"], g.user["user_id"])
    ).fetchone()
    
    if not instructor_check:
        return jsonify({"error": "Forbidden"}), 403
    
    if req["status"] != "pending":
        return jsonify({"error": "Already resolved"}), 400

    # LOOKUP: Find the attendance record for this student in this session
    student_records = get_records_for_student(req["student_id"])
    att_row = next((r for r in student_records if r["att_session_id"] == req["att_session_id"]), None)
    
    # Update correction request status in shard (includes acted_* fields)
    update_correction_request_status(req_id, "accepted", g.user["user_id"], "instructor")
    
    # UPDATE: Use shard router to update the attendance record
    if att_row:
        shard_update(att_row["record_id"], "present", req["student_id"])
    
    db.commit()
    broadcast("correction_resolved", {
        "req_id":     req_id,
        "status":     "accepted",
        "student_id": req["student_id"],
        "course_id":  req["course_id"],
    })
    audit_log(
        "ACCEPT_CORRECTION",
        f"/api/instructor/corrections/{req_id}/accept",
        g.user["user_id"],
        details=f"req_id={req_id} record_id={att_row['record_id'] if att_row else 'unknown'}",
        old_value={
            "req_id":        req_id,
            "req_status":    "pending",
            "record_id":     att_row["record_id"] if att_row else None,
            "record_status": att_row["status"] if att_row else None
        },
        new_value={
            "req_id":        req_id,
            "req_status":    "accepted",
            "record_id":     att_row["record_id"] if att_row else None,
            "record_status": "present"
        }
    )
    return jsonify({"message": "Accepted; attendance updated"})

@bp.post("/corrections/<int:req_id>/reject")
@require_role("instructor")
@thread_safe_db("corrections", "attendance", "courses")
def reject_correction(req_id):
    db = get_db()
    
    # Get correction request from MySQL shard
    from ..shard_router import get_correction_request_by_id, update_correction_request_status
    
    req = get_correction_request_by_id(req_id)
    if not req:
        return jsonify({"error": "Not found"}), 404
    
    # Verify this instructor teaches this course
    instructor_check = db.execute(
        """SELECT 1 FROM course_instructors ci
           WHERE ci.course_id=? AND ci.instructor_id=?""",
        (req["course_id"], g.user["user_id"])
    ).fetchone()
    
    if not instructor_check:
        return jsonify({"error": "Forbidden"}), 403
    
    if req["status"] != "pending":
        return jsonify({"error": "Already resolved"}), 400
    
    # Update correction request status in shard (includes acted_* fields)
    update_correction_request_status(req_id, "rejected", g.user["user_id"], "instructor")
    
    db.commit()
    broadcast("correction_resolved", {
        "req_id":     req_id,
        "status":     "rejected",
        "student_id": req["student_id"],
        "course_id":  req["course_id"],
    })

    audit_log(
        "REJECT_CORRECTION",
        f"/api/instructor/corrections/{req_id}/reject",
        g.user["user_id"],
        details=f"req_id={req_id}",
        old_value={"req_id": req_id, "status": "pending"},
        new_value={"req_id": req_id, "status": "rejected"}
    )
    return jsonify({"message": "Rejected"})

@bp.get("/courses/<int:cid>/sessions")
@require_role("instructor")
@thread_safe_db("courses", "attendance")
def course_sessions(cid):
    db  = get_db()
    sem = db.execute("SELECT semester_id FROM semesters WHERE is_active=1 LIMIT 1").fetchone()
    if not sem:
        return jsonify([])
    if not db.execute(
        "SELECT 1 FROM course_instructors WHERE course_id=? AND instructor_id=?",
        (cid, g.user["user_id"])
    ).fetchone():
        return jsonify({"error": "Forbidden"}), 403
    # Also verify this course belongs to active semester
    course = db.execute(
        "SELECT 1 FROM courses WHERE course_id=? AND semester_id=?",
        (cid, sem["semester_id"])
    ).fetchone()
    if not course:
        return jsonify({"error": "Course not in active semester"}), 403
    rows = db.execute(
        """SELECT att_session_id, session_date, topic
           FROM attendance_sessions WHERE course_id=?
           ORDER BY session_date DESC""", (cid,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.get("/courses/<int:cid>/tas")
@require_role("instructor")
@thread_safe_db("courses")
def course_tas(cid):
    db = get_db()
    if not db.execute("SELECT 1 FROM course_instructors WHERE course_id=? AND instructor_id=?",
                      (cid, g.user["user_id"])).fetchone():
        return jsonify({"error": "Forbidden"}), 403
    rows = db.execute(
        """SELECT u.user_id, u.username,
                  p.department, p.designation
           FROM users u
           JOIN course_tas ct ON ct.ta_id=u.user_id
           LEFT JOIN user_profiles p ON p.user_id=u.user_id
           WHERE ct.course_id=?
           ORDER BY u.username""", (cid,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.get("/available-tas/<int:cid>")
@require_role("instructor")
@thread_safe_db("courses")
def available_tas(cid):
    """TAs not yet assigned to this course."""
    rows = get_db().execute(
        """SELECT u.user_id, u.username FROM users u
           WHERE u.role='ta'
           AND u.user_id NOT IN (
               SELECT ta_id FROM course_tas WHERE course_id=?
           )""", (cid,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@bp.post("/courses/<int:cid>/tas")
@require_role("instructor")
@thread_safe_db("courses")
def assign_ta(cid):
    db  = get_db()
    if not db.execute("SELECT 1 FROM course_instructors WHERE course_id=? AND instructor_id=?",
                      (cid, g.user["user_id"])).fetchone():
        return jsonify({"error": "Forbidden"}), 403
    tid = (request.json or {}).get("ta_id")
    if not tid:
        return jsonify({"error": "ta_id required"}), 400
    try:
        db.execute("INSERT INTO course_tas VALUES (?,?)", (cid, tid))
        db.commit()
    except Exception:
        return jsonify({"error": "Already assigned"}), 409
    audit_log("INSTR_ASSIGN_TA", f"/api/instructor/courses/{cid}/tas", g.user["user_id"])
    return jsonify({"message": "TA assigned"}), 201

@bp.get("/corrections/<int:req_id>/logs")
@require_role("instructor")
@thread_safe_db("corrections")
def correction_logs(req_id):
    # Get correction request from shard (includes acted_* fields)
    from ..shard_router import get_correction_request_by_id
    req = get_correction_request_by_id(req_id)
    
    if not req:
        return jsonify({"error": "Request not found"}), 404
    
    # If processed, return the acted_* fields as a log entry
    if req["status"] != "pending":
        db = get_db()
        user = db.execute("SELECT username FROM users WHERE user_id = ?", (req["acted_by"],)).fetchone()
        return jsonify([{
            "action": req["status"],
            "role": req["acted_role"],
            "acted_at": req["acted_at"],
            "username": user["username"] if user else "Unknown"
        }])
    
    return jsonify([])

@bp.delete("/courses/<int:cid>/tas/<int:tid>")
@require_role("instructor")
@thread_safe_db("courses")
def remove_ta(cid, tid):
    db = get_db()
    if not db.execute("SELECT 1 FROM course_instructors WHERE course_id=? AND instructor_id=?",
                      (cid, g.user["user_id"])).fetchone():
        return jsonify({"error": "Forbidden"}), 403
    db.execute("DELETE FROM course_tas WHERE course_id=? AND ta_id=?", (cid, tid))
    db.commit()
    audit_log("INSTR_REMOVE_TA", f"/api/instructor/courses/{cid}/tas/{tid}", g.user["user_id"])
    return jsonify({"message": "TA removed"})


@bp.get("/profile")
@require_role("instructor")
@thread_safe_db("users")
def profile():
    row = get_db().execute(
        """SELECT u.user_id, u.username, u.role, u.last_login,
                  p.department, p.designation
           FROM users u LEFT JOIN user_profiles p ON p.user_id=u.user_id
           WHERE u.user_id=?""", (g.user["user_id"],)
    ).fetchone()
    return jsonify(dict(row))

@bp.get("/archive")
@require_role("instructor")
@thread_safe_db("courses", "attendance")
def archive():
    db   = get_db()
    sems = db.execute(
        """SELECT DISTINCT s.semester_id, s.name
           FROM semesters s
           JOIN courses c ON c.semester_id=s.semester_id
           JOIN course_instructors ci ON ci.course_id=c.course_id
           WHERE ci.instructor_id=? AND s.is_active=0
           ORDER BY s.semester_id DESC""",
        (g.user["user_id"],)
    ).fetchall()

    result = []
    for sem in sems:
        courses = db.execute(
            """SELECT c.course_id, c.name, c.code
               FROM courses c
               JOIN course_instructors ci ON ci.course_id=c.course_id
               WHERE ci.instructor_id=? AND c.semester_id=?""",
            (g.user["user_id"], sem["semester_id"])
        ).fetchall()

        course_list = []
        for c in courses:
            students = db.execute(
                """SELECT u.username, p.roll_no, p.program, p.batch
                   FROM users u
                   JOIN course_enrollments ce ON ce.student_id=u.user_id
                   LEFT JOIN user_profiles p ON p.user_id=u.user_id
                   WHERE ce.course_id=? ORDER BY u.username""",
                (c["course_id"],)
            ).fetchall()
            tas = db.execute(
                """SELECT u.username, p.department, p.designation
                   FROM users u
                   JOIN course_tas ct ON ct.ta_id=u.user_id
                   LEFT JOIN user_profiles p ON p.user_id=u.user_id
                   WHERE ct.course_id=? ORDER BY u.username""",
                (c["course_id"],)
            ).fetchall()
            sessions = db.execute(
                """SELECT att.att_session_id, att.session_date, att.topic
                   FROM attendance_sessions att
                   WHERE att.course_id=?
                   ORDER BY att.session_date DESC""",
                (c["course_id"],)
            ).fetchall()
            # For each session get records
            from ..shard_router import get_records_for_session
            session_list = []
            for s in sessions:
                # RANGE QUERY — get all records for this session across shards
                shard_rows = get_records_for_session(s["att_session_id"])
                
                # Enrich with profile data from main SQLite db
                records = []
                for row in shard_rows:
                    profile = db.execute(
                        """SELECT u.username, p.roll_no
                           FROM users u
                           LEFT JOIN user_profiles p ON p.user_id = u.user_id
                           WHERE u.user_id = ?""",
                        (row["student_id"],)
                    ).fetchone()
                    
                    records.append({
                        "username": profile["username"] if profile else "—",
                        "status":   row["status"],
                        "roll_no":  profile["roll_no"] if profile else "—",
                    })
                session_list.append({
                    "att_session_id": s["att_session_id"],
                    "session_date":   s["session_date"],
                    "topic":          s["topic"],
                    "records":        [dict(r) for r in records]
                })
            course_list.append({
                "course_id": c["course_id"],
                "name":      c["name"],
                "code":      c["code"],
                "students":  [dict(s) for s in students],
                "tas":       [dict(t) for t in tas],
                "sessions":  session_list,
            })
        result.append({
            "semester_id":   sem["semester_id"],
            "semester_name": sem["name"],
            "courses":       course_list
        })
    return jsonify(result)
