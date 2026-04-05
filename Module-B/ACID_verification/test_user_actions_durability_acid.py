"""
test_user_actions_durability_acid.py
====================================
ACID Property: DURABILITY
Tests for ALL user actions - Data persistence and recovery
"""

import sqlite3
import json
import time
import random
from datetime import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class UserActionsDurabilityTester:
    """Test DURABILITY for all user actions"""

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
    # DURABILITY TESTS FOR USER ACTIONS
    # ═════════════════════════════════════════════════════════════════════════

    def test_admin_create_semester_durable(self):
        """ADMIN: Created semester must persist"""
        action = "admin_create_semester_durable"
        try:
            conn = self.get_connection()
            sem_name = f"DurSem_{int(time.time())}_{random.randint(1000, 9999)}"

            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    "INSERT INTO semesters (name, is_active) VALUES (?, ?)",
                    (sem_name, 0)
                )
                sem_id = cur.lastrowid
                conn.commit()
            except Exception as e:
                conn.rollback()
                self.log_result(action, "durability", "FAIL", str(e))
                return

            conn.close()

            # New connection to verify persistence
            conn2 = self.get_connection()
            persisted = conn2.execute(
                "SELECT name FROM semesters WHERE semester_id=?", (sem_id,)
            ).fetchone()

            if persisted and persisted["name"] == sem_name:
                self.log_result(action, "durability", "PASS", "Semester persisted")
            else:
                self.log_result(action, "durability", "FAIL", "Semester not persisted")

            conn2.close()
        except Exception as e:
            self.log_result(action, "durability", "FAIL", str(e))

    def test_admin_add_course_durable(self):
        """ADMIN: Added course must persist"""
        action = "admin_add_course_durable"
        try:
            conn = self.get_connection()
            sem = conn.execute("SELECT semester_id FROM semesters LIMIT 1").fetchone()

            if not sem:
                self.log_result(action, "durability", "SKIP", "No semester")
                return

            code = f"DURCRS{int(time.time())}"
            name = "Durable Course"

            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    "INSERT INTO courses (code, name, semester_id) VALUES (?, ?, ?)",
                    (code, name, sem[0])
                )
                course_id = cur.lastrowid
                conn.commit()
            except:
                conn.rollback()
                self.log_result(action, "durability", "FAIL", "Course insert failed")
                return

            conn.close()

            # Verify persistence
            conn2 = self.get_connection()
            persisted = conn2.execute(
                "SELECT name FROM courses WHERE course_id=?", (course_id,)
            ).fetchone()

            if persisted and persisted["name"] == name:
                self.log_result(action, "durability", "PASS", "Course persisted")
            else:
                self.log_result(action, "durability", "FAIL", "Course not persisted")

            conn2.close()
        except Exception as e:
            self.log_result(action, "durability", "FAIL", str(e))

    def test_instructor_create_session_durable(self):
        """INSTRUCTOR: Created attendance session must persist"""
        action = "instructor_create_session_durable"
        try:
            conn = self.get_connection()
            course = conn.execute("SELECT course_id FROM courses LIMIT 1").fetchone()

            if not course:
                self.log_result(action, "durability", "SKIP", "No course")
                return

            topic = f"Topic_{int(time.time())}"

            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    "INSERT INTO attendance_sessions (course_id, session_date, topic, created_by) VALUES (?, ?, ?, ?)",
                    (course[0], datetime.now().date(), topic, 1)
                )
                session_id = cur.lastrowid
                conn.commit()
            except:
                conn.rollback()
                self.log_result(action, "durability", "FAIL", "Session insert failed")
                return

            conn.close()

            # Verify persistence
            conn2 = self.get_connection()
            persisted = conn2.execute(
                "SELECT topic FROM attendance_sessions WHERE att_session_id=?", (session_id,)
            ).fetchone()

            if persisted and persisted["topic"] == topic:
                self.log_result(action, "durability", "PASS", "Session persisted")
            else:
                self.log_result(action, "durability", "FAIL", "Session not persisted")

            conn2.close()
        except Exception as e:
            self.log_result(action, "durability", "FAIL", str(e))

    def test_ta_update_attendance_durable(self):
        """TA: Updated attendance must persist"""
        action = "ta_update_attendance_durable"
        try:
            conn = self.get_connection()
            record = conn.execute(
                "SELECT record_id FROM attendance_records LIMIT 1"
            ).fetchone()

            if not record:
                self.log_result(action, "durability", "SKIP", "No attendance record")
                return

            record_id = record[0]
            new_status = "present"

            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "UPDATE attendance_records SET status=? WHERE record_id=?",
                    (new_status, record_id)
                )
                conn.commit()
            except:
                conn.rollback()
                self.log_result(action, "durability", "FAIL", "Update failed")
                return

            conn.close()

            # Verify persistence
            conn2 = self.get_connection()
            persisted = conn2.execute(
                "SELECT status FROM attendance_records WHERE record_id=?", (record_id,)
            ).fetchone()

            if persisted and persisted["status"] == new_status:
                self.log_result(action, "durability", "PASS", "Attendance update persisted")
            else:
                self.log_result(action, "durability", "FAIL", "Attendance update not persisted")

            conn2.close()
        except Exception as e:
            self.log_result(action, "durability", "FAIL", str(e))

    def test_instructor_accept_correction_durable(self):
        """INSTRUCTOR: Correction acceptance must persist"""
        action = "instructor_accept_correction_durable"
        try:
            conn = self.get_connection()
            request = conn.execute(
                "SELECT req_id FROM correction_requests WHERE status='pending' LIMIT 1"
            ).fetchone()

            if not request:
                self.log_result(action, "durability", "SKIP", "No pending correction")
                return

            req_id = request[0]

            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "UPDATE correction_requests SET status=? WHERE req_id=?",
                    ("accepted", req_id)
                )
                conn.commit()
            except:
                conn.rollback()
                self.log_result(action, "durability", "FAIL", "Update failed")
                return

            conn.close()

            # Verify persistence
            conn2 = self.get_connection()
            persisted = conn2.execute(
                "SELECT status FROM correction_requests WHERE req_id=?", (req_id,)
            ).fetchone()

            if persisted and persisted["status"] == "accepted":
                self.log_result(action, "durability", "PASS", "Correction acceptance persisted")
            else:
                self.log_result(action, "durability", "FAIL", "Correction acceptance not persisted")

            conn2.close()
        except Exception as e:
            self.log_result(action, "durability", "FAIL", str(e))

    def test_student_submit_correction_durable(self):
        """STUDENT: Submitted correction request must persist"""
        action = "student_submit_correction_durable"
        try:
            conn = self.get_connection()
            # Create a fresh test session with an absent record
            course = conn.execute("SELECT course_id FROM courses LIMIT 1").fetchone()
            student = conn.execute("SELECT user_id FROM users WHERE role='student' LIMIT 1").fetchone()

            if not course or not student:
                self.log_result(action, "durability", "SKIP", "Missing test data")
                return

            # Create a fresh attendance session for this test
            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    "INSERT INTO attendance_sessions (course_id, session_date, topic, created_by) VALUES (?, ?, ?, ?)",
                    (course[0], datetime.now().date(), f"DurTest_{int(time.time())}", 1)
                )
                session_id = cur.lastrowid
                conn.commit()
            except:
                conn.rollback()
                self.log_result(action, "durability", "SKIP", "Cannot create test session")
                return

            # Create an absent attendance record for the student
            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    "INSERT INTO attendance_records (att_session_id, student_id, status) VALUES (?, ?, ?)",
                    (session_id, student[0], "absent")
                )
                conn.commit()
            except:
                conn.rollback()
                self.log_result(action, "durability", "SKIP", "Cannot create absent record")
                return

            reason = f"Correction_{int(time.time())}"

            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    "INSERT INTO correction_requests (att_session_id, student_id, course_id, reason, status) VALUES (?, ?, ?, ?, ?)",
                    (session_id, student[0], course[0], reason, "pending")
                )
                req_id = cur.lastrowid
                conn.commit()
            except sqlite3.IntegrityError:
                conn.rollback()
                self.log_result(action, "durability", "FAIL", "Uniqueness constraint violated")
                return
            except:
                conn.rollback()
                self.log_result(action, "durability", "FAIL", "Insert failed")
                return

            conn.close()

            # Verify persistence
            conn2 = self.get_connection()
            persisted = conn2.execute(
                "SELECT reason FROM correction_requests WHERE req_id=?", (req_id,)
            ).fetchone()

            if persisted and persisted["reason"] == reason:
                self.log_result(action, "durability", "PASS", "Correction submission persisted")
            else:
                self.log_result(action, "durability", "FAIL", "Correction submission not persisted")

            conn2.close()
        except Exception as e:
            self.log_result(action, "durability", "FAIL", str(e))

    def run_all_tests(self):
        print(f"\n{'='*100}")
        print(f"USER ACTIONS DURABILITY TESTS - {self.level.upper()} LEVEL")
        print(f"{'='*100}\n")

        self.test_admin_create_semester_durable()
        self.test_admin_add_course_durable()
        self.test_instructor_create_session_durable()
        self.test_ta_update_attendance_durable()
        self.test_instructor_accept_correction_durable()
        self.test_student_submit_correction_durable()

        self.print_summary()

    def print_summary(self):
        total = self.pass_count + self.fail_count + self.skip_count
        pass_pct = (self.pass_count / max(1, self.pass_count + self.fail_count)) * 100 if (self.pass_count + self.fail_count) > 0 else 0

        print(f"\n{'-'*100}")
        print(f"USER ACTIONS DURABILITY SUMMARY ({self.level.upper()})")
        print(f"{'-'*100}")
        print(f"Total: {total} | Passed: {self.pass_count} | Failed: {self.fail_count} | Skipped: {self.skip_count}")
        print(f"Pass Rate: {pass_pct:.1f}%")

        output_file = f"user_actions_durability_test_results_{self.level}.json"
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
    tester = UserActionsDurabilityTester(level=level)
    tester.run_all_tests()
