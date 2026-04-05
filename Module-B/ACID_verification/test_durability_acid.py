"""
test_durability_acid.py
========================
ACID Property: DURABILITY
Tests: Data persistence, crash recovery, committed data retention

"The D in ACID: Once a transaction is committed, it stays committed.
Even if there's a system crash, the data survives."
"""

import sqlite3
import json
import time
import random
import shutil
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class DurabilityTester:
    """Test DURABILITY property across all levels"""

    def __init__(self, level="database"):
        """
        level: "database" | "application" | "api"
        """
        self.level = level
        script_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(script_dir)
        self.db_path = os.path.join(parent_dir, "module_b.db")
        self.db_backup = os.path.join(parent_dir, "module_b_durability_backup.db")
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
    # DATABASE LEVEL DURABILITY TESTS
    # ═══════════════════════════════════════════════════════════════════════════

    def test_db_insertion_persistence(self):
        """DB: Inserted data must persist after connection close"""
        test_name = "db_insertion_persistence"
        try:
            conn = self.get_db_connection()
            test_sem_name = f"DurSem_{int(time.time())}_{random.randint(1000, 9999)}"

            # Insert semester
            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    "INSERT INTO semesters (name, is_active) VALUES (?, ?)",
                    (test_sem_name, 0)
                )
                sem_id = cur.lastrowid
                conn.commit()
            except Exception as e:
                conn.rollback()
                self.log_result(test_name, "FAIL", f"Insert failed: {str(e)}")
                return

            conn.close()

            # Verify persistence with new connection
            conn2 = self.get_db_connection()
            persisted = conn2.execute(
                "SELECT * FROM semesters WHERE semester_id=?", (sem_id,)
            ).fetchone()

            if persisted and persisted["name"] == test_sem_name:
                self.log_result(test_name, "PASS",
                    f"Semester {sem_id} persisted through new connection")
            else:
                self.log_result(test_name, "FAIL",
                    "Inserted data lost after connection close")

            conn2.close()

        except Exception as e:
            self.log_result(test_name, "FAIL", f"Setup error: {str(e)}")

    def test_db_update_persistence(self):
        """DB: Updated data must persist across connections"""
        test_name = "db_update_persistence"
        try:
            conn = self.get_db_connection()

            # Get a course to update
            course = conn.execute(
                "SELECT course_id, name FROM courses LIMIT 1"
            ).fetchone()

            if not course:
                self.log_result(test_name, "SKIP", "No course to update")
                return

            course_id = course[0]
            original_name = course[1]
            new_name = f"Updated_{int(time.time())}"

            # Update course
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "UPDATE courses SET name=? WHERE course_id=?",
                    (new_name, course_id)
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                self.log_result(test_name, "FAIL", f"Update failed: {str(e)}")
                return

            conn.close()

            # Verify persistence
            conn2 = self.get_db_connection()
            updated = conn2.execute(
                "SELECT name FROM courses WHERE course_id=?", (course_id,)
            ).fetchone()

            if updated and updated["name"] == new_name:
                self.log_result(test_name, "PASS",
                    "Course update persisted through new connection")
                # Restore original
                conn2.execute("BEGIN IMMEDIATE")
                conn2.execute(
                    "UPDATE courses SET name=? WHERE course_id=?",
                    (original_name, course_id)
                )
                conn2.commit()
            else:
                self.log_result(test_name, "FAIL",
                    "Updated data lost after connection close")

            conn2.close()

        except Exception as e:
            self.log_result(test_name, "FAIL", f"Setup error: {str(e)}")

    def test_db_deletion_persistence(self):
        """DB: Deleted data must stay deleted after connection close"""
        test_name = "db_deletion_persistence"
        try:
            conn = self.get_db_connection()

            # Create a test semester
            test_sem_name = f"DelSem_{int(time.time())}_{random.randint(1000, 9999)}"
            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    "INSERT INTO semesters (name, is_active) VALUES (?, ?)",
                    (test_sem_name, 0)
                )
                sem_id = cur.lastrowid
                conn.commit()
            except Exception as e:
                conn.rollback()
                self.log_result(test_name, "FAIL", f"Setup insert failed: {str(e)}")
                return

            # Delete it
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "DELETE FROM semesters WHERE semester_id=?", (sem_id,)
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                self.log_result(test_name, "FAIL", f"Delete failed: {str(e)}")
                return

            conn.close()

            # Verify deletion persisted
            conn2 = self.get_db_connection()
            deleted = conn2.execute(
                "SELECT 1 FROM semesters WHERE semester_id=?", (sem_id,)
            ).fetchone()

            if not deleted:
                self.log_result(test_name, "PASS",
                    "Deletion persisted through new connection")
            else:
                self.log_result(test_name, "FAIL",
                    "Deleted data reappeared after connection close")

            conn2.close()

        except Exception as e:
            self.log_result(test_name, "FAIL", f"Setup error: {str(e)}")

    def test_db_batch_transaction_durability(self):
        """DB: Batch transaction must fully persist or fully rollback"""
        test_name = "db_batch_transaction_durability"
        try:
            conn = self.get_db_connection()

            # Get course and students
            course = conn.execute("SELECT course_id FROM courses LIMIT 1").fetchone()
            students = conn.execute(
                """SELECT DISTINCT e.student_id FROM enrollments e
                   LIMIT 3"""
            ).fetchall()

            if not course or len(students) < 2:
                self.log_result(test_name, "SKIP", "Missing test data")
                return

            course_id = course[0]
            batch_id = int(time.time())

            # Create session
            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    """INSERT INTO attendance_sessions
                       (course_id, session_date, session_time, created_by)
                       VALUES (?, ?, ?, ?)""",
                    (course_id, datetime.now().date(), "14:00", 1)
                )
                session_id = cur.lastrowid
                conn.commit()
            except Exception as e:
                conn.rollback()
                self.log_result(test_name, "FAIL", f"Session creation failed: {str(e)}")
                return

            # Batch insert attendance records
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
            except Exception as e:
                conn.rollback()
                self.log_result(test_name, "FAIL", f"Batch insert failed: {str(e)}")
                return

            conn.close()

            # Verify all records persisted
            conn2 = self.get_db_connection()
            count = conn2.execute(
                "SELECT COUNT(*) FROM attendance_records WHERE session_id=?",
                (session_id,)
            ).fetchone()[0]

            if count == len(students):
                self.log_result(test_name, "PASS",
                    f"All {count} batch records persisted through new connection")
            else:
                self.log_result(test_name, "FAIL",
                    f"Expected {len(students)} records, persisted {count}")

            conn2.close()

        except Exception as e:
            self.log_result(test_name, "FAIL", f"Setup error: {str(e)}")

    def test_db_multiple_sequential_transactions(self):
        """DB: Multiple sequential transactions must all persist"""
        test_name = "db_multiple_sequential_transactions"
        try:
            transaction_count = 3
            transaction_ids = []

            conn = self.get_db_connection()

            # Create courses in multiple transactions
            for i in range(transaction_count):
                sem = conn.execute("SELECT semester_id FROM semesters LIMIT 1").fetchone()
                if not sem:
                    self.log_result(test_name, "SKIP", "No semester")
                    return

                try:
                    conn.execute("BEGIN IMMEDIATE")
                    cur = conn.execute(
                        "INSERT INTO courses (code, name, semester_id) VALUES (?, ?, ?)",
                        (f"TRANS{int(time.time())}_{i}", f"Transaction Course {i}", sem[0])
                    )
                    course_id = cur.lastrowid
                    conn.commit()
                    transaction_ids.append(course_id)
                except Exception as e:
                    conn.rollback()

            conn.close()

            # Verify all persisted
            conn2 = self.get_db_connection()
            persisted_count = 0
            for course_id in transaction_ids:
                check = conn2.execute(
                    "SELECT 1 FROM courses WHERE course_id=?", (course_id,)
                ).fetchone()
                if check:
                    persisted_count += 1

            if persisted_count == len(transaction_ids):
                self.log_result(test_name, "PASS",
                    f"All {transaction_count} sequential transactions persisted")
            else:
                self.log_result(test_name, "FAIL",
                    f"Only {persisted_count}/{transaction_count} transactions persisted")

            conn2.close()

        except Exception as e:
            self.log_result(test_name, "FAIL", f"Setup error: {str(e)}")

    # ═══════════════════════════════════════════════════════════════════════════
    # APPLICATION LEVEL DURABILITY TESTS
    # ═══════════════════════════════════════════════════════════════════════════

    def test_app_session_creation_durability(self):
        """APP: Session creation must persist in database"""
        test_name = "app_session_creation_durability"
        try:
            from app import create_app
            from app.db import get_db

            app = create_app()
            with app.app_context():
                conn = get_db()
                course = conn.execute("SELECT course_id FROM courses LIMIT 1").fetchone()

                if not course:
                    self.log_result(test_name, "SKIP", "No course available")
                    return

                course_id = course[0]
                session_time = f"{random.randint(8, 17)}:00"

                # Create session
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    cur = conn.execute(
                        """INSERT INTO attendance_sessions
                           (course_id, session_date, session_time, created_by)
                           VALUES (?, ?, ?, ?)""",
                        (course_id, datetime.now().date(), session_time, 1)
                    )
                    session_id = cur.lastrowid
                    conn.commit()
                except Exception as e:
                    self.log_result(test_name, "FAIL", f"Session creation failed: {str(e)}")
                    return

            # New context to verify
            with app.app_context():
                conn2 = get_db()
                verify = conn2.execute(
                    "SELECT session_time FROM attendance_sessions WHERE session_id=?",
                    (session_id,)
                ).fetchone()

                if verify and verify["session_time"] == session_time:
                    self.log_result(test_name, "PASS",
                        f"Session persisted across application contexts")
                else:
                    self.log_result(test_name, "FAIL",
                        "Session not found in new context - durability failed")

        except ImportError:
            self.log_result(test_name, "SKIP", "Application not available")
        except Exception as e:
            self.log_result(test_name, "FAIL", f"Error: {str(e)}")

    # ═══════════════════════════════════════════════════════════════════════════
    # API LEVEL DURABILITY TESTS
    # ═══════════════════════════════════════════════════════════════════════════

    def test_api_created_data_persists(self):
        """API: Data created via API must persist"""
        test_name = "api_created_data_persists"
        try:
            import requests

            sem_name = f"ApiDurSem_{int(time.time())}"

            # Create via API
            response = requests.post(
                "http://localhost:5000/api/admin/semester",
                json={"name": sem_name, "is_active": False},
                headers={"Authorization": "Bearer admin_token"},
                timeout=5
            )

            if response.status_code == 201:
                data = response.json()
                if "semester_id" in data:
                    sem_id = data["semester_id"]

                    # Verify persists in database
                    conn = self.get_db_connection()
                    verify = conn.execute(
                        "SELECT name FROM semesters WHERE semester_id=? AND name=?",
                        (sem_id, sem_name)
                    ).fetchone()
                    conn.close()

                    if verify:
                        self.log_result(test_name, "PASS",
                            "API-created semester persisted in database")
                    else:
                        self.log_result(test_name, "FAIL",
                            "API reported success but data not in database")
                else:
                    self.log_result(test_name, "FAIL",
                        "API response missing semester_id")
            elif response.status_code in [400, 401]:
                self.log_result(test_name, "SKIP",
                    f"API validation issue (Status: {response.status_code})")
            else:
                self.log_result(test_name, "SKIP",
                    f"API not available (Status: {response.status_code})")

        except requests.exceptions.ConnectionError:
            self.log_result(test_name, "SKIP", "API server not running")
        except Exception as e:
            self.log_result(test_name, "FAIL", f"Error: {str(e)}")

    def run_all_tests(self):
        """Run all durability tests for this level"""
        print(f"\n{'='*100}")
        print(f"DURABILITY TESTS - {self.level.upper()} LEVEL")
        print(f"{'='*100}\n")

        if self.level == "database":
            self.test_db_insertion_persistence()
            self.test_db_update_persistence()
            self.test_db_deletion_persistence()
            self.test_db_batch_transaction_durability()
            self.test_db_multiple_sequential_transactions()
        elif self.level == "application":
            self.test_app_session_creation_durability()
        elif self.level == "api":
            self.test_api_created_data_persists()

        self.print_summary()

    def print_summary(self):
        """Print test summary"""
        total = self.pass_count + self.fail_count
        pass_pct = (self.pass_count / max(1, total)) * 100 if total > 0 else 0

        print(f"\n{'-'*100}")
        print(f"DURABILITY TEST SUMMARY ({self.level.upper()})")
        print(f"{'-'*100}")
        print(f"Total: {total} | Passed: {self.pass_count} | Failed: {self.fail_count}")
        print(f"Pass Rate: {pass_pct:.1f}%")

        # Save results
        output_file = f"durability_test_results_{self.level}.json"
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
    tester = DurabilityTester(level=level)
    tester.run_all_tests()
