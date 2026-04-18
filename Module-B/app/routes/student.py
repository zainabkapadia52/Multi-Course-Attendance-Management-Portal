from flask import Blueprint, request, jsonify, g
from ..db import get_db
from ..middleware import require_role, thread_safe_db
from ..logger import audit_log
from ..events import broadcast

bp = Blueprint("student", __name__)

@bp.get("/courses")
@require_role("student")
@thread_safe_db("courses", "enrollments")
def my_courses():
    from flask import make_response
    db   = get_db()
    rows = db.execute(
        """SELECT c.course_id, c.name, c.code, s.name AS semester,
                  GROUP_CONCAT(u.username) AS instructors
           FROM courses c
           JOIN course_enrollments ce ON ce.course_id=c.course_id
           JOIN semesters s ON s.semester_id=c.semester_id
           LEFT JOIN course_instructors ci ON ci.course_id=c.course_id
           LEFT JOIN users u ON u.user_id=ci.instructor_id
           WHERE ce.student_id=? GROUP BY c.course_id""", (g.user["user_id"],)
    ).fetchall()
    
    # CACHE-BUSTING: Return response with no-cache headers to force fresh data on each request
    response = make_response(jsonify([dict(r) for r in rows]))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@bp.get("/attendance-stats")
@require_role("student")
@thread_safe_db("attendance")
def attendance_stats():
    from flask import make_response
    db      = get_db()
    courses = db.execute(
        """SELECT c.course_id, c.name, c.code
           FROM courses c JOIN course_enrollments ce ON ce.course_id=c.course_id
           WHERE ce.student_id=?""", (g.user["user_id"],)
    ).fetchall()
    
    # CACHE-BUSTING: No-cache headers ensure fresh data on every request
    response = make_response(jsonify(_build_stats(db, courses, g.user["user_id"])))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@bp.get("/corrections/current")
@require_role("student")
@thread_safe_db("corrections")
def corrections_current():
    """Only correction requests for courses in the active semester."""
    db  = get_db()
    sem = db.execute("SELECT semester_id FROM semesters WHERE is_active=1 LIMIT 1").fetchone()
    if not sem:
        return jsonify([])
    
    # Get correction requests from MySQL shards for this student
    from ..shard_router import get_correction_requests_for_student
    corrections = get_correction_requests_for_student(g.user["user_id"])
    
    # Filter to active semester and enrich with course/session data
    result = []
    for cr in corrections:
        course = db.execute(
            "SELECT name, semester_id FROM courses WHERE course_id = ?",
            (cr["course_id"],)
        ).fetchone()
        
        if not course or course["semester_id"] != sem["semester_id"]:
            continue
        
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
            "course_name": course["name"] if course else "Unknown",
            "session_date": session["session_date"] if session else None,
            "topic": session["topic"] if session else None,
        })
    
    # Sort by created_at DESC
    result.sort(key=lambda x: x["created_at"], reverse=True)
    
    return jsonify(result)

@bp.get("/corrections/archive")
@require_role("student")
@thread_safe_db("corrections")
def corrections_archive():
    """Correction requests grouped by past semester."""
    db = get_db()
    
    # Get correction requests from MySQL shards for this student
    from ..shard_router import get_correction_requests_for_student
    corrections = get_correction_requests_for_student(g.user["user_id"])
    
    # Get past semesters
    sems = db.execute(
        """SELECT semester_id, name
           FROM semesters
           WHERE is_active=0
           ORDER BY semester_id DESC"""
    ).fetchall()
    
    result = []
    for sem in sems:
        sem_corrections = []
        
        for cr in corrections:
            course = db.execute(
                "SELECT name, semester_id FROM courses WHERE course_id = ?",
                (cr["course_id"],)
            ).fetchone()
            
            if not course or course["semester_id"] != sem["semester_id"]:
                continue
            
            session = db.execute(
                "SELECT session_date, topic FROM attendance_sessions WHERE att_session_id = ?",
                (cr["att_session_id"],)
            ).fetchone()
            
            sem_corrections.append({
                "req_id": cr["req_id"],
                "student_id": cr["student_id"],
                "course_id": cr["course_id"],
                "att_session_id": cr["att_session_id"],
                "reason": cr["reason"],
                "proof_url": cr.get("proof_url"),
                "status": cr["status"],
                "created_at": cr["created_at"],
                "course_name": course["name"] if course else "Unknown",
                "session_date": session["session_date"] if session else None,
                "topic": session["topic"] if session else None,
            })
        
        if sem_corrections:
            # Sort by created_at DESC
            sem_corrections.sort(key=lambda x: x["created_at"], reverse=True)
            result.append({
                "semester_id":   sem["semester_id"],
                "semester_name": sem["name"],
                "requests":      sem_corrections
            })
    
    return jsonify(result)

