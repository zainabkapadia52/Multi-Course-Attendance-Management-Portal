from flask import Blueprint, request, jsonify, g
from werkzeug.security import generate_password_hash
from ..db import get_db
from ..middleware import require_role
from ..logger import audit_log
from ..events import broadcast

bp = Blueprint("admin", __name__)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _course_detail(db, course_id):
    c = db.execute("SELECT * FROM courses WHERE course_id=?", (course_id,)).fetchone()
    if not c:
        return None
    instructors = db.execute(
        """SELECT u.user_id, u.username, p.department, p.designation
           FROM course_instructors ci
           JOIN users u ON u.user_id = ci.instructor_id
           LEFT JOIN user_profiles p ON p.user_id = u.user_id
           WHERE ci.course_id = ?""", (course_id,)
    ).fetchall()
    tas = db.execute(
        """SELECT u.user_id, u.username, p.department, p.designation
           FROM course_tas ct
           JOIN users u ON u.user_id = ct.ta_id
           LEFT JOIN user_profiles p ON p.user_id = u.user_id
           WHERE ct.course_id = ?""", (course_id,)
    ).fetchall()
    students = db.execute(
        """SELECT u.user_id, u.username, p.roll_no, p.program, p.batch
           FROM course_enrollments ce
           JOIN users u ON u.user_id = ce.student_id
           LEFT JOIN user_profiles p ON p.user_id = u.user_id
           WHERE ce.course_id = ?""", (course_id,)
    ).fetchall()
    return {
        "course":      dict(c),
        "instructors": [dict(i) for i in instructors],
        "tas":         [dict(t) for t in tas],
        "students":    [dict(s) for s in students],
    }

def _semester_courses(db, semester_id):
    courses = db.execute("SELECT course_id FROM courses WHERE semester_id=?", (semester_id,)).fetchall()
    return [_course_detail(db, c["course_id"]) for c in courses]

# ── Semesters ─────────────────────────────────────────────────────────────────

@bp.get("/active-semester")
@require_role("admin")
def active_semester():
    db  = get_db()
    sem = db.execute("SELECT * FROM semesters WHERE is_active=1 LIMIT 1").fetchone()
    return jsonify(dict(sem) if sem else {})

@bp.get("/semesters")
@require_role("admin")
def list_semesters():
    db = get_db()
    rows = db.execute("SELECT * FROM semesters ORDER BY semester_id DESC").fetchall()
    return jsonify([dict(r) for r in rows])

@bp.post("/semesters")
@require_role("admin")
def create_semester():
    d           = request.json or {}
    sem_number  = str(d.get("sem_number", "")).strip()
    acad_year   = str(d.get("acad_year", "")).strip()
    start_date  = d.get("start_date", "").strip()
    end_date    = d.get("end_date", "").strip()
    is_active   = int(d.get("is_active", 0))

    # Validate fields
    if sem_number not in ("1", "2"):
        return jsonify({"error": "Semester number must be 1 or 2"}), 400
    if not acad_year:
        return jsonify({"error": "Academic year is required"}), 400

    # Validate dates if both provided
    if start_date and end_date and start_date >= end_date:
        return jsonify({"error": "Start date must be before end date"}), 400

    # Build canonical name
    sem_label = "I" if sem_number == "1" else "II"
    name      = f"Sem {sem_label} {acad_year}"

    db = get_db()

    # Duplicate check — same semester number + same academic year
    exists = db.execute(
        "SELECT 1 FROM semesters WHERE LOWER(name)=LOWER(?)", (name,)
    ).fetchone()
    if exists:
        return jsonify({"error": f"Semester {sem_label} of {acad_year} already exists"}), 409

    if is_active:
        db.execute("UPDATE semesters SET is_active=0")
    db.execute(
        "INSERT INTO semesters (name,start_date,end_date,is_active) VALUES (?,?,?,?)",
        (name, start_date, end_date, is_active)
    )
    db.commit()
    audit_log("CREATE_SEMESTER", "/api/admin/semesters", g.user["user_id"], f"name={name}")
    return jsonify({"message": f"Semester '{name}' created"}), 201

@bp.get("/semesters/<int:sid>/courses")
@require_role("admin")
def semester_courses(sid):
    return jsonify(_semester_courses(get_db(), sid))

@bp.get("/archive")
@require_role("admin")
def archive():
    db   = get_db()
    sems = db.execute("SELECT * FROM semesters WHERE is_active=0 ORDER BY semester_id DESC").fetchall()
    return jsonify([{"semester": dict(s), "courses": _semester_courses(db, s["semester_id"])} for s in sems])

# ── Courses ───────────────────────────────────────────────────────────────────

@bp.get("/courses")
@require_role("admin")
def list_courses():
    db   = get_db()
    rows = db.execute("SELECT c.*,s.name AS semester_name FROM courses c JOIN semesters s USING(semester_id)").fetchall()
    return jsonify([dict(r) for r in rows])

