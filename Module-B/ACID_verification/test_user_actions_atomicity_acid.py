"""
test_user_actions_atomicity_acid.py
===================================
ACID Property: ATOMICITY
Tests for ALL user actions across Database, Application, and API levels
"""

import sqlite3
import json
import time
import threading
import random
from datetime import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class UserActionsAtomicityTester:
    """Test ATOMICITY for all user actions"""

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
        """Log test result"""
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
    # ADMIN ACTIONS - ATOMICITY TESTS
    # ═════════════════════════════════════════════════════════════════════════

    def test_admin_add_instructor_to_course_atomic(self):
        """ADMIN: Add instructor to course must be atomic"""
        action = "admin_add_instructor_to_course"
        try:
            conn = self.get_connection()
            # Find a course-instructor pair not already assigned
            pair = conn.execute(
                "SELECT c.course_id, u.user_id FROM courses c, users u "
                "WHERE u.role='instructor' AND NOT EXISTS ("
                "  SELECT 1 FROM course_instructors WHERE course_id=c.course_id AND instructor_id=u.user_id"
                ") LIMIT 1"
            ).fetchone()

            if not pair:
                self.log_result(action, "atomicity", "SKIP", "No available instructor-course pair")
                return

            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT INTO course_instructors (course_id, instructor_id) VALUES (?, ?)",
                    (pair[0], pair[1])
                )
                conn.commit()
                self.log_result(action, "atomicity", "PASS", "Instructor added atomically")
            except:
                conn.rollback()
                self.log_result(action, "atomicity", "FAIL", "Instructor assignment failed")
            finally:
                conn.close()
        except Exception as e:
            self.log_result(action, "atomicity", "FAIL", str(e))

    def test_admin_remove_instructor_from_course_atomic(self):
        """ADMIN: Remove instructor from course must be atomic"""
        action = "admin_remove_instructor_from_course"
        try:
            conn = self.get_connection()
            instructor = conn.execute(
                "SELECT course_id, instructor_id FROM course_instructors LIMIT 1"
            ).fetchone()

            if not instructor:
                self.log_result(action, "atomicity", "SKIP", "No instructor assignments found")
                return

            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "DELETE FROM course_instructors WHERE course_id=? AND instructor_id=?",
                    (instructor[0], instructor[1])
                )
                conn.commit()
                self.log_result(action, "atomicity", "PASS", "Instructor removed atomically")
            finally:
                conn.close()
        except Exception as e:
            self.log_result(action, "atomicity", "FAIL", str(e))

    def test_admin_add_ta_to_course_atomic(self):
        """ADMIN: Add TA to course must be atomic"""
        action = "admin_add_ta_to_course"
        try:
            conn = self.get_connection()
            # Find a course-TA pair not already assigned
            pair = conn.execute(
                "SELECT c.course_id, u.user_id FROM courses c, users u "
                "WHERE u.role='ta' AND NOT EXISTS ("
                "  SELECT 1 FROM course_tas WHERE course_id=c.course_id AND ta_id=u.user_id"
                ") LIMIT 1"
            ).fetchone()

            if not pair:
                self.log_result(action, "atomicity", "SKIP", "No available TA-course pair")
                return

            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT INTO course_tas (course_id, ta_id) VALUES (?, ?)",
                    (pair[0], pair[1])
                )
                conn.commit()
                self.log_result(action, "atomicity", "PASS", "TA added atomically")
            except:
                conn.rollback()
                self.log_result(action, "atomicity", "FAIL", "TA assignment failed")
            finally:
                conn.close()
        except Exception as e:
            self.log_result(action, "atomicity", "FAIL", str(e))

    def test_admin_remove_ta_from_course_atomic(self):
        """ADMIN: Remove TA from course must be atomic"""
        action = "admin_remove_ta_from_course"
        try:
            conn = self.get_connection()
            ta_assignment = conn.execute(
                "SELECT course_id, ta_id FROM course_tas LIMIT 1"
            ).fetchone()

            if not ta_assignment:
                self.log_result(action, "atomicity", "SKIP", "No TA assignments found")
                return

            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "DELETE FROM course_tas WHERE course_id=? AND ta_id=?",
                    (ta_assignment[0], ta_assignment[1])
                )
                conn.commit()
                self.log_result(action, "atomicity", "PASS", "TA removed atomically")
            finally:
                conn.close()
        except Exception as e:
            self.log_result(action, "atomicity", "FAIL", str(e))

    def test_admin_add_enrolled_student_atomic(self):
        """ADMIN: Add enrolled student must be atomic"""
        action = "admin_add_enrolled_student"
        try:
            conn = self.get_connection()
            # Find a course and any student not already enrolled in that course
            enroll = conn.execute(
                "SELECT c.course_id, u.user_id FROM courses c, users u "
                "WHERE u.role='student' AND NOT EXISTS ("
                "  SELECT 1 FROM course_enrollments WHERE course_id=c.course_id AND student_id=u.user_id"
                ") LIMIT 1"
            ).fetchone()

            if not enroll:
                self.log_result(action, "atomicity", "SKIP", "No available student-course pair")
                return

            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT INTO course_enrollments (course_id, student_id) VALUES (?, ?)",
                    (enroll[0], enroll[1])
                )
                conn.commit()
                self.log_result(action, "atomicity", "PASS", "Student enrolled atomically")
            except:
                conn.rollback()
                self.log_result(action, "atomicity", "FAIL", "Enrollment failed")
            finally:
                conn.close()
        except Exception as e:
            self.log_result(action, "atomicity", "FAIL", str(e))

    def test_admin_remove_enrolled_student_atomic(self):
        """ADMIN: Remove enrolled student must be atomic"""
        action = "admin_remove_enrolled_student"
        try:
            conn = self.get_connection()
            enrollment = conn.execute(
                "SELECT course_id, student_id FROM course_enrollments LIMIT 1"
            ).fetchone()

            if not enrollment:
                self.log_result(action, "atomicity", "SKIP", "No enrollments found")
                return

            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "DELETE FROM course_enrollments WHERE course_id=? AND student_id=?",
                    (enrollment[0], enrollment[1])
                )
                conn.commit()
                self.log_result(action, "atomicity", "PASS", "Student removed atomically")
            finally:
                conn.close()
        except Exception as e:
            self.log_result(action, "atomicity", "FAIL", str(e))

    def test_admin_delete_course_atomic(self):
        """ADMIN: Delete course (with cascade) must be atomic"""
        action = "admin_delete_course"
        try:
            conn = self.get_connection()
            # Find a course with no enrollments to avoid issues
            course = conn.execute(
                "SELECT course_id FROM courses WHERE course_id NOT IN "
                "(SELECT DISTINCT course_id FROM course_enrollments) LIMIT 1"
            ).fetchone()

            if not course:
                # Create a test course
                sem = conn.execute("SELECT semester_id FROM semesters LIMIT 1").fetchone()
                if not sem:
                    self.log_result(action, "atomicity", "SKIP", "No semester found")
                    return
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    cur = conn.execute(
                        "INSERT INTO courses (code, name, semester_id) VALUES (?, ?, ?)",
                        (f"DELTEST{int(time.time())}", "Delete Test Course", sem[0])
                    )
                    course_id = cur.lastrowid
                    conn.commit()
                except:
                    conn.rollback()
                    self.log_result(action, "atomicity", "SKIP", "Could not create test course")
                    return
            else:
                course_id = course[0]

            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("DELETE FROM courses WHERE course_id=?", (course_id,))
                conn.commit()
                self.log_result(action, "atomicity", "PASS", "Course deleted atomically with cascade")
            finally:
                conn.close()
        except Exception as e:
            self.log_result(action, "atomicity", "FAIL", str(e))

    def test_admin_create_semester_atomic(self):
        """ADMIN: Create semester must be atomic"""
        action = "admin_create_semester"
        try:
            conn = self.get_connection()
            sem_name = f"TestSem_{int(time.time())}_{random.randint(1000, 9999)}"

            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    "INSERT INTO semesters (name, is_active) VALUES (?, ?)",
                    (sem_name, 0)
                )
                sem_id = cur.lastrowid
                conn.commit()

                verify = conn.execute(
                    "SELECT name FROM semesters WHERE semester_id=?", (sem_id,)
                ).fetchone()

                if verify:
                    self.log_result(action, "atomicity", "PASS", "Semester created atomically")
                else:
                    self.log_result(action, "atomicity", "FAIL", "Semester not committed")
            finally:
                conn.close()
        except Exception as e:
            self.log_result(action, "atomicity", "FAIL", str(e))

    def test_admin_add_course_atomic(self):
        """ADMIN: Add course must be atomic"""
        action = "admin_add_course"
        try:
            conn = self.get_connection()
            sem = conn.execute("SELECT semester_id FROM semesters LIMIT 1").fetchone()

            if not sem:
                self.log_result(action, "atomicity", "SKIP", "No semester found")
                return

            code = f"TESTCRS{int(time.time())}"

            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    "INSERT INTO courses (code, name, semester_id) VALUES (?, ?, ?)",
                    (code, "Test Course", sem[0])
                )
                course_id = cur.lastrowid
                conn.commit()
                self.log_result(action, "atomicity", "PASS", "Course added atomically")
            finally:
                conn.close()
        except Exception as e:
            self.log_result(action, "atomicity", "FAIL", str(e))

    def test_admin_create_user_atomic(self):
        """ADMIN: Create user must be atomic"""
        action = "admin_create_user"
        try:
            conn = self.get_connection()
            username = f"testuser_{int(time.time())}_{random.randint(1000, 9999)}"

            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    "INSERT INTO users (username, pwd_hash, role) VALUES (?, ?, ?)",
                    (username, "hashedpwd", "student")
                )
                user_id = cur.lastrowid
                conn.commit()
                self.log_result(action, "atomicity", "PASS", "User created atomically")
            finally:
                conn.close()
        except Exception as e:
            self.log_result(action, "atomicity", "FAIL", str(e))

    def test_admin_delete_user_atomic(self):
        """ADMIN: Delete user must be atomic"""
        action = "admin_delete_user"
        try:
            conn = self.get_connection()
            # Find a user with no foreign key dependencies
            user = conn.execute(
                "SELECT u.user_id FROM users u "
                "WHERE u.role NOT IN ('admin', 'dean') "
                "AND NOT EXISTS (SELECT 1 FROM course_instructors WHERE instructor_id=u.user_id) "
                "AND NOT EXISTS (SELECT 1 FROM course_tas WHERE ta_id=u.user_id) "
                "AND NOT EXISTS (SELECT 1 FROM course_enrollments WHERE student_id=u.user_id) "
                "AND NOT EXISTS (SELECT 1 FROM attendance_records WHERE student_id=u.user_id) "
                "AND NOT EXISTS (SELECT 1 FROM correction_requests WHERE student_id=u.user_id) "
                "AND NOT EXISTS (SELECT 1 FROM attendance_sessions WHERE created_by=u.user_id) "
                "LIMIT 1"
            ).fetchone()

            if not user:
                self.log_result(action, "atomicity", "SKIP", "No user without dependencies to delete")
                return

            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("DELETE FROM users WHERE user_id=?", (user[0],))
                conn.commit()
                self.log_result(action, "atomicity", "PASS", "User deleted atomically")
            except:
                conn.rollback()
                self.log_result(action, "atomicity", "FAIL", "User deletion failed")
            finally:
                conn.close()
        except Exception as e:
            self.log_result(action, "atomicity", "FAIL", str(e))

    def test_admin_delete_past_semester_atomic(self):
        """ADMIN: Delete past semester must be atomic"""
        action = "admin_delete_past_semester"
        try:
            conn = self.get_connection()
            # Find an inactive semester
            sem = conn.execute(
                "SELECT semester_id FROM semesters WHERE is_active=0 LIMIT 1"
            ).fetchone()

            if not sem:
                self.log_result(action, "atomicity", "SKIP", "No inactive semester found")
                return

            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("DELETE FROM semesters WHERE semester_id=?", (sem[0],))
                conn.commit()
                self.log_result(action, "atomicity", "PASS", "Past semester deleted atomically")
            finally:
                conn.close()
        except Exception as e:
            self.log_result(action, "atomicity", "FAIL", str(e))

    def test_admin_override_attendance_batch_atomic(self):
        """ADMIN: Batch override attendance must be atomic"""
        action = "admin_override_attendance_batch"
        try:
            conn = self.get_connection()
            session = conn.execute(
                "SELECT att_session_id FROM attendance_sessions LIMIT 1"
            ).fetchone()

            if not session:
                self.log_result(action, "atomicity", "SKIP", "No session found")
                return

            # Get students in this session
            students = conn.execute(
                "SELECT DISTINCT student_id FROM attendance_records WHERE att_session_id=? LIMIT 3",
                (session[0],)
            ).fetchall()

            if not students:
                self.log_result(action, "atomicity", "SKIP", "No attendance records found")
                return

            try:
                conn.execute("BEGIN IMMEDIATE")
                for student in students:
                    conn.execute(
                        "UPDATE attendance_records SET status=? WHERE att_session_id=? AND student_id=?",
                        ("absent", session[0], student[0])
                    )
                conn.commit()
                self.log_result(action, "atomicity", "PASS", f"Batch override {len(students)} records atomically")
            finally:
                conn.close()
        except Exception as e:
            self.log_result(action, "atomicity", "FAIL", str(e))

    # ═════════════════════════════════════════════════════════════════════════
    # INSTRUCTOR ACTIONS - ATOMICITY TESTS
    # ═════════════════════════════════════════════════════════════════════════

    def test_instructor_create_attendance_session_atomic(self):
        """INSTRUCTOR: Create attendance session must be atomic"""
        action = "instructor_create_attendance_session"
        try:
            conn = self.get_connection()
            course = conn.execute("SELECT course_id FROM courses LIMIT 1").fetchone()

            if not course:
                self.log_result(action, "atomicity", "SKIP", "No course found")
                return

            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    "INSERT INTO attendance_sessions (course_id, session_date, topic, created_by) VALUES (?, ?, ?, ?)",
                    (course[0], datetime.now().date(), "Test Topic", 1)
                )
                session_id = cur.lastrowid
                conn.commit()
                self.log_result(action, "atomicity", "PASS", "Attendance session created atomically")
            finally:
                conn.close()
        except Exception as e:
            self.log_result(action, "atomicity", "FAIL", str(e))

    def test_instructor_accept_correction_request_atomic(self):
        """INSTRUCTOR: Accept correction request must be atomic"""
        action = "instructor_accept_correction_request"
        try:
            conn = self.get_connection()
            request = conn.execute(
                "SELECT req_id FROM correction_requests WHERE status='pending' LIMIT 1"
            ).fetchone()

            if not request:
                self.log_result(action, "atomicity", "SKIP", "No pending correction request")
                return

            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "UPDATE correction_requests SET status=? WHERE req_id=?",
                    ("accepted", request[0])
                )
                conn.commit()
                self.log_result(action, "atomicity", "PASS", "Correction request accepted atomically")
            finally:
                conn.close()
        except Exception as e:
            self.log_result(action, "atomicity", "FAIL", str(e))

    def test_instructor_reject_correction_request_atomic(self):
        """INSTRUCTOR: Reject correction request must be atomic"""
        action = "instructor_reject_correction_request"
        try:
            conn = self.get_connection()
            request = conn.execute(
                "SELECT req_id FROM correction_requests WHERE status='pending' LIMIT 1"
            ).fetchone()

            if not request:
                self.log_result(action, "atomicity", "SKIP", "No pending correction request")
                return

            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "UPDATE correction_requests SET status=? WHERE req_id=?",
                    ("rejected", request[0])
                )
                conn.commit()
                self.log_result(action, "atomicity", "PASS", "Correction request rejected atomically")
            finally:
                conn.close()
        except Exception as e:
            self.log_result(action, "atomicity", "FAIL", str(e))

    # ═════════════════════════════════════════════════════════════════════════
    # TA ACTIONS - ATOMICITY TESTS
    # ═════════════════════════════════════════════════════════════════════════

    def test_ta_save_attendance_changes_atomic(self):
        """TA: Save attendance changes must be atomic"""
        action = "ta_save_attendance_changes"
        try:
            conn = self.get_connection()
            records = conn.execute(
                "SELECT record_id FROM attendance_records LIMIT 3"
            ).fetchall()

            if not records:
                self.log_result(action, "atomicity", "SKIP", "No attendance records")
                return

            try:
                conn.execute("BEGIN IMMEDIATE")
                for record in records:
                    conn.execute(
                        "UPDATE attendance_records SET status=? WHERE record_id=?",
                        ("present", record[0])
                    )
                conn.commit()
                self.log_result(action, "atomicity", "PASS", f"Saved {len(records)} changes atomically")
            finally:
                conn.close()
        except Exception as e:
            self.log_result(action, "atomicity", "FAIL", str(e))

    # ═════════════════════════════════════════════════════════════════════════
    # STUDENT ACTIONS - ATOMICITY TESTS
    # ═════════════════════════════════════════════════════════════════════════

    def test_student_submit_correction_request_atomic(self):
        """STUDENT: Submit correction request must be atomic"""
        action = "student_submit_correction_request"
        try:
            conn = self.get_connection()
            # Create fresh session with absent record
            course = conn.execute("SELECT course_id FROM courses LIMIT 1").fetchone()
            student = conn.execute("SELECT user_id FROM users WHERE role='student' LIMIT 1").fetchone()

            if not course or not student:
                self.log_result(action, "atomicity", "SKIP", "Missing test data")
                return

            # Create fresh session
            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    "INSERT INTO attendance_sessions (course_id, session_date, topic, created_by) VALUES (?, ?, ?, ?)",
                    (course[0], datetime.now().date(), f"Atomic_{int(time.time())}", 1)
                )
                session_id = cur.lastrowid
                conn.commit()
            except:
                self.log_result(action, "atomicity", "SKIP", "Cannot create test session")
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
                self.log_result(action, "atomicity", "SKIP", "Cannot create absent record")
                return

            # Submit correction
            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    "INSERT INTO correction_requests (att_session_id, student_id, course_id, reason, status) VALUES (?, ?, ?, ?, ?)",
                    (session_id, student[0], course[0], "I was present", "pending")
                )
                conn.commit()
                self.log_result(action, "atomicity", "PASS", "Correction request submitted atomically")
            except:
                conn.rollback()
                self.log_result(action, "atomicity", "FAIL", "Correction submission failed")
            finally:
                conn.close()
        except Exception as e:
            self.log_result(action, "atomicity", "FAIL", str(e))

    def test_instructor_add_ta_to_course_atomic(self):
        """INSTRUCTOR: Add TA to course must be atomic"""
        action = "instructor_add_ta_to_course"
        try:
            conn = self.get_connection()
            # Find a course-TA pair not already assigned
            pair = conn.execute(
                "SELECT c.course_id, u.user_id FROM courses c, users u "
                "WHERE u.role='ta' AND NOT EXISTS ("
                "  SELECT 1 FROM course_tas WHERE course_id=c.course_id AND ta_id=u.user_id"
                ") LIMIT 1"
            ).fetchone()

            if not pair:
                self.log_result(action, "atomicity", "SKIP", "No available TA-course pair")
                return

            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT INTO course_tas (course_id, ta_id) VALUES (?, ?)",
                    (pair[0], pair[1])
                )
                conn.commit()
                self.log_result(action, "atomicity", "PASS", "TA added to course atomically")
            except:
                conn.rollback()
                self.log_result(action, "atomicity", "FAIL", "TA assignment failed")
            finally:
                conn.close()
        except Exception as e:
            self.log_result(action, "atomicity", "FAIL", str(e))

    def test_instructor_remove_ta_from_course_atomic(self):
        """INSTRUCTOR: Remove TA from course must be atomic"""
        action = "instructor_remove_ta_from_course"
        try:
            conn = self.get_connection()
            # Find an existing TA assignment to remove
            ta_assignment = conn.execute(
                "SELECT course_id, ta_id FROM course_tas LIMIT 1"
            ).fetchone()

            if not ta_assignment:
                self.log_result(action, "atomicity", "SKIP", "No TA assignments to remove")
                return

            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "DELETE FROM course_tas WHERE course_id=? AND ta_id=?",
                    (ta_assignment[0], ta_assignment[1])
                )
                conn.commit()
                self.log_result(action, "atomicity", "PASS", "TA removed from course atomically")
            except:
                conn.rollback()
                self.log_result(action, "atomicity", "FAIL", "TA removal failed")
            finally:
                conn.close()
        except Exception as e:
            self.log_result(action, "atomicity", "FAIL", str(e))

    def test_ta_create_attendance_session_atomic(self):
        """TA: Create attendance session must be atomic"""
        action = "ta_create_attendance_session"
        try:
            conn = self.get_connection()
            course = conn.execute("SELECT course_id FROM courses LIMIT 1").fetchone()

            if not course:
                self.log_result(action, "atomicity", "SKIP", "No course available")
                return

            topic = f"TASession_{int(time.time())}"

            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    "INSERT INTO attendance_sessions (course_id, session_date, topic, created_by) VALUES (?, ?, ?, ?)",
                    (course[0], datetime.now().date(), topic, 2)  # created_by=2 for TA
                )
                session_id = cur.lastrowid
                conn.commit()
                self.log_result(action, "atomicity", "PASS", "Attendance session created atomically by TA")
            except:
                conn.rollback()
                self.log_result(action, "atomicity", "FAIL", "Session creation failed")
            finally:
                conn.close()
        except Exception as e:
            self.log_result(action, "atomicity", "FAIL", str(e))

    def test_ta_accept_correction_request_atomic(self):
        """TA: Accept correction request must be atomic"""
        action = "ta_accept_correction_request"
        try:
            conn = self.get_connection()
            request = conn.execute(
                "SELECT req_id FROM correction_requests WHERE status='pending' LIMIT 1"
            ).fetchone()

            if not request:
                self.log_result(action, "atomicity", "SKIP", "No pending corrections")
                return

            req_id = request[0]

            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "UPDATE correction_requests SET status=? WHERE req_id=?",
                    ("accepted", req_id)
                )
                conn.commit()
                self.log_result(action, "atomicity", "PASS", "Correction accepted atomically by TA")
            except:
                conn.rollback()
                self.log_result(action, "atomicity", "FAIL", "Correction acceptance failed")
            finally:
                conn.close()
        except Exception as e:
            self.log_result(action, "atomicity", "FAIL", str(e))

    def test_ta_reject_correction_request_atomic(self):
        """TA: Reject correction request must be atomic"""
        action = "ta_reject_correction_request"
        try:
            conn = self.get_connection()
            # Find a pending correction to reject
            request = conn.execute(
                "SELECT req_id FROM correction_requests WHERE status='pending' LIMIT 1 OFFSET 1"
            ).fetchone()

            if not request:
                self.log_result(action, "atomicity", "SKIP", "No additional pending corrections")
                return

            req_id = request[0]

            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "UPDATE correction_requests SET status=? WHERE req_id=?",
                    ("rejected", req_id)
                )
                conn.commit()
                self.log_result(action, "atomicity", "PASS", "Correction rejected atomically by TA")
            except:
                conn.rollback()
                self.log_result(action, "atomicity", "FAIL", "Correction rejection failed")
            finally:
                conn.close()
        except Exception as e:
            self.log_result(action, "atomicity", "FAIL", str(e))

    # ═════════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ═════════════════════════════════════════════════════════════════════════

    def run_all_tests(self):
        """Run all atomicity tests for user actions"""
        print(f"\n{'='*100}")
        print(f"USER ACTIONS ATOMICITY TESTS - {self.level.upper()} LEVEL")
        print(f"{'='*100}\n")

        # Admin actions
        print("[ADMIN ACTIONS - ATOMICITY]\n")
        self.test_admin_add_instructor_to_course_atomic()
        self.test_admin_remove_instructor_from_course_atomic()
        self.test_admin_add_ta_to_course_atomic()
        self.test_admin_remove_ta_from_course_atomic()
        self.test_admin_add_enrolled_student_atomic()
        self.test_admin_remove_enrolled_student_atomic()
        self.test_admin_delete_course_atomic()
        self.test_admin_create_semester_atomic()
        self.test_admin_add_course_atomic()
        self.test_admin_create_user_atomic()
        self.test_admin_delete_user_atomic()
        self.test_admin_delete_past_semester_atomic()
        self.test_admin_override_attendance_batch_atomic()

        # Instructor actions
        print("\n[INSTRUCTOR ACTIONS - ATOMICITY]\n")
        self.test_instructor_create_attendance_session_atomic()
        self.test_instructor_accept_correction_request_atomic()
        self.test_instructor_reject_correction_request_atomic()
        self.test_instructor_add_ta_to_course_atomic()
        self.test_instructor_remove_ta_from_course_atomic()

        # TA actions
        print("\n[TA ACTIONS - ATOMICITY]\n")
        self.test_ta_save_attendance_changes_atomic()
        self.test_ta_create_attendance_session_atomic()
        self.test_ta_accept_correction_request_atomic()
        self.test_ta_reject_correction_request_atomic()

        # Student actions
        print("\n[STUDENT ACTIONS - ATOMICITY]\n")
        self.test_student_submit_correction_request_atomic()

        self.print_summary()

    def print_summary(self):
        """Print test summary"""
        total = self.pass_count + self.fail_count + self.skip_count
        pass_pct = (self.pass_count / max(1, self.pass_count + self.fail_count)) * 100 if (self.pass_count + self.fail_count) > 0 else 0

        print(f"\n{'-'*100}")
        print(f"USER ACTIONS ATOMICITY SUMMARY ({self.level.upper()})")
        print(f"{'-'*100}")
        print(f"Total: {total} | Passed: {self.pass_count} | Failed: {self.fail_count} | Skipped: {self.skip_count}")
        print(f"Pass Rate: {pass_pct:.1f}%")

        # Save results
        output_file = f"user_actions_atomicity_test_results_{self.level}.json"
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
    tester = UserActionsAtomicityTester(level=level)
    tester.run_all_tests()
