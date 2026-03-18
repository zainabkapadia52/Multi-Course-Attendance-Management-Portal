import sqlite3
from werkzeug.security import generate_password_hash

DB_PATH = "module_b.db"

def init():
    with open("sql/schema.sql") as f:
        schema = f.read()
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(schema)

    users = [
        (1, "admin",      "password123", "admin"),
        (2, "prof_singh", "password123", "instructor"),
        (3, "prof_rao",   "password123", "instructor"),
        (4, "student_a",  "password123", "student"),
        (5, "student_b",  "password123", "student"),
        (6, "student_c",  "password123", "student"),
        (7, "ta_amit",    "password123", "ta"),
        (8, "dean_joshi", "password123", "dean"),
    ]
    for uid, username, pwd, role in users:
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, username, pwd_hash, role) VALUES (?,?,?,?)",
            (uid, username, generate_password_hash(pwd), role)
        )

    profiles = [
        (2, None, None, None, "Computer Science", "Associate Professor"),
        (3, None, None, None, "Mathematics",      "Assistant Professor"),
        (4, "24110001", "B.Tech CSE", "2024", None, None),
        (5, "24110002", "B.Tech EE",  "2024", None, None),
        (6, "24110003", "M.Tech CSE", "2023", None, None),
        (7, None, None, None, "Computer Science", "Teaching Assistant"),
        (8, None, None, None, "Administration",   "Dean of Academics"),
    ]
    for uid, roll, prog, batch, dept, desig in profiles:
        conn.execute(
            "INSERT OR IGNORE INTO user_profiles VALUES (?,?,?,?,?,?)",
            (uid, roll, prog, batch, dept, desig)
        )

    conn.execute("INSERT OR IGNORE INTO semesters VALUES (1,'Sem II 2025-26','2026-01-01','2026-05-31',1)")
    conn.execute("INSERT OR IGNORE INTO semesters VALUES (2,'Sem I 2025-26','2025-07-01','2025-11-30',0)")

    conn.execute("INSERT OR IGNORE INTO courses VALUES (1,'Databases','CS432',1)")
    conn.execute("INSERT OR IGNORE INTO courses VALUES (2,'Algorithms','CS301',1)")
    conn.execute("INSERT OR IGNORE INTO courses VALUES (3,'Operating Systems','CS302',2)")

    conn.execute("INSERT OR IGNORE INTO course_instructors VALUES (1,2)")
    conn.execute("INSERT OR IGNORE INTO course_instructors VALUES (2,3)")
    conn.execute("INSERT OR IGNORE INTO course_instructors VALUES (3,2)")
    conn.execute("INSERT OR IGNORE INTO course_tas VALUES (1,7)")

    for sid in (4, 5, 6):
        conn.execute("INSERT OR IGNORE INTO course_enrollments VALUES (1,?)", (sid,))
        conn.execute("INSERT OR IGNORE INTO course_enrollments VALUES (2,?)", (sid,))
    for sid in (4, 5):
        conn.execute("INSERT OR IGNORE INTO course_enrollments VALUES (3,?)", (sid,))

    conn.execute("INSERT OR IGNORE INTO attendance_sessions VALUES (1,1,'2026-03-10','B+ Trees',2)")
    conn.execute("INSERT OR IGNORE INTO attendance_sessions VALUES (2,1,'2026-03-12','Query Optimization',2)")

    for att_sid, stu_id, status in [
        (1,4,'present'),(1,5,'absent'),(1,6,'late'),
        (2,4,'present'),(2,5,'present'),(2,6,'absent'),
    ]:
        conn.execute(
            "INSERT OR IGNORE INTO attendance_records (att_session_id,student_id,status) VALUES (?,?,?)",
            (att_sid, stu_id, status)
        )

    conn.commit()
    conn.close()
    print("DB ready. Logins: admin / prof_singh / student_a / ta_amit / dean_joshi — all password123")

if __name__ == "__main__":
    init()