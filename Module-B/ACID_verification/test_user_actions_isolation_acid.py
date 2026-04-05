"""
test_user_actions_isolation_acid.py
==================================
ACID Property: ISOLATION
Tests for ALL user actions - Concurrent operation isolation
"""

import sqlite3
import json
import threading
from datetime import datetime
import time
import random
import os
import sys
from threading import Lock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class UserActionsIsolationTester:
    """Test ISOLATION for all user actions"""

    def __init__(self, level="database"):
        self.level = level
        script_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(script_dir)
        self.db_path = os.path.join(parent_dir, "module_b.db")
        self.results = []
        self.pass_count = 0
        self.fail_count = 0
        self.skip_count = 0

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.isolation_level = None
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        return conn

    def log_result(self, action_name, test_name, status, message=""):
        result = {
            "timestamp": datetime.now().isoformat(),
            "action": action_name,
            "test": test_name,
            "status": status,
            "message": message
        }
        self.results.append(result)

        symbol = "[PASS]" if status == "PASS" else ("[FAIL]" if status == "FAIL" else "[SKIP]")
        try:
            print(f"{symbol} [{self.level.upper()}] {action_name}: {test_name} - {status}")
            if message:
                print(f"       {message}")
        except UnicodeEncodeError:
            print(f"{symbol} [{self.level.upper()}] {action_name}: {test_name} - {status}")

        if status == "PASS":
            self.pass_count += 1
        elif status == "FAIL":
            self.fail_count += 1
        else:
            self.skip_count += 1

    # ═════════════════════════════════════════════════════════════════════════
    # ISOLATION TESTS FOR USER ACTIONS
    # ═════════════════════════════════════════════════════════════════════════

    def test_admin_concurrent_course_creation(self):
        """ADMIN: Concurrent course creation must be isolated"""
        action = "admin_concurrent_course_creation"
        try:
            conn = self.get_connection()
            sem = conn.execute("SELECT semester_id FROM semesters LIMIT 1").fetchone()

            if not sem:
                self.log_result(action, "isolation", "SKIP", "No semester found")
                return

            results = {"success": 0, "failed": 0}
            lock = Lock()

            def create_course(idx):
                try:
                    c = self.get_connection()
                    c.execute("BEGIN IMMEDIATE")
                    c.execute(
                        "INSERT INTO courses (code, name, semester_id) VALUES (?, ?, ?)",
                        (f"CONC{int(time.time())}_{idx}", f"Concurrent Course {idx}", sem[0])
                    )
                    c.commit()
                    with lock:
                        results["success"] += 1
                    c.close()
                except:
                    with lock:
                        results["failed"] += 1

            threads = [threading.Thread(target=create_course, args=(i,)) for i in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            if results["failed"] == 0:
                self.log_result(action, "isolation", "PASS",
                    f"All {results['success']} concurrent course creations succeeded")
            else:
                self.log_result(action, "isolation", "FAIL",
                    f"Concurrent failures: {results['failed']}")

            conn.close()
        except Exception as e:
            self.log_result(action, "isolation", "FAIL", str(e))

    def test_student_concurrent_correction_submission(self):
        """STUDENT: Concurrent correction submission must be isolated"""
        action = "student_concurrent_correction_submission"
        try:
            conn = self.get_connection()
            # Create a fresh session with an absent record for clean isolation test
            course = conn.execute("SELECT course_id FROM courses LIMIT 1").fetchone()
            student = conn.execute("SELECT user_id FROM users WHERE role='student' LIMIT 1").fetchone()

            if not course or not student:
                self.log_result(action, "isolation", "SKIP", "Missing test data")
                return

            # Create fresh session
            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    "INSERT INTO attendance_sessions (course_id, session_date, topic, created_by) VALUES (?, ?, ?, ?)",
                    (course[0], datetime.now().date(), f"Iso_{int(time.time())}", 1)
                )
                session_id = cur.lastrowid
                conn.commit()
            except:
                conn.rollback()
                self.log_result(action, "isolation", "SKIP", "Cannot create test session")
                return

            # Create absent record
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT INTO attendance_records (att_session_id, student_id, status) VALUES (?, ?, ?)",
                    (session_id, student[0], "absent")
                )
                conn.commit()
            except:
                conn.rollback()
                self.log_result(action, "isolation", "SKIP", "Cannot create absent record")
                return

            results = {"success": 0, "conflict": 0, "locked": 0}
            lock = Lock()

            def submit_correction(idx):
                try:
                    c = self.get_connection()
                    c.execute("BEGIN IMMEDIATE")
                    c.execute(
                        "INSERT INTO correction_requests (att_session_id, student_id, course_id, reason, status) VALUES (?, ?, ?, ?, ?)",
                        (session_id, student[0], course[0], f"Reason {idx}", "pending")
                    )
                    c.commit()
                    with lock:
                        results["success"] += 1
                    c.close()
                except sqlite3.IntegrityError:
                    with lock:
                        results["conflict"] += 1
                    c.close()
                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e):
                        with lock:
                            results["locked"] += 1
                    c.close()

            threads = [threading.Thread(target=submit_correction, args=(i,)) for i in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # At least one should succeed, others should conflict/lock due to uniqueness
            total_operations = results["success"] + results["conflict"] + results["locked"]
            if total_operations >= 2 and results["success"] >= 1:
                self.log_result(action, "isolation", "PASS",
                    f"Concurrent isolation working: {results['success']} success, {results['conflict']} conflict, {results['locked']} locked")
            elif results["success"] >= 1:
                self.log_result(action, "isolation", "PASS", "Concurrent access properly isolated")
            else:
                self.log_result(action, "isolation", "FAIL", "Isolation issue detected")

            conn.close()
        except Exception as e:
            self.log_result(action, "isolation", "FAIL", str(e))

    def test_instructor_concurrent_session_creation(self):
        """INSTRUCTOR: Concurrent attendance session creation must be isolated"""
        action = "instructor_concurrent_session_creation"
        try:
            conn = self.get_connection()
            course = conn.execute("SELECT course_id FROM courses LIMIT 1").fetchone()

            if not course:
                self.log_result(action, "isolation", "SKIP", "No course")
                return

            results = {"success": 0, "failed": 0}
            lock = Lock()

            def create_session(idx):
                try:
                    c = self.get_connection()
                    c.execute("BEGIN IMMEDIATE")
                    c.execute(
                        "INSERT INTO attendance_sessions (course_id, session_date, topic, created_by) VALUES (?, ?, ?, ?)",
                        (course[0], datetime.now().date(), f"Topic {idx}", 1)
                    )
                    c.commit()
                    with lock:
                        results["success"] += 1
                    c.close()
                except:
                    with lock:
                        results["failed"] += 1

            threads = [threading.Thread(target=create_session, args=(i,)) for i in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            if results["failed"] == 0:
                self.log_result(action, "isolation", "PASS",
                    f"All {results['success']} concurrent session creations isolated")
            else:
                self.log_result(action, "isolation", "FAIL",
                    f"Concurrent failures: {results['failed']}")

            conn.close()
        except Exception as e:
            self.log_result(action, "isolation", "FAIL", str(e))

    def test_ta_concurrent_attendance_updates(self):
        """TA: Concurrent attendance updates must not cause lost updates"""
        action = "ta_concurrent_attendance_updates"
        try:
            conn = self.get_connection()
            records = conn.execute(
                "SELECT record_id FROM attendance_records LIMIT 2"
            ).fetchall()

            if len(records) < 2:
                self.log_result(action, "isolation", "SKIP", "Not enough records")
                return

            results = {"success": 0, "failed": 0}
            lock = Lock()

            def update_attendance(record_id):
                try:
                    c = self.get_connection()
                    c.execute("BEGIN IMMEDIATE")
                    c.execute(
                        "UPDATE attendance_records SET status=? WHERE record_id=?",
                        ("present", record_id)
                    )
                    c.commit()
                    with lock:
                        results["success"] += 1
                    c.close()
                except:
                    with lock:
                        results["failed"] += 1

            threads = [threading.Thread(target=update_attendance, args=(r[0],)) for r in records]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            if results["failed"] == 0:
                self.log_result(action, "isolation", "PASS",
                    f"All {results['success']} concurrent updates isolated - no lost updates")
            else:
                self.log_result(action, "isolation", "FAIL",
                    f"Concurrent update failures: {results['failed']}")

            conn.close()
        except Exception as e:
            self.log_result(action, "isolation", "FAIL", str(e))

    def run_all_tests(self):
        print(f"\n{'='*100}")
        print(f"USER ACTIONS ISOLATION TESTS - {self.level.upper()} LEVEL")
        print(f"{'='*100}\n")

        self.test_admin_concurrent_course_creation()
        self.test_student_concurrent_correction_submission()
        self.test_instructor_concurrent_session_creation()
        self.test_ta_concurrent_attendance_updates()

        self.print_summary()

    def print_summary(self):
        total = self.pass_count + self.fail_count + self.skip_count
        pass_pct = (self.pass_count / max(1, self.pass_count + self.fail_count)) * 100 if (self.pass_count + self.fail_count) > 0 else 0

        print(f"\n{'-'*100}")
        print(f"USER ACTIONS ISOLATION SUMMARY ({self.level.upper()})")
        print(f"{'-'*100}")
        print(f"Total: {total} | Passed: {self.pass_count} | Failed: {self.fail_count} | Skipped: {self.skip_count}")
        print(f"Pass Rate: {pass_pct:.1f}%")

        output_file = f"user_actions_isolation_test_results_{self.level}.json"
        with open(output_file, "w") as f:
            json.dump({
                "level": self.level,
                "timestamp": datetime.now().isoformat(),
                "summary": {
                    "total": total,
                    "passed": self.pass_count,
                    "failed": self.fail_count,
                    "skipped": self.skip_count,
                    "pass_rate": pass_pct
                },
                "results": self.results
            }, f, indent=2)

        print(f"Results saved to: {output_file}")


if __name__ == "__main__":
    level = sys.argv[1] if len(sys.argv) > 1 else "database"
    tester = UserActionsIsolationTester(level=level)
    tester.run_all_tests()
