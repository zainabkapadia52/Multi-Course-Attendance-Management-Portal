# migrate_to_shards_directory.py (updated — department-based assignment)
import sqlite3
import os

MAIN_DB = "module_b.db"
NUM_SHARDS = 3

SHARD_SCHEMA = """
CREATE TABLE IF NOT EXISTS attendance_records (
    record_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    att_session_id INTEGER NOT NULL,
    student_id     INTEGER NOT NULL,
    status         TEXT    CHECK(status IN ('present','absent')) NOT NULL DEFAULT 'absent'
);
CREATE INDEX IF NOT EXISTS idx_ar_student ON attendance_records(student_id);
CREATE INDEX IF NOT EXISTS idx_ar_session ON attendance_records(att_session_id);
"""

DIRECTORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS shard_directory (
    student_id  INTEGER PRIMARY KEY,
    shard_id    INTEGER NOT NULL,
    department  TEXT,
    assigned_at TEXT    DEFAULT (datetime('now'))
);
"""

# Department → shard mapping
# CS gets its own shard (largest dept, 24 students)
# Electronics and Mechanical share shards 1 and 2
DEPARTMENT_SHARD = {
    "Computer Science":       0,
    "Electronics":            1,
    "Mechanical Engineering": 2,
}


def get_shard_path(shard_id: int) -> str:
    return f"dir_shard_{shard_id}.db"


def migrate():
    main_conn = sqlite3.connect(MAIN_DB)
    main_conn.row_factory = sqlite3.Row

    rows = main_conn.execute(
        "SELECT record_id, att_session_id, student_id, status FROM attendance_records ORDER BY student_id"
    ).fetchall()

    # Fetch student → department mapping
    students = main_conn.execute(
        """SELECT u.user_id, up.department
           FROM users u
           JOIN user_profiles up ON up.user_id = u.user_id
           WHERE u.role = 'student'"""
    ).fetchall()

    print(f"Total records in main.db  : {len(rows)}")
    print(f"Total students            : {len(students)}")
    print(f"Assignment strategy       : department-based")
    print(f"  Computer Science        → shard_0")
    print(f"  Electronics             → shard_1")
    print(f"  Mechanical Engineering  → shard_2")
    print()

    # Delete old files
    for shard_id in range(NUM_SHARDS):
        path = get_shard_path(shard_id)
        if os.path.exists(path):
            os.remove(path)
            print(f"Deleted old {path}")
    if os.path.exists("directory.db"):
        os.remove("directory.db")
        print("Deleted old directory.db")
    print()

    # Create directory DB
    dir_conn = sqlite3.connect("directory.db")
    dir_conn.executescript(DIRECTORY_SCHEMA)
    dir_conn.commit()

    # Create shard DBs
    shard_conns = {}
    for shard_id in range(NUM_SHARDS):
        path = get_shard_path(shard_id)
        conn = sqlite3.connect(path)
        conn.executescript(SHARD_SCHEMA)
        conn.commit()
        shard_conns[shard_id] = conn
        print(f"Initialised {path}")

    print()

    # Build directory from department mapping
    directory = {}
    skipped_students = []
    for s in students:
        dept = s["department"]
        shard_id = DEPARTMENT_SHARD.get(dept)
        if shard_id is None:
            skipped_students.append(s["user_id"])
            continue
        directory[s["user_id"]] = shard_id
        dir_conn.execute(
            "INSERT INTO shard_directory (student_id, shard_id, department) VALUES (?, ?, ?)",
            (s["user_id"], shard_id, dept)
        )

    dir_conn.commit()
    print(f"Directory built: {len(directory)} student → shard mappings")
    print()

    # Distribute records using directory lookup
    counts = {i: 0 for i in range(NUM_SHARDS)}
    skipped = []

    for row in rows:
        shard_id = directory.get(row["student_id"])
        if shard_id is None:
            skipped.append(row["student_id"])
            continue
        shard_conns[shard_id].execute(
            """INSERT INTO attendance_records
               (record_id, att_session_id, student_id, status)
               VALUES (?, ?, ?, ?)""",
            (row["record_id"], row["att_session_id"], row["student_id"], row["status"])
        )
        counts[shard_id] += 1

    # Commit and close
    for shard_id, conn in shard_conns.items():
        conn.commit()
        conn.close()
    dir_conn.close()
    main_conn.close()

    # Report
    print("--- Migration Results ---")
    total_migrated = 0
    dept_labels = {0: "Computer Science", 1: "Electronics", 2: "Mechanical Engg"}
    for shard_id in range(NUM_SHARDS):
        print(f"  dir_shard_{shard_id}.db  [{dept_labels[shard_id]:>20}]  →  {counts[shard_id]} records")
        total_migrated += counts[shard_id]

    print(f"\n  Total migrated : {total_migrated}")
    print(f"  Total in main  : {len(rows)}")

    if skipped:
        print(f"\n  Skipped user_ids: {sorted(set(skipped))}  ({len(skipped)} records)")

    # Skew analysis
    print("\n--- Skew Analysis ---")
    avg = total_migrated / NUM_SHARDS
    print(f"  Expected per shard (avg) : {avg:.1f}")
    for shard_id in range(NUM_SHARDS):
        delta = counts[shard_id] - avg
        pct = (delta / avg) * 100
        bar = "▓" * int(counts[shard_id] / 20)
        print(f"  dir_shard_{shard_id}  [{dept_labels[shard_id]:>20}]  {counts[shard_id]:>5} records  {pct:+.1f}%  {bar}")

    max_diff = max(counts.values()) - min(counts.values())
    print(f"\n  Max imbalance  : {max_diff} records between most and least loaded shard")

    if max_diff > avg * 0.2:
        print("  ⚠  Skew detected — department-based directory sharding is uneven")
    else:
        print("  ✓  Distribution is acceptably balanced")

    # Show sample directory entries
    print("\n--- Sample Directory Entries ---")
    dir_conn2 = sqlite3.connect("directory.db")
    dir_conn2.row_factory = sqlite3.Row
    for dept, sid in DEPARTMENT_SHARD.items():
        sample = dir_conn2.execute(
            "SELECT student_id, shard_id, department FROM shard_directory WHERE department=? LIMIT 3",
            (dept,)
        ).fetchall()
        for r in sample:
            print(f"  student_id {r['student_id']:>3}  [{r['department']:>22}]  →  dir_shard_{r['shard_id']}.db")
    dir_conn2.close()


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    migrate()