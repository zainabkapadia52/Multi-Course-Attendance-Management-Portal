"""
Comprehensive Performance Benchmarking & Analysis
=================================================
Measures SQL query times, API response times, and query plans.
Run BEFORE and AFTER indexing to compare performance.
"""

import sqlite3
import time
import statistics
import json
import sys
from datetime import datetime

DB_PATH = "module_b.db"

# ── Query Collection ──────────────────────────────────────────────────────

# All major queries extracted from the API routes
QUERIES = {
    # Student routes
    "student_my_courses": {
        "query": """SELECT c.course_id,c.name,c.code,s.name AS semester,
                           GROUP_CONCAT(u.username) AS instructors
                    FROM courses c
                    JOIN course_enrollments ce ON ce.course_id=c.course_id
                    JOIN semesters s ON s.semester_id=c.semester_id
                    LEFT JOIN course_instructors ci ON ci.course_id=c.course_id
                    LEFT JOIN users u ON u.user_id=ci.instructor_id
                    WHERE ce.student_id=? GROUP BY c.course_id""",
        "params": (1,),
        "category": "student",
    },

    "instructor_my_courses": {
        "query": """SELECT c.course_id,c.name,c.code,s.name AS semester
                    FROM courses c
                    JOIN course_instructors ci ON ci.course_id=c.course_id
                    JOIN semesters s ON s.semester_id=c.semester_id
                    WHERE ci.instructor_id=?""",
        "params": (1,),
        "category": "instructor",
    },

    "student_my_attendance": {
        "query": """SELECT ar.status,att.session_date,att.topic,c.name AS course_name,c.code
                    FROM attendance_records ar
                    JOIN attendance_sessions att ON att.att_session_id=ar.att_session_id
                    JOIN courses c ON c.course_id=att.course_id
                    WHERE ar.student_id=? ORDER BY att.session_date DESC""",
        "params": (1,),
        "category": "student",
    },

    "instructor_corrections": {
        "query": """SELECT cr.*,u.username AS student_name,c.name AS course_name,
                           att.session_date,att.topic
                    FROM correction_requests cr
                    JOIN users u ON u.user_id=cr.student_id
                    JOIN courses c ON c.course_id=cr.course_id
                    JOIN attendance_sessions att ON att.att_session_id=cr.att_session_id
                    JOIN course_instructors ci ON ci.course_id=cr.course_id
                    WHERE ci.instructor_id=?
                    ORDER BY (cr.status='pending') DESC, cr.created_at DESC""",
        "params": (1,),
        "category": "instructor",
    },

    "admin_list_users": {
        "query": """SELECT u.user_id, u.username, u.role, u.last_login,
                           p.roll_no, p.program, p.batch, p.department, p.designation
                    FROM users u LEFT JOIN user_profiles p ON p.user_id = u.user_id
                    ORDER BY u.role, u.username""",
        "params": (),
        "category": "admin",
    },

    "admin_course_students": {
        "query": """SELECT u.user_id, u.username, p.roll_no, p.program, p.batch
                    FROM course_enrollments ce
                    JOIN users u ON u.user_id = ce.student_id
                    LEFT JOIN user_profiles p ON p.user_id = u.user_id
                    WHERE ce.course_id = ?""",
        "params": (1,),
        "category": "admin",
    },

    "instructor_session_records": {
        "query": """SELECT ar.record_id, u.username, ar.status
                    FROM attendance_records ar JOIN users u ON u.user_id=ar.student_id
                    WHERE ar.att_session_id=? ORDER BY u.username""",
        "params": (1,),
        "category": "instructor",
    },

    "student_course_sessions": {
        "query": """SELECT att.att_session_id, att.session_date, att.topic, ar.status
                    FROM attendance_sessions att
                    JOIN attendance_records ar ON ar.att_session_id=att.att_session_id
                    WHERE att.course_id=? AND ar.student_id=? AND ar.status != 'present'
                    ORDER BY att.session_date DESC""",
        "params": (1, 1),
        "category": "student",
    },

    "instructor_sessions": {
        "query": """SELECT att.*,c.name AS course_name
                    FROM attendance_sessions att
                    JOIN courses c ON c.course_id=att.course_id
                    JOIN course_instructors ci ON ci.course_id=att.course_id
                    WHERE ci.instructor_id=? ORDER BY att.session_date DESC""",
        "params": (1,),
        "category": "instructor",
    },

    "admin_list_courses": {
        "query": """SELECT c.*,s.name AS semester_name
                    FROM courses c JOIN semesters s USING(semester_id)""",
        "params": (),
        "category": "admin",
    },
}

