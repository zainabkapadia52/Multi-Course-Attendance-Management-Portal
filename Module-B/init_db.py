"""
init_db.py
================
Large-scale seed script for the Multi-Course Attendance Management System.
Reads schema from sql/schema.sql (single source of truth).

Generates:
  • 2  semesters
  • 10 courses  (5 per semester)
  •  5 instructors + 4 TAs + 1 admin + 1 dean
  • 60 students
  • ~120 attendance sessions
  • ~2400+ attendance records
  • ~40  correction requests
  • correction_logs for every accepted/rejected correction

All passwords: password123
"""

import sqlite3
import random
from datetime import date, timedelta
from werkzeug.security import generate_password_hash
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

DB_PATH     = "module_b.db"
SCHEMA_PATH = "sql/schema.sql"
random.seed(42)

PWD = generate_password_hash("password123")

# ── helpers ───────────────────────────────────────────────────────────────────

def insert_user(conn, username, role):
    cur = conn.execute(
        "INSERT OR IGNORE INTO users (username, pwd_hash, role) VALUES (?,?,?)",
        (username, PWD, role)
    )
    if cur.lastrowid:
        return cur.lastrowid
    return conn.execute(
        "SELECT user_id FROM users WHERE username = ?", (username,)
    ).fetchone()[0]


def daterange(start: date, end: date, step_days: int = 4):
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            yield cur
        cur += timedelta(days=step_days)


def weighted_status():
    return random.choices(
        ["present", "absent", "late"],
        weights=[75, 15, 10]
    )[0]


# ── static people data ────────────────────────────────────────────────────────

INSTRUCTOR_DATA = [
    # (username, department, designation)
    ("prof_singh",  "Computer Science",       "Associate Professor"),
    ("prof_rao",    "Mathematics",            "Assistant Professor"),
    ("prof_mehta",  "Electronics",            "Professor"),
    ("prof_sharma", "Computer Science",       "Assistant Professor"),
    ("prof_jain",   "Mechanical Engineering", "Associate Professor"),
]

# TAs are M.Tech students — full profiles including roll_no, program, batch
TA_DATA = [
    # (username, department, program, batch, roll_no, designation)
    ("ta_amit",  "Computer Science", "M.Tech CSE", "2023", "2311TA001", "Teaching Assistant"),
    ("ta_priya", "Mathematics",      "M.Tech CSE", "2023", "2311TA002", "Teaching Assistant"),
    ("ta_ravi",  "Electronics",      "M.Tech EE",  "2022", "2211TA003", "Teaching Assistant"),
    ("ta_sneha", "Computer Science", "M.Tech CSE", "2022", "2211TA004", "Teaching Assistant"),
]

FIRST_NAMES = [
    "Aarav","Aditi","Akash","Ananya","Arjun","Ayesha","Chirag","Deepika",
    "Dev","Divya","Gaurav","Harsha","Ishaan","Jiya","Kabir","Kavya",
    "Kunal","Lakshmi","Manav","Meera","Mihir","Muskan","Nandini","Nikhil",
    "Nisha","Parth","Pooja","Pranav","Priya","Rahul","Riya","Rohan",
    "Sakshi","Sarthak","Shivani","Shreya","Siddharth","Simran","Snehal","Tanvi",
    "Tarun","Uday","Umang","Vandana","Varun","Vidya","Vikas","Vinay",
    "Vishal","Yash","Aman","Bhavna","Chetan","Disha","Ekta","Farhan",
    "Gauri","Hemant","Isha","Jayesh",
]
LAST_NAMES = [
    "Patel","Sharma","Singh","Verma","Gupta","Joshi","Mehta","Shah",
    "Kumar","Mishra","Agarwal","Nair","Reddy","Yadav","Tiwari","Chopra",
    "Bose","Malhotra","Bhat","Pillai",
]
PROGRAMS = ["B.Tech CSE", "B.Tech EE", "B.Tech ME", "M.Tech CSE", "M.Tech EE"]
BATCHES  = ["2022", "2023", "2024", "2025"]

