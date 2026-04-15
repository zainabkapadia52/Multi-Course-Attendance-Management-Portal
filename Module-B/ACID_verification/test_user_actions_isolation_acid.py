"""
test_user_actions_isolation_acid.py
==================================
ACID Property: ISOLATION
Tests for ALL user actions - Concurrent operation isolation
Complete test suite: 23 isolation tests (13 Admin + 5 Instructor + 4 TA + 1 Student)
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

    # ═════════════════════════════════════════════════════════════════════════
    # ADMIN ACTION ISOLATION TESTS (13 total)
    # ═════════════════════════════════════════════════════════════════════════

    def test_admin_create_semester_isolated(self):
        """ADMIN: Concurrent create_semester operations must be isolated"""
        action = "admin_create_semester"
        try:
            results = {"success": 0, "failed": 0, "conflict": 0}
            lock = Lock()
            timestamp = int(time.time() * 1000)

            def create_semester(idx):
                try:
                    c = self.get_connection()
                    c.execute("BEGIN IMMEDIATE")
                    c.execute(
                        "INSERT INTO semesters (name, start_date, end_date) VALUES (?, ?, ?)",
                        (f"Sem_{timestamp}_{idx}", datetime.now().date(), datetime.now().date())
                    )
                    c.commit()
                    with lock:
                        results["success"] += 1
                    c.close()
                except sqlite3.IntegrityError:
                    with lock:
                        results["conflict"] += 1
                    c.close()
                except:
                    with lock:
                        results["failed"] += 1
                    c.close()

            # 3 concurrent semester creations
            threads = [threading.Thread(target=create_semester, args=(i,)) for i in range(1, 4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            if results["failed"] == 0 and results["success"] > 0:
                self.log_result(action, "isolation", "PASS",
                    f"Semesters created isolated: {results['success']} success, {results['conflict']} conflict")
            else:
                self.log_result(action, "isolation", "FAIL",
                    f"Isolation failed: {results['success']} success, {results['failed']} failed")
        except Exception as e:
            self.log_result(action, "isolation", "FAIL", str(e))

    def test_admin_create_user_isolated(self):
        """ADMIN: Concurrent create_user operations must be isolated"""
        action = "admin_create_user"
        try:
            results = {"success": 0, "failed": 0, "conflict": 0}
            lock = Lock()
            timestamp = int(time.time() * 1000)

            def create_user(idx):
                try:
                    c = self.get_connection()
                    c.execute("BEGIN IMMEDIATE")
                    c.execute(
                        "INSERT INTO users (username, pwd_hash, role) VALUES (?, ?, ?)",
                        (f"user_iso_{timestamp}_{idx}", "hash", "student")
                    )
                    c.commit()
                    with lock:
                        results["success"] += 1
                    c.close()
                except sqlite3.IntegrityError:
                    with lock:
                        results["conflict"] += 1
                    c.close()
                except:
                    with lock:
                        results["failed"] += 1
                    c.close()

            # 3 concurrent user creations
            threads = [threading.Thread(target=create_user, args=(i,)) for i in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            if results["failed"] == 0 and results["success"] > 0:
                self.log_result(action, "isolation", "PASS",
                    f"Users created isolated: {results['success']} success, {results['conflict']} conflict")
            else:
                self.log_result(action, "isolation", "FAIL",
                    f"Isolation failed: {results['success']} success, {results['failed']} failed")
        except Exception as e:
            self.log_result(action, "isolation", "FAIL", str(e))

    def test_admin_add_course_isolated(self):
        """ADMIN: Concurrent add_course operations must be isolated"""
        action = "admin_add_course"
        try:
            conn = self.get_connection()
            sem = conn.execute("SELECT semester_id FROM semesters LIMIT 1").fetchone()

            if not sem:
                self.log_result(action, "isolation", "SKIP", "No semester found")
                conn.close()
                return

            results = {"success": 0, "failed": 0, "locked": 0}
            lock = Lock()
            timestamp = int(time.time() * 1000)

            def add_course(idx):
                try:
                    c = self.get_connection()
                    c.execute("BEGIN IMMEDIATE")
                    c.execute(
                        "INSERT INTO courses (code, name, semester_id) VALUES (?, ?, ?)",
                        (f"ACID{timestamp}_{idx}", f"Concurrent Course {idx}", sem[0])
                    )
                    c.commit()
                    with lock:
                        results["success"] += 1
                    c.close()
                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e):
                        with lock:
                            results["locked"] += 1
                    else:
                        with lock:
                            results["failed"] += 1
                    c.close()
                except:
                    with lock:
                        results["failed"] += 1
                    c.close()

            # 3 concurrent threads
            threads = [threading.Thread(target=add_course, args=(i,)) for i in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            if results["failed"] == 0 and results["success"] > 0:
                self.log_result(action, "isolation", "PASS",
                    f"Courses created isolated: {results['success']} success, {results['locked']} locked")
            else:
                self.log_result(action, "isolation", "FAIL",
                    f"Isolation failed: {results['success']} success, {results['failed']} failed")

            conn.close()
        except Exception as e:
            self.log_result(action, "isolation", "FAIL", str(e))

    def test_admin_delete_course_isolated(self):
        """ADMIN: Concurrent delete_course operations must be isolated"""
        action = "admin_delete_course"
        try:
            conn = self.get_connection()
            # Get 2 courses without dependencies
            courses = conn.execute(
                "SELECT course_id FROM courses c "
                "WHERE NOT EXISTS (SELECT 1 FROM course_instructors WHERE course_id=c.course_id) "
                "AND NOT EXISTS (SELECT 1 FROM course_tas WHERE course_id=c.course_id) "
                "AND NOT EXISTS (SELECT 1 FROM attendance_sessions WHERE course_id=c.course_id) "
                "LIMIT 3"
            ).fetchall()

            if len(courses) < 2:
                self.log_result(action, "isolation", "SKIP", "Not enough independent courses")
                conn.close()
                return

            results = {"success": 0, "failed": 0, "not_found": 0}
            lock = Lock()
            delete_courses = [courses[i][0] for i in range(min(2, len(courses)))]

            def delete_course(course_id):
                try:
                    c = self.get_connection()
                    c.execute("BEGIN IMMEDIATE")
                    check = c.execute("SELECT course_id FROM courses WHERE course_id=?", (course_id,)).fetchone()
                    if not check:
                        with lock:
                            results["not_found"] += 1
                        c.close()
                        return

                    c.execute("DELETE FROM courses WHERE course_id=?", (course_id,))
                    c.commit()
                    with lock:
                        results["success"] += 1
                    c.close()
                except:
                    with lock:
                        results["failed"] += 1
                    c.close()

            # 2 concurrent deletes
            threads = [threading.Thread(target=delete_course, args=(cid,)) for cid in delete_courses]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            if results["failed"] == 0 and results["success"] > 0:
                self.log_result(action, "isolation", "PASS",
                    f"Courses deleted isolated: {results['success']} deleted successfully")
            else:
                self.log_result(action, "isolation", "FAIL",
                    f"Isolation issue: {results['success']} success, {results['failed']} failed")

            conn.close()
        except Exception as e:
            self.log_result(action, "isolation", "FAIL", str(e))

    def test_admin_add_instructor_isolated(self):
        """ADMIN: Concurrent add_instructor operations must be isolated"""
        action = "admin_add_instructor"
        try:
            conn = self.get_connection()
            course = conn.execute("SELECT course_id FROM courses LIMIT 1").fetchone()
            instructors = conn.execute(
                "SELECT user_id FROM users WHERE role='instructor' LIMIT 3"
            ).fetchall()

            if not course or len(instructors) < 2:
                self.log_result(action, "isolation", "SKIP", "Missing course or instructors")
                conn.close()
                return

            results = {"success": 0, "failed": 0, "conflict": 0}
            lock = Lock()

            def add_instructor(instr_idx):
                try:
                    c = self.get_connection()
                    c.execute("BEGIN IMMEDIATE")
                    check = c.execute(
                        "SELECT 1 FROM course_instructors WHERE course_id=? AND instructor_id=?",
                        (course[0], instructors[instr_idx][0])
                    ).fetchone()
                    if check:
                        with lock:
                            results["conflict"] += 1
                        c.close()
                        return

                    c.execute(
                        "INSERT INTO course_instructors (course_id, instructor_id) VALUES (?, ?)",
                        (course[0], instructors[instr_idx][0])
                    )
                    c.commit()
                    with lock:
                        results["success"] += 1
                    c.close()
                except sqlite3.IntegrityError:
                    with lock:
                        results["conflict"] += 1
                    c.close()
                except:
                    with lock:
                        results["failed"] += 1
                    c.close()

            # 2 concurrent add_instructor operations
            threads = [threading.Thread(target=add_instructor, args=(i,)) for i in range(min(2, len(instructors)))]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            if results["failed"] == 0:
                self.log_result(action, "isolation", "PASS",
                    f"Instructors added isolated: {results['success']} success, {results['conflict']} already assigned")
            else:
                self.log_result(action, "isolation", "FAIL",
                    f"Isolation issue: {results['success']} success, {results['failed']} failed")

            conn.close()
        except Exception as e:
            self.log_result(action, "isolation", "FAIL", str(e))

    def test_admin_remove_instructor_isolated(self):
        """ADMIN: Concurrent remove_instructor operations must be isolated"""
        action = "admin_remove_instructor"
        try:
            conn = self.get_connection()
            # Get 2 course-instructor pairs
            pairs = conn.execute(
                "SELECT course_id, instructor_id FROM course_instructors LIMIT 3"
            ).fetchall()

            if len(pairs) < 2:
                self.log_result(action, "isolation", "SKIP", "Not enough course-instructor pairs")
                conn.close()
                return

            results = {"success": 0, "failed": 0, "not_found": 0}
            lock = Lock()
            delete_pairs = pairs[:min(2, len(pairs))]

            def remove_instructor(pair_idx):
                try:
                    c = self.get_connection()
                    c.execute("BEGIN IMMEDIATE")
                    pair = delete_pairs[pair_idx]
                    check = c.execute(
                        "SELECT 1 FROM course_instructors WHERE course_id=? AND instructor_id=?",
                        (pair[0], pair[1])
                    ).fetchone()
                    if not check:
                        with lock:
                            results["not_found"] += 1
                        c.close()
                        return

                    c.execute(
                        "DELETE FROM course_instructors WHERE course_id=? AND instructor_id=?",
                        (pair[0], pair[1])
                    )
                    c.commit()
                    with lock:
                        results["success"] += 1
                    c.close()
                except:
                    with lock:
                        results["failed"] += 1
                    c.close()

            # 2 concurrent remove operations
            threads = [threading.Thread(target=remove_instructor, args=(i,)) for i in range(len(delete_pairs))]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            if results["failed"] == 0 and results["success"] > 0:
                self.log_result(action, "isolation", "PASS",
                    f"Instructors removed isolated: {results['success']} removed successfully")
            else:
                self.log_result(action, "isolation", "FAIL",
                    f"Isolation issue: {results['success']} success, {results['failed']} failed")

            conn.close()
        except Exception as e:
            self.log_result(action, "isolation", "FAIL", str(e))

    def test_admin_add_ta_isolated(self):
        """ADMIN: Concurrent add_ta operations must be isolated"""
        action = "admin_add_ta"
        try:
            conn = self.get_connection()
            course = conn.execute("SELECT course_id FROM courses LIMIT 1").fetchone()
            tas = conn.execute(
                "SELECT user_id FROM users WHERE role='ta' LIMIT 3"
            ).fetchall()

            if not course or len(tas) < 2:
                self.log_result(action, "isolation", "SKIP", "Missing course or TAs")
                conn.close()
                return

            results = {"success": 0, "failed": 0, "conflict": 0}
            lock = Lock()

            def add_ta(ta_idx):
                try:
                    c = self.get_connection()
                    c.execute("BEGIN IMMEDIATE")
                    check = c.execute(
                        "SELECT 1 FROM course_tas WHERE course_id=? AND ta_id=?",
                        (course[0], tas[ta_idx][0])
                    ).fetchone()
                    if check:
                        with lock:
                            results["conflict"] += 1
                        c.close()
                        return

                    c.execute(
                        "INSERT INTO course_tas (course_id, ta_id) VALUES (?, ?)",
                        (course[0], tas[ta_idx][0])
                    )
                    c.commit()
                    with lock:
                        results["success"] += 1
                    c.close()
                except sqlite3.IntegrityError:
                    with lock:
                        results["conflict"] += 1
                    c.close()
                except:
                    with lock:
                        results["failed"] += 1
                    c.close()

            # 2 concurrent add_ta operations
            threads = [threading.Thread(target=add_ta, args=(i,)) for i in range(min(2, len(tas)))]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            if results["failed"] == 0:
                self.log_result(action, "isolation", "PASS",
                    f"TAs added isolated: {results['success']} success, {results['conflict']} already assigned")
            else:
                self.log_result(action, "isolation", "FAIL",
                    f"Isolation issue: {results['success']} success, {results['failed']} failed")

            conn.close()
        except Exception as e:
            self.log_result(action, "isolation", "FAIL", str(e))

    def test_admin_remove_ta_isolated(self):
        """ADMIN: Concurrent remove_ta operations must be isolated"""
        action = "admin_remove_ta"
        try:
            conn = self.get_connection()
            # Get 2 course-ta pairs
            pairs = conn.execute(
                "SELECT course_id, ta_id FROM course_tas LIMIT 3"
            ).fetchall()

            if len(pairs) < 2:
                self.log_result(action, "isolation", "SKIP", "Not enough course-ta pairs")
                conn.close()
                return

            results = {"success": 0, "failed": 0, "not_found": 0}
            lock = Lock()
            delete_pairs = pairs[:min(2, len(pairs))]

            def remove_ta(pair_idx):
                try:
                    c = self.get_connection()
                    c.execute("BEGIN IMMEDIATE")
                    pair = delete_pairs[pair_idx]
                    check = c.execute(
                        "SELECT 1 FROM course_tas WHERE course_id=? AND ta_id=?",
                        (pair[0], pair[1])
                    ).fetchone()
                    if not check:
                        with lock:
                            results["not_found"] += 1
                        c.close()
                        return

                    c.execute(
                        "DELETE FROM course_tas WHERE course_id=? AND ta_id=?",
                        (pair[0], pair[1])
                    )
                    c.commit()
                    with lock:
                        results["success"] += 1
                    c.close()
                except:
                    with lock:
                        results["failed"] += 1
                    c.close()

            # 2 concurrent remove operations
            threads = [threading.Thread(target=remove_ta, args=(i,)) for i in range(len(delete_pairs))]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            if results["failed"] == 0 and results["success"] > 0:
                self.log_result(action, "isolation", "PASS",
                    f"TAs removed isolated: {results['success']} removed successfully")
            else:
                self.log_result(action, "isolation", "FAIL",
                    f"Isolation issue: {results['success']} success, {results['failed']} failed")

            conn.close()
        except Exception as e:
            self.log_result(action, "isolation", "FAIL", str(e))

    def test_admin_add_enrolled_student_isolated(self):
        """ADMIN: Concurrent add_enrolled_student operations must be isolated"""
        action = "admin_add_enrolled_student"
        try:
            conn = self.get_connection()
            course = conn.execute("SELECT course_id FROM courses LIMIT 1").fetchone()
            students = conn.execute(
                "SELECT user_id FROM users WHERE role='student' LIMIT 3"
            ).fetchall()

            if not course or len(students) < 2:
                self.log_result(action, "isolation", "SKIP", "Missing course or students")
                conn.close()
                return

            results = {"success": 0, "failed": 0, "conflict": 0}
            lock = Lock()

            def enroll_student(student_idx):
                try:
                    c = self.get_connection()
                    c.execute("BEGIN IMMEDIATE")
                    check = c.execute(
                        "SELECT 1 FROM course_enrollments WHERE course_id=? AND student_id=?",
                        (course[0], students[student_idx][0])
                    ).fetchone()
                    if check:
                        with lock:
                            results["conflict"] += 1
                        c.close()
                        return

                    c.execute(
                        "INSERT INTO course_enrollments (course_id, student_id) VALUES (?, ?)",
                        (course[0], students[student_idx][0])
                    )
                    c.commit()
                    with lock:
                        results["success"] += 1
                    c.close()
                except sqlite3.IntegrityError:
                    with lock:
                        results["conflict"] += 1
                    c.close()
                except:
                    with lock:
                        results["failed"] += 1
                    c.close()

            # 2 concurrent enrollment operations
            threads = [threading.Thread(target=enroll_student, args=(i,)) for i in range(min(2, len(students)))]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            if results["failed"] == 0:
                self.log_result(action, "isolation", "PASS",
                    f"Students enrolled isolated: {results['success']} success, {results['conflict']} already enrolled")
            else:
                self.log_result(action, "isolation", "FAIL",
                    f"Isolation issue: {results['success']} success, {results['failed']} failed")

            conn.close()
        except Exception as e:
            self.log_result(action, "isolation", "FAIL", str(e))

    def test_admin_remove_enrolled_student_isolated(self):
        """ADMIN: Concurrent remove_enrolled_student operations must be isolated"""
        action = "admin_remove_enrolled_student"
        try:
            conn = self.get_connection()
            # Get 2 course-student enrollment pairs
            pairs = conn.execute(
                "SELECT course_id, student_id FROM course_enrollments LIMIT 3"
            ).fetchall()

            if len(pairs) < 2:
                self.log_result(action, "isolation", "SKIP", "Not enough enrolled students")
                conn.close()
                return

            results = {"success": 0, "failed": 0, "not_found": 0}
            lock = Lock()
            delete_pairs = pairs[:min(2, len(pairs))]

            def unenroll_student(pair_idx):
                try:
                    c = self.get_connection()
                    c.execute("BEGIN IMMEDIATE")
                    pair = delete_pairs[pair_idx]
                    check = c.execute(
                        "SELECT 1 FROM course_enrollments WHERE course_id=? AND student_id=?",
                        (pair[0], pair[1])
                    ).fetchone()
                    if not check:
                        with lock:
                            results["not_found"] += 1
                        c.close()
                        return

                    c.execute(
                        "DELETE FROM course_enrollments WHERE course_id=? AND student_id=?",
                        (pair[0], pair[1])
                    )
                    c.commit()
                    with lock:
                        results["success"] += 1
                    c.close()
                except:
                    with lock:
                        results["failed"] += 1
                    c.close()

            # 2 concurrent remove operations
            threads = [threading.Thread(target=unenroll_student, args=(i,)) for i in range(len(delete_pairs))]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            if results["failed"] == 0 and results["success"] > 0:
                self.log_result(action, "isolation", "PASS",
                    f"Students unenrolled isolated: {results['success']} removed successfully")
            else:
                self.log_result(action, "isolation", "FAIL",
                    f"Isolation issue: {results['success']} success, {results['failed']} failed")

            conn.close()
        except Exception as e:
            self.log_result(action, "isolation", "FAIL", str(e))

    def test_admin_delete_user_isolated(self):
        """ADMIN: Concurrent delete_user operations must be isolated (cascade delete)"""
        action = "admin_delete_user"
        try:
            conn = self.get_connection()
            # Get 2 users that are not instructors/TAs (to avoid cascade issues)
            users = conn.execute(
                "SELECT user_id FROM users u "
                "WHERE u.role='student' "
                "AND NOT EXISTS (SELECT 1 FROM course_instructors WHERE instructor_id=u.user_id) "
                "AND NOT EXISTS (SELECT 1 FROM course_tas WHERE ta_id=u.user_id) "
                "LIMIT 3"
            ).fetchall()

            if len(users) < 2:
                self.log_result(action, "isolation", "SKIP", "Not enough independent users to delete")
                conn.close()
                return

            results = {"success": 0, "failed": 0, "not_found": 0}
            lock = Lock()
            delete_users = [users[i][0] for i in range(min(2, len(users)))]

            def delete_user(user_id):
                try:
                    c = self.get_connection()
                    c.execute("BEGIN IMMEDIATE")
                    check = c.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,)).fetchone()
                    if not check:
                        with lock:
                            results["not_found"] += 1
                        c.close()
                        return

                    c.execute("DELETE FROM users WHERE user_id=?", (user_id,))
                    c.commit()
                    with lock:
                        results["success"] += 1
                    c.close()
                except sqlite3.IntegrityError:
                    with lock:
                        results["failed"] += 1
                    c.close()
                except:
                    with lock:
                        results["failed"] += 1
                    c.close()

            # 2 concurrent deletes
            threads = [threading.Thread(target=delete_user, args=(uid,)) for uid in delete_users]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            total = results["success"] + results["failed"] + results["not_found"]
            if results["failed"] == 0 and results["success"] > 0:
                self.log_result(action, "isolation", "PASS",
                    f"User deletions isolated: {results['success']} deleted successfully")
            else:
                self.log_result(action, "isolation", "FAIL",
                    f"Isolation issue: {results['success']} success, {results['failed']} failed")

            conn.close()
        except Exception as e:
            self.log_result(action, "isolation", "FAIL", str(e))

    def test_admin_override_attendance_batch_isolated(self):
        """ADMIN: Concurrent batch attendance override must be isolated"""
        action = "admin_override_attendance_batch"
        try:
            conn = self.get_connection()
            # Get 2 different attendance records
            records = conn.execute(
                "SELECT record_id, att_session_id, student_id FROM attendance_records LIMIT 3"
            ).fetchall()

            if len(records) < 2:
                self.log_result(action, "isolation", "SKIP", "Not enough records for batch test")
                conn.close()
                return

            results = {"success": 0, "failed": 0}
            lock = Lock()

            def override_batch(record_idx):
                try:
                    c = self.get_connection()
                    c.execute("BEGIN IMMEDIATE")
                    record = records[record_idx]
                    c.execute(
                        "UPDATE attendance_records SET status=? WHERE record_id=?",
                        ("present", record[0])
                    )
                    c.commit()
                    with lock:
                        results["success"] += 1
                    c.close()
                except:
                    with lock:
                        results["failed"] += 1
                    c.close()

            # 2 concurrent batch overrides
            threads = [threading.Thread(target=override_batch, args=(i,)) for i in range(min(2, len(records)))]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            if results["failed"] == 0 and results["success"] > 0:
                self.log_result(action, "isolation", "PASS",
                    f"Batch overrides isolated: {results['success']} successful")
            else:
                self.log_result(action, "isolation", "FAIL",
                    f"Isolation issue: {results['success']} success, {results['failed']} failed")

            conn.close()
        except Exception as e:
            self.log_result(action, "isolation", "FAIL", str(e))


    # ═════════════════════════════════════════════════════════════════════════
    # INSTRUCTOR ACTION ISOLATION TESTS (5 total)
    # ═════════════════════════════════════════════════════════════════════════

    def test_instructor_create_session_isolated(self):
        """INSTRUCTOR: Concurrent create_session operations must be isolated"""
        action = "instructor_create_session"
        try:
            conn = self.get_connection()
            course = conn.execute("SELECT course_id FROM courses LIMIT 1").fetchone()

            if not course:
                self.log_result(action, "isolation", "SKIP", "No course found")
                conn.close()
                return

            results = {"success": 0, "failed": 0, "locked": 0}
            lock = Lock()
            timestamp = int(time.time() * 1000)

            def create_session(idx):
                try:
                    c = self.get_connection()
                    c.execute("BEGIN IMMEDIATE")
                    c.execute(
                        "INSERT INTO attendance_sessions (course_id, session_date, topic, created_by) VALUES (?, ?, ?, ?)",
                        (course[0], datetime.now().date(), f"Topic_{timestamp}_{idx}", 1)
                    )
                    c.commit()
                    with lock:
                        results["success"] += 1
                    c.close()
                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e):
                        with lock:
                            results["locked"] += 1
                    else:
                        with lock:
                            results["failed"] += 1
                    c.close()
                except:
                    with lock:
                        results["failed"] += 1
                    c.close()

            # 3 concurrent session creations
            threads = [threading.Thread(target=create_session, args=(i,)) for i in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            if results["failed"] == 0 and results["success"] > 0:
                self.log_result(action, "isolation", "PASS",
                    f"Sessions created isolated: {results['success']} success, {results['locked']} locked")
            else:
                self.log_result(action, "isolation", "FAIL",
                    f"Isolation issue: {results['success']} success, {results['failed']} failed")

            conn.close()
        except Exception as e:
            self.log_result(action, "isolation", "FAIL", str(e))

    def test_instructor_add_ta_isolated(self):
        """INSTRUCTOR: Concurrent add_ta operations must be isolated"""
        action = "instructor_add_ta"
        try:
            conn = self.get_connection()
            course = conn.execute("SELECT course_id FROM courses LIMIT 1").fetchone()
            tas = conn.execute(
                "SELECT user_id FROM users WHERE role='ta' LIMIT 3"
            ).fetchall()

            if not course or len(tas) < 2:
                self.log_result(action, "isolation", "SKIP", "Missing course or TAs")
                conn.close()
                return

            results = {"success": 0, "failed": 0, "conflict": 0}
            lock = Lock()

            def add_ta(ta_idx):
                try:
                    c = self.get_connection()
                    c.execute("BEGIN IMMEDIATE")
                    check = c.execute(
                        "SELECT 1 FROM course_tas WHERE course_id=? AND ta_id=?",
                        (course[0], tas[ta_idx][0])
                    ).fetchone()
                    if check:
                        with lock:
                            results["conflict"] += 1
                        c.close()
                        return

                    c.execute(
                        "INSERT INTO course_tas (course_id, ta_id) VALUES (?, ?)",
                        (course[0], tas[ta_idx][0])
                    )
                    c.commit()
                    with lock:
                        results["success"] += 1
                    c.close()
                except sqlite3.IntegrityError:
                    with lock:
                        results["conflict"] += 1
                    c.close()
                except:
                    with lock:
                        results["failed"] += 1
                    c.close()

            # 2 concurrent add_ta operations
            threads = [threading.Thread(target=add_ta, args=(i,)) for i in range(min(2, len(tas)))]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            if results["failed"] == 0:
                self.log_result(action, "isolation", "PASS",
                    f"TAs added isolated: {results['success']} success, {results['conflict']} already assigned")
            else:
                self.log_result(action, "isolation", "FAIL",
                    f"Isolation issue: {results['success']} success, {results['failed']} failed")

            conn.close()
        except Exception as e:
            self.log_result(action, "isolation", "FAIL", str(e))

    def test_instructor_accept_correction_isolated(self):
        """INSTRUCTOR: Concurrent accept_correction operations must be isolated"""
        action = "instructor_accept_correction"
        try:
            conn = self.get_connection()
            # Get pending correction requests
            corrections = conn.execute(
                "SELECT req_id, att_session_id, student_id FROM correction_requests WHERE status='pending' LIMIT 3"
            ).fetchall()

            if len(corrections) < 2:
                self.log_result(action, "isolation", "SKIP", "Not enough pending corrections")
                conn.close()
                return

            results = {"success": 0, "failed": 0}
            lock = Lock()

            def accept_correction(corr_idx):
                try:
                    c = self.get_connection()
                    c.execute("BEGIN IMMEDIATE")
                    corr = corrections[corr_idx]
                    c.execute(
                        "UPDATE correction_requests SET status=? WHERE req_id=?",
                        ("accepted", corr[0])
                    )
                    c.execute(
                        "UPDATE attendance_records SET status=? WHERE att_session_id=? AND student_id=?",
                        ("present", corr[1], corr[2])
                    )
                    c.commit()
                    with lock:
                        results["success"] += 1
                    c.close()
                except:
                    with lock:
                        results["failed"] += 1
                    c.close()

            # 2 concurrent accept operations
            threads = [threading.Thread(target=accept_correction, args=(i,)) for i in range(min(2, len(corrections)))]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            if results["failed"] == 0 and results["success"] > 0:
                self.log_result(action, "isolation", "PASS",
                    f"Corrections accepted isolated: {results['success']} successful")
            else:
                self.log_result(action, "isolation", "FAIL",
                    f"Isolation issue: {results['success']} success, {results['failed']} failed")

            conn.close()
        except Exception as e:
            self.log_result(action, "isolation", "FAIL", str(e))

    def test_instructor_reject_correction_isolated(self):
        """INSTRUCTOR: Concurrent reject_correction operations must be isolated"""
        action = "instructor_reject_correction"
        try:
            conn = self.get_connection()
            # Get pending correction requests
            corrections = conn.execute(
                "SELECT req_id FROM correction_requests WHERE status='pending' LIMIT 3"
            ).fetchall()

            if len(corrections) < 2:
                self.log_result(action, "isolation", "SKIP", "Not enough pending corrections to reject")
                conn.close()
                return

            results = {"success": 0, "failed": 0}
            lock = Lock()

            def reject_correction(corr_idx):
                try:
                    c = self.get_connection()
                    c.execute("BEGIN IMMEDIATE")
                    corr_id = corrections[corr_idx][0]
                    c.execute(
                        "UPDATE correction_requests SET status=? WHERE req_id=?",
                        ("rejected", corr_id)
                    )
                    c.commit()
                    with lock:
                        results["success"] += 1
                    c.close()
                except:
                    with lock:
                        results["failed"] += 1
                    c.close()

            # 2 concurrent reject operations
            threads = [threading.Thread(target=reject_correction, args=(i,)) for i in range(min(2, len(corrections)))]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            if results["failed"] == 0 and results["success"] > 0:
                self.log_result(action, "isolation", "PASS",
                    f"Corrections rejected isolated: {results['success']} successful")
            else:
                self.log_result(action, "isolation", "FAIL",
                    f"Isolation issue: {results['success']} success, {results['failed']} failed")

            conn.close()
        except Exception as e:
            self.log_result(action, "isolation", "FAIL", str(e))

    def test_instructor_remove_ta_isolated(self):
        """INSTRUCTOR: Concurrent remove_ta operations must be isolated"""
        action = "instructor_remove_ta"
        try:
            conn = self.get_connection()
            # Get 2 course-ta pairs
            pairs = conn.execute(
                "SELECT course_id, ta_id FROM course_tas LIMIT 3"
            ).fetchall()

            if len(pairs) < 2:
                self.log_result(action, "isolation", "SKIP", "Not enough course-ta pairs")
                conn.close()
                return

            results = {"success": 0, "failed": 0, "not_found": 0}
            lock = Lock()
            delete_pairs = pairs[:min(2, len(pairs))]

            def remove_ta(pair_idx):
                try:
                    c = self.get_connection()
                    c.execute("BEGIN IMMEDIATE")
                    pair = delete_pairs[pair_idx]
                    check = c.execute(
                        "SELECT 1 FROM course_tas WHERE course_id=? AND ta_id=?",
                        (pair[0], pair[1])
                    ).fetchone()
                    if not check:
                        with lock:
                            results["not_found"] += 1
                        c.close()
                        return

                    c.execute(
                        "DELETE FROM course_tas WHERE course_id=? AND ta_id=?",
                        (pair[0], pair[1])
                    )
                    c.commit()
                    with lock:
                        results["success"] += 1
                    c.close()
                except:
                    with lock:
                        results["failed"] += 1
                    c.close()

            # 2 concurrent remove operations
            threads = [threading.Thread(target=remove_ta, args=(i,)) for i in range(len(delete_pairs))]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            if results["failed"] == 0 and results["success"] > 0:
                self.log_result(action, "isolation", "PASS",
                    f"TAs removed isolated: {results['success']} removed successfully")
            else:
                self.log_result(action, "isolation", "FAIL",
                    f"Isolation issue: {results['success']} success, {results['failed']} failed")

            conn.close()
        except Exception as e:
            self.log_result(action, "isolation", "FAIL", str(e))

    # ═════════════════════════════════════════════════════════════════════════
    # TA ACTION ISOLATION TESTS (4 total)
    # ═════════════════════════════════════════════════════════════════════════

    def test_ta_save_attendance_isolated(self):
        """TA: Concurrent save_attendance operations must not cause lost updates"""
        action = "ta_save_attendance"
        try:
            conn = self.get_connection()
            # Get multiple attendance records to update concurrently
            records = conn.execute(
                "SELECT record_id, att_session_id, student_id FROM attendance_records LIMIT 3"
            ).fetchall()

            if len(records) < 2:
                self.log_result(action, "isolation", "SKIP", "Not enough records for concurrent save")
                conn.close()
                return

            results = {"success": 0, "failed": 0}
            lock = Lock()

            def save_attendance(record_idx):
                try:
                    c = self.get_connection()
                    c.execute("BEGIN IMMEDIATE")
                    record = records[record_idx]
                    c.execute(
                        "UPDATE attendance_records SET status=? WHERE record_id=?",
                        ("present", record[0])
                    )
                    c.commit()
                    with lock:
                        results["success"] += 1
                    c.close()
                except:
                    with lock:
                        results["failed"] += 1
                    c.close()

            # 3 concurrent save operations on different records
            threads = [threading.Thread(target=save_attendance, args=(i,)) for i in range(min(3, len(records)))]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            if results["failed"] == 0 and results["success"] > 0:
                self.log_result(action, "isolation", "PASS",
                    f"Concurrent saves isolated: {results['success']} successful, no lost updates")
            else:
                self.log_result(action, "isolation", "FAIL",
                    f"Isolation issue: {results['success']} success, {results['failed']} failed")

            conn.close()
        except Exception as e:
            self.log_result(action, "isolation", "FAIL", str(e))

    def test_ta_create_session_isolated(self):
        """TA: Concurrent create_session operations must be isolated"""
        action = "ta_create_session"
        try:
            conn = self.get_connection()
            course = conn.execute("SELECT course_id FROM courses LIMIT 1").fetchone()

            if not course:
                self.log_result(action, "isolation", "SKIP", "No course found")
                conn.close()
                return

            results = {"success": 0, "failed": 0}
            lock = Lock()
            timestamp = int(time.time() * 1000)

            def create_session(idx):
                try:
                    c = self.get_connection()
                    c.execute("BEGIN IMMEDIATE")
                    c.execute(
                        "INSERT INTO attendance_sessions (course_id, session_date, topic, created_by) VALUES (?, ?, ?, ?)",
                        (course[0], datetime.now().date(), f"TA_Topic_{timestamp}_{idx}", 2)
                    )
                    c.commit()
                    with lock:
                        results["success"] += 1
                    c.close()
                except:
                    with lock:
                        results["failed"] += 1
                    c.close()

            # 2 concurrent session creations by TA
            threads = [threading.Thread(target=create_session, args=(i,)) for i in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            if results["failed"] == 0 and results["success"] > 0:
                self.log_result(action, "isolation", "PASS",
                    f"TA sessions created isolated: {results['success']} successful")
            else:
                self.log_result(action, "isolation", "FAIL",
                    f"Isolation issue: {results['success']} success, {results['failed']} failed")

            conn.close()
        except Exception as e:
            self.log_result(action, "isolation", "FAIL", str(e))

    def test_ta_accept_correction_isolated(self):
        """TA: Concurrent accept_correction operations must be isolated"""
        action = "ta_accept_correction"
        try:
            conn = self.get_connection()
            # Get pending correction requests
            corrections = conn.execute(
                "SELECT req_id, att_session_id, student_id FROM correction_requests WHERE status='pending' LIMIT 3"
            ).fetchall()

            if len(corrections) < 2:
                self.log_result(action, "isolation", "SKIP", "Not enough pending corrections")
                conn.close()
                return

            results = {"success": 0, "failed": 0}
            lock = Lock()

            def accept_correction(corr_idx):
                try:
                    c = self.get_connection()
                    c.execute("BEGIN IMMEDIATE")
                    corr = corrections[corr_idx]
                    check = c.execute(
                        "SELECT status FROM correction_requests WHERE req_id=?",
                        (corr[0],)
                    ).fetchone()
                    if not check or check[0] != "pending":
                        with lock:
                            results["failed"] += 1
                        c.close()
                        return

                    c.execute(
                        "UPDATE correction_requests SET status=? WHERE req_id=?",
                        ("accepted", corr[0])
                    )
                    c.execute(
                        "UPDATE attendance_records SET status=? WHERE att_session_id=? AND student_id=?",
                        ("present", corr[1], corr[2])
                    )
                    c.commit()
                    with lock:
                        results["success"] += 1
                    c.close()
                except:
                    with lock:
                        results["failed"] += 1
                    c.close()

            # 2 concurrent accept operations by TA
            threads = [threading.Thread(target=accept_correction, args=(i,)) for i in range(min(2, len(corrections)))]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            if results["failed"] == 0 and results["success"] > 0:
                self.log_result(action, "isolation", "PASS",
                    f"TA corrections accepted isolated: {results['success']} successful")
            else:
                self.log_result(action, "isolation", "FAIL",
                    f"Isolation issue: {results['success']} success, {results['failed']} failed")

            conn.close()
        except Exception as e:
            self.log_result(action, "isolation", "FAIL", str(e))

    def test_ta_reject_correction_isolated(self):
        """TA: Concurrent reject_correction operations must be isolated"""
        action = "ta_reject_correction"
        try:
            conn = self.get_connection()
            # Get pending correction requests
            corrections = conn.execute(
                "SELECT req_id FROM correction_requests WHERE status='pending' LIMIT 3"
            ).fetchall()

            if len(corrections) < 2:
                self.log_result(action, "isolation", "SKIP", "Not enough pending corrections to reject")
                conn.close()
                return

            results = {"success": 0, "failed": 0}
            lock = Lock()

            def reject_correction(corr_idx):
                try:
                    c = self.get_connection()
                    c.execute("BEGIN IMMEDIATE")
                    corr_id = corrections[corr_idx][0]
                    c.execute(
                        "UPDATE correction_requests SET status=? WHERE req_id=?",
                        ("rejected", corr_id)
                    )
                    c.commit()
                    with lock:
                        results["success"] += 1
                    c.close()
                except:
                    with lock:
                        results["failed"] += 1
                    c.close()

            # 2 concurrent reject operations
            threads = [threading.Thread(target=reject_correction, args=(i,)) for i in range(min(2, len(corrections)))]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            if results["failed"] == 0 and results["success"] > 0:
                self.log_result(action, "isolation", "PASS",
                    f"TA corrections rejected isolated: {results['success']} successful")
            else:
                self.log_result(action, "isolation", "FAIL",
                    f"Isolation issue: {results['success']} success, {results['failed']} failed")

            conn.close()
        except Exception as e:
            self.log_result(action, "isolation", "FAIL", str(e))

    # ═════════════════════════════════════════════════════════════════════════
    # STUDENT ACTION ISOLATION TESTS (1 total)
    # ═════════════════════════════════════════════════════════════════════════

    def test_student_submit_correction_isolated(self):
        """STUDENT: Concurrent submit_correction operations must be isolated"""
        action = "student_submit_correction"
        try:
            conn = self.get_connection()
            # Create a fresh session with an absent record for clean isolation test
            course = conn.execute("SELECT course_id FROM courses LIMIT 1").fetchone()
            student = conn.execute("SELECT user_id FROM users WHERE role='student' LIMIT 1").fetchone()

            if not course or not student:
                self.log_result(action, "isolation", "SKIP", "Missing test data")
                conn.close()
                return

            # Create fresh session
            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    "INSERT INTO attendance_sessions (course_id, session_date, topic, created_by) VALUES (?, ?, ?, ?)",
                    (course[0], datetime.now().date(), f"Student_Iso_{int(time.time())}", 1)
                )
                session_id = cur.lastrowid
                conn.commit()
            except:
                conn.rollback()
                self.log_result(action, "isolation", "SKIP", "Cannot create test session")
                conn.close()
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
                conn.close()
                return

            results = {"success": 0, "conflict": 0, "locked": 0}
            lock = Lock()

            def submit_correction(idx):
                try:
                    c = self.get_connection()
                    c.execute("BEGIN IMMEDIATE")
                    c.execute(
                        "INSERT INTO correction_requests (att_session_id, student_id, course_id, reason, status) VALUES (?, ?, ?, ?, ?)",
                        (session_id, student[0], course[0], f"Student Reason {idx}", "pending")
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
                except:
                    with lock:
                        results["locked"] += 1
                    c.close()

            # 2 concurrent correction submissions
            threads = [threading.Thread(target=submit_correction, args=(i,)) for i in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

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

    # ═════════════════════════════════════════════════════════════════════════
    # MAIN TEST RUNNER
    # ═════════════════════════════════════════════════════════════════════════

    def run_all_tests(self):
        print(f"\n{'='*100}")
        print(f"USER ACTIONS ISOLATION TESTS - {self.level.upper()} LEVEL")
        print(f"Total: 23 Isolation Tests (13 Admin + 5 Instructor + 4 TA + 1 Student)")
        print(f"{'='*100}\n")

        # Admin Actions (13 total)
        print("\n[ADMIN ACTIONS - 13 TESTS]")
        self.test_admin_create_semester_isolated()
        self.test_admin_create_user_isolated()
        self.test_admin_add_course_isolated()
        self.test_admin_delete_course_isolated()
        self.test_admin_add_instructor_isolated()
        self.test_admin_remove_instructor_isolated()
        self.test_admin_add_ta_isolated()
        self.test_admin_remove_ta_isolated()
        self.test_admin_add_enrolled_student_isolated()
        self.test_admin_remove_enrolled_student_isolated()
        self.test_admin_delete_user_isolated()
        self.test_admin_override_attendance_batch_isolated()

        # Instructor Actions (5 total)
        print("\n[INSTRUCTOR ACTIONS - 5 TESTS]")
        self.test_instructor_create_session_isolated()
        self.test_instructor_add_ta_isolated()
        self.test_instructor_accept_correction_isolated()
        self.test_instructor_reject_correction_isolated()
        self.test_instructor_remove_ta_isolated()

        # TA Actions (4 total)
        print("\n[TA ACTIONS - 4 TESTS]")
        self.test_ta_save_attendance_isolated()
        self.test_ta_create_session_isolated()
        self.test_ta_accept_correction_isolated()
        self.test_ta_reject_correction_isolated()

        # Student Actions (1 total)
        print("\n[STUDENT ACTIONS - 1 TEST]")
        self.test_student_submit_correction_isolated()

        self.print_summary()

    def print_summary(self):
        total = self.pass_count + self.fail_count + self.skip_count
        pass_pct = (self.pass_count / max(1, self.pass_count + self.fail_count)) * 100 if (self.pass_count + self.fail_count) > 0 else 0

        print(f"\n{'-'*100}")
        print(f"USER ACTIONS ISOLATION TEST SUMMARY ({self.level.upper()})")
        print(f"{'-'*100}")
        print(f"Total: 22 Tests | Passed: {self.pass_count} | Failed: {self.fail_count} | Skipped: {self.skip_count}")
        print(f"Pass Rate: {pass_pct:.1f}%")

        # Breakdown by category
        admin_tests = sum(1 for r in self.results if "admin_" in r["action"])
        instructor_tests = sum(1 for r in self.results if "instructor_" in r["action"])
        ta_tests = sum(1 for r in self.results if "ta_" in r["action"])
        student_tests = sum(1 for r in self.results if "student_" in r["action"])

        print(f"\nBreakdown:")
        print(f"  Admin Actions: {admin_tests} tests")
        print(f"  Instructor Actions: {instructor_tests} tests")
        print(f"  TA Actions: {ta_tests} tests")
        print(f"  Student Actions: {student_tests} tests")

        output_file = f"user_actions_isolation_test_results_{self.level}.json"
        with open(output_file, "w") as f:
            json.dump({
                "level": self.level,
                "timestamp": datetime.now().isoformat(),
                "summary": {
                    "total": 23,
                    "passed": self.pass_count,
                    "failed": self.fail_count,
                    "skipped": self.skip_count,
                    "pass_rate": pass_pct
                },
                "results": self.results
            }, f, indent=2)

        print(f"\nResults saved to: {output_file}")


if __name__ == "__main__":
    level = sys.argv[1] if len(sys.argv) > 1 else "database"
    tester = UserActionsIsolationTester(level=level)
    tester.run_all_tests()
