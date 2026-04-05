"""
locust_test.py
==============
HTTP-level stress test for the Multi-Course Attendance Management Portal.
Simulates StudentUser, InstructorUser, and AdminUser concurrently.

Run with Gunicorn (recommended — Flask dev server can't handle concurrent load):
    ./run_gunicorn.sh

Then in a second terminal:
    locust -f locust_test.py --host=http://localhost:5050

Locust UI: http://localhost:8089
  - Light load:  10 users, spawn rate 2
  - Medium load: 50 users, spawn rate 5
  - Heavy load: 100 users, spawn rate 10
"""

from locust import HttpUser, task, between, events
import random
import time
import json

print("=" * 80)
print("LOCUST STRESS TEST CONFIGURATION")
print("=" * 80)
print("Target: http://localhost:5050")
print("Expected test scenarios:")
print("  - StudentUser:    checking attendance, viewing/submitting corrections")
print("  - InstructorUser: viewing courses, sessions, corrections")
print("  - AdminUser:      listing users, courses, semesters, profile")
print("=" * 80)


# ═══════════════════════════════════════════════════════════════════════════════
# VALIDATION HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

class DataValidator:
    """Validates API response data format and basic integrity."""

    @staticmethod
    def validate_attendance_stats(data):
        """Validate /api/student/attendance-stats/current response."""
        errors = []
        if not isinstance(data, list):
            return ["Response must be a list"]
        for stat in data:
            if not isinstance(stat, dict):
                errors.append("Stat item is not a dict")
                continue
            for field in ["course_id", "name", "code", "total_sessions", "present", "absent", "late"]:
                if field not in stat:
                    errors.append(f"Missing field: {field}")
            try:
                total   = int(stat.get("total_sessions", 0))
                present = int(stat.get("present", 0))
                absent  = int(stat.get("absent", 0))
                late    = int(stat.get("late", 0))
                if present + absent + late != total:
                    errors.append(
                        f"Math error: {present}+{absent}+{late} ≠ {total} in {stat.get('code')}"
                    )
                if any(x < 0 for x in [total, present, absent, late]):
                    errors.append("Negative attendance count detected")
            except (ValueError, TypeError) as e:
                errors.append(f"Non-numeric attendance value: {e}")
        return errors

    @staticmethod
    def validate_course_list(data):
        """Validate course list responses."""
        errors = []
        if not isinstance(data, list):
            return ["Response must be a list"]
        for course in data:
            if not isinstance(course, dict):
                errors.append("Course item is not a dict")
                continue
            for field in ["course_id", "name", "code"]:
                if field not in course:
                    errors.append(f"Missing field: {field}")
            if not isinstance(course.get("course_id"), int) or course.get("course_id", 0) <= 0:
                errors.append(f"Invalid course_id: {course.get('course_id')}")
        return errors

    @staticmethod
    def validate_corrections_list(data):
        """Validate corrections list (student or instructor view)."""
        errors = []
        if not isinstance(data, list):
            return ["Response must be a list"]
        for cr in data:
            if not isinstance(cr, dict):
                errors.append("Correction item is not a dict")
                continue
            for field in ["req_id", "course_id", "status"]:
                if field not in cr:
                    errors.append(f"Missing field: {field}")
            # status must be one of the three valid values in our schema
            if cr.get("status") not in ["pending", "accepted", "rejected"]:
                errors.append(f"Invalid status: {cr.get('status')}")
        return errors

    @staticmethod
    def validate_user_list(data):
        """Validate /api/admin/users response."""
        errors = []
        if not isinstance(data, list):
            return ["Response must be a list"]
        for user in data:
            if not isinstance(user, dict):
                errors.append("User item is not a dict")
                continue
            for field in ["user_id", "username", "role"]:
                if field not in user:
                    errors.append(f"Missing field: {field}")
            if user.get("role") not in ["admin", "dean", "instructor", "ta", "student"]:
                errors.append(f"Invalid role: {user.get('role')}")
        return errors

    @staticmethod
    def validate_semester_list(data):
        """Validate /api/admin/semesters response."""
        errors = []
        if not isinstance(data, list):
            return ["Response must be a list"]
        for sem in data:
            if not isinstance(sem, dict):
                errors.append("Semester item is not a dict")
                continue
            for field in ["semester_id", "name"]:
                if field not in sem:
                    errors.append(f"Missing field: {field}")
        return errors


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH HELPER
# ═══════════════════════════════════════════════════════════════════════════════

