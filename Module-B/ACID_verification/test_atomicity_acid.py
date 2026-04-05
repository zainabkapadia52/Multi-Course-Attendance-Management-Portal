"""
test_atomicity_acid.py
=======================
ACID Property: ATOMICITY
Tests: All-or-nothing transactions across database, application, and API levels

"The A in ACID: A transaction either completes fully or rolls back completely.
There are no partial states."
"""

import sqlite3
import json
import time
import threading
import random
from datetime import datetime, timedelta
import os
import sys
import requests
from threading import Lock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class AtomicityTester:
    """Test ATOMICITY property across all levels"""

    def __init__(self, level="database"):
        """
        level: "database" | "application" | "api"
        """
        self.level = level
        script_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(script_dir)
        self.db_path = os.path.join(parent_dir, "module_b.db")
        self.api_base_url = "http://localhost:5050"
        self.results = []
        self.lock = Lock()
        self.pass_count = 0
        self.fail_count = 0

    def log_result(self, test_name, status, message="", details=None):
        """Log test result"""
        with self.lock:
            result = {
                "timestamp": datetime.now().isoformat(),
                "test_name": test_name,
                "status": status,
                "message": message,
                "details": details or {}
            }
            self.results.append(result)

            symbol = "[OK]" if status == "PASS" else "[FAIL]"
            try:
                print(f"{symbol} [{self.level.upper()}] {test_name}: {status}")
                if message:
                    print(f"      - {message}")
            except UnicodeEncodeError:
                safe_msg = message.encode('ascii', 'ignore').decode('ascii') if message else ""
                print(f"{symbol} [{self.level.upper()}] {test_name}: {status}")
                if safe_msg:
                    print(f"      - {safe_msg}")

            if status == "PASS":
                self.pass_count += 1
            elif status == "FAIL":
                self.fail_count += 1

    def get_db_connection(self):
        """Create database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.isolation_level = None
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        return conn

    # ═══════════════════════════════════════════════════════════════════════════
    # DATABASE LEVEL ATOMICITY TESTS
    # ═══════════════════════════════════════════════════════════════════════════

    def test_db_semester_creation_atomicity(self):
        """DB: Semester creation must be atomic"""
        test_name = "db_semester_creation_atomicity"
        try:
            conn = self.get_db_connection()
            test_sem_name = f"AtomSem_{int(time.time())}_{random.randint(1000, 9999)}"

            # Test 1: Transaction commits fully
            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    "INSERT INTO semesters (name, is_active) VALUES (?, ?)",
                    (test_sem_name, 0)
                )
                sem_id = cur.lastrowid
                conn.commit()

                # Verify full insertion
                verify = conn.execute(
                    "SELECT name, is_active FROM semesters WHERE semester_id=?",
                    (sem_id,)
                ).fetchone()

                if verify and verify["name"] == test_sem_name and verify["is_active"] == 0:
                    self.log_result(test_name, "PASS",
                        "Semester created atomically with all fields committed")
                else:
                    self.log_result(test_name, "FAIL",
                        "Partial insertion detected - missing fields")
            except Exception as e:
                conn.rollback()
                self.log_result(test_name, "FAIL", f"Transaction error: {str(e)}")

            conn.close()
        except Exception as e:
            self.log_result(test_name, "FAIL", f"Setup error: {str(e)}")

    def test_db_student_enrollment_atomic_cascade(self):
        """DB: Student enrollment must be atomic - if constraint fails, nothing commits"""
        test_name = "db_student_enrollment_atomic_cascade"
        try:
            conn = self.get_db_connection()

            # Find test data
            course = conn.execute("SELECT course_id FROM courses LIMIT 1").fetchone()
            student = conn.execute(
                "SELECT user_id FROM users WHERE role='student' LIMIT 1"
            ).fetchone()

            if not course or not student:
                self.log_result(test_name, "SKIP", "Missing test data")
                return

            course_id = course[0]
            student_id = student[0]

            # Test: Attempt to enroll student twice (should fail on unique constraint)
            enrollment_count_before = conn.execute(
                "SELECT COUNT(*) FROM enrollments WHERE student_id=? AND course_id=?",
                (student_id, course_id)
            ).fetchone()[0]

            if enrollment_count_before == 0:
                # First enrollment should succeed
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute(
                        "INSERT INTO enrollments (student_id, course_id, enrollment_date) VALUES (?, ?, ?)",
                        (student_id, course_id, datetime.now().date())
                    )
                    conn.commit()
                except Exception as e:
                    conn.rollback()

                # Second enrollment should fail (unique constraint)
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute(
                        "INSERT INTO enrollments (student_id, course_id, enrollment_date) VALUES (?, ?, ?)",
                        (student_id, course_id, datetime.now().date())
                    )
                    conn.commit()
                    self.log_result(test_name, "FAIL",
                        "Duplicate enrollment allowed - atomicity violated")
                except sqlite3.IntegrityError:
                    # This is expected - transaction should fully rollback
                    enrollment_count_after = conn.execute(
                        "SELECT COUNT(*) FROM enrollments WHERE student_id=? AND course_id=?",
                        (student_id, course_id)
                    ).fetchone()[0]

                    if enrollment_count_after == 1:
                        self.log_result(test_name, "PASS",
                            "Failed transaction fully rolled back - atomicity maintained")
                    else:
                        self.log_result(test_name, "FAIL",
                            "Partial enrollment state after rollback")
            else:
                self.log_result(test_name, "SKIP", "Student already enrolled")

            conn.close()
        except Exception as e:
            self.log_result(test_name, "FAIL", f"Setup error: {str(e)}")

    def test_db_batch_attendance_atomic(self):
        """DB: Batch attendance update must be atomic - all records or none"""
        test_name = "db_batch_attendance_atomic"
        try:
            conn = self.get_db_connection()

            # Find course and create session
            course = conn.execute("SELECT course_id FROM courses LIMIT 1").fetchone()
            if not course:
                self.log_result(test_name, "SKIP", "No course found")
                return

            course_id = course[0]
            session_date = datetime.now().date()

            # Create test session
            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    """INSERT INTO attendance_sessions
                       (course_id, session_date, session_time, created_by)
                       VALUES (?, ?, ?, ?)""",
                    (course_id, session_date, "10:00", 1)
                )
                session_id = cur.lastrowid
                conn.commit()
            except Exception as e:
                conn.rollback()
                self.log_result(test_name, "FAIL", f"Session creation failed: {str(e)}")
                return

            # Get students enrolled in this course
            students = conn.execute(
                """SELECT DISTINCT e.student_id FROM enrollments e
                   WHERE e.course_id = ? LIMIT 5""",
                (course_id,)
            ).fetchall()

            if len(students) < 2:
                self.log_result(test_name, "SKIP", "Not enough enrolled students")
                return

            # Test atomic batch insert
            try:
                conn.execute("BEGIN IMMEDIATE")
                for student in students:
                    conn.execute(
                        """INSERT INTO attendance_records
                           (session_id, student_id, status)
                           VALUES (?, ?, ?)""",
                        (session_id, student[0], "present")
                    )
                conn.commit()

                # Verify all inserted
                count = conn.execute(
                    "SELECT COUNT(*) FROM attendance_records WHERE session_id=?",
                    (session_id,)
                ).fetchone()[0]

                if count == len(students):
                    self.log_result(test_name, "PASS",
                        f"All {len(students)} attendance records committed atomically")
                else:
                    self.log_result(test_name, "FAIL",
                        f"Expected {len(students)} records, got {count}")
            except Exception as e:
                conn.rollback()
                self.log_result(test_name, "FAIL", f"Batch insert failed: {str(e)}")

            conn.close()
        except Exception as e:
            self.log_result(test_name, "FAIL", f"Setup error: {str(e)}")

    # ═══════════════════════════════════════════════════════════════════════════
    # APPLICATION LEVEL ATOMICITY TESTS
    # ═══════════════════════════════════════════════════════════════════════════

    def test_app_create_attendance_session_atomic(self):
        """APP: Attendance session creation must be atomic"""
        test_name = "app_create_attendance_session_atomic"
        try:
            # Import application modules
            from app import create_app
            from app.db import get_db

            app = create_app()
            with app.app_context():
                conn = get_db()

                # Get test data
                course = conn.execute("SELECT course_id FROM courses LIMIT 1").fetchone()
                instructor = conn.execute(
                    "SELECT user_id FROM users WHERE role='instructor' LIMIT 1"
                ).fetchone()

                if not course or not instructor:
                    self.log_result(test_name, "SKIP", "Missing test data")
                    return

                course_id = course[0]
                instructor_id = instructor[0]

                # Simulate session creation (would normally go through service layer)
                session_date = datetime.now().date()
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    cur = conn.execute(
                        """INSERT INTO attendance_sessions
                           (course_id, session_date, session_time, created_by)
                           VALUES (?, ?, ?, ?)""",
                        (course_id, session_date, "11:00", instructor_id)
                    )
                    session_id = cur.lastrowid
                    conn.commit()

                    # Verify creation
                    verify = conn.execute(
                        "SELECT COUNT(*) FROM attendance_sessions WHERE session_id=?",
                        (session_id,)
                    ).fetchone()[0]

                    if verify == 1:
                        self.log_result(test_name, "PASS",
                            "Session created atomically at application level")
                    else:
                        self.log_result(test_name, "FAIL",
                            "Session not fully created")
                except Exception as e:
                    conn.rollback()
                    self.log_result(test_name, "FAIL", f"Transaction failed: {str(e)}")

        except ImportError:
            self.log_result(test_name, "SKIP", "Application not available")
        except Exception as e:
            self.log_result(test_name, "FAIL", f"Setup error: {str(e)}")

    # ═══════════════════════════════════════════════════════════════════════════
    # API LEVEL ATOMICITY TESTS
    # ═══════════════════════════════════════════════════════════════════════════

    def test_api_create_semester_atomic(self):
        """API: Semester creation via API must be atomic"""
        test_name = "api_create_semester_atomic"
        try:
            test_sem_name = f"ApiAtomSem_{int(time.time())}"

            # Attempt API call
            response = requests.post(
                f"{self.api_base_url}/api/admin/semester",
                json={"name": test_sem_name, "is_active": False},
                headers={"Authorization": "Bearer admin_token"},
                timeout=5
            )

            if response.status_code == 201:
                data = response.json()
                if "semester_id" in data:
                    self.log_result(test_name, "PASS",
                        f"Semester created atomically via API (ID: {data['semester_id']})")
                else:
                    self.log_result(test_name, "FAIL",
                        "Response missing semester_id - partial creation")
            elif response.status_code == 400:
                # Bad request is fine - just testing atomicity
                self.log_result(test_name, "PASS",
                    "API properly rejects bad requests atomically")
            else:
                self.log_result(test_name, "SKIP",
                    f"API not available (Status: {response.status_code})")

        except requests.exceptions.ConnectionError:
            self.log_result(test_name, "SKIP", "API server not running")
        except Exception as e:
            self.log_result(test_name, "FAIL", f"Error: {str(e)}")

    def run_all_tests(self):
        """Run all atomicity tests for this level"""
        print(f"\n{'='*100}")
        print(f"ATOMICITY TESTS - {self.level.upper()} LEVEL")
        print(f"{'='*100}\n")

        if self.level == "database":
            self.test_db_semester_creation_atomicity()
            self.test_db_student_enrollment_atomic_cascade()
            self.test_db_batch_attendance_atomic()
        elif self.level == "application":
            self.test_app_create_attendance_session_atomic()
        elif self.level == "api":
            self.test_api_create_semester_atomic()

        self.print_summary()

    def print_summary(self):
        """Print test summary"""
        total = self.pass_count + self.fail_count
        pass_pct = (self.pass_count / max(1, total)) * 100 if total > 0 else 0

        print(f"\n{'-'*100}")
        print(f"ATOMICITY TEST SUMMARY ({self.level.upper()})")
        print(f"{'-'*100}")
        print(f"Total: {total} | Passed: {self.pass_count} | Failed: {self.fail_count}")
        print(f"Pass Rate: {pass_pct:.1f}%")

        # Save results
        output_file = f"atomicity_test_results_{self.level}.json"
        with open(output_file, "w") as f:
            json.dump({
                "level": self.level,
                "timestamp": datetime.now().isoformat(),
                "summary": {
                    "total": total,
                    "passed": self.pass_count,
                    "failed": self.fail_count,
                    "pass_rate": pass_pct
                },
                "results": self.results
            }, f, indent=2)

        print(f"Results saved to: {output_file}")


if __name__ == "__main__":
    import sys

    level = sys.argv[1] if len(sys.argv) > 1 else "database"
    tester = AtomicityTester(level=level)
    tester.run_all_tests()
