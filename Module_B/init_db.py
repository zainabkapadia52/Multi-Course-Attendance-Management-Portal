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

All passwords: password123
"""

import sqlite3
import random
from datetime import date, timedelta
from werkzeug.security import generate_password_hash

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
    ("prof_singh",  "Computer Science",       "Associate Professor"),
    ("prof_rao",    "Mathematics",            "Assistant Professor"),
    ("prof_mehta",  "Electronics",            "Professor"),
    ("prof_sharma", "Computer Science",       "Assistant Professor"),
    ("prof_jain",   "Mechanical Engineering", "Associate Professor"),
]

TA_DATA = [
    ("ta_amit",  "Computer Science"),
    ("ta_priya", "Mathematics"),
    ("ta_ravi",  "Electronics"),
    ("ta_sneha", "Computer Science"),
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

    # ── schema ────────────────────────────────────────────────────────────────
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    print("  ✓  Schema loaded from", SCHEMA_PATH)

    # ── admin & dean ──────────────────────────────────────────────────────────
    insert_user(conn, "admin", "admin")
    dean_id = insert_user(conn, "dean_joshi", "dean")
    conn.execute(
        "INSERT OR IGNORE INTO user_profiles (user_id, department, designation) VALUES (?,?,?)",
        (dean_id, "Administration", "Dean of Academics")
    )

    # ── instructors ───────────────────────────────────────────────────────────
    instructor_ids = {}
    for uname, dept, desig in INSTRUCTOR_DATA:
        uid = insert_user(conn, uname, "instructor")
        conn.execute(
            "INSERT OR IGNORE INTO user_profiles (user_id, department, designation) VALUES (?,?,?)",
            (uid, dept, desig)
        )
        instructor_ids[uname] = uid
    print(f"  ✓  {len(instructor_ids)} instructors inserted")

    # ── TAs ───────────────────────────────────────────────────────────────────
    ta_ids = {}
    for uname, dept in TA_DATA:
        uid = insert_user(conn, uname, "ta")
        conn.execute(
            "INSERT OR IGNORE INTO user_profiles (user_id, department, designation) VALUES (?,?,?)",
            (uid, dept, "Teaching Assistant")
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
        dept = ("Computer Science"       if "CSE" in program else
                "Electronics"           if "EE"  in program else
                "Mechanical Engineering")
        uid = insert_user(conn, uname, "student")
        conn.execute(
            "INSERT OR IGNORE INTO user_profiles (user_id, roll_no, program, batch, department) VALUES (?,?,?,?,?)",
            (uid, roll, program, batch, dept)
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
    course_ids = {}
    for name, code, sem_idx, instr_uname in COURSE_DEFS:
        cur = conn.execute(
            "INSERT OR IGNORE INTO courses (name, code, semester_id) VALUES (?,?,?)",
            (name, code, sem_ids[sem_idx])
        )
        cid = cur.lastrowid or conn.execute(
            "SELECT course_id FROM courses WHERE code = ?", (code,)
        ).fetchone()[0]
        course_ids[code] = cid
        conn.execute("INSERT OR IGNORE INTO course_instructors VALUES (?,?)",
                     (cid, instructor_ids[instr_uname]))
        if code in COURSE_TA:
            conn.execute("INSERT OR IGNORE INTO course_tas VALUES (?,?)",
                         (cid, ta_ids[COURSE_TA[code]]))
    print(f"  ✓  {len(course_ids)} courses inserted")

    # ── enrollments ───────────────────────────────────────────────────────────
    cs_codes = ["CS432","CS301","CS303","CS302","CS501","CS401"]
    ee_codes = ["MA201","EC401","EC302","MA301","CS303"]
    me_codes = ["MA201","MA301","EC401","CS302"]

    enrollments = set()
    for uid, program, dept in student_ids:
        pool = cs_codes if "CSE" in program else (ee_codes if "EE" in program else me_codes)
        extra = [c for c in cs_codes if c not in pool]
        combined = pool + extra
        for code in combined[:random.randint(3, 5)]:
            enrollments.add((course_ids[code], uid))

    conn.executemany("INSERT OR IGNORE INTO course_enrollments VALUES (?,?)", list(enrollments))
    print(f"  ✓  {len(enrollments)} enrolments inserted")

    # ── attendance sessions ───────────────────────────────────────────────────
    # list of (att_session_id, code) for building records
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
    print(f"  ✓  {len(records)} attendance records inserted  ← main table")

    # ── correction requests ───────────────────────────────────────────────────
    absent_list = [
        (sess_id, stu_id, course_ids[code])
        for sess_id, code in all_sessions
        for stu_id in enrolled_map.get(course_ids[code], [])
        if (sess_id, stu_id, "absent") in {(r[0], r[1], r[2]) for r in records}
    ]
    # Fast set lookup
    absent_set = {(r[0], r[1]) for r in records if r[2] == "absent"}
    absent_list = [
        (sess_id, stu_id, course_ids[code])
        for sess_id, code in all_sessions
        for stu_id in enrolled_map.get(course_ids[code], [])
        if (sess_id, stu_id) in absent_set
    ]

    sample = random.sample(absent_list, min(40, len(absent_list)))
    cr_statuses = ["pending","pending","pending","accepted","rejected"]
    inserted_cr = 0
    for sess_id, stu_id, cid in sample:
        try:
            conn.execute(
                """INSERT OR IGNORE INTO correction_requests
                   (student_id, course_id, att_session_id, reason, status)
                   VALUES (?,?,?,?,?)""",
                (stu_id, cid, sess_id,
                 random.choice(CORRECTION_REASONS),
                 random.choice(cr_statuses))
            )
            inserted_cr += 1
        except sqlite3.IntegrityError:
            pass
    print(f"  ✓  {inserted_cr} correction requests inserted")

    first_student = conn.execute(
    "SELECT username FROM users WHERE role='student' ORDER BY user_id LIMIT 1"
    ).fetchone()[0]

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
    print("  ta_amit      (ta)")
    # print("  aarav_patel0 (student — first one)")
    print(f"  {first_student} (student — first one)")
    print("═" * 55)


if __name__ == "__main__":
    init()