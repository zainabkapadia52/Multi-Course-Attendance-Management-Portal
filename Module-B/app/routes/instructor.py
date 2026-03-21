from flask import Blueprint, request, jsonify, g   # fixed: was 'afrom'
from ..db import get_db
from ..middleware import require_role
from ..logger import audit_log
from ..events import broadcast

bp = Blueprint("instructor", __name__)

@bp.get("/courses")
@require_role("instructor")
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
        """SELECT ar.record_id, u.username, ar.status,
                  p.roll_no, p.program, p.batch
           FROM attendance_records ar
           JOIN users u ON u.user_id=ar.student_id
           LEFT JOIN user_profiles p ON p.user_id=u.user_id
           WHERE ar.att_session_id=?
           ORDER BY u.username""", (sid,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@bp.get("/corrections")
@require_role("instructor")
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
           JOIN course_instructors ci ON ci.course_id=cr.course_id
           WHERE ci.instructor_id=? AND c.semester_id=?
           ORDER BY (cr.status='pending') DESC, cr.created_at DESC""",
        (g.user["user_id"], sem["semester_id"])
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
    db.execute(
        "INSERT INTO correction_logs (req_id, action, acted_by, role) VALUES (?,?,?,?)",
        (req_id, "accepted", g.user["user_id"], "instructor")
    )
    db.commit()
    broadcast("correction_resolved", {
        "req_id":     req_id,
        "status":     "rejected",     # ← fixed
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
    db.execute(
        "INSERT INTO correction_logs (req_id, action, acted_by, role) VALUES (?,?,?,?)",
        (req_id, "rejected", g.user["user_id"], "instructor")
    )
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

@bp.get("/courses/<int:cid>/sessions")
@require_role("instructor")
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
def correction_logs(req_id):
    rows = get_db().execute(
        """SELECT cl.action, cl.role, cl.acted_at, u.username
           FROM correction_logs cl
           JOIN users u ON u.user_id=cl.acted_by
           WHERE cl.req_id=?
           ORDER BY cl.acted_at ASC""", (req_id,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@bp.delete("/courses/<int:cid>/tas/<int:tid>")
@require_role("instructor")
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
            session_list = []
            for s in sessions:
                records = db.execute(
                    """SELECT u.username, ar.status, p.roll_no
                       FROM attendance_records ar
                       JOIN users u ON u.user_id=ar.student_id
                       LEFT JOIN user_profiles p ON p.user_id=u.user_id
                       WHERE ar.att_session_id=?
                       ORDER BY u.username""",
                    (s["att_session_id"],)
                ).fetchall()
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