@bp.post("/courses")
@require_role("admin")
def create_course():
    d   = request.json or {}
    name, code, semester_id = d.get("name","").strip(), d.get("code","").strip(), d.get("semester_id")
    if not name or not code or not semester_id:
        return jsonify({"error": "name, code, semester_id required"}), 400
    db = get_db()
    db.execute("INSERT INTO courses (name,code,semester_id) VALUES (?,?,?)", (name, code, semester_id))
    db.commit()
    audit_log("CREATE_COURSE", "/api/admin/courses", g.user["user_id"], f"code={code}")
    return jsonify({"message": "Course created"}), 201

@bp.delete("/courses/<int:cid>")
@require_role("admin")
def delete_course(cid):
    db     = get_db()
    course = db.execute("SELECT code FROM courses WHERE course_id=?", (cid,)).fetchone()
    if not course:
        return jsonify({"error": "Course not found"}), 404
    db.execute("DELETE FROM courses WHERE course_id=?", (cid,))
    db.commit()
    audit_log("DELETE_COURSE", f"/api/admin/courses/{cid}", g.user["user_id"], f"code={course['code']}")
    return jsonify({"message": f"Course {course['code']} deleted"})

# ── Instructor / TA / Student assignment ──────────────────────────────────────

@bp.post("/courses/<int:cid>/instructors")
@require_role("admin")
def assign_instructor(cid):
    iid = (request.json or {}).get("instructor_id")
    if not iid:
        return jsonify({"error": "instructor_id required"}), 400
    db = get_db()
    try:
        db.execute("INSERT INTO course_instructors VALUES (?,?)", (cid, iid))
        db.commit()
    except Exception:
        return jsonify({"error": "Already assigned"}), 409
    audit_log("ASSIGN_INSTRUCTOR", f"/api/admin/courses/{cid}/instructors", g.user["user_id"])
    return jsonify({"message": "Instructor assigned"}), 201

@bp.delete("/courses/<int:cid>/instructors/<int:iid>")
@require_role("admin")
def remove_instructor(cid, iid):
    db = get_db()
    db.execute("DELETE FROM course_instructors WHERE course_id=? AND instructor_id=?", (cid, iid))
    db.commit()
    audit_log("REMOVE_INSTRUCTOR", f"/api/admin/courses/{cid}/instructors/{iid}", g.user["user_id"])
    return jsonify({"message": "Instructor removed"})

@bp.post("/courses/<int:cid>/tas")
@require_role("admin")
def assign_ta(cid):
    tid = (request.json or {}).get("ta_id")
    if not tid:
        return jsonify({"error": "ta_id required"}), 400
    db = get_db()
    try:
        db.execute("INSERT INTO course_tas VALUES (?,?)", (cid, tid))
        db.commit()
    except Exception:
        return jsonify({"error": "Already assigned"}), 409
    audit_log("ASSIGN_TA", f"/api/admin/courses/{cid}/tas", g.user["user_id"])
    return jsonify({"message": "TA assigned"}), 201

@bp.delete("/courses/<int:cid>/tas/<int:tid>")
@require_role("admin")
def remove_ta(cid, tid):
    db = get_db()
    db.execute("DELETE FROM course_tas WHERE course_id=? AND ta_id=?", (cid, tid))
    db.commit()
    audit_log("REMOVE_TA", f"/api/admin/courses/{cid}/tas/{tid}", g.user["user_id"])
    return jsonify({"message": "TA removed"})

@bp.post("/courses/<int:cid>/enrollments")
@require_role("admin")
def enroll_student(cid):
    sid = (request.json or {}).get("student_id")
    if not sid:
        return jsonify({"error": "student_id required"}), 400
    db = get_db()
    try:
        db.execute("INSERT INTO course_enrollments VALUES (?,?)", (cid, sid))
        db.commit()
    except Exception:
        return jsonify({"error": "Already enrolled"}), 409
    audit_log("ENROLL_STUDENT", f"/api/admin/courses/{cid}/enrollments", g.user["user_id"])
    return jsonify({"message": "Student enrolled"}), 201

@bp.delete("/courses/<int:cid>/enrollments/<int:sid>")
@require_role("admin")
def remove_enrollment(cid, sid):
    db = get_db()
    db.execute("DELETE FROM course_enrollments WHERE course_id=? AND student_id=?", (cid, sid))
    db.commit()
    audit_log("REMOVE_ENROLLMENT", f"/api/admin/courses/{cid}/enrollments/{sid}", g.user["user_id"])
    return jsonify({"message": "Student removed"})

# ── Users ─────────────────────────────────────────────────────────────────────

