from locust import HttpUser, task, between, events
import random
import time

print("=" * 80)
print("LOCUST STRESS TEST CONFIGURATION")
print("=" * 80)
print("Target: http://localhost:5050")
print("Expected test scenarios:")
print("  - StudentUser: Checking attendance, submitting corrections")
print("  - InstructorUser: Viewing courses, marking attendance")
print("  - AdminUser: Listing users, viewing admin operations")
print("=" * 80)


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def get_session(client, username, password):
    """Authenticate user and return session token + mac"""
    try:
        with client.post(
            "/login",
            json={"username": username, "password": password},
            catch_response=True
        ) as res:
            if res.status_code not in [200, 302, 301]:
                print(f"[AUTH] Login failed for {username}: {res.status_code} - {res.text[:100]}")
                res.failure(f"Auth failed: {res.status_code}")
                return None, None
            
            # Try to parse JSON response
            try:
                data = res.json()
                session_token = data.get("session_token", "")
                mac = data.get("mac", "")
                
                if not session_token or not mac:
                    print(f"[AUTH] Missing session_token or mac in response for {username}")
                    res.failure("Missing session credentials in response")
                    return None, None
                
                res.success()
                return session_token, mac
            except Exception as json_err:
                print(f"[AUTH] Failed to parse login response for {username}: {str(json_err)[:100]}")
                print(f"[AUTH] Response text: {res.text[:200]}")
                res.failure(f"Failed to parse login response: {str(json_err)[:50]}")
                return None, None
    except Exception as e:
        print(f"[AUTH] Exception during login for {username}: {str(e)[:100]}")
        return None, None


