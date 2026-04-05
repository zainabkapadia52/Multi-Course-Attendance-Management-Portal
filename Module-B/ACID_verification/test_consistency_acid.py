"""
test_consistency_acid.py
========================
ACID Property: CONSISTENCY
Tests: Data integrity, constraint enforcement, referential integrity

"The C in ACID: A transaction takes the database from one valid state to another.
All constraints, rules, and triggers are enforced."
"""

import sqlite3
import json
import time
import random
from datetime import datetime, timedelta
import os
import sys
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class ConsistencyTester:
    """Test CONSISTENCY property across all levels"""

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
        self.pass_count = 0
        self.fail_count = 0

    def log_result(self, test_name, status, message="", details=None):
        """Log test result"""
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
    # DATABASE LEVEL CONSISTENCY TESTS
    # ═══════════════════════════════════════════════════════════════════════════

    def test_db_foreign_key_constraint(self):
        """DB: Foreign key constraints must be enforced"""
        test_name = "db_foreign_key_constraint"
        try:
            conn = self.get_db_connection()

            # Test 1: Attempt to insert course with invalid semester_id
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT INTO courses (code, name, semester_id) VALUES (?, ?, ?)",
                    (f"INVALID{int(time.time())}", "Invalid Course", 99999)
                )
                conn.commit()
                self.log_result(test_name, "FAIL",
                    "Foreign key constraint not enforced - orphaned course created")
            except sqlite3.IntegrityError:
                self.log_result(test_name, "PASS",
                    "Foreign key constraint properly enforced - invalid semester rejected")
            finally:
                conn.close()

        except Exception as e:
            self.log_result(test_name, "FAIL", f"Setup error: {str(e)}")

    def test_db_unique_constraint_usernames(self):
        """DB: Unique constraint on usernames must be enforced"""
        test_name = "db_unique_constraint_usernames"
        try:
            conn = self.get_db_connection()

            # Create unique test username
            test_user = f"testuser_{int(time.time())}_{random.randint(1000, 9999)}"

            # First insert should succeed
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT INTO users (username, pwd_hash, role) VALUES (?, ?, ?)",
                    (test_user, "hash123", "student")
                )
                conn.commit()

                # Second insert with same username should fail
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute(
                        "INSERT INTO users (username, pwd_hash, role) VALUES (?, ?, ?)",
                        (test_user, "hash456", "instructor")
                    )
                    conn.commit()
                    self.log_result(test_name, "FAIL",
                        "Duplicate username allowed - uniqueness constraint violated")
                except sqlite3.IntegrityError:
                    self.log_result(test_name, "PASS",
                        "Unique constraint properly enforced - duplicate username rejected")
            except Exception as e:
                conn.rollback()
                self.log_result(test_name, "FAIL", f"First insert failed: {str(e)}")

            conn.close()

        except Exception as e:
            self.log_result(test_name, "FAIL", f"Setup error: {str(e)}")

    def test_db_cascade_delete_consistency(self):
        """DB: Cascade delete maintains referential consistency"""
        test_name = "db_cascade_delete_consistency"
        try:
            conn = self.get_db_connection()

            # Find or create a test semester with no courses
            sem = conn.execute(
                "SELECT s.semester_id FROM semesters s LIMIT 1"
            ).fetchone()

            if not sem:
                self.log_result(test_name, "SKIP", "No semester available")
                return

            sem_id = sem[0]

            # Delete semester - cascading deletes should remove courses
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("DELETE FROM semesters WHERE semester_id=?", (sem_id,))
                conn.commit()

                # Verify no orphaned courses
                orphaned = conn.execute(
                    "SELECT COUNT(*) FROM courses WHERE semester_id=?", (sem_id,)
                ).fetchone()[0]

                if orphaned == 0:
                    self.log_result(test_name, "PASS",
                        "Cascade delete maintained referential consistency")
                else:
                    self.log_result(test_name, "FAIL",
                        f"{orphaned} orphaned records after deletion")
            except Exception as e:
                conn.rollback()
                self.log_result(test_name, "FAIL", f"Delete failed: {str(e)}")

            conn.close()

        except Exception as e:
            self.log_result(test_name, "FAIL", f"Setup error: {str(e)}")

    def test_db_check_constraint_attendance_status(self):
        """DB: Check constraint on attendance status must enforce valid values"""
        test_name = "db_check_constraint_attendance_status"
        try:
            conn = self.get_db_connection()

            # Get valid session
            session = conn.execute(
                "SELECT session_id FROM attendance_sessions LIMIT 1"
            ).fetchone()
            student = conn.execute(
                "SELECT user_id FROM users WHERE role='student' LIMIT 1"
            ).fetchone()

            if not session or not student:
                self.log_result(test_name, "SKIP", "Missing test data")
                return

            # Test invalid status
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    """INSERT INTO attendance_records
                       (session_id, student_id, status)
                       VALUES (?, ?, ?)""",
                    (session[0], student[0], "invalid_status")
                )
                conn.commit()
                self.log_result(test_name, "FAIL",
                    "Check constraint not enforced - invalid status accepted")
            except sqlite3.IntegrityError:
                self.log_result(test_name, "PASS",
                    "Check constraint enforced - invalid status rejected")
            finally:
                conn.close()

        except Exception as e:
            self.log_result(test_name, "FAIL", f"Setup error: {str(e)}")

    def test_db_data_type_consistency(self):
        """DB: Data types must be consistent with schema"""
        test_name = "db_data_type_consistency"
        try:
            conn = self.get_db_connection()

            # Get all courses and verify data types
            courses = conn.execute(
                "SELECT course_id, semester_id, code, name FROM courses LIMIT 5"
            ).fetchall()

            if not courses:
                self.log_result(test_name, "SKIP", "No courses to verify")
                return

            type_violations = 0
            for course in courses:
                # course_id, semester_id should be integers
                if not isinstance(course[0], int) or not isinstance(course[1], int):
                    type_violations += 1
                # code, name should be strings
                if not isinstance(course[2], str) or not isinstance(course[3], str):
                    type_violations += 1

            if type_violations == 0:
                self.log_result(test_name, "PASS",
                    f"All {len(courses)} course records have consistent data types")
            else:
                self.log_result(test_name, "FAIL",
                    f"Found {type_violations} type violations")

            conn.close()

        except Exception as e:
            self.log_result(test_name, "FAIL", f"Setup error: {str(e)}")

    # ═══════════════════════════════════════════════════════════════════════════
    # APPLICATION LEVEL CONSISTENCY TESTS
    # ═══════════════════════════════════════════════════════════════════════════

    def test_app_attendance_record_consistency(self):
        """APP: Attendance records must maintain student-course-session relationships"""
        test_name = "app_attendance_record_consistency"
        try:
            from app import create_app
            from app.db import get_db

            app = create_app()
            with app.app_context():
                conn = get_db()

                # Get test data
                session = conn.execute(
                    "SELECT s.session_id, c.course_id FROM attendance_sessions s "
                    "JOIN courses c ON s.course_id = c.course_id LIMIT 1"
                ).fetchone()

                if not session:
                    self.log_result(test_name, "SKIP", "No session data")
                    return

                session_id, course_id = session[0], session[1]

                # Get enrolled students
                students = conn.execute(
                    "SELECT user_id FROM enrollments WHERE course_id=? LIMIT 3",
                    (course_id,)
                ).fetchall()

                if not students:
                    self.log_result(test_name, "SKIP", "No enrolled students")
                    return

                # Add attendance records
                for student in students:
                    conn.execute(
                        """INSERT INTO attendance_records
                           (session_id, student_id, status)
                           VALUES (?, ?, ?)""",
                        (session_id, student[0], "present")
                    )

                # Verify consistency: all records exist and are valid
                records = conn.execute(
                    "SELECT COUNT(*) FROM attendance_records WHERE session_id=?",
                    (session_id,)
                ).fetchone()[0]

                if records >= len(students):
                    self.log_result(test_name, "PASS",
                        f"Attendance records consistent - {records} records verified")
                else:
                    self.log_result(test_name, "FAIL",
                        f"Expected {len(students)} records, found {records}")

        except ImportError:
            self.log_result(test_name, "SKIP", "Application not available")
        except Exception as e:
            self.log_result(test_name, "FAIL", f"Error: {str(e)}")

    # ═══════════════════════════════════════════════════════════════════════════
    # API LEVEL CONSISTENCY TESTS
    # ═══════════════════════════════════════════════════════════════════════════

    def test_api_semester_data_validation(self):
        """API: Semester creation must validate data consistency"""
        test_name = "api_semester_data_validation"
        try:
            # Test with missing required field
            response = requests.post(
                f"{self.api_base_url}/api/admin/semester",
                json={"is_active": False},  # missing "name"
                headers={"Authorization": "Bearer admin_token"},
                timeout=5
            )

            if response.status_code == 400:
                self.log_result(test_name, "PASS",
                    "API validates required fields - invalid data rejected")
            elif response.status_code == 201:
                self.log_result(test_name, "FAIL",
                    "API accepted incomplete data - validation missing")
            else:
                self.log_result(test_name, "SKIP",
                    f"API not properly configured (Status: {response.status_code})")

        except requests.exceptions.ConnectionError:
            self.log_result(test_name, "SKIP", "API server not running")
        except Exception as e:
            self.log_result(test_name, "FAIL", f"Error: {str(e)}")

    def run_all_tests(self):
        """Run all consistency tests for this level"""
        print(f"\n{'='*100}")
        print(f"CONSISTENCY TESTS - {self.level.upper()} LEVEL")
        print(f"{'='*100}\n")

        if self.level == "database":
            self.test_db_foreign_key_constraint()
            self.test_db_unique_constraint_usernames()
            self.test_db_cascade_delete_consistency()
            self.test_db_check_constraint_attendance_status()
            self.test_db_data_type_consistency()
        elif self.level == "application":
            self.test_app_attendance_record_consistency()
        elif self.level == "api":
            self.test_api_semester_data_validation()

        self.print_summary()

    def print_summary(self):
        """Print test summary"""
        total = self.pass_count + self.fail_count
        pass_pct = (self.pass_count / max(1, total)) * 100 if total > 0 else 0

        print(f"\n{'-'*100}")
        print(f"CONSISTENCY TEST SUMMARY ({self.level.upper()})")
        print(f"{'-'*100}")
        print(f"Total: {total} | Passed: {self.pass_count} | Failed: {self.fail_count}")
        print(f"Pass Rate: {pass_pct:.1f}%")

        # Save results
        output_file = f"consistency_test_results_{self.level}.json"
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
    tester = ConsistencyTester(level=level)
    tester.run_all_tests()