def get_session(client, username, password):
    """
    POST /login and return (session_id, mac, user_id).
    Returns (None, None, None) on failure.
    """
    for attempt in range(3):
        try:
            with client.post(
                "/login",
                json={"username": username, "password": password},
                catch_response=True,
                timeout=15,
                name="/login"
            ) as res:
                if res.status_code == 0:
                    if attempt < 2:
                        time.sleep(1)
                        continue
                    res.failure("Connection refused after 3 retries")
                    return None, None, None

                if res.status_code != 200:
                    res.failure(f"Login HTTP {res.status_code}")
                    return None, None, None

                try:
                    data = res.json()
                except Exception:
                    res.failure("Login response is not JSON")
                    return None, None, None

                sid     = data.get("session_token", "")
                mac     = data.get("mac", "")
                user_id = data.get("user_id")

                if not sid or not mac or user_id is None:
                    res.failure("Login response missing session_token / mac / user_id")
                    return None, None, None

                res.success()
                return sid, mac, user_id

        except Exception as e:
            if attempt < 2:
                time.sleep(1)
                continue
            print(f"[AUTH] Exception for {username}: {str(e)[:80]}")

    return None, None, None


# ═══════════════════════════════════════════════════════════════════════════════
# STUDENT USER
# ═══════════════════════════════════════════════════════════════════════════════

class StudentUser(HttpUser):
    """Simulates a student: viewing attendance, corrections, submitting requests."""
    wait_time = between(1, 3)

    # All 60 students from init_db.py with random.seed(42)
    STUDENTS = [
        "aarav_verma0", "aditi_shah1", "akash_verma2", "ananya_bhat3",
        "arjun_patel4", "ayesha_shah5", "chirag_malhotra6", "deepika_shah7",
        "dev_patel8", "divya_agarwal9", "gaurav_mehta10", "harsha_singh11",
        "ishaan_nair12", "jiya_sharma13", "kabir_reddy14", "kavya_pillai15",
        "kunal_singh16", "lakshmi_mishra17", "manav_verma18", "meera_tiwari19",
        "mihir_nair20", "muskan_kumar21", "nandini_malhotra22", "nikhil_tiwari23",
        "nisha_malhotra24", "parth_sharma25", "pooja_agarwal26", "pranav_singh27",
        "priya_mehta28", "rahul_tiwari29", "riya_gupta30", "rohan_bhat31",
        "sakshi_nair32", "sarthak_bose33", "shivani_sharma34", "shreya_joshi35",
        "siddharth_reddy36", "simran_bose37", "snehal_verma38", "tanvi_agarwal39",
        "tarun_yadav40", "uday_patel41", "umang_bose42", "vandana_bose43",
        "varun_gupta44", "vidya_malhotra45", "vikas_pillai46", "vinay_patel47",
        "vishal_mishra48", "yash_shah49", "aman_singh50", "bhavna_malhotra51",
        "chetan_chopra52", "disha_kumar53", "ekta_mehta54", "farhan_mishra55",
        "gauri_tiwari56", "hemant_verma57", "isha_singh58", "jayesh_bhat59",
    ]

    def on_start(self):
        self.username = random.choice(self.STUDENTS)
        self.sid, self.mac, self.user_id = get_session(
            self.client, self.username, "password123"
        )
        self.authenticated = bool(self.sid and self.mac and self.user_id is not None)
        self.headers = {
            "X-Session-Id":  self.sid  or "",
            "X-Session-Mac": self.mac  or "",
            "Content-Type":  "application/json",
        }
        status = "✓" if self.authenticated else "✗"
        print(f"[STUDENT] {status} {self.username} (user_id={self.user_id})")

    def on_stop(self):
        if self.authenticated:
            self.client.post("/logout", headers=self.headers, name="/logout")

    # ── tasks ─────────────────────────────────────────────────────────────────

    @task(5)
    def view_attendance_stats(self):
        if not self.authenticated:
            return
        with self.client.get(
            "/api/student/attendance-stats/current",
            headers=self.headers,
            catch_response=True,
            name="GET /api/student/attendance-stats/current",
        ) as r:
            if r.status_code == 200:
                try:
                    errs = DataValidator.validate_attendance_stats(r.json())
                    if errs:
                        r.failure(f"Validation: {'; '.join(errs[:2])}")
                    else:
                        r.success()
                except Exception as e:
                    r.failure(f"JSON error: {str(e)[:80]}")
            elif r.status_code == 401:
                r.failure("Not authenticated")
            else:
                r.failure(f"HTTP {r.status_code}")

    @task(3)
    def view_corrections(self):
        if not self.authenticated:
            return
        with self.client.get(
            "/api/student/corrections/current",
            headers=self.headers,
            catch_response=True,
            name="GET /api/student/corrections/current",
        ) as r:
            if r.status_code == 200:
                try:
                    errs = DataValidator.validate_corrections_list(r.json())
                    if errs:
                        r.failure(f"Validation: {'; '.join(errs[:2])}")
                    else:
                        r.success()
                except Exception as e:
                    r.failure(f"JSON error: {str(e)[:80]}")
            elif r.status_code == 401:
                r.failure("Not authenticated")
            else:
                r.failure(f"HTTP {r.status_code}")

    @task(2)
    def view_past_attendance(self):
        if not self.authenticated:
            return
        with self.client.get(
            "/api/student/attendance-stats/archive",
            headers=self.headers,
            catch_response=True,
            name="GET /api/student/attendance-stats/archive",
        ) as r:
            if r.status_code in [200, 404]:
                r.success()
            elif r.status_code == 401:
                r.failure("Not authenticated")
            else:
                r.failure(f"HTTP {r.status_code}")

    @task(2)
    def view_profile(self):
        if not self.authenticated:
            return
        with self.client.get(
            "/api/student/profile",
            headers=self.headers,
            catch_response=True,
            name="GET /api/student/profile",
        ) as r:
            if r.status_code == 200:
                r.success()
            elif r.status_code == 401:
                r.failure("Not authenticated")
            else:
                r.failure(f"HTTP {r.status_code}")

    @task(1)
    def submit_correction(self):
        """
        Submit a correction request for a random absent session.
        Expects 200/201 (created), 409 (duplicate — expected), 400/403/404 (OK).
        """
        if not self.authenticated:
            return
        with self.client.post(
            "/api/student/corrections",
            headers=self.headers,
            json={
                "course_id":      random.randint(1, 10),
                "att_session_id": random.randint(1, 120),
                "reason":         f"Load test correction from {self.username}",
                "proof_url":      "",
            },
            catch_response=True,
            name="POST /api/student/corrections",
        ) as r:
            if r.status_code in [200, 201, 400, 403, 404, 409]:
                # 409 = duplicate (UNIQUE constraint) — correct behaviour
                r.success()
            elif r.status_code == 401:
                r.failure("Not authenticated")
            else:
                r.failure(f"HTTP {r.status_code}")


