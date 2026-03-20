from flask import Blueprint, request, jsonify, g
from ..db import get_db
from ..middleware import require_role
from ..logger import audit_log
from ..events import broadcast

bp = Blueprint("ta", __name__)

@bp.get("/courses")
@require_role("ta")
def my_courses():
    db  = get_db()
    sem = db.execute("SELECT semester_id FROM semesters WHERE is_active=1 LIMIT 1").fetchone()
    if not sem:
        return jsonify([])
    rows = db.execute(
        """SELECT c.course_id, c.name, c.code, s.name AS semester
           FROM courses c
           JOIN course_tas ct ON ct.course_id=c.course_id
           JOIN semesters s ON s.semester_id=c.semester_id
           WHERE ct.ta_id=? AND c.semester_id=?""",
        (g.user["user_id"], sem["semester_id"])
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@bp.get("/courses/<int:cid>/students")
@require_role("ta")
def course_students(cid):
    db = get_db()
    if not db.execute("SELECT 1 FROM course_tas WHERE course_id=? AND ta_id=?",
                      (cid, g.user["user_id"])).fetchone():
        return jsonify({"error": "Forbidden"}), 403
    rows = db.execute(
        "SELECT u.user_id, u.username FROM users u "
        "JOIN course_enrollments ce ON ce.student_id=u.user_id WHERE ce.course_id=?",
        (cid,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@bp.get("/courses/<int:cid>/sessions")
@require_role("ta")
def course_sessions(cid):
    db  = get_db()
    sem = db.execute("SELECT semester_id FROM semesters WHERE is_active=1 LIMIT 1").fetchone()
    if not sem:
        return jsonify([])
    if not db.execute(
        "SELECT 1 FROM course_tas WHERE course_id=? AND ta_id=?",
        (cid, g.user["user_id"])
    ).fetchone():
        return jsonify({"error": "Forbidden"}), 403
    course = db.execute(
        "SELECT 1 FROM courses WHERE course_id=? AND semester_id=?",
        (cid, sem["semester_id"])
    ).fetchone()
    if not course:
        return jsonify({"error": "Course not in active semester"}), 403
    rows = db.execute(
        "SELECT att_session_id, session_date, topic FROM attendance_sessions "
        "WHERE course_id=? ORDER BY session_date DESC", (cid,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@bp.post("/attendance-sessions")
@require_role("ta")
def create_session():
    d            = request.json or {}
    course_id    = d.get("course_id")
    session_date = d.get("session_date")
    topic        = d.get("topic", "")
    records      = d.get("records", [])
    if not course_id or not session_date:
        return jsonify({"error": "course_id and session_date required"}), 400
    db  = get_db()
    sem = db.execute("SELECT semester_id FROM semesters WHERE is_active=1 LIMIT 1").fetchone()
    if not sem:
        return jsonify({"error": "No active semester"}), 400
    if not db.execute(
        "SELECT 1 FROM course_tas WHERE course_id=? AND ta_id=?",
        (course_id, g.user["user_id"])
    ).fetchone():
        return jsonify({"error": "Forbidden"}), 403
    if not db.execute(
        "SELECT 1 FROM courses WHERE course_id=? AND semester_id=?",
        (course_id, sem["semester_id"])
    ).fetchone():
        return jsonify({"error": "Course not in active semester"}), 403
    cur = db.execute(
        "INSERT INTO attendance_sessions (course_id,session_date,topic,created_by) VALUES (?,?,?,?)",
        (course_id, session_date, topic, g.user["user_id"])
    )
    sid = cur.lastrowid
    for rec in records:
        s, st = rec.get("student_id"), rec.get("status", "absent")
        if s and st in ("present", "absent"):
            db.execute(
                "INSERT INTO attendance_records (att_session_id,student_id,status) VALUES (?,?,?)",
                (sid, s, st)
            )
    db.commit()
    broadcast("attendance_session_created", {"course_id": course_id, "att_session_id": sid})
    audit_log("TA_CREATE_SESSION", "/api/ta/attendance-sessions", g.user["user_id"])
    return jsonify({"message": "Session created", "att_session_id": sid}), 201

@bp.get("/attendance-sessions/<int:sid>/records")
@require_role("ta")
def session_records(sid):
    rows = get_db().execute(
        """SELECT ar.record_id, u.username, ar.status
           FROM attendance_records ar JOIN users u ON u.user_id=ar.student_id
           WHERE ar.att_session_id=? ORDER BY u.username""", (sid,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@bp.put("/records/<int:rid>")
@require_role("ta")
def update_record(rid):
    status = (request.json or {}).get("status")
    if status not in ("present", "absent"):
        return jsonify({"error": "Invalid status"}), 400
    db = get_db()
    db.execute("UPDATE attendance_records SET status=? WHERE record_id=?", (status, rid))
    db.commit()
    broadcast("attendance_updated", {"record_id": rid, "status": status})
    audit_log("TA_UPDATE_ATT", f"/api/ta/records/{rid}", g.user["user_id"])
    return jsonify({"message": "Record updated"})

# ── Corrections (shared with instructor — same table, shared status) ──────────

@bp.get("/corrections")
@require_role("ta")
def list_corrections():
    db  = get_db()
    sem = db.execute("SELECT semester_id FROM semesters WHERE is_active=1 LIMIT 1").fetchone()
    if not sem:
        return jsonify([])
    rows = db.execute(
        """SELECT cr.*, u.username AS student_name, c.name AS course_name,
                  att.session_date, att.topic
           FROM correction_requests cr
           JOIN users u ON u.user_id=cr.student_id
           JOIN courses c ON c.course_id=cr.course_id
           JOIN attendance_sessions att ON att.att_session_id=cr.att_session_id
           JOIN course_tas ct ON ct.course_id=cr.course_id
           WHERE ct.ta_id=? AND c.semester_id=?
           ORDER BY (cr.status='pending') DESC, cr.created_at DESC""",
        (g.user["user_id"], sem["semester_id"])
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@bp.post("/corrections/<int:req_id>/accept")
@require_role("ta")
def accept_correction(req_id):
    db  = get_db()
    req = db.execute(
        """SELECT cr.* FROM correction_requests cr
           JOIN course_tas ct ON ct.course_id=cr.course_id
           WHERE cr.req_id=? AND ct.ta_id=?""",
        (req_id, g.user["user_id"])
    ).fetchone()
    if not req:
        return jsonify({"error": "Not found or forbidden"}), 404
    if req["status"] != "pending":
        return jsonify({"error": "Already resolved"}), 400
    # Update both — shared status visible to instructor and TA immediately
    db.execute("UPDATE correction_requests SET status='accepted' WHERE req_id=?", (req_id,))
    db.execute("UPDATE attendance_records SET status='present' WHERE att_session_id=? AND student_id=?",
               (req["att_session_id"], req["student_id"]))
    db.commit()
    broadcast("correction_resolved", {
        "req_id": req_id, "status": "accepted",
        "student_id": req["student_id"], "course_id": req["course_id"]
    })
    audit_log("TA_ACCEPT_CORRECTION", f"/api/ta/corrections/{req_id}/accept", g.user["user_id"])
    return jsonify({"message": "Accepted; attendance updated"})

@bp.post("/corrections/<int:req_id>/reject")
@require_role("ta")
def reject_correction(req_id):
    db  = get_db()
    req = db.execute(
        """SELECT cr.* FROM correction_requests cr
           JOIN course_tas ct ON ct.course_id=cr.course_id
           WHERE cr.req_id=? AND ct.ta_id=?""",
        (req_id, g.user["user_id"])
    ).fetchone()
    if not req:
        return jsonify({"error": "Not found or forbidden"}), 404
    if req["status"] != "pending":
        return jsonify({"error": "Already resolved"}), 400
    db.execute("UPDATE correction_requests SET status='rejected' WHERE req_id=?", (req_id,))
    db.commit()
    broadcast("correction_resolved", {
        "req_id": req_id, "status": "rejected",
        "student_id": req["student_id"], "course_id": req["course_id"]
    })
    audit_log("TA_REJECT_CORRECTION", f"/api/ta/corrections/{req_id}/reject", g.user["user_id"])
    return jsonify({"message": "Rejected"})


@bp.get("/profile")
@require_role("ta")
def profile():
    row = get_db().execute(
        """SELECT u.user_id, u.username, u.role, u.last_login,
                  p.roll_no, p.program, p.batch, p.designation
           FROM users u LEFT JOIN user_profiles p ON p.user_id=u.user_id
           WHERE u.user_id=?""", (g.user["user_id"],)
    ).fetchone()
    return jsonify(dict(row))

@bp.get("/archive")
@require_role("ta")
def archive():
    db   = get_db()
    sems = db.execute(
        """SELECT DISTINCT s.semester_id, s.name
           FROM semesters s
           JOIN courses c ON c.semester_id=s.semester_id
           JOIN course_tas ct ON ct.course_id=c.course_id
           WHERE ct.ta_id=? AND s.is_active=0
           ORDER BY s.semester_id DESC""",
        (g.user["user_id"],)
    ).fetchall()

    result = []
    for sem in sems:
        courses = db.execute(
            """SELECT c.course_id, c.name, c.code
               FROM courses c
               JOIN course_tas ct ON ct.course_id=c.course_id
               WHERE ct.ta_id=? AND c.semester_id=?""",
            (g.user["user_id"], sem["semester_id"])
        ).fetchall()
        result.append({
            "semester_id":   sem["semester_id"],
            "semester_name": sem["name"],
            "courses":       [dict(c) for c in courses]
        })
    return jsonify(result)