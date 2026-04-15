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
    return jsonify([dict(r) for r in rows])

@bp.get("/attendance-stats")
@require_role("student")
@thread_safe_db("attendance")
def attendance_stats():
    db      = get_db()
    courses = db.execute(
        """SELECT c.course_id, c.name, c.code
           FROM courses c JOIN course_enrollments ce ON ce.course_id=c.course_id
           WHERE ce.student_id=?""", (g.user["user_id"],)
    ).fetchall()
    return jsonify(_build_stats(db, courses, g.user["user_id"]))


@bp.get("/corrections/current")
@require_role("student")
@thread_safe_db("corrections")
def corrections_current():
    """Only correction requests for courses in the active semester."""
    db  = get_db()
    sem = db.execute("SELECT semester_id FROM semesters WHERE is_active=1 LIMIT 1").fetchone()
    if not sem:
        return jsonify([])
    rows = db.execute(
        """SELECT cr.*, c.name AS course_name, att.session_date, att.topic
           FROM correction_requests cr
           JOIN courses c ON c.course_id=cr.course_id
           JOIN attendance_sessions att ON att.att_session_id=cr.att_session_id
           WHERE cr.student_id=? AND c.semester_id=?
           ORDER BY cr.created_at DESC""",
        (g.user["user_id"], sem["semester_id"])
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@bp.get("/corrections/archive")
@require_role("student")
@thread_safe_db("corrections")
def corrections_archive():
    """Correction requests grouped by past semester."""
    db   = get_db()
    sems = db.execute(
        """SELECT DISTINCT s.semester_id, s.name
           FROM semesters s
           JOIN courses c ON c.semester_id=s.semester_id
           JOIN correction_requests cr ON cr.course_id=c.course_id
           WHERE cr.student_id=? AND s.is_active=0
           ORDER BY s.semester_id DESC""",
        (g.user["user_id"],)
    ).fetchall()

    result = []
    for sem in sems:
        rows = db.execute(
            """SELECT cr.*, c.name AS course_name, att.session_date, att.topic
               FROM correction_requests cr
               JOIN courses c ON c.course_id=cr.course_id
               JOIN attendance_sessions att ON att.att_session_id=cr.att_session_id
               WHERE cr.student_id=? AND c.semester_id=?
               ORDER BY cr.created_at DESC""",
            (g.user["user_id"], sem["semester_id"])
        ).fetchall()
        if rows:
            result.append({
                "semester_id":   sem["semester_id"],
                "semester_name": sem["name"],
                "requests":      [dict(r) for r in rows]
            })
    return jsonify(result)

@bp.get("/corrections/<int:req_id>/logs")
@require_role("student")
@thread_safe_db("corrections")
def correction_logs(req_id):
    db  = get_db()
    # Verify this request belongs to this student
    req = db.execute(
        "SELECT 1 FROM correction_requests WHERE req_id=? AND student_id=?",
        (req_id, g.user["user_id"])
    ).fetchone()
    if not req:
        return jsonify({"error": "Not found"}), 404
    rows = db.execute(
        """SELECT cl.action, cl.role, cl.acted_at, u.username
           FROM correction_logs cl
           JOIN users u ON u.user_id=cl.acted_by
           WHERE cl.req_id=?
           ORDER BY cl.acted_at ASC""", (req_id,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

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
            "records":        [dict(r) for r in records]
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
    rows = get_db().execute(
        """SELECT cr.*, c.name AS course_name, att.session_date, att.topic
           FROM correction_requests cr
           JOIN courses c ON c.course_id=cr.course_id
           JOIN attendance_sessions att ON att.att_session_id=cr.att_session_id
           WHERE cr.student_id=? ORDER BY cr.created_at DESC""", (g.user["user_id"],)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

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
    try:
        cur = db.execute(
            "INSERT INTO correction_requests (student_id,course_id,att_session_id,reason,proof_url) VALUES (?,?,?,?,?)",
            (g.user["user_id"], course_id, att_session_id, reason, proof_url)
        )
        req_id = cur.lastrowid
        db.commit()
    except Exception:
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