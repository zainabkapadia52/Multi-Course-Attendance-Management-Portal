from flask import Blueprint, jsonify
from ..db import get_db
from ..middleware import require_role

bp = Blueprint("dean", __name__)

@bp.get("/semesters")
@require_role("dean")
def list_semesters():
    rows = get_db().execute("SELECT * FROM semesters ORDER BY semester_id DESC").fetchall()
    return jsonify([dict(r) for r in rows])

@bp.get("/active-semester")
@require_role("dean")
def active_semester():
    sem = get_db().execute("SELECT * FROM semesters WHERE is_active=1 LIMIT 1").fetchone()
    return jsonify(dict(sem) if sem else {})

@bp.get("/semesters/<int:sid>/courses")
@require_role("dean")
def semester_courses(sid):
    db      = get_db()
    courses = db.execute("SELECT * FROM courses WHERE semester_id=?", (sid,)).fetchall()
    result  = []
    for c in courses:
        instructors = db.execute(
            """SELECT u.username, p.department, p.designation
               FROM course_instructors ci JOIN users u ON u.user_id=ci.instructor_id
               LEFT JOIN user_profiles p ON p.user_id=u.user_id
               WHERE ci.course_id=?""", (c["course_id"],)
        ).fetchall()
        tas = db.execute(
            """SELECT u.username, p.department, p.designation
               FROM course_tas ct JOIN users u ON u.user_id=ct.ta_id
               LEFT JOIN user_profiles p ON p.user_id=u.user_id
               WHERE ct.course_id=?""", (c["course_id"],)
        ).fetchall()
        students = db.execute(
            """SELECT u.username, p.roll_no, p.program, p.batch
               FROM course_enrollments ce JOIN users u ON u.user_id=ce.student_id
               LEFT JOIN user_profiles p ON p.user_id=u.user_id
               WHERE ce.course_id=?""", (c["course_id"],)
        ).fetchall()
        result.append({
            "course":      dict(c),
            "instructors": [dict(i) for i in instructors],
            "tas":         [dict(t) for t in tas],
            "students":    [dict(s) for s in students],
        })
    return jsonify(result)


@bp.get("/profile")
@require_role("dean")
def profile():
    row = get_db().execute(
        """SELECT u.user_id, u.username, u.role, u.last_login,
                  p.department, p.designation
           FROM users u LEFT JOIN user_profiles p ON p.user_id=u.user_id
           WHERE u.user_id=?""", (g.user["user_id"],)
    ).fetchone()
    return jsonify(dict(row))