# ── course & topic data ───────────────────────────────────────────────────────

COURSE_DEFS = [
    # (name, code, sem_idx, instructor_username)
    ("Database Systems",                "CS432", 0, "prof_singh"),
    ("Design & Analysis of Algorithms", "CS301", 0, "prof_rao"),
    ("Computer Networks",               "CS303", 0, "prof_sharma"),
    ("Linear Algebra",                  "MA201", 0, "prof_rao"),
    ("Embedded Systems",                "EC401", 0, "prof_mehta"),
    ("Operating Systems",               "CS302", 1, "prof_singh"),
    ("Machine Learning",                "CS501", 1, "prof_sharma"),
    ("Digital Signal Processing",       "EC302", 1, "prof_mehta"),
    ("Numerical Methods",               "MA301", 1, "prof_jain"),
    ("Theory of Computation",           "CS401", 1, "prof_singh"),
]

COURSE_TA = {
    "CS432": "ta_amit",
    "CS301": "ta_priya",
    "CS303": "ta_sneha",
    "EC401": "ta_ravi",
    "CS501": "ta_sneha",
    "EC302": "ta_ravi",
}

TOPICS = {
    "CS432": ["ER Diagrams","Relational Model","SQL Basics","Joins","Aggregates",
              "Subqueries","Indexing","B+ Trees","Query Optimization",
              "Transactions","Concurrency Control","Recovery","NoSQL Overview"],
    "CS301": ["Asymptotic Notation","Recurrences","Sorting","Divide & Conquer",
              "Dynamic Programming","Greedy Algorithms","BFS/DFS",
              "Shortest Paths","MST","NP-Completeness","Approximation Algos"],
    "CS303": ["OSI Model","TCP/IP Stack","IP Addressing","Subnetting","Routing",
              "TCP Basics","UDP","HTTP","DNS","Security Basics","Wireless Networks"],
    "MA201": ["Vector Spaces","Basis & Dimension","Linear Maps","Matrix Operations",
              "Determinants","Eigenvalues","Eigenvectors","SVD","PCA Introduction"],
    "EC401": ["Microcontrollers","GPIO","Interrupts","Timers","ADC/DAC",
              "UART","SPI","I2C","RTOS Basics","Power Management"],
    "CS302": ["Processes & Threads","CPU Scheduling","Synchronisation","Deadlocks",
              "Memory Management","Paging","Segmentation","Virtual Memory",
              "File Systems","I/O Systems","Security"],
    "CS501": ["Intro to ML","Linear Regression","Logistic Regression","Decision Trees",
              "Ensemble Methods","SVM","Neural Networks","CNN","RNN","Clustering",
              "PCA","Model Evaluation","Bias-Variance"],
    "EC302": ["Signals & Systems","Fourier Transform","Sampling Theorem","DFT","FFT",
              "FIR Filters","IIR Filters","Z-Transform","Spectral Analysis"],
    "MA301": ["Error Analysis","Root Finding","Interpolation","Numerical Differentiation",
              "Numerical Integration","ODE Solvers","Linear Systems","Iterative Methods"],
    "CS401": ["Automata Theory","Regular Languages","CFGs",
              "Pushdown Automata","Turing Machines","Decidability","Complexity Classes"],
}

SEM_DATES = [
    (date(2026, 1,  5), date(2026, 5, 20)),
    (date(2025, 7, 14), date(2025, 11, 28)),
]

CORRECTION_REASONS = [
    "I was present but marked absent due to a system error.",
    "I submitted a medical certificate for this date.",
    "I had an approved inter-college event on this day.",
    "I was representing the institute at a sports meet.",
    "Network issue prevented QR scan; professor can verify.",
    "I was late due to a lab overrun from the previous slot.",
    "I have a signed permission letter from the instructor.",
    "I was attending a mandatory placement test.",
]

# ── main seed function ────────────────────────────────────────────────────────