# ── Benchmark Functions ────────────────────────────────────────────────────

def run_query(conn, sql, params=()):
    """Execute query and return time (ms) and row count"""
    start = time.perf_counter()
    rows  = conn.execute(sql, params).fetchall()
    end   = time.perf_counter()
    return (end - start) * 1000, len(rows)

def explain_query(conn, sql, params=()):
    """Get EXPLAIN QUERY PLAN"""
    plan = conn.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()
    return plan

def benchmark_query(conn, name, sql, params=(), iterations=30):
    """Run query multiple times and collect statistics"""
    times = []
    for _ in range(iterations):
        t, rows = run_query(conn, sql, params)
        times.append(t)

    return {
        "name": name,
        "min": min(times),
        "max": max(times),
        "mean": statistics.mean(times),
        "median": statistics.median(times),
        "stdev": statistics.stdev(times) if len(times) > 1 else 0,
        "rows": rows,
        "iterations": iterations,
        "total_time": sum(times),
    }

def run_benchmarks(phase="before"):
    """Run all benchmarks and collect results"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    print(f"\n{'='*80}")
    print(f"BENCHMARKING PHASE: {phase.upper()}")
    print(f"{'='*80}")

    results = {
        "phase": phase,
        "timestamp": datetime.now().isoformat(),
        "queries": {}
    }

    for name, query_info in QUERIES.items():
        sql = query_info["query"]
        params = query_info["params"]

        try:
            print(f"\n[{name}]")
            bench = benchmark_query(conn, name, sql, params)

            # Get explain plan
            explain = explain_query(conn, sql, params)

            bench["explain_plan"] = [dict(row) for row in explain]
            bench["category"] = query_info["category"]

            results["queries"][name] = bench

            print(f"  Mean: {bench['mean']:.4f}ms | Median: {bench['median']:.4f}ms | Rows: {bench['rows']}")
            for p in bench['explain_plan']:
                print(f"    {p}")

        except Exception as e:
            print(f"  ERROR: {e}")
            results["queries"][name] = {"error": str(e)}

    conn.close()
    return results

def save_results(results, filename):
    """Save benchmark results to JSON"""
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n[OK] Results saved to {filename}")

def print_summary(results):
    """Print summary of benchmark results"""
    print(f"\n{'='*80}")
    print(f"SUMMARY - {results['phase'].upper()}")
    print(f"{'='*80}")

    total_time = 0
    query_count = 0

    print(f"\n{'Query Name':<40} {'Mean (ms)':>12} {'Median':>12} {'Rows':>8}")
    print("-" * 80)

    for name, data in sorted(results['queries'].items()):
        if 'error' not in data:
            print(f"{name:<40} {data['mean']:>12.4f} {data['median']:>12.4f} {data['rows']:>8}")
            total_time += data['mean']
            query_count += 1

    print("-" * 80)
    print(f"{'Total average query time':<40} {total_time:>12.4f}")
    print(f"Average across all queries: {total_time/query_count:.4f}ms" if query_count > 0 else "No results")

def main():
    import os

    # Ensure we're in the right directory
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}")
        sys.exit(1)

    # Run benchmarks
    results = run_benchmarks(phase="before" if "--before" in sys.argv else "after")

    # Save results
    phase = results["phase"]
    filename = f"benchmark_results_{phase}.json"
    save_results(results, filename)

    # Print summary
    print_summary(results)

if __name__ == "__main__":
    main()
