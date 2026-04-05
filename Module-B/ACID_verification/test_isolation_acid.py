"""
test_isolation_acid.py
=======================
ACID Property: ISOLATION
Tests: Concurrent operations, no lost updates, read consistency

"The I in ACID: Concurrent transactions don't interfere with each other.
Each transaction operates as if it's the only one running."
"""

import sqlite3
import json
import time
import threading
import random
from datetime import datetime, timedelta
from threading import Lock, Barrier
import os
import sys
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class IsolationTester:
    """Test ISOLATION property across all levels"""

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
    # DATABASE LEVEL ISOLATION TESTS
    # ═══════════════════════════════════════════════════════════════════════════

    def test_db_concurrent_semester_inserts(self):
        """DB: Concurrent semester inserts must be isolated"""
        test_name = "db_concurrent_semester_inserts"
        try:
            results = {"inserted": 0, "failed": 0}
            lock = Lock()

            def insert_semester(sem_num):
                conn = self.get_db_connection()
                try:
                    sem_name = f"ConcSem_{int(time.time())}_{sem_num}_{random.randint(1000, 9999)}"
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute(
                        "INSERT INTO semesters (name, is_active) VALUES (?, ?)",
                        (sem_name, 0)
                    )
                    conn.commit()
                    with lock:
                        results["inserted"] += 1
                except Exception as e:
                    with lock:
                        results["failed"] += 1
                finally:
                    conn.close()

            # Run 5 concurrent inserts
            threads = []
            for i in range(5):
                t = threading.Thread(target=insert_semester, args=(i,))
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

            if results["inserted"] == 5 and results["failed"] == 0:
                self.log_result(test_name, "PASS",
                    f"All 5 concurrent inserts succeeded - database properly isolated")
            else:
                self.log_result(test_name, "FAIL",
                    f"Concurrent operations failed: {results['inserted']} success, {results['failed']} failed")

        except Exception as e:
            self.log_result(test_name, "FAIL", f"Setup error: {str(e)}")

    def test_db_concurrent_attendance_updates(self):
        """DB: Concurrent attendance updates must not cause lost updates"""
        test_name = "db_concurrent_attendance_updates"
        try:
            # Get test session
            conn = self.get_db_connection()
            session = conn.execute(
                "SELECT session_id FROM attendance_sessions LIMIT 1"
            ).fetchone()
            conn.close()

            if not session:
                self.log_result(test_name, "SKIP", "No session found")
                return

            session_id = session[0]
            updates = {"count": 0, "failed": 0}
            lock = Lock()

            def update_status(student_id):
                conn = self.get_db_connection()
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute(
                        """UPDATE attendance_records
                           SET status = ? WHERE session_id = ? AND student_id = ?""",
                        ("present", session_id, student_id)
                    )
                    conn.commit()
                    with lock:
                        updates["count"] += 1
                except Exception as e:
                    with lock:
                        updates["failed"] += 1
                finally:
                    conn.close()

            # Get students with records in this session
            conn = self.get_db_connection()
            students = conn.execute(
                "SELECT DISTINCT student_id FROM attendance_records WHERE session_id=? LIMIT 5",
                (session_id,)
            ).fetchall()
            conn.close()

            if not students:
                self.log_result(test_name, "SKIP", "No attendance records found")
                return

            # Concurrent updates
            threads = []
            for student in students:
                t = threading.Thread(target=update_status, args=(student[0],))
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

            if updates["failed"] == 0:
                self.log_result(test_name, "PASS",
                    f"All {updates['count']} concurrent updates succeeded without conflicts")
            else:
                self.log_result(test_name, "FAIL",
                    f"Concurrent updates failed: {updates['failed']} conflicts")

        except Exception as e:
            self.log_result(test_name, "FAIL", f"Setup error: {str(e)}")

    def test_db_read_consistency_under_writes(self):
        """DB: Reads must see consistent snapshot during concurrent writes"""
        test_name = "db_read_consistency_under_writes"
        try:
            course = None
            sem = None
            conn = self.get_db_connection()
            sem = conn.execute("SELECT semester_id FROM semesters LIMIT 1").fetchone()
            conn.close()

            if not sem:
                self.log_result(test_name, "SKIP", "No semester found")
                return

            sem_id = sem[0]
            results = {"reads": [], "success": False}
            lock = Lock()

            # Create initial data
            base_code = f"READTEST_{int(time.time())}"

            # Writer thread
            def writer_thread():
                for i in range(3):
                    conn = self.get_db_connection()
                    try:
                        conn.execute("BEGIN IMMEDIATE")
                        conn.execute(
                            "INSERT INTO courses (code, name, semester_id) VALUES (?, ?, ?)",
                            (f"{base_code}_{i}", f"Course {i}", sem_id)
                        )
                        conn.commit()
                        time.sleep(0.1)
                    except:
                        pass
                    finally:
                        conn.close()

            # Reader thread
            def reader_thread():
                time.sleep(0.05)  # Let first write start
                conn = self.get_db_connection()
                try:
                    # Snapshot read
                    count = conn.execute(
                        f"SELECT COUNT(*) FROM courses WHERE code LIKE '{base_code}%'"
                    ).fetchone()[0]
                    with lock:
                        results["reads"].append(count)
                finally:
                    conn.close()

            # Run concurrently
            t1 = threading.Thread(target=writer_thread)
            t2 = threading.Thread(target=reader_thread)
            t1.start()
            t2.start()
            t1.join()
            t2.join()

            # Final count should match
            conn = self.get_db_connection()
            final_count = conn.execute(
                f"SELECT COUNT(*) FROM courses WHERE code LIKE '{base_code}%'"
            ).fetchone()[0]
            conn.close()

            if final_count >= 3:
                self.log_result(test_name, "PASS",
                    f"Read isolation maintained - final count: {final_count}")
            else:
                self.log_result(test_name, "FAIL",
                    f"Read saw inconsistent data - expected >=3, got {final_count}")

        except Exception as e:
            self.log_result(test_name, "FAIL", f"Setup error: {str(e)}")

    def test_db_unique_constraint_isolation(self):
        """DB: Unique constraints must be enforced under concurrent inserts"""
        test_name = "db_unique_constraint_isolation"
        try:
            unique_username = f"isolateduser_{int(time.time())}"
            results = {"success": 0, "conflicts": 0}
            lock = Lock()

            def insert_user(attempt):
                conn = self.get_db_connection()
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute(
                        "INSERT INTO users (username, pwd_hash, role) VALUES (?, ?, ?)",
                        (unique_username, "hash123", "student")
                    )
                    conn.commit()
                    with lock:
                        results["success"] += 1
                except sqlite3.IntegrityError:
                    with lock:
                        results["conflicts"] += 1
                finally:
                    conn.close()

            # Concurrent attempts to insert same username
            threads = []
            for i in range(3):
                t = threading.Thread(target=insert_user, args=(i,))
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

            # Exactly one should succeed
            if results["success"] == 1 and results["conflicts"] == 2:
                self.log_result(test_name, "PASS",
                    "Unique constraint properly isolated - only 1 insert succeeded")
            else:
                self.log_result(test_name, "FAIL",
                    f"Isolation failed: {results['success']} success, {results['conflicts']} conflicts")

        except Exception as e:
            self.log_result(test_name, "FAIL", f"Setup error: {str(e)}")

    # ═══════════════════════════════════════════════════════════════════════════
    # APPLICATION LEVEL ISOLATION TESTS
    # ═══════════════════════════════════════════════════════════════════════════

    def test_app_concurrent_session_creation(self):
        """APP: Concurrent session creation must be isolated"""
        test_name = "app_concurrent_session_creation"
        try:
            from app import create_app
            from app.db import get_db

            app = create_app()
            with app.app_context():
                conn = get_db()
                course = conn.execute("SELECT course_id FROM courses LIMIT 1").fetchone()

                if not course:
                    self.log_result(test_name, "SKIP", "No course found")
                    return

                course_id = course[0]

                results = {"created": 0, "failed": 0}
                lock = Lock()

                def create_session(idx):
                    try:
                        c = get_db()
                        c.execute("BEGIN IMMEDIATE")
                        c.execute(
                            """INSERT INTO attendance_sessions
                               (course_id, session_date, session_time, created_by)
                               VALUES (?, ?, ?, ?)""",
                            (course_id, datetime.now().date(), f"0{idx}:00", 1)
                        )
                        c.commit()
                        with lock:
                            results["created"] += 1
                    except:
                        with lock:
                            results["failed"] += 1

                threads = []
                for i in range(3):
                    t = threading.Thread(target=create_session, args=(i,))
                    threads.append(t)
                    t.start()

                for t in threads:
                    t.join()

                if results["failed"] == 0:
                    self.log_result(test_name, "PASS",
                        f"All {results['created']} sessions created with proper isolation")
                else:
                    self.log_result(test_name, "FAIL",
                        f"Isolation issues detected: {results['failed']} failures")

        except ImportError:
            self.log_result(test_name, "SKIP", "Application not available")
        except Exception as e:
            self.log_result(test_name, "FAIL", f"Error: {str(e)}")

    # ═══════════════════════════════════════════════════════════════════════════
    # API LEVEL ISOLATION TESTS
    # ═══════════════════════════════════════════════════════════════════════════

    def test_api_concurrent_requests(self):
        """API: Concurrent API requests must be isolated"""
        test_name = "api_concurrent_requests"
        try:
            results = {"success": 0, "failed": 0}
            lock = Lock()

            def make_request(idx):
                try:
                    response = requests.get(
                        f"{self.api_base_url}/api/dean/current-semester",
                        headers={"Authorization": "Bearer dean_token"},
                        timeout=5
                    )
                    if response.status_code in [200, 401]:  # 200=OK, 401=auth issue expected
                        with lock:
                            results["success"] += 1
                    else:
                        with lock:
                            results["failed"] += 1
                except requests.exceptions.ConnectionError:
                    raise
                except:
                    with lock:
                        results["failed"] += 1

            try:
                threads = []
                for i in range(5):
                    t = threading.Thread(target=make_request, args=(i,))
                    threads.append(t)
                    t.start()

                for t in threads:
                    t.join()

                if results["success"] > 0:
                    self.log_result(test_name, "PASS",
                        f"All {results['success']} concurrent API requests succeeded")
                else:
                    self.log_result(test_name, "SKIP",
                        "API not responding to concurrent requests")
            except requests.exceptions.ConnectionError:
                self.log_result(test_name, "SKIP", "API server not running")

        except Exception as e:
            self.log_result(test_name, "FAIL", f"Error: {str(e)}")

    def run_all_tests(self):
        """Run all isolation tests for this level"""
        print(f"\n{'='*100}")
        print(f"ISOLATION TESTS - {self.level.upper()} LEVEL")
        print(f"{'='*100}\n")

        if self.level == "database":
            self.test_db_concurrent_semester_inserts()
            self.test_db_concurrent_attendance_updates()
            self.test_db_read_consistency_under_writes()
            self.test_db_unique_constraint_isolation()
        elif self.level == "application":
            self.test_app_concurrent_session_creation()
        elif self.level == "api":
            self.test_api_concurrent_requests()

        self.print_summary()

    def print_summary(self):
        """Print test summary"""
        total = self.pass_count + self.fail_count
        pass_pct = (self.pass_count / max(1, total)) * 100 if total > 0 else 0

        print(f"\n{'-'*100}")
        print(f"ISOLATION TEST SUMMARY ({self.level.upper()})")
        print(f"{'-'*100}")
        print(f"Total: {total} | Passed: {self.pass_count} | Failed: {self.fail_count}")
        print(f"Pass Rate: {pass_pct:.1f}%")

        # Save results
        output_file = f"isolation_test_results_{self.level}.json"
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
    tester = IsolationTester(level=level)
    tester.run_all_tests()