@bp.get("/corrections/<int:req_id>/logs")
@require_role("student")
@thread_safe_db("corrections")
def correction_logs(req_id):
    # Get correction request from shard (includes acted_* fields)
    from ..shard_router import get_correction_request_by_id
    req = get_correction_request_by_id(req_id)
    
    if not req:
        return jsonify({"error": "Request not found"}), 404
    
    # Verify this request belongs to this student
    if req["student_id"] != g.user["user_id"]:
        return jsonify({"error": "Not found"}), 404
    
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

@bp.get("/attendance-stats/current")
@require_role("student")
@thread_safe_db("attendance")
def attendance_stats_current():
    """Only courses in the active semester."""
    db      = get_db()
    sem     = db.execute("SELECT semester_id FROM semesters WHERE is_active=1 LIMIT 1").fetchone()
    if not sem:
        return jsonify([])

    courses = db.execute(
        """SELECT c.course_id, c.name, c.code
           FROM courses c
           JOIN course_enrollments ce ON ce.course_id=c.course_id
           WHERE ce.student_id=? AND c.semester_id=?""",
        (g.user["user_id"], sem["semester_id"])
    ).fetchall()

    return jsonify(_build_stats(db, courses, g.user["user_id"]))

@bp.get("/attendance-stats/archive")
@require_role("student")
@thread_safe_db("attendance")
def attendance_stats_archive():
    """All past semesters this student has courses in."""
    db   = get_db()
    sems = db.execute(
        """SELECT DISTINCT s.semester_id, s.name
           FROM semesters s
           JOIN courses c ON c.semester_id=s.semester_id
           JOIN course_enrollments ce ON ce.course_id=c.course_id
           WHERE ce.student_id=? AND s.is_active=0
           ORDER BY s.semester_id DESC""",
        (g.user["user_id"],)
    ).fetchall()

    result = []
    for sem in sems:
        courses = db.execute(
            """SELECT c.course_id, c.name, c.code
               FROM courses c
               JOIN course_enrollments ce ON ce.course_id=c.course_id
               WHERE ce.student_id=? AND c.semester_id=?""",
            (g.user["user_id"], sem["semester_id"])
        ).fetchall()
        result.append({
            "semester_id":   sem["semester_id"],
            "semester_name": sem["name"],
            "courses":       _build_stats(db, courses, g.user["user_id"], archive=True)
        })
    return jsonify(result)


@bp.get("/sync")
@require_role("student")
@thread_safe_db("courses", "enrollments")
def sync_enrollment_changes():
    """
    REAL-TIME SYNC ENDPOINT — called by frontend polling to detect course changes.
    Returns courses with a hash/timestamp so frontend can detect when courses changed.
    
    Frontend usage:
    - Call this every 5-10 seconds
    - If hash differs from last response, refresh course list
    - This ensures instant updates when courses are deleted
    """
    from flask import make_response
    import hashlib
    
    db = get_db()
    student_id = g.user["user_id"]
    
    # Get current enrolled courses with their deletion status
    rows = db.execute(
        """SELECT c.course_id, c.name, c.code, c.semester_id, s.name AS semester
           FROM courses c
           JOIN course_enrollments ce ON ce.course_id=c.course_id
           JOIN semesters s ON s.semester_id=c.semester_id
           WHERE ce.student_id=?
           ORDER BY c.course_id""", 
        (student_id,)
    ).fetchall()
    
    courses = [dict(r) for r in rows]
    
    # Create hash of current courses to detect changes
    course_data = ",".join([f"{c['course_id']}:{c['code']}" for c in courses])
    courses_hash = hashlib.md5(course_data.encode()).hexdigest()
    
    response_data = {
        "hash": courses_hash,
        "count": len(courses),
        "courses": courses
    }
    
    response = make_response(jsonify(response_data))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@bp.get("/events")