def init():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row

    # ── schema ────────────────────────────────────────────────────────────────
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    print("  ✓  Schema loaded from", SCHEMA_PATH)

    # ── admin ─────────────────────────────────────────────────────────────────
    admin_id = insert_user(conn, "admin", "admin")
    conn.execute(
        """INSERT OR IGNORE INTO user_profiles
           (user_id, department, designation)
           VALUES (?,?,?)""",
        (admin_id, "Administration", "System Administrator")
    )

    # ── dean ──────────────────────────────────────────────────────────────────
    dean_id = insert_user(conn, "dean_joshi", "dean")
    conn.execute(
        """INSERT OR IGNORE INTO user_profiles
           (user_id, department, designation)
           VALUES (?,?,?)""",
        (dean_id, "Administration", "Dean of Academics")
    )

    # ── instructors ───────────────────────────────────────────────────────────
    instructor_ids = {}
    for uname, dept, desig in INSTRUCTOR_DATA:
        uid = insert_user(conn, uname, "instructor")
        conn.execute(
            """INSERT OR IGNORE INTO user_profiles
               (user_id, department, designation)
               VALUES (?,?,?)""",
            (uid, dept, desig)
        )
        instructor_ids[uname] = uid
    print(f"  ✓  {len(instructor_ids)} instructors inserted")

    # ── TAs ───────────────────────────────────────────────────────────────────
    # TAs are M.Tech students — full profile including roll_no, program, batch
    ta_ids = {}
    for uname, dept, program, batch, roll_no, desig in TA_DATA:
        uid = insert_user(conn, uname, "ta")
        conn.execute(
            """INSERT OR IGNORE INTO user_profiles
               (user_id, roll_no, program, batch, department, designation)
               VALUES (?,?,?,?,?,?)""",
            (uid, roll_no, program, batch, dept, desig)
        )
        ta_ids[uname] = uid
    print(f"  ✓  {len(ta_ids)} TAs inserted")

    # ── students ──────────────────────────────────────────────────────────────
    student_ids = []
    used_rolls  = set()
    for i, fname in enumerate(FIRST_NAMES):
        lname   = random.choice(LAST_NAMES)
        uname   = f"{fname.lower()}_{lname.lower()}{i}"
        program = random.choice(PROGRAMS)
        batch   = random.choice(BATCHES)
        roll    = f"{batch[2:]}11{str(i+1).zfill(3)}"
        while roll in used_rolls:
            roll = roll[:-3] + str(random.randint(100, 999))
        used_rolls.add(roll)
        dept = ("Computer Science"        if "CSE" in program else
                "Electronics"            if "EE"  in program else
                "Mechanical Engineering")
        uid = insert_user(conn, uname, "student")
        conn.execute(
            """INSERT OR IGNORE INTO user_profiles
               (user_id, roll_no, program, batch, department, designation)
               VALUES (?,?,?,?,?,?)""",
            (uid, roll, program, batch, dept, "Student")
        )
        student_ids.append((uid, program, dept))
    print(f"  ✓  {len(student_ids)} students inserted")

    # ── semesters ─────────────────────────────────────────────────────────────
    sem_ids = []
    for idx, (label, is_active) in enumerate([("Sem II 2025-26", 1), ("Sem I 2025-26", 0)]):
        start, end = SEM_DATES[idx]
        cur = conn.execute(
            "INSERT OR IGNORE INTO semesters (name, start_date, end_date, is_active) VALUES (?,?,?,?)",
            (label, start.isoformat(), end.isoformat(), is_active)
        )
        sid = cur.lastrowid or conn.execute(
            "SELECT semester_id FROM semesters WHERE name = ?", (label,)
        ).fetchone()[0]
        sem_ids.append(sid)

    # ── courses ───────────────────────────────────────────────────────────────
    course_ids   = {}
    course_instr = {}   # code → instructor_id (needed for correction_logs)
    for name, code, sem_idx, instr_uname in COURSE_DEFS:
        cur = conn.execute(
            "INSERT OR IGNORE INTO courses (name, code, semester_id) VALUES (?,?,?)",
            (name, code, sem_ids[sem_idx])
        )
        cid = cur.lastrowid or conn.execute(
            "SELECT course_id FROM courses WHERE code = ?", (code,)
        ).fetchone()[0]
        course_ids[code]   = cid
        course_instr[code] = instructor_ids[instr_uname]
        conn.execute("INSERT OR IGNORE INTO course_instructors VALUES (?,?)",
                     (cid, instructor_ids[instr_uname]))
        if code in COURSE_TA:
            conn.execute("INSERT OR IGNORE INTO course_tas VALUES (?,?)",
                         (cid, ta_ids[COURSE_TA[code]]))
    print(f"  ✓  {len(course_ids)} courses inserted")

    # reverse map: course_id → instructor_id (for correction_logs)
    cid_to_instr = {course_ids[code]: course_instr[code] for code in course_ids}

    # ── enrollments ───────────────────────────────────────────────────────────
    cs_codes = ["CS432","CS301","CS303","CS302","CS501","CS401"]
    ee_codes = ["MA201","EC401","EC302","MA301","CS303"]
    me_codes = ["MA201","MA301","EC401","CS302"]

    enrollments = set()
    for uid, program, dept in student_ids:
        pool     = cs_codes if "CSE" in program else (ee_codes if "EE" in program else me_codes)
        extra    = [c for c in cs_codes if c not in pool]
        combined = pool + extra
        for code in combined[:random.randint(3, 5)]:
            enrollments.add((course_ids[code], uid))

    conn.executemany("INSERT OR IGNORE INTO course_enrollments VALUES (?,?)", list(enrollments))
    print(f"  ✓  {len(enrollments)} enrolments inserted")

    # ── attendance sessions ───────────────────────────────────────────────────
    all_sessions = []
    for name, code, sem_idx, instr_uname in COURSE_DEFS:
        cid   = course_ids[code]
        instr = instructor_ids[instr_uname]
        start, end = SEM_DATES[sem_idx]
        topics = TOPICS[code]
        dates  = list(daterange(start, end))[:len(topics)]
        for d, topic in zip(dates, topics):
            cur = conn.execute(
                "INSERT INTO attendance_sessions (course_id, session_date, topic, created_by) VALUES (?,?,?,?)",
                (cid, d.isoformat(), topic, instr)
            )
            all_sessions.append((cur.lastrowid, code))
    print(f"  ✓  {len(all_sessions)} attendance sessions inserted")

    # ── attendance records ────────────────────────────────────────────────────
    enrolled_map: dict[int, list[int]] = {}
    for cid, uid in enrollments:
        enrolled_map.setdefault(cid, []).append(uid)

    records = []
    for sess_id, code in all_sessions:
        cid = course_ids[code]
        for stu_id in enrolled_map.get(cid, []):
            records.append((sess_id, stu_id, weighted_status()))

    conn.executemany(
        "INSERT OR IGNORE INTO attendance_records (att_session_id, student_id, status) VALUES (?,?,?)",
        records
    )
    print(f"  ✓  {len(records)} attendance records inserted")

    # ── correction requests + correction_logs ─────────────────────────────────
    absent_set  = {(r[0], r[1]) for r in records if r[2] == "absent"}
    absent_list = [
        (sess_id, stu_id, course_ids[code])
        for sess_id, code in all_sessions
        for stu_id in enrolled_map.get(course_ids[code], [])
        if (sess_id, stu_id) in absent_set
    ]

    sample      = random.sample(absent_list, min(40, len(absent_list)))
    cr_statuses = ["pending","pending","pending","accepted","rejected"]
    inserted_cr = 0
    inserted_cl = 0

    for sess_id, stu_id, cid in sample:
        status = random.choice(cr_statuses)
        try:
            cur = conn.execute(
                """INSERT OR IGNORE INTO correction_requests
                   (student_id, course_id, att_session_id, reason, status)
                   VALUES (?,?,?,?,?)""",
                (stu_id, cid, sess_id,
                 random.choice(CORRECTION_REASONS),
                 status)
            )
            req_id = cur.lastrowid
            if not req_id:
                continue

            inserted_cr += 1

            # For every accepted or rejected request write a correction_log entry.
            # acted_by = the instructor responsible for that course.
            # No trigger on correction_logs — it is append-only by design.
            if status in ("accepted", "rejected"):
                acted_by = cid_to_instr.get(cid)
                if acted_by:
                    conn.execute(
                        """INSERT INTO correction_logs
                           (req_id, action, acted_by, role, acted_at)
                           VALUES (?,?,?,?,datetime('now'))""",
                        (req_id, status, acted_by, "instructor")
                    )
                    inserted_cl += 1

                # If accepted also mark attendance as present
                if status == "accepted":
                    conn.execute(
                        """UPDATE attendance_records
                           SET status = 'present'
                           WHERE att_session_id = ? AND student_id = ?""",
                        (sess_id, stu_id)
                    )

        except sqlite3.IntegrityError:
            pass

    print(f"  ✓  {inserted_cr} correction requests inserted")
    print(f"  ✓  {inserted_cl} correction_logs entries inserted")

    first_student = conn.execute(
        "SELECT username FROM users WHERE role='student' ORDER BY user_id LIMIT 1"
    ).fetchone()[0]

    # ── triggers ──────────────────────────────────────────────────────────────
    # correction_logs has NO trigger intentionally — it is append-only.
    # Only the system writes to it on accept/reject. No unauthorized modification
    # is possible through normal usage so tracking it adds noise with no value.

    conn.execute("DROP TRIGGER IF EXISTS trg_attendance_records_insert")
    conn.execute("DROP TRIGGER IF EXISTS trg_attendance_records_update")
    conn.execute("DROP TRIGGER IF EXISTS trg_attendance_records_delete")

    conn.execute("""
        CREATE TRIGGER trg_attendance_records_insert
        AFTER INSERT ON attendance_records FOR EACH ROW
        BEGIN
            INSERT INTO raw_changes (table_name, record_id, old_value, new_value, changed_at)
            VALUES ('attendance_records', NEW.record_id, NULL,
                json_object('att_session_id', NEW.att_session_id,
                            'student_id',     NEW.student_id,
                            'status',         NEW.status),
                datetime('now'));
        END
    """)

    conn.execute("""
        CREATE TRIGGER trg_attendance_records_update
        AFTER UPDATE ON attendance_records FOR EACH ROW
        BEGIN
            INSERT INTO raw_changes (table_name, record_id, old_value, new_value, changed_at)
            VALUES ('attendance_records', OLD.record_id,
                json_object('att_session_id', OLD.att_session_id,
                            'student_id',     OLD.student_id,
                            'status',         OLD.status),
                json_object('att_session_id', NEW.att_session_id,
                            'student_id',     NEW.student_id,
                            'status',         NEW.status),
                datetime('now'));
        END
    """)

    conn.execute("""
        CREATE TRIGGER trg_attendance_records_delete
        AFTER DELETE ON attendance_records FOR EACH ROW
        BEGIN
            INSERT INTO raw_changes (table_name, record_id, old_value, new_value, changed_at)
            VALUES ('attendance_records', OLD.record_id,
                json_object('att_session_id', OLD.att_session_id,
                            'student_id',     OLD.student_id,
                            'status',         OLD.status),
                NULL, datetime('now'));
        END
    """)

    conn.execute("DROP TRIGGER IF EXISTS trg_attendance_sessions_insert")
    conn.execute("""
        CREATE TRIGGER trg_attendance_sessions_insert
        AFTER INSERT ON attendance_sessions FOR EACH ROW
        BEGIN
            INSERT INTO raw_changes (table_name, record_id, old_value, new_value, changed_at)
            VALUES ('attendance_sessions', NEW.att_session_id, NULL,
                json_object('course_id',    NEW.course_id,
                            'session_date', NEW.session_date,
                            'topic',        NEW.topic,
                            'created_by',   NEW.created_by),
                datetime('now'));
        END
    """)

    conn.execute("DROP TRIGGER IF EXISTS trg_semesters_insert")
    conn.execute("DROP TRIGGER IF EXISTS trg_semesters_delete")
    conn.execute("""
        CREATE TRIGGER trg_semesters_insert
        AFTER INSERT ON semesters FOR EACH ROW
        BEGIN
            INSERT INTO raw_changes (table_name, record_id, old_value, new_value, changed_at)
            VALUES ('semesters', NEW.semester_id, NULL,
                json_object('semester_id', NEW.semester_id, 'name', NEW.name, 'is_active', NEW.is_active),
                datetime('now'));
        END
    """)
    conn.execute("""
        CREATE TRIGGER trg_semesters_delete
        AFTER DELETE ON semesters FOR EACH ROW
        BEGIN
            INSERT INTO raw_changes (table_name, record_id, old_value, new_value, changed_at)
            VALUES ('semesters', OLD.semester_id,
                json_object('semester_id', OLD.semester_id, 'name', OLD.name),
                NULL, datetime('now'));
        END
    """)

    conn.execute("DROP TRIGGER IF EXISTS trg_courses_insert")
    conn.execute("DROP TRIGGER IF EXISTS trg_courses_delete")
    conn.execute("""
        CREATE TRIGGER trg_courses_insert
        AFTER INSERT ON courses FOR EACH ROW
        BEGIN
            INSERT INTO raw_changes (table_name, record_id, old_value, new_value, changed_at)
            VALUES ('courses', NEW.course_id, NULL,
                json_object('course_id', NEW.course_id, 'name', NEW.name, 'code', NEW.code),
                datetime('now'));
        END
    """)
    conn.execute("""
        CREATE TRIGGER trg_courses_delete
        AFTER DELETE ON courses FOR EACH ROW
        BEGIN
            INSERT INTO raw_changes (table_name, record_id, old_value, new_value, changed_at)
            VALUES ('courses', OLD.course_id,
                json_object('course_id', OLD.course_id, 'name', OLD.name, 'code', OLD.code),
                NULL, datetime('now'));
        END
    """)

    conn.execute("DROP TRIGGER IF EXISTS trg_course_instructors_insert")
    conn.execute("DROP TRIGGER IF EXISTS trg_course_instructors_delete")
    conn.execute("""
        CREATE TRIGGER trg_course_instructors_insert
        AFTER INSERT ON course_instructors FOR EACH ROW
        BEGIN
            INSERT INTO raw_changes (table_name, record_id, old_value, new_value, changed_at)
            VALUES ('course_instructors', NEW.course_id, NULL,
                json_object('course_id', NEW.course_id, 'instructor_id', NEW.instructor_id),
                datetime('now'));
        END
    """)
    conn.execute("""
        CREATE TRIGGER trg_course_instructors_delete
        AFTER DELETE ON course_instructors FOR EACH ROW
        BEGIN
            INSERT INTO raw_changes (table_name, record_id, old_value, new_value, changed_at)
            VALUES ('course_instructors', OLD.course_id,
                json_object('course_id', OLD.course_id, 'instructor_id', OLD.instructor_id),
                NULL, datetime('now'));
        END
    """)

    conn.execute("DROP TRIGGER IF EXISTS trg_course_tas_insert")
    conn.execute("DROP TRIGGER IF EXISTS trg_course_tas_delete")
    conn.execute("""
        CREATE TRIGGER trg_course_tas_insert
        AFTER INSERT ON course_tas FOR EACH ROW
        BEGIN
            INSERT INTO raw_changes (table_name, record_id, old_value, new_value, changed_at)
            VALUES ('course_tas', NEW.course_id, NULL,
                json_object('course_id', NEW.course_id, 'ta_id', NEW.ta_id),
                datetime('now'));
        END
    """)
    conn.execute("""
        CREATE TRIGGER trg_course_tas_delete
        AFTER DELETE ON course_tas FOR EACH ROW
        BEGIN
            INSERT INTO raw_changes (table_name, record_id, old_value, new_value, changed_at)
            VALUES ('course_tas', OLD.course_id,
                json_object('course_id', OLD.course_id, 'ta_id', OLD.ta_id),
                NULL, datetime('now'));
        END
    """)

    conn.execute("DROP TRIGGER IF EXISTS trg_course_enrollments_insert")
    conn.execute("DROP TRIGGER IF EXISTS trg_course_enrollments_delete")
    conn.execute("""
        CREATE TRIGGER trg_course_enrollments_insert
        AFTER INSERT ON course_enrollments FOR EACH ROW
        BEGIN
            INSERT INTO raw_changes (table_name, record_id, old_value, new_value, changed_at)
            VALUES ('course_enrollments', NEW.course_id, NULL,
                json_object('course_id', NEW.course_id, 'student_id', NEW.student_id),
                datetime('now'));
        END
    """)
    conn.execute("""
        CREATE TRIGGER trg_course_enrollments_delete
        AFTER DELETE ON course_enrollments FOR EACH ROW
        BEGIN
            INSERT INTO raw_changes (table_name, record_id, old_value, new_value, changed_at)
            VALUES ('course_enrollments', OLD.course_id,
                json_object('course_id', OLD.course_id, 'student_id', OLD.student_id),
                NULL, datetime('now'));
        END
    """)

    conn.execute("DROP TRIGGER IF EXISTS trg_users_insert")
    conn.execute("DROP TRIGGER IF EXISTS trg_users_delete")
    conn.execute("""
        CREATE TRIGGER trg_users_insert
        AFTER INSERT ON users FOR EACH ROW
        BEGIN
            INSERT INTO raw_changes (table_name, record_id, old_value, new_value, changed_at)
            VALUES ('users', NEW.user_id, NULL,
                json_object('user_id', NEW.user_id, 'username', NEW.username, 'role', NEW.role),
                datetime('now'));
        END
    """)
    conn.execute("""
        CREATE TRIGGER trg_users_delete
        AFTER DELETE ON users FOR EACH ROW
        BEGIN
            INSERT INTO raw_changes (table_name, record_id, old_value, new_value, changed_at)
            VALUES ('users', OLD.user_id,
                json_object('user_id', OLD.user_id, 'username', OLD.username, 'role', OLD.role),
                NULL, datetime('now'));
        END
    """)

    conn.execute("DROP TRIGGER IF EXISTS trg_correction_requests_insert")
    conn.execute("DROP TRIGGER IF EXISTS trg_correction_requests_update")
    conn.execute("""
        CREATE TRIGGER trg_correction_requests_insert
        AFTER INSERT ON correction_requests FOR EACH ROW
        BEGIN
            INSERT INTO raw_changes (table_name, record_id, old_value, new_value, changed_at)
            VALUES ('correction_requests', NEW.req_id, NULL,
                json_object('req_id', NEW.req_id, 'student_id', NEW.student_id,
                            'att_session_id', NEW.att_session_id, 'status', NEW.status),
                datetime('now'));
        END
    """)
    conn.execute("""
        CREATE TRIGGER trg_correction_requests_update
        AFTER UPDATE ON correction_requests FOR EACH ROW
        BEGIN
            INSERT INTO raw_changes (table_name, record_id, old_value, new_value, changed_at)
            VALUES ('correction_requests', OLD.req_id,
                json_object('req_id', OLD.req_id, 'status', OLD.status),
                json_object('req_id', NEW.req_id, 'status', NEW.status),
                datetime('now'));
        END
    """)

    print("  ✓  All triggers created (correction_logs intentionally excluded)")

    conn.commit()
    conn.close()

    print()
    print("═" * 55)
    print("  DB ready at:", DB_PATH)
    print("  All accounts use password:  password123")
    print()
    print("  Sample logins")
    print("  ─────────────────────────────────────────")
    print("  admin        (admin)")
    print("  dean_joshi   (dean)")
    print("  prof_singh   (instructor)")
    print("  prof_mehta   (instructor)")
    print("  ta_amit      (ta)  — roll: 2311TA001, M.Tech CSE 2023")
    print("  ta_priya     (ta)  — roll: 2311TA002, M.Tech CSE 2023")
    print(f"  {first_student} (student — first one)")
    print("═" * 55)


if __name__ == "__main__":
    init()