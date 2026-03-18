from flask import Blueprint, request, jsonify, g
from ..db import get_db
from ..middleware import require_role
from ..logger import audit_log
from ..events import broadcast

bp = Blueprint("student", __name__)

@bp.get("/courses")
@require_role("student")
def my_courses():
    rows = get_db().execute(
        """SELECT c.course_id,c.name,c.code,s.name AS semester,
                  GROUP_CONCAT(u.username) AS instructors
           FROM courses c
           JOIN course_enrollments ce ON ce.course_id=c.course_id
           JOIN semesters s ON s.semester_id=c.semester_id
           LEFT JOIN course_instructors ci ON ci.course_id=c.course_id
           LEFT JOIN users u ON u.user_id=ci.instructor_id
           WHERE ce.student_id=? GROUP BY c.course_id""", (g.user["user_id"],)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@bp.get("/attendance")
@require_role("student")
def my_attendance():
    rows = get_db().execute(
        """SELECT ar.status,att.session_date,att.topic,c.name AS course_name,c.code
           FROM attendance_records ar
           JOIN attendance_sessions att ON att.att_session_id=ar.att_session_id
           JOIN courses c ON c.course_id=att.course_id
           WHERE ar.student_id=? ORDER BY att.session_date DESC""", (g.user["user_id"],)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@bp.get("/courses/<int:cid>/sessions")
@require_role("student")
def course_sessions(cid):
    """Only returns sessions where student was absent or late — not present."""
    db = get_db()
    if not db.execute("SELECT 1 FROM course_enrollments WHERE course_id=? AND student_id=?",
                      (cid, g.user["user_id"])).fetchone():
        return jsonify({"error": "Not enrolled"}), 403
    rows = db.execute(
        """SELECT att.att_session_id, att.session_date, att.topic, ar.status
           FROM attendance_sessions att
           JOIN attendance_records ar ON ar.att_session_id=att.att_session_id
           WHERE att.course_id=? AND ar.student_id=? AND ar.status != 'present'
           ORDER BY att.session_date DESC""",
        (cid, g.user["user_id"])
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@bp.get("/corrections")
@require_role("student")
def my_corrections():
    rows = get_db().execute(
        """SELECT cr.*,c.name AS course_name,att.session_date,att.topic
           FROM correction_requests cr
           JOIN courses c ON c.course_id=cr.course_id
           JOIN attendance_sessions att ON att.att_session_id=cr.att_session_id
           WHERE cr.student_id=? ORDER BY cr.created_at DESC""", (g.user["user_id"],)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@bp.post("/corrections")
@require_role("student")
def submit_correction():
    d              = request.json or {}
    course_id      = d.get("course_id")
    att_session_id = d.get("att_session_id")
    reason         = d.get("reason","").strip()
    proof_url      = d.get("proof_url","").strip()
    if not course_id or not att_session_id or not reason:
        return jsonify({"error": "course_id, att_session_id, and reason required"}), 400
    db = get_db()
    if not db.execute("SELECT 1 FROM course_enrollments WHERE course_id=? AND student_id=?",
                      (course_id, g.user["user_id"])).fetchone():
        return jsonify({"error": "Not enrolled"}), 403
    try:
        db.execute(
            "INSERT INTO correction_requests (student_id,course_id,att_session_id,reason,proof_url) VALUES (?,?,?,?,?)",
            (g.user["user_id"], course_id, att_session_id, reason, proof_url)
        )
        db.commit()
        broadcast("correction_submitted", {
            "course_id":      course_id,
            "att_session_id": att_session_id,
            "student_id":     g.user["user_id"],
        })
    except Exception:
        return jsonify({"error": "You already submitted a request for this session"}), 409
    audit_log("SUBMIT_CORRECTION", "/api/student/corrections", g.user["user_id"])
    return jsonify({"message": "Correction request submitted"}), 201

@bp.get("/profile")
@require_role("student")
def profile():
    row = get_db().execute(
        """SELECT u.user_id,u.username,u.role,u.last_login,
                  p.roll_no,p.program,p.batch
           FROM users u LEFT JOIN user_profiles p ON p.user_id=u.user_id
           WHERE u.user_id=?""", (g.user["user_id"],)
    ).fetchone()
    return jsonify(dict(row))