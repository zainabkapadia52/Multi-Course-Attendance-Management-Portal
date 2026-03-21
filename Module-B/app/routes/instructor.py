# afrom flask import Blueprint, request, jsonify, g
# from ..db import get_db
# from ..middleware import require_role
# from ..logger import audit_log
# from ..events import broadcast

# bp = Blueprint("instructor", __name__)

# @bp.get("/courses")
# @require_role("instructor")
# def my_courses():
#     rows = get_db().execute(
#         """SELECT c.course_id,c.name,c.code,s.name AS semester
#            FROM courses c
#            JOIN course_instructors ci ON ci.course_id=c.course_id
#            JOIN semesters s ON s.semester_id=c.semester_id
#            WHERE ci.instructor_id=?""", (g.user["user_id"],)
#     ).fetchall()
#     return jsonify([dict(r) for r in rows])

# @bp.get("/courses/<int:cid>/students")
# @require_role("instructor")
# def course_students(cid):
#     db = get_db()
#     if not db.execute("SELECT 1 FROM course_instructors WHERE course_id=? AND instructor_id=?",
#                       (cid, g.user["user_id"])).fetchone():
#         return jsonify({"error": "Forbidden"}), 403
#     rows = db.execute(
#         "SELECT u.user_id,u.username FROM users u JOIN course_enrollments ce ON ce.student_id=u.user_id WHERE ce.course_id=?",
#         (cid,)
#     ).fetchall()
#     return jsonify([dict(r) for r in rows])

# @bp.post("/attendance-sessions")
# @require_role("instructor")
# def create_session():
#     d            = request.json or {}
#     course_id    = d.get("course_id")
#     session_date = d.get("session_date")
#     topic        = d.get("topic","")
#     records      = d.get("records",[])
#     if not course_id or not session_date:
#         return jsonify({"error": "course_id and session_date required"}), 400
#     db = get_db()
#     if not db.execute("SELECT 1 FROM course_instructors WHERE course_id=? AND instructor_id=?",
#                       (course_id, g.user["user_id"])).fetchone():
#         return jsonify({"error": "Forbidden"}), 403
#     cur = db.execute(
#         "INSERT INTO attendance_sessions (course_id,session_date,topic,created_by) VALUES (?,?,?,?)",
#         (course_id, session_date, topic, g.user["user_id"])
#     )
#     sid = cur.lastrowid
#     for rec in records:
#         s, st = rec.get("student_id"), rec.get("status","absent")
#         if s and st in ("present","absent","late"):
#             db.execute("INSERT INTO attendance_records (att_session_id,student_id,status) VALUES (?,?,?)", (sid, s, st))
#     db.commit()
#     broadcast("attendance_session_created", {
#         "course_id":    course_id,
#         "att_session_id": sid,
#         "session_date": session_date,
#     })
#     audit_log("CREATE_ATT_SESSION", "/api/instructor/attendance-sessions", g.user["user_id"], f"course={course_id}")
#     return jsonify({"message": "Session created", "att_session_id": sid}), 201

# @bp.get("/attendance-sessions")
# @require_role("instructor")
# def list_sessions():
#     rows = get_db().execute(
#         """SELECT att.*,c.name AS course_name
#            FROM attendance_sessions att
#            JOIN courses c ON c.course_id=att.course_id
#            JOIN course_instructors ci ON ci.course_id=att.course_id
#            WHERE ci.instructor_id=? ORDER BY att.session_date DESC""", (g.user["user_id"],)
#     ).fetchall()
#     return jsonify([dict(r) for r in rows])

# @bp.get("/attendance-sessions/<int:sid>/records")
# @require_role("instructor")
# def session_records(sid):
#     db = get_db()
#     if not db.execute(
#         """SELECT 1 FROM attendance_sessions att
#            JOIN course_instructors ci ON ci.course_id=att.course_id
#            WHERE att.att_session_id=? AND ci.instructor_id=?""",
#         (sid, g.user["user_id"])
#     ).fetchone():
#         return jsonify({"error": "Forbidden"}), 403
#     rows = db.execute(
#         """SELECT ar.record_id, u.username, ar.status
#            FROM attendance_records ar JOIN users u ON u.user_id=ar.student_id
#            WHERE ar.att_session_id=? ORDER BY u.username""", (sid,)
#     ).fetchall()
#     return jsonify([dict(r) for r in rows])

