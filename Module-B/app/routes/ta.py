from flask import Blueprint, request, jsonify, g
from ..db import get_db
from ..middleware import require_role
from ..logger import audit_log
from ..events import broadcast

bp = Blueprint("ta", __name__)

@bp.get("/courses")
@require_role("ta")
def my_courses():
    rows = get_db().execute(
        """SELECT c.course_id,c.name,c.code,s.name AS semester
           FROM courses c
           JOIN course_tas ct ON ct.course_id=c.course_id
           JOIN semesters s ON s.semester_id=c.semester_id
           WHERE ct.ta_id=?""", (g.user["user_id"],)
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
        "SELECT u.user_id,u.username FROM users u JOIN course_enrollments ce ON ce.student_id=u.user_id WHERE ce.course_id=?",
        (cid,)
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

    db = get_db()

    if not db.execute(
        "SELECT 1 FROM course_tas WHERE course_id=? AND ta_id=?",
        (course_id, g.user["user_id"])
    ).fetchone():
        return jsonify({"error": "Forbidden"}), 403

    cur = db.execute(
        "INSERT INTO attendance_sessions (course_id, session_date, topic, created_by) VALUES (?,?,?,?)",
        (course_id, session_date, topic, g.user["user_id"])
    )
    sid = cur.lastrowid

    inserted_records = []
    for rec in records:
        s  = rec.get("student_id")
        st = rec.get("status", "absent")
        if s and st in ("present", "absent", "late"):
            db.execute(
                "INSERT INTO attendance_records (att_session_id, student_id, status) VALUES (?,?,?)",
                (sid, s, st)
            )
            inserted_records.append({"student_id": s, "status": st})

    db.commit()

    broadcast("attendance_session_created", {
        "course_id":      course_id,
        "att_session_id": sid,
        "session_date":   session_date,
    })

    # Log the session creation with full details
    audit_log(
        action="TA_CREATE_SESSION",
        endpoint="/api/ta/attendance-sessions",
        user_id=g.user["user_id"],
        details=f"att_session_id={sid}",
        old_value=None,
        new_value={
            "att_session_id": sid,
            "course_id":      course_id,
            "session_date":   session_date,
            "topic":          topic,
            "created_by":     g.user["user_id"],
            "records":        inserted_records   # all students marked in this session
        }
    )

    return jsonify({"message": "Session created", "att_session_id": sid}), 201
    

@bp.get("/attendance-sessions")
@require_role("ta")
def list_sessions():
    rows = get_db().execute(
        """SELECT att.*,c.name AS course_name
           FROM attendance_sessions att
           JOIN courses c ON c.course_id=att.course_id
           JOIN course_tas ct ON ct.course_id=att.course_id
           WHERE ct.ta_id=? ORDER BY att.session_date DESC""", (g.user["user_id"],)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@bp.get("/attendance-sessions/<int:sid>/records")
@require_role("ta")
def session_records(sid):
    rows = get_db().execute(
        """SELECT ar.record_id, u.username, ar.status
           FROM attendance_records ar JOIN users u ON u.user_id=ar.student_id
           WHERE ar.att_session_id=? ORDER BY u.username""", (sid,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

# @bp.put("/records/<int:rid>")
# @require_role("ta")
# def update_record(rid):
#     status = (request.json or {}).get("status")
#     if status not in ("present","absent","late"):
#         return jsonify({"error": "Invalid status"}), 400
#     db = get_db()
#     db.execute("UPDATE attendance_records SET status=? WHERE record_id=?", (status, rid))
#     db.commit()
#     broadcast("attendance_updated", {
#         "record_id": rid,
#         "status":    status,
#     })
#     audit_log("TA_UPDATE_ATT", f"/api/ta/records/{rid}", g.user["user_id"], f"status={status}")
#     return jsonify({"message": "Record updated"})

@bp.put("/records/<int:rid>")
@require_role("ta")
def update_record(rid):
    status = (request.json or {}).get("status")
    if status not in ("present", "absent", "late"):
        return jsonify({"error": "Invalid status"}), 400

    db = get_db()

    # Fetch old value BEFORE making the change
    row = db.execute(
        "SELECT status, student_id, att_session_id FROM attendance_records WHERE record_id = ?",
        (rid,)
    ).fetchone()

    if not row:
        return jsonify({"error": "Record not found"}), 404

    old_status = row["status"]

    # Make the change — trigger fires here → raw_changes gets an entry
    db.execute(
        "UPDATE attendance_records SET status = ? WHERE record_id = ?",
        (status, rid)
    )
    db.commit()

    broadcast("attendance_updated", {
        "record_id": rid,
        "status":    status,
    })

    # Write to audit.log — this is the API fingerprint
    audit_log(
        action="TA_UPDATE_ATT",
        endpoint=f"/api/ta/records/{rid}",
        user_id=g.user["user_id"],
        details=f"record_id={rid}",
        old_value={
            "record_id":     rid,
            "student_id":    row["student_id"],
            "att_session_id": row["att_session_id"],
            "status":        old_status
        },
        new_value={
            "record_id":     rid,
            "student_id":    row["student_id"],
            "att_session_id": row["att_session_id"],
            "status":        status
        }
    )

    return jsonify({"message": "Record updated"})