# ═══════════════════════════════════════════════════════════════════════════════
# INSTRUCTOR USER
# ═══════════════════════════════════════════════════════════════════════════════

class InstructorUser(HttpUser):
    """Simulates an instructor: viewing courses, sessions, and corrections."""
    wait_time = between(2, 5)

    # All 5 seeded instructors
    INSTRUCTORS = ["prof_singh", "prof_rao", "prof_mehta", "prof_sharma", "prof_jain"]

    def on_start(self):
        self.username = random.choice(self.INSTRUCTORS)
        self.sid, self.mac, self.user_id = get_session(
            self.client, self.username, "password123"
        )
        self.authenticated = bool(self.sid and self.mac and self.user_id is not None)
        self.headers = {
            "X-Session-Id":  self.sid  or "",
            "X-Session-Mac": self.mac  or "",
            "Content-Type":  "application/json",
        }
        
        # Fetch this instructor's assigned courses to avoid 403 errors
        self.course_ids = []
        if self.authenticated:
            try:
                resp = self.client.get(
                    "/api/instructor/courses",
                    headers=self.headers,
                    catch_response=True,
                )
                if resp.status_code == 200:
                    courses = resp.json()
                    self.course_ids = [c.get("course_id") for c in courses if "course_id" in c]
                resp.close()
            except:
                pass
        
        status = "✓" if self.authenticated else "✗"
        print(f"[INSTRUCTOR] {status} {self.username} (user_id={self.user_id}, courses={len(self.course_ids)})")

    def on_stop(self):
        if self.authenticated:
            self.client.post("/logout", headers=self.headers, name="/logout")

    # ── tasks ─────────────────────────────────────────────────────────────────

    @task(5)
    def view_courses(self):
        if not self.authenticated:
            return
        with self.client.get(
            "/api/instructor/courses",
            headers=self.headers,
            catch_response=True,
            name="GET /api/instructor/courses",
        ) as r:
            if r.status_code == 200:
                try:
                    errs = DataValidator.validate_course_list(r.json())
                    if errs:
                        r.failure(f"Validation: {'; '.join(errs[:2])}")
                    else:
                        r.success()
                except Exception as e:
                    r.failure(f"JSON error: {str(e)[:80]}")
            elif r.status_code == 401:
                r.failure("Not authenticated")
            else:
                r.failure(f"HTTP {r.status_code}")

    @task(4)
    def view_corrections(self):
        if not self.authenticated:
            return
        with self.client.get(
            "/api/instructor/corrections",
            headers=self.headers,
            catch_response=True,
            name="GET /api/instructor/corrections",
        ) as r:
            if r.status_code == 200:
                try:
                    data = r.json()
                    if not isinstance(data, list):
                        r.failure("Response must be a list")
                    else:
                        for cr in data:
                            if not isinstance(cr, dict):
                                r.failure("Correction item is not a dict")
                                return
                            for field in ["req_id", "course_id", "status"]:
                                if field not in cr:
                                    r.failure(f"Missing field: {field}")
                                    return
                            # accepted / rejected / pending are all valid here
                            if cr.get("status") not in ["pending", "accepted", "rejected"]:
                                r.failure(f"Invalid status: {cr.get('status')}")
                                return
                        r.success()
                except Exception as e:
                    r.failure(f"JSON error: {str(e)[:80]}")
            elif r.status_code == 401:
                r.failure("Not authenticated")
            else:
                r.failure(f"HTTP {r.status_code}")

    @task(3)
    def view_course_sessions(self):
        """GET /api/instructor/courses/{id}/sessions — correct endpoint."""
        if not self.authenticated or not self.course_ids:
            return
        course_id = random.choice(self.course_ids)
        with self.client.get(
            f"/api/instructor/courses/{course_id}/sessions",
            headers=self.headers,
            catch_response=True,
            name="GET /api/instructor/courses/<id>/sessions",
        ) as r:
            if r.status_code == 200:
                r.success()
            elif r.status_code == 401:
                r.failure("Not authenticated")
            else:
                r.failure(f"HTTP {r.status_code}")

    @task(2)
    def view_archive(self):
        if not self.authenticated:
            return
        with self.client.get(
            "/api/instructor/archive",
            headers=self.headers,
            catch_response=True,
            name="GET /api/instructor/archive",
        ) as r:
            if r.status_code in [200, 404]:
                r.success()
            elif r.status_code == 401:
                r.failure("Not authenticated")
            else:
                r.failure(f"HTTP {r.status_code}")

    @task(2)
    def view_profile(self):
        if not self.authenticated:
            return
        with self.client.get(
            "/api/instructor/profile",
            headers=self.headers,
            catch_response=True,
            name="GET /api/instructor/profile",
        ) as r:
            if r.status_code == 200:
                r.success()
            elif r.status_code == 401:
                r.failure("Not authenticated")
            else:
                r.failure(f"HTTP {r.status_code}")

    @task(1)
    def create_attendance_session(self):
        """
        POST /api/instructor/attendance-sessions.
        Duplicate date/course combos may return 400 — treat as OK.
        """
        if not self.authenticated or not self.course_ids:
            return
        with self.client.post(
            "/api/instructor/attendance-sessions",
            headers=self.headers,
            json={
                "course_id":    random.choice(self.course_ids),
                "session_date": time.strftime("%Y-%m-%d"),
                "topic":        "Load test session",
                "records":      [],
            },
            catch_response=True,
            name="POST /api/instructor/attendance-sessions",
        ) as r:
            if r.status_code in [200, 201, 400, 409]:
                r.success()
            elif r.status_code == 401:
                r.failure("Not authenticated")
            else:
                r.failure(f"HTTP {r.status_code}")


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN USER
# ═══════════════════════════════════════════════════════════════════════════════