# @bp.get("/corrections")
# @require_role("instructor")
# def list_corrections():
#     rows = get_db().execute(
#         """SELECT cr.*,u.username AS student_name,c.name AS course_name,
#                   att.session_date,att.topic
#            FROM correction_requests cr
#            JOIN users u ON u.user_id=cr.student_id
#            JOIN courses c ON c.course_id=cr.course_id
#            JOIN attendance_sessions att ON att.att_session_id=cr.att_session_id
#            JOIN course_instructors ci ON ci.course_id=cr.course_id
#            WHERE ci.instructor_id=?
#            ORDER BY (cr.status='pending') DESC, cr.created_at DESC""", (g.user["user_id"],)
#     ).fetchall()
#     return jsonify([dict(r) for r in rows])

# @bp.post("/corrections/<int:req_id>/accept")
# @require_role("instructor")
# def accept_correction(req_id):
#     db  = get_db()
#     req = db.execute(
#         """SELECT cr.* FROM correction_requests cr
#            JOIN course_instructors ci ON ci.course_id=cr.course_id
#            WHERE cr.req_id=? AND ci.instructor_id=?""",
#         (req_id, g.user["user_id"])
#     ).fetchone()
#     if not req:
#         return jsonify({"error": "Not found or forbidden"}), 404
#     if req["status"] != "pending":
#         return jsonify({"error": "Already resolved"}), 400
#     db.execute("UPDATE correction_requests SET status='accepted' WHERE req_id=?", (req_id,))
#     db.execute("UPDATE attendance_records SET status='present' WHERE att_session_id=? AND student_id=?",
#                (req["att_session_id"], req["student_id"]))
#     db.commit()
#     broadcast("correction_resolved", {
#         "req_id":    req_id,
#         "status":    "accepted",
#         "student_id": req["student_id"],
#         "course_id":  req["course_id"],
#     })

#     audit_log("ACCEPT_CORRECTION", f"/api/instructor/corrections/{req_id}/accept", g.user["user_id"])
#     return jsonify({"message": "Accepted; attendance updated"})

# @bp.post("/corrections/<int:req_id>/reject")
# @require_role("instructor")
# def reject_correction(req_id):
#     db  = get_db()
#     req = db.execute(
#         """SELECT cr.* FROM correction_requests cr
#            JOIN course_instructors ci ON ci.course_id=cr.course_id
#            WHERE cr.req_id=? AND ci.instructor_id=?""",
#         (req_id, g.user["user_id"])
#     ).fetchone()
#     if not req:
#         return jsonify({"error": "Not found or forbidden"}), 404
#     if req["status"] != "pending":
#         return jsonify({"error": "Already resolved"}), 400
#     db.execute("UPDATE correction_requests SET status='rejected' WHERE req_id=?", (req_id,))
#     db.commit()
#     broadcast("correction_resolved", {
#         "req_id":    req_id,
#         "status":    "accepted",
#         "student_id": req["student_id"],
#         "course_id":  req["course_id"],
#     })

#     audit_log("REJECT_CORRECTION", f"/api/instructor/corrections/{req_id}/reject", g.user["user_id"])
#     return jsonify({"message": "Rejected"})

from flask import Blueprint, request, jsonify, g   # fixed: was 'afrom'
from ..db import get_db
from ..middleware import require_role
from ..logger import audit_log
from ..events import broadcast

bp = Blueprint("instructor", __name__)