# ═══════════════════════════════════════════════════════════════════════════════
# STUDENT USER — Simulates student checking attendance and submitting corrections
# ═══════════════════════════════════════════════════════════════════════════════
class StudentUser(HttpUser):
    wait_time = between(1, 3)  # Wait 1-3 seconds between requests
    
    def on_start(self):
        """Initialize student session at start"""
        # CORRECTED: ALL 60 actual credentials from database (with proper random.seed(42))
        students = [
            "aarav_verma0", "aditi_shah1", "akash_verma2", "aman_singh50", "ananya_bhat3",
            "arjun_patel4", "ayesha_shah5", "bhavna_malhotra51", "chetan_chopra52", "chirag_malhotra6",
            "deepika_shah7", "dev_patel8", "disha_kumar53", "divya_agarwal9", "ekta_mehta54",
            "farhan_mishra55", "gaurav_mehta10", "gauri_tiwari56", "harsha_singh11", "hemant_verma57",
            "isha_singh58", "ishaan_nair12", "jayesh_bhat59", "jiya_sharma13", "kabir_reddy14",
            "kavya_pillai15", "kunal_singh16", "lakshmi_mishra17", "manav_verma18", "meera_tiwari19",
            "mihir_nair20", "muskan_kumar21", "nandini_malhotra22", "nikhil_tiwari23", "nisha_malhotra24",
            "parth_sharma25", "pooja_agarwal26", "pranav_singh27", "priya_mehta28", "rahul_tiwari29",
            "riya_gupta30", "rohan_bhat31", "sakshi_nair32", "sarthak_bose33", "shivani_sharma34",
            "shreya_joshi35", "siddharth_reddy36", "simran_bose37", "snehal_verma38", "tanvi_agarwal39",
            "tarun_yadav40", "uday_patel41", "umang_bose42", "vandana_bose43", "varun_gupta44",
            "vidya_malhotra45", "vikas_pillai46", "vinay_patel47", "vishal_mishra48", "yash_shah49"
        ]
        self.username = random.choice(students)
        print(f"[STUDENT] Attempting login for: {self.username}")
        
        self.sid, self.mac = get_session(self.client, self.username, "password123")
        self.is_authenticated = (self.sid is not None and self.mac is not None and self.sid != "" and self.mac != "")
        
        if self.is_authenticated:
            self.headers = {
                "X-Session-Id": self.sid,
                "X-Session-Mac": self.mac,
                "Content-Type": "application/json"
            }
            print(f"[STUDENT] ✓ Auth SUCCESS for {self.username}")
        else:
            self.headers = {"Content-Type": "application/json"}
            print(f"[STUDENT] ✗ Auth FAILED for {self.username} - API calls will fail")

    @task(4)
    def view_attendance_stats(self):
        """Task: View attendance statistics"""
        with self.client.get(
            "/api/student/attendance-stats/current",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                # Log actual status for debugging
                try:
                    error_detail = f"Status: {response.status_code}, Reason: {response.text[:50]}"
                except:
                    error_detail = f"Status: {response.status_code}"
                response.failure(f"Attendance stats failed: {error_detail}")

    @task(3)
    def view_corrections(self):
        """Task: View submitted corrections"""
        with self.client.get(
            "/api/student/corrections/current",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                # Log actual status for debugging
                try:
                    error_detail = f"Status: {response.status_code}, Reason: {response.text[:50]}"
                except:
                    error_detail = f"Status: {response.status_code}"
                response.failure(f"View corrections failed: {error_detail}")

    @task(2)
    def view_enrollments(self):
        """Task: View enrolled courses"""
        with self.client.get(
            "/api/student/enrollments",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"View enrollments failed: {response.status_code}")

    @task(1)
    def submit_correction(self):
        """Task: Submit attendance correction (may get 409 if duplicate)"""
        with self.client.post(
            "/api/student/corrections",
            headers=self.headers,
            json={
                "course_id": 1,
                "att_session_id": random.randint(1, 10),
                "reason": f"Load test correction from {self.username}",
                "proof_url": ""
            },
            catch_response=True
        ) as response:
            if response.status_code in [200, 201, 409]:
                response.success()
            else:
                response.failure(f"Submit correction failed: {response.status_code}")


# ═══════════════════════════════════════════════════════════════════════════════
# INSTRUCTOR USER — Simulates marking attendance and viewing corrections
# ═══════════════════════════════════════════════════════════════════════════════
class InstructorUser(HttpUser):
    wait_time = between(2, 5)
    
    def on_start(self):
        """Initialize instructor session at start"""
        print("[INSTRUCTOR] Starting session for: prof_singh")
        self.sid, self.mac = get_session(self.client, "prof_singh", "password123")
        self.is_authenticated = (self.sid is not None and self.mac is not None and self.sid != "" and self.mac != "")
        
        if self.is_authenticated:
            self.headers = {
                "X-Session-Id": self.sid,
                "X-Session-Mac": self.mac,
                "Content-Type": "application/json"
            }
            print(f"[INSTRUCTOR] ✓ Auth SUCCESS for prof_singh")
        else:
            self.headers = {"Content-Type": "application/json"}
            print(f"[INSTRUCTOR] ✗ Auth FAILED for prof_singh - API calls will fail")

    @task(4)
    def view_courses(self):
        """Task: View assigned courses"""
        with self.client.get(
            "/api/instructor/courses",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"View courses failed: {response.status_code}")

    @task(3)
    def view_corrections(self):
        """Task: View pending corrections"""
        with self.client.get(
            "/api/instructor/corrections",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"View corrections failed: {response.status_code}")

    @task(2)
    def view_attendance_sessions(self):
        """Task: View attendance sessions for course"""
        with self.client.get(
            "/api/instructor/attendance-sessions?course_id=1",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"View sessions failed: {response.status_code}")

    @task(1)
    def create_attendance_session(self):
        """Task: Create new attendance session"""
        with self.client.post(
            "/api/instructor/attendance-sessions",
            headers=self.headers,
            json={
                "course_id": 1,
                "session_date": time.strftime("%Y-%m-%d"),
                "topic": "Load test session",
                "records": []
            },
            catch_response=True
        ) as response:
            if response.status_code in [200, 201, 400]:
                response.success()
            else:
                response.failure(f"Create session failed: {response.status_code}")


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN USER — Simulates comprehensive admin system management
# ═══════════════════════════════════════════════════════════════════════════════
class AdminUser(HttpUser):
    wait_time = between(2, 4)
    
    def on_start(self):
        """Initialize admin session at start"""
        print("[ADMIN] Starting session for: admin")
        self.sid, self.mac = get_session(self.client, "admin", "password123")
        self.is_authenticated = (self.sid is not None and self.mac is not None and self.sid != "" and self.mac != "")
        
        if self.is_authenticated:
            self.headers = {
                "X-Session-Id": self.sid,
                "X-Session-Mac": self.mac,
                "Content-Type": "application/json"
            }
            print(f"[ADMIN] ✓ Auth SUCCESS for admin")
        else:
            self.headers = {"Content-Type": "application/json"}
            print(f"[ADMIN] ✗ Auth FAILED for admin - API calls will fail")

    @task(5)
    def list_users(self):
        """Task: List all users - Most common admin operation"""
        with self.client.get(
            "/api/admin/users",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"List users failed: {response.status_code}")

    @task(5)
    def list_courses(self):
        """Task: List all courses with semester info"""
        with self.client.get(
            "/api/admin/courses",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"List courses failed: {response.status_code}")

    @task(4)
    def list_semesters(self):
        """Task: List all semesters"""
        with self.client.get(
            "/api/admin/semesters",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"List semesters failed: {response.status_code}")

    @task(4)
    def get_active_semester(self):
        """Task: Get currently active semester"""
        with self.client.get(
            "/api/admin/active-semester",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"Get active semester failed: {response.status_code}")

    @task(3)
    def view_archived_semesters(self):
        """Task: View archived (inactive) semesters"""
        with self.client.get(
            "/api/admin/archive",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"View archive failed: {response.status_code}")

    @task(3)
    def get_instructors_list(self):
        """Task: Get list of all instructors"""
        with self.client.get(
            "/api/admin/instructors",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"Get instructors list failed: {response.status_code}")

    @task(3)
    def get_students_list(self):
        """Task: Get list of all students"""
        with self.client.get(
            "/api/admin/students",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"Get students list failed: {response.status_code}")

    @task(3)
    def get_tas_list(self):
        """Task: Get list of all TAs"""
        with self.client.get(
            "/api/admin/tas",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"Get TAs list failed: {response.status_code}")

    @task(2)
    def view_semester_courses(self):
        """Task: View courses for a specific semester"""
        semester_id = random.randint(1, 2)
        with self.client.get(
            f"/api/admin/semesters/{semester_id}/courses",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"View semester courses failed: {response.status_code}")

    @task(2)
    def view_course_attendance_sessions(self):
        """Task: View attendance sessions for a course"""
        course_id = random.randint(1, 5)
        with self.client.get(
            f"/api/admin/courses/{course_id}/sessions",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"View course sessions failed: {response.status_code}")

    @task(2)
    def view_admin_profile(self):
        """Task: View current admin profile"""
        with self.client.get(
            "/api/admin/profile",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"View profile failed: {response.status_code}")

    @task(1)
    def view_attendance_records(self):
        """Task: View attendance records for a session"""
        session_id = random.randint(1, 20)
        with self.client.get(
            f"/api/admin/sessions/{session_id}/records",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"View attendance records failed: {response.status_code}")

    @task(1)
    def get_available_instructors(self):
        """Task: Get instructors NOT assigned to a specific course"""
        course_id = random.randint(1, 5)
        with self.client.get(
            f"/api/admin/courses/{course_id}/available-instructors",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"Get available instructors failed: {response.status_code}")


# ═══════════════════════════════════════════════════════════════════════════════
# EVENT LISTENERS FOR REPORTING
# ═══════════════════════════════════════════════════════════════════════════════

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Generate test report when load test completes"""
    print("\n" + "=" * 80)
    print("LOAD TEST COMPLETED — FINAL STATISTICS")
    print("=" * 80)
    
    if hasattr(environment, 'stats') and hasattr(environment.stats, 'entries'):
        for req in environment.stats.entries.values():
            print(f"\n{req.name}:")
            print(f"  Requests: {req.num_requests}")
            print(f"  Failures: {req.num_failures}")
            if req.num_requests > 0:
                print(f"  Avg Response: {req.avg_response_time:.2f} ms")
                print(f"  Min Response: {req.min_response_time:.2f} ms")
                print(f"  Max Response: {req.max_response_time:.2f} ms")