class AdminUser(HttpUser):
    """Simulates an admin: listing users, courses, semesters, and profile."""
    wait_time = between(2, 4)

    def on_start(self):
        self.sid, self.mac, self.user_id = get_session(
            self.client, "admin", "password123"
        )
        self.authenticated = bool(self.sid and self.mac and self.user_id is not None)
        self.headers = {
            "X-Session-Id":  self.sid  or "",
            "X-Session-Mac": self.mac  or "",
            "Content-Type":  "application/json",
        }
        status = "✓" if self.authenticated else "✗"
        print(f"[ADMIN] {status} admin (user_id={self.user_id})")

    def on_stop(self):
        if self.authenticated:
            self.client.post("/logout", headers=self.headers, name="/logout")

    # ── tasks ─────────────────────────────────────────────────────────────────

    @task(5)
    def list_users(self):
        if not self.authenticated:
            return
        with self.client.get(
            "/api/admin/users",
            headers=self.headers,
            catch_response=True,
            name="GET /api/admin/users",
        ) as r:
            if r.status_code == 200:
                try:
                    errs = DataValidator.validate_user_list(r.json())
                    if errs:
                        r.failure(f"Validation: {'; '.join(errs[:2])}")
                    else:
                        r.success()
                except Exception as e:
                    r.failure(f"JSON error: {str(e)[:80]}")
            elif r.status_code == 401:
                r.failure("Not authenticated")
            else:
                r.failure(f"HTTP {r.status_code}")

    @task(5)
    def list_courses(self):
        if not self.authenticated:
            return
        with self.client.get(
            "/api/admin/courses",
            headers=self.headers,
            catch_response=True,
            name="GET /api/admin/courses",
        ) as r:
            if r.status_code == 200:
                try:
                    errs = DataValidator.validate_course_list(r.json())
                    if errs:
                        r.failure(f"Validation: {'; '.join(errs[:2])}")
                    else:
                        r.success()
                except Exception as e:
                    r.failure(f"JSON error: {str(e)[:80]}")
            elif r.status_code == 401:
                r.failure("Not authenticated")
            else:
                r.failure(f"HTTP {r.status_code}")

    @task(4)
    def list_semesters(self):
        if not self.authenticated:
            return
        with self.client.get(
            "/api/admin/semesters",
            headers=self.headers,
            catch_response=True,
            name="GET /api/admin/semesters",
        ) as r:
            if r.status_code == 200:
                try:
                    errs = DataValidator.validate_semester_list(r.json())
                    if errs:
                        r.failure(f"Validation: {'; '.join(errs[:2])}")
                    else:
                        r.success()
                except Exception as e:
                    r.failure(f"JSON error: {str(e)[:80]}")
            elif r.status_code == 401:
                r.failure("Not authenticated")
            else:
                r.failure(f"HTTP {r.status_code}")

    @task(4)
    def get_active_semester(self):
        if not self.authenticated:
            return
        with self.client.get(
            "/api/admin/active-semester",
            headers=self.headers,
            catch_response=True,
            name="GET /api/admin/active-semester",
        ) as r:
            if r.status_code == 200:
                try:
                    data = r.json()
                    if not isinstance(data, dict):
                        r.failure("Response must be a dict")
                    elif "semester_id" not in data or "name" not in data:
                        r.failure("Missing semester_id or name")
                    else:
                        r.success()
                except Exception as e:
                    r.failure(f"JSON error: {str(e)[:80]}")
            elif r.status_code in [404, 204]:
                r.success()  # No active semester is valid
            elif r.status_code == 401:
                r.failure("Not authenticated")
            else:
                r.failure(f"HTTP {r.status_code}")

    @task(2)
    def view_profile(self):
        if not self.authenticated:
            return
        with self.client.get(
            "/api/admin/profile",
            headers=self.headers,
            catch_response=True,
            name="GET /api/admin/profile",
        ) as r:
            if r.status_code == 200:
                r.success()
            elif r.status_code == 401:
                r.failure("Not authenticated")
            else:
                r.failure(f"HTTP {r.status_code}")


# ═══════════════════════════════════════════════════════════════════════════════
# TEST COMPLETION REPORT
# ═══════════════════════════════════════════════════════════════════════════════

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    print("\n" + "=" * 80)
    print("LOAD TEST COMPLETED — FINAL STATISTICS")
    print("=" * 80)
    if hasattr(environment, "stats") and hasattr(environment.stats, "entries"):
        for req in sorted(environment.stats.entries.values(), key=lambda x: x.name):
            fail_pct = (
                100 * req.num_failures / req.num_requests
                if req.num_requests > 0 else 0
            )
            print(
                f"\n{req.method} {req.name}:"
                f"\n  Requests: {req.num_requests}  Failures: {req.num_failures} ({fail_pct:.1f}%)"
                f"\n  Avg: {req.avg_response_time:.1f} ms  "
                f"Min: {req.min_response_time:.1f} ms  "
                f"Max: {req.max_response_time:.1f} ms"
            )