@bp.get("/courses")
@require_role("instructor")
def my_courses():
    rows = get_db().execute(
        """SELECT c.course_id,c.name,c.code,s.name AS semester
           FROM courses c
           JOIN course_instructors ci ON ci.course_id=c.course_id
           JOIN semesters s ON s.semester_id=c.semester_id
           WHERE ci.instructor_id=?""", (g.user["user_id"],)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@bp.get("/courses/<int:cid>/students")
@require_role("instructor")
def course_students(cid):
    db = get_db()
    if not db.execute("SELECT 1 FROM course_instructors WHERE course_id=? AND instructor_id=?",
                      (cid, g.user["user_id"])).fetchone():
        return jsonify({"error": "Forbidden"}), 403
    rows = db.execute(
        "SELECT u.user_id,u.username FROM users u JOIN course_enrollments ce ON ce.student_id=u.user_id WHERE ce.course_id=?",
        (cid,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@bp.post("/attendance-sessions")
@require_role("instructor")
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
    for rec in records:
        s, st = rec.get("student_id"), rec.get("status","absent")
        if s and st in ("present","absent","late"):
            db.execute(
                "INSERT INTO attendance_records (att_session_id,student_id,status) VALUES (?,?,?)",
                (sid, s, st)
            )
            inserted_records.append({"student_id": s, "status": st})
    db.commit()
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
def list_sessions():
    rows = get_db().execute(
        """SELECT att.*,c.name AS course_name
           FROM attendance_sessions att
           JOIN courses c ON c.course_id=att.course_id
           JOIN course_instructors ci ON ci.course_id=att.course_id
           WHERE ci.instructor_id=? ORDER BY att.session_date DESC""", (g.user["user_id"],)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@bp.get("/attendance-sessions/<int:sid>/records")
@require_role("instructor")
def session_records(sid):
    db = get_db()
    if not db.execute(
        """SELECT 1 FROM attendance_sessions att
           JOIN course_instructors ci ON ci.course_id=att.course_id
           WHERE att.att_session_id=? AND ci.instructor_id=?""",
        (sid, g.user["user_id"])
    ).fetchone():
        return jsonify({"error": "Forbidden"}), 403
    rows = db.execute(
        """SELECT ar.record_id, u.username, ar.status
           FROM attendance_records ar JOIN users u ON u.user_id=ar.student_id
           WHERE ar.att_session_id=? ORDER BY u.username""", (sid,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@bp.get("/corrections")
@require_role("instructor")
def list_corrections():
    rows = get_db().execute(
        """SELECT cr.*,u.username AS student_name,c.name AS course_name,
                  att.session_date,att.topic
           FROM correction_requests cr
           JOIN users u ON u.user_id=cr.student_id
           JOIN courses c ON c.course_id=cr.course_id
           JOIN attendance_sessions att ON att.att_session_id=cr.att_session_id
           JOIN course_instructors ci ON ci.course_id=cr.course_id
           WHERE ci.instructor_id=?
           ORDER BY (cr.status='pending') DESC, cr.created_at DESC""", (g.user["user_id"],)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@bp.post("/corrections/<int:req_id>/accept")
@require_role("instructor")
def accept_correction(req_id):
    db  = get_db()
    req = db.execute(
        """SELECT cr.* FROM correction_requests cr
           JOIN course_instructors ci ON ci.course_id=cr.course_id
           WHERE cr.req_id=? AND ci.instructor_id=?""",
        (req_id, g.user["user_id"])
    ).fetchone()
    if not req:
        return jsonify({"error": "Not found or forbidden"}), 404
    if req["status"] != "pending":
        return jsonify({"error": "Already resolved"}), 400

    # Fetch old attendance status before updating
    att_row = db.execute(
        "SELECT record_id, status FROM attendance_records WHERE att_session_id=? AND student_id=?",
        (req["att_session_id"], req["student_id"])
    ).fetchone()

    db.execute("UPDATE correction_requests SET status='accepted' WHERE req_id=?", (req_id,))
    db.execute(
        "UPDATE attendance_records SET status='present' WHERE att_session_id=? AND student_id=?",
        (req["att_session_id"], req["student_id"])
    )
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
def reject_correction(req_id):
    db  = get_db()
    req = db.execute(
        """SELECT cr.* FROM correction_requests cr
           JOIN course_instructors ci ON ci.course_id=cr.course_id
           WHERE cr.req_id=? AND ci.instructor_id=?""",
        (req_id, g.user["user_id"])
    ).fetchone()
    if not req:
        return jsonify({"error": "Not found or forbidden"}), 404
    if req["status"] != "pending":
        return jsonify({"error": "Already resolved"}), 400
    db.execute("UPDATE correction_requests SET status='rejected' WHERE req_id=?", (req_id,))
    db.commit()
    broadcast("correction_resolved", {
        "req_id":     req_id,
        "status":     "rejected",   # fixed: was "accepted" in original
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