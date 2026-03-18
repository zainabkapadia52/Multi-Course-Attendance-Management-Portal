"""
Run this script BEFORE adding indexes, record results,
then uncomment the indexes in schema.sql, run init_db.py,
and run this script again. Compare the two outputs.
"""
import sqlite3, time, statistics

DB_PATH = "module_b.db"

def run_query(conn, sql, params=()):
    start = time.perf_counter()
    rows  = conn.execute(sql, params).fetchall()
    end   = time.perf_counter()
    return (end - start) * 1000, len(rows)  # ms, row count

def explain(conn, sql, params=()):
    plan = conn.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()
    return [dict(row) for row in plan]

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    queries = {
        "Student attendance lookup": (
            "SELECT ar.* FROM attendance_records ar WHERE ar.student_id = ?",
            (4,)
        ),
        "Correction requests by student": (
            "SELECT * FROM correction_requests WHERE student_id = ?",
            (4,)
        ),
        "Enrollment lookup": (
            "SELECT * FROM course_enrollments WHERE student_id = ?",
            (4,)
        ),
        "Attendance records for a session": (
            "SELECT * FROM attendance_records WHERE att_session_id = ?",
            (1,)
        ),
    }

    print(f"{'Query':<40} {'Time (ms)':>12} {'Rows':>6} {'Plan'}")
    print("-" * 90)
    for label, (sql, params) in queries.items():
        times = []
        for _ in range(50):
            t, rows = run_query(conn, sql, params)
            times.append(t)
        avg = statistics.mean(times)
        plan = explain(conn, sql, params)
        plan_str = " | ".join(p.get("detail", "") for p in plan)
        print(f"{label:<40} {avg:>12.4f} {rows:>6} {plan_str}")

    conn.close()

if __name__ == "__main__":
    main()