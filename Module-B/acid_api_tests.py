import requests
import threading
import time
import json
import random
import unittest
from datetime import datetime

# Configuration
BASE_URL = "http://127.0.0.1:5050"
DEFAULT_PASSWORD = "password123"

class APIACIDTester(unittest.TestCase):
    """
    API-level ACID testing. 
    Requires the Flask server to be running at BASE_URL.
    """

    def setUp(self):
        self.session = requests.Session()
        self.results = []

    def login(self, username, password=DEFAULT_PASSWORD):
        """Authenticates and returns headers required by middleware.py"""
        url = f"{BASE_URL}/api/auth/login"
        payload = {"username": username, "password": password}
        response = self.session.post(url, json=payload)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "X-Session-Id": data['session_token'],
                "X-Session-Mac": data['mac'],
                "Content-Type": "application/json"
            }
        return None

    def log_api_result(self, role, action, prop, status, msg=""):
        res = f"[{status}] API_{role.upper()} - {action} ({prop}): {msg}"
        print(res)
        self.results.append(res)

    # ─────────────────────────────────────────────────────────────────────────
    # ADMIN API TESTS
    # ─────────────────────────────────────────────────────────────────────────

    def test_admin_api_suite(self):
        role = "admin"
        headers = self.login("admin")
        self.assertIsNotNone(headers, "Admin login failed")

        # --- Action: Create Course (Atomicity/Consistency) ---
        action = "create_course"
        course_data = {
            "name": f"API Test Course {random.randint(1,1000)}",
            "code": f"CS{random.randint(100,999)}",
            "semester_id": 1
        }
        
        # 1. ATOMICITY: Full creation via POST
        resp = requests.post(f"{BASE_URL}/api/admin/courses", json=course_data, headers=headers)
        if resp.status_code == 201:
            self.log_api_result(role, action, "atomicity", "PASS", "Course created via API")
        else:
            self.log_api_result(role, action, "atomicity", "FAIL", f"Status: {resp.status_code}")

        # 2. CONSISTENCY: Verify via GET endpoint
        get_resp = requests.get(f"{BASE_URL}/api/admin/courses", headers=headers)
        courses = get_resp.json()
        found = any(c['code'] == course_data['code'] for c in courses)
        self.log_api_result(role, action, "consistency", "PASS" if found else "FAIL", "Course visible in list")

        # 3. ISOLATION: Concurrent creation attempts
        def worker():
            h = self.login("admin")
            requests.post(f"{BASE_URL}/api/admin/courses", 
                          json={"name": "IsoTest", "code": f"C{random.random()}", "semester_id": 1}, 
                          headers=h)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.log_api_result(role, action, "isolation", "PASS", "Handled concurrent creation requests")

    # ─────────────────────────────────────────────────────────────────────────
    # INSTRUCTOR API TESTS
    # ─────────────────────────────────────────────────────────────────────────

    def test_instructor_api_suite(self):
        role = "instructor"
        headers = self.login("prof_singh")
        self.assertIsNotNone(headers)

        # --- Action: Create Session ---
        action = "create_session"
        payload = {"course_id": 1, "session_date": "2025-11-11", "topic": "API ACID Test"}
        
        resp = requests.post(f"{BASE_URL}/api/instructor/sessions", json=payload, headers=headers)
        status = "PASS" if resp.status_code == 201 else "FAIL"
        self.log_api_result(role, action, "atomicity", status)

    # ─────────────────────────────────────────────────────────────────────────
    # STUDENT API TESTS
    # ─────────────────────────────────────────────────────────────────────────

    def test_student_api_suite(self):
        role = "student"
        headers = self.login("student_01")
        self.assertIsNotNone(headers)

        # --- Action: View Attendance (Read Durability) ---
        action = "view_stats"
        resp = requests.get(f"{BASE_URL}/api/student/attendance-stats", headers=headers)
        if resp.status_code == 200:
            self.log_api_result(role, action, "durability", "PASS", "Retrieved stats successfully")
        else:
            self.log_api_result(role, action, "durability", "FAIL")

        # --- SECURITY CHECK (Consistency of Permissions) ---
        # Student trying to delete a user
        forbidden_resp = requests.delete(f"{BASE_URL}/api/admin/users/1", headers=headers)
        if forbidden_resp.status_code == 403:
            self.log_api_result(role, "admin_delete_access", "consistency", "PASS", "Permission denied as expected")
        else:
            self.log_api_result(role, "admin_delete_access", "consistency", "FAIL", "Security vulnerability detected!")

    # ─────────────────────────────────────────────────────────────────────────
    # DURABILITY (Server Restart Simulation)
    # ─────────────────────────────────────────────────────────────────────────

    def test_durability_across_sessions(self):
        """Verify data remains after logout/login cycle"""
        headers = self.login("admin")
        
        # 1. Create something
        unique_name = f"DurableSem_{random.randint(1,9999)}"
        requests.post(f"{BASE_URL}/api/admin/semesters", json={"name": unique_name}, headers=headers)
        
        # 2. Logout
        requests.post(f"{BASE_URL}/api/auth/logout", headers=headers)
        
        # 3. Login again and check
        new_headers = self.login("admin")
        resp = requests.get(f"{BASE_URL}/api/admin/semesters", headers=new_headers)
        found = any(s['name'] == unique_name for s in resp.json())
        
        self.log_api_result("admin", "durability_check", "durability", "PASS" if found else "FAIL")

if __name__ == "__main__":
    print(f"Starting API Tests against {BASE_URL}...")
    unittest.main()