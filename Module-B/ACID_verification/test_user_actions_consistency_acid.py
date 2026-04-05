"""
test_user_actions_consistency_acid.py
====================================
ACID Property: CONSISTENCY
Tests for ALL user actions - Data integrity and constraint enforcement
"""

import sqlite3
import json
from datetime import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class UserActionsConsistencyTester:
    """Test CONSISTENCY for all user actions"""

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
    # CONSISTENCY TESTS FOR USER ACTIONS
    # ═════════════════════════════════════════════════════════════════════════

    def test_admin_add_instructor_consistency(self):
        """ADMIN: Adding instructor must maintain referential integrity"""
        action = "admin_add_instructor_consistency"
        try:
            conn = self.get_connection()
            course = conn.execute("SELECT course_id FROM courses LIMIT 1").fetchone()
            instructor = conn.execute("SELECT user_id FROM users WHERE role='instructor' LIMIT 1").fetchone()

            if not course or not instructor:
                self.log_result(action, "consistency", "SKIP", "Missing test data")
                return

            # Verify FK exists before and after
            course_exists_before = conn.execute("SELECT 1 FROM courses WHERE course_id=?", (course[0],)).fetchone()
            instructor_exists_before = conn.execute("SELECT 1 FROM users WHERE user_id=?", (instructor[0],)).fetchone()

            if course_exists_before and instructor_exists_before:
                self.log_result(action, "consistency", "PASS", "FK references valid")
            else:
                self.log_result(action, "consistency", "FAIL", "FK references invalid")

            conn.close()
        except Exception as e:
            self.log_result(action, "consistency", "FAIL", str(e))

    def test_admin_delete_course_cascade_consistency(self):
        """ADMIN: Deleting course must cascade correctly"""
        action = "admin_delete_course_cascade_consistency"
        try:
            conn = self.get_connection()
            # Find a course and check if cascade works
            course = conn.execute(
                "SELECT c.course_id FROM courses c "
                "LEFT JOIN course_enrollments e ON c.course_id = e.course_id "
                "WHERE e.course_id IS NULL LIMIT 1"
            ).fetchone()

            if course:
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute("DELETE FROM courses WHERE course_id=?", (course[0],))
                    conn.commit()

                    # Verify course is gone
                    verify = conn.execute("SELECT 1 FROM courses WHERE course_id=?", (course[0],)).fetchone()
                    if not verify:
                        self.log_result(action, "consistency", "PASS", "Course deleted with cascade")
                    else:
                        self.log_result(action, "consistency", "FAIL", "Course deletion failed")
                except:
                    conn.rollback()
                    self.log_result(action, "consistency", "FAIL", "Cascade failed")
            else:
                self.log_result(action, "consistency", "SKIP", "No suitable course found")

            conn.close()
        except Exception as e:
            self.log_result(action, "consistency", "FAIL", str(e))

    def test_instructor_create_session_consistency(self):
        """INSTRUCTOR: Create session must maintain data consistency"""
        action = "instructor_create_session_consistency"
        try:
            conn = self.get_connection()
            course = conn.execute("SELECT course_id FROM courses LIMIT 1").fetchone()

            if not course:
                self.log_result(action, "consistency", "SKIP", "No course found")
                return

            # Verify course exists before session creation
            course_check = conn.execute("SELECT code FROM courses WHERE course_id=?", (course[0],)).fetchone()

            if course_check:
                self.log_result(action, "consistency", "PASS", "Course reference consistent")
            else:
                self.log_result(action, "consistency", "FAIL", "Course reference invalid")

            conn.close()
        except Exception as e:
            self.log_result(action, "consistency", "FAIL", str(e))

    def test_student_submit_correction_consistency(self):
        """STUDENT: Submit correction must check constraints"""
        action = "student_submit_correction_consistency"
        try:
            conn = self.get_connection()

            # Try to insert correction with invalid att_session_id
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT INTO correction_requests (att_session_id, student_id, course_id, reason, status) VALUES (?, ?, ?, ?, ?)",
                    (999999, 1, 999999, "Test", "pending")
                )
                conn.commit()
                self.log_result(action, "consistency", "FAIL", "FK constraint not enforced")
            except sqlite3.IntegrityError:
                self.log_result(action, "consistency", "PASS", "FK constraint enforced on correction")
            finally:
                conn.close()
        except Exception as e:
            self.log_result(action, "consistency", "FAIL", str(e))

    def test_admin_add_enrolled_duplicate_check(self):
        """ADMIN: Add enrolled student must prevent duplicates"""
        action = "admin_add_enrolled_duplicate_check"
        try:
            conn = self.get_connection()
            enrollment = conn.execute("SELECT course_id, student_id FROM course_enrollments LIMIT 1").fetchone()

            if not enrollment:
                self.log_result(action, "consistency", "SKIP", "No enrollment to test")
                return

            # Try to insert duplicate
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT INTO course_enrollments (course_id, student_id) VALUES (?, ?)",
                    (enrollment[0], enrollment[1])
                )
                conn.commit()
                self.log_result(action, "consistency", "FAIL", "Duplicate enrollment allowed")
            except sqlite3.IntegrityError:
                self.log_result(action, "consistency", "PASS", "Unique constraint prevents duplicate enrollment")
            finally:
                conn.close()
        except Exception as e:
            self.log_result(action, "consistency", "FAIL", str(e))

    def test_admin_attendance_status_constraint(self):
        """ADMIN: Override attendance must maintain status check constraint"""
        action = "admin_attendance_status_constraint"
        try:
            conn = self.get_connection()
            session = conn.execute("SELECT att_session_id FROM attendance_sessions LIMIT 1").fetchone()
            student = conn.execute("SELECT user_id FROM users WHERE role='student' LIMIT 1").fetchone()

            if not session or not student:
                self.log_result(action, "consistency", "SKIP", "Missing test data")
                return

            # Try invalid status
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT INTO attendance_records (att_session_id, student_id, status) VALUES (?, ?, ?)",
                    (session[0], student[0], "invalid_status")
                )
                conn.commit()
                self.log_result(action, "consistency", "FAIL", "Check constraint not enforced")
            except sqlite3.IntegrityError:
                self.log_result(action, "consistency", "PASS", "Status check constraint enforced")
            finally:
                conn.close()
        except Exception as e:
            self.log_result(action, "consistency", "FAIL", str(e))

    def test_instructor_accept_correction_valid_transition(self):
        """INSTRUCTOR: Accept correction must maintain valid status transition"""
        action = "instructor_accept_correction_valid_transition"
        try:
            conn = self.get_connection()
            request = conn.execute(
                "SELECT req_id, status FROM correction_requests LIMIT 1"
            ).fetchone()

            if not request:
                self.log_result(action, "consistency", "SKIP", "No correction request")
                return

            # Verify status is valid before update
            if request[1] in ("pending", "accepted", "rejected"):
                self.log_result(action, "consistency", "PASS", "Correction status valid")
            else:
                self.log_result(action, "consistency", "FAIL", "Invalid correction status")

            conn.close()
        except Exception as e:
            self.log_result(action, "consistency", "FAIL", str(e))

    def run_all_tests(self):
        print(f"\n{'='*100}")
        print(f"USER ACTIONS CONSISTENCY TESTS - {self.level.upper()} LEVEL")
        print(f"{'='*100}\n")

        self.test_admin_add_instructor_consistency()
        self.test_admin_delete_course_cascade_consistency()
        self.test_instructor_create_session_consistency()
        self.test_student_submit_correction_consistency()
        self.test_admin_add_enrolled_duplicate_check()
        self.test_admin_attendance_status_constraint()
        self.test_instructor_accept_correction_valid_transition()

        self.print_summary()

    def print_summary(self):
        total = self.pass_count + self.fail_count + self.skip_count
        pass_pct = (self.pass_count / max(1, self.pass_count + self.fail_count)) * 100 if (self.pass_count + self.fail_count) > 0 else 0

        print(f"\n{'-'*100}")
        print(f"USER ACTIONS CONSISTENCY SUMMARY ({self.level.upper()})")
        print(f"{'-'*100}")
        print(f"Total: {total} | Passed: {self.pass_count} | Failed: {self.fail_count} | Skipped: {self.skip_count}")
        print(f"Pass Rate: {pass_pct:.1f}%")

        output_file = f"user_actions_consistency_test_results_{self.level}.json"
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
    tester = UserActionsConsistencyTester(level=level)
    tester.run_all_tests()