@bp.get("/users")
@require_role("admin")
def list_users():
    db   = get_db()
    rows = db.execute(
        """SELECT u.user_id, u.username, u.role, u.last_login,
                  p.roll_no, p.program, p.batch, p.department, p.designation
           FROM users u LEFT JOIN user_profiles p ON p.user_id = u.user_id
           ORDER BY u.role, u.username"""
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@bp.post("/users")
@require_role("admin")
def create_user():
    d        = request.json or {}
    username = d.get("username", "").strip()
    password = d.get("password", "").strip()
    role     = d.get("role", "")
    if not username or not password or role not in ("admin","instructor","student","ta","dean"):
        return jsonify({"error": "username, password, and valid role required"}), 400
    db = get_db()
    try:
        cur     = db.execute(
            "INSERT INTO users (username,pwd_hash,role) VALUES (?,?,?)",
            (username, generate_password_hash(password), role)
        )
        user_id = cur.lastrowid
        if role == "instructor":
                db.execute(
                "INSERT INTO user_profiles (user_id,department,designation) VALUES (?,?,?)",
                (user_id, d.get("department",""), d.get("designation",""))
            )
        elif role == "ta":
            db.execute(
                "INSERT INTO user_profiles (user_id,roll_no,program,batch) VALUES (?,?,?,?)",
                (user_id, d.get("roll_no",""), d.get("program",""), d.get("batch",""))
            )
        elif role == "student":
            db.execute(
                "INSERT INTO user_profiles (user_id,roll_no,program,batch) VALUES (?,?,?,?)",
                (user_id, d.get("roll_no",""), d.get("program",""), d.get("batch",""))
            )
        db.commit()
    except Exception:
        return jsonify({"error": "Username already exists"}), 409
    audit_log("CREATE_USER", "/api/admin/users", g.user["user_id"], f"created={username} role={role}")
    return jsonify({"message": f"User {username} created"}), 201

@bp.delete("/users/<int:uid>")
@require_role("admin")
def delete_user(uid):
    db   = get_db()
    user = db.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user["role"] == "admin":
        cnt = db.execute("SELECT COUNT(*) AS c FROM users WHERE role='admin'").fetchone()["c"]
        if cnt <= 1:
            return jsonify({"error": "Cannot delete the last admin account"}), 400
    db.execute("DELETE FROM users WHERE user_id=?", (uid,))
    db.commit()
    audit_log("DELETE_USER", f"/api/admin/users/{uid}", g.user["user_id"], f"deleted={user['username']}")
    return jsonify({"message": "User permanently deleted"})

# ── Dropdown helpers ──────────────────────────────────────────────────────────

@bp.get("/instructors")
@require_role("admin")
def list_instructors():
    rows = get_db().execute("SELECT user_id,username FROM users WHERE role='instructor'").fetchall()
    return jsonify([dict(r) for r in rows])

@bp.get("/courses/<int:cid>/available-instructors")
@require_role("admin")
def available_instructors(cid):
    """Instructors NOT yet assigned to this course."""
    rows = get_db().execute(
        """SELECT u.user_id, u.username FROM users u
           WHERE u.role='instructor'
           AND u.user_id NOT IN (
               SELECT instructor_id FROM course_instructors WHERE course_id=?
           )""", (cid,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@bp.get("/students")
@require_role("admin")
def list_students():
    rows = get_db().execute("SELECT user_id,username FROM users WHERE role='student'").fetchall()
    return jsonify([dict(r) for r in rows])

@bp.get("/tas")
@require_role("admin")
def list_tas():
    rows = get_db().execute("SELECT user_id,username FROM users WHERE role='ta'").fetchall()
    return jsonify([dict(r) for r in rows])

# ── Attendance override ───────────────────────────────────────────────────────

@bp.get("/courses/<int:cid>/sessions")
@require_role("admin")
def course_sessions(cid):
    rows = get_db().execute(
        "SELECT att_session_id,session_date,topic FROM attendance_sessions WHERE course_id=? ORDER BY session_date DESC",
        (cid,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@bp.get("/sessions/<int:sid>/records")
@require_role("admin")
def session_records(sid):
    rows = get_db().execute(
        """SELECT ar.record_id, ar.student_id, u.username, ar.status
           FROM attendance_records ar JOIN users u ON u.user_id=ar.student_id
           WHERE ar.att_session_id=? ORDER BY u.username""", (sid,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@bp.put("/records/<int:rid>")
@require_role("admin")
def update_record(rid):
    status = (request.json or {}).get("status")
    if status not in ("present","absent"):
        return jsonify({"error": "Invalid status"}), 400
    db = get_db()
    db.execute("UPDATE attendance_records SET status=? WHERE record_id=?", (status, rid))
    db.commit()
    broadcast("attendance_updated", {
        "record_id": rid,
        "status":    status,
    })
    audit_log("ADMIN_ATT_OVERRIDE", f"/api/admin/records/{rid}", g.user["user_id"], f"status={status}")
    return jsonify({"message": "Record updated"})