@require_role("student")
def course_events():
    """
    SERVER-SENT EVENTS (SSE) — Real-time course update notifications.
    
    Browser usage:
      const eventSource = new EventSource('/api/student/events');
      eventSource.addEventListener('course_deleted', (e) => {
        console.log('Course deleted:', e.data);
        location.reload();  // Refresh page
      });
    """
    from flask import Response
    from ..events import subscribe, unsubscribe
    import time
    
    def generate():
        q = subscribe()
        student_id = g.user["user_id"]
        
        try:
            # Send initial keep-alive
            yield f"data: {{'type': 'connected', 'student_id': {student_id}}}\n\n"
            
            # Stream events to this student
            while True:
                try:
                    msg = q.get(timeout=30)  # 30s timeout for keep-alive
                    
                    # msg contains: {"type": "course_deleted", "data": {...}}
                    import json as json_module
                    event_data = json_module.loads(msg)
                    event_type = event_data.get("type", "message")
                    event_payload = json_module.dumps(event_data.get("data", {}))
                    
                    # Send in proper SSE format: event: TYPE\ndata: PAYLOAD
                    yield f"event: {event_type}\ndata: {event_payload}\n\n"
                except Exception:
                    # Keep-alive ping every 30s
                    yield f": keep-alive\n\n"
                    
        finally:
            unsubscribe(q)
    
    response = Response(generate(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"  # Disable buffering in proxies
    return response

def _build_stats(db, courses, student_id, archive=False):
    """Shared helper — builds per-course attendance stats."""
    from ..shard_router import get_records_for_student
    MIN_SESSIONS_TO_WARN = 5
    result = []
    
    # LOOKUP: Get all records for this student from the correct shard
    all_student_records = get_records_for_student(student_id)
    
    for course in courses:
        # Filter to this course using session lookup in main SQLite db
        session_ids_for_course = {
            r["att_session_id"] for r in db.execute(
                "SELECT att_session_id FROM attendance_sessions WHERE course_id = ?",
                (course["course_id"],)
            ).fetchall()
        }
        
        records = [r for r in all_student_records
                   if r["att_session_id"] in session_ids_for_course]

        total   = len(records)
        present = sum(1 for r in records if r["status"] == "present")
        late    = sum(1 for r in records if r["status"] == "late")
        absent  = sum(1 for r in records if r["status"] == "absent")
        pct     = round((present / total * 100) if total > 0 else 0, 1)

        if archive:
            # Archive — just show percentage, no warning logic
            colour  = "success" if pct >= 75 else "danger"
            warning = "safe"    if pct >= 75 else "at_risk"
        else:
            if total == 0:
                colour, warning = "secondary", "no_sessions"
            elif total < MIN_SESSIONS_TO_WARN:
                colour, warning = "secondary", "too_early"
            elif pct < 75:
                colour, warning = "danger", "at_risk"
            elif pct < 85:
                colour, warning = "warning", "borderline"
            else:
                colour, warning = "success", "safe"

        # Enrich records with session details (date, topic) from main SQLite db
        enriched_records = []
        for r in records:
            session = db.execute(
                "SELECT session_date, topic FROM attendance_sessions WHERE att_session_id = ?",
                (r["att_session_id"],)
            ).fetchone()
            enriched_records.append({
                "record_id":      r["record_id"],
                "att_session_id": r["att_session_id"],
                "student_id":     r["student_id"],
                "status":         r["status"],
                "session_date":   session["session_date"] if session else None,
                "topic":          session["topic"] if session else None,
            })

        result.append({
            "course_id":      course["course_id"],
            "name":           course["name"],
            "code":           course["code"],
            "total_sessions": total,
            "present":        present,
            "late":           late,
            "absent":         absent,
            "percentage":     pct,
            "colour":         colour,
            "warning":        warning,
            "records":        enriched_records
        })
    return result


@bp.get("/courses/<int:cid>/sessions")
@require_role("student")
@thread_safe_db("courses", "attendance")
def course_sessions(cid):
    """Only absent sessions are eligible for correction requests."""
    db = get_db()
    if not db.execute("SELECT 1 FROM course_enrollments WHERE course_id=? AND student_id=?",
                      (cid, g.user["user_id"])).fetchone():
        return jsonify({"error": "Not enrolled"}), 403
    
    # LOOKUP: Get all records for this student from the correct shard
    from ..shard_router import get_records_for_student
    all_student_records = get_records_for_student(g.user["user_id"])
    
    # Filter by course and absent status
    session_ids_for_course = {
        r["att_session_id"] for r in db.execute(
            "SELECT att_session_id FROM attendance_sessions WHERE course_id = ?",
            (cid,)
        ).fetchall()
    }
    
    absent_records = [r for r in all_student_records
                      if r["att_session_id"] in session_ids_for_course and r["status"] == "absent"]
    
    # Enrich with session details from main db
    result = []
    for rec in absent_records:
        session = db.execute(
            "SELECT att_session_id, session_date, topic FROM attendance_sessions WHERE att_session_id = ?",
            (rec["att_session_id"],)
        ).fetchone()
        if session:
            result.append({
                "att_session_id": session["att_session_id"],
                "session_date":   session["session_date"],
                "topic":          session["topic"],
                "status":         rec["status"],
            })
    
    return jsonify(sorted(result, key=lambda x: x["session_date"], reverse=True))

@bp.get("/corrections")
@require_role("student")
@thread_safe_db("corrections")
def my_corrections():
    db = get_db()
    
    # Get correction requests from MySQL shards for this student
    from ..shard_router import get_correction_requests_for_student
    corrections = get_correction_requests_for_student(g.user["user_id"])
    
    # Enrich with course/session data
    result = []
    for cr in corrections:
        course = db.execute(
            "SELECT name FROM courses WHERE course_id = ?",
            (cr["course_id"],)
        ).fetchone()
        
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
            "course_name": course["name"] if course else "Unknown",
            "session_date": session["session_date"] if session else None,
            "topic": session["topic"] if session else None,
        })
    
    # Sort by created_at DESC
    result.sort(key=lambda x: x["created_at"], reverse=True)
    
    return jsonify(result)

@bp.post("/corrections")
@require_role("student")
@thread_safe_db("corrections", "courses", "attendance")
def submit_correction():
    d              = request.json or {}
    course_id      = d.get("course_id")
    att_session_id = d.get("att_session_id")
    reason         = d.get("reason", "").strip()
    proof_url      = d.get("proof_url", "").strip()
    if not course_id or not att_session_id or not reason:
        return jsonify({"error": "course_id, att_session_id, and reason required"}), 400
    db = get_db()
    if not db.execute("SELECT 1 FROM course_enrollments WHERE course_id=? AND student_id=?",
                      (course_id, g.user["user_id"])).fetchone():
        return jsonify({"error": "Not enrolled"}), 403
    
    # Insert into MySQL shard instead of SQLite
    from ..shard_router import insert_correction_request
    
    try:
        req_id = insert_correction_request(
            student_id=g.user["user_id"],
            course_id=course_id,
            att_session_id=att_session_id,
            reason=reason,
            proof_url=proof_url if proof_url else None
        )
        
        if req_id == 0:
            return jsonify({"error": "Failed to submit correction request"}), 500
        
        db.commit()
    except Exception as e:
        return jsonify({"error": "You already submitted a request for this session"}), 409
    
    broadcast("correction_submitted", {
        "course_id": course_id, "att_session_id": att_session_id,
        "student_id": g.user["user_id"]
    })
    audit_log(
        "SUBMIT_CORRECTION",
        "/api/student/corrections",
        g.user["user_id"],
        details=f"req_id={req_id}",
        old_value=None,
        new_value={
            "req_id":        req_id,
            "course_id":     course_id,
            "att_session_id": att_session_id,
            "reason":        reason
        }
    )
    return jsonify({"message": "Correction request submitted"}), 201

@bp.get("/profile")
@require_role("student")
@thread_safe_db("users")
def profile():
    row = get_db().execute(
        """SELECT u.user_id, u.username, u.role, u.last_login,
                  p.roll_no, p.program, p.batch
           FROM users u LEFT JOIN user_profiles p ON p.user_id=u.user_id
           WHERE u.user_id=?""", (g.user["user_id"],)
    ).fetchone()
    return jsonify(dict(row))