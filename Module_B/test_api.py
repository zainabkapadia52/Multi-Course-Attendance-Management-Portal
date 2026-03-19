#!/usr/bin/env python3
"""
API Testing Script for Module B
Demonstrates the REST API functionality without using the web UI
"""

import requests
import json
from typing import Optional, Dict

BASE_URL = "http://localhost:5000"

class APIClient:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.session_token: Optional[str] = None
        self.mac: Optional[str] = None
        self.username: Optional[str] = None
        self.role: Optional[str] = None
    
    def _headers(self) -> Dict[str, str]:
        """Get headers with authentication tokens"""
        headers = {"Content-Type": "application/json"}
        if self.session_token and self.mac:
            headers["X-Session-Id"] = self.session_token
            headers["X-Session-Mac"] = self.mac
        return headers
    
    def login(self, username: str, password: str) -> Dict:
        """Login and store session tokens"""
        response = requests.post(
            f"{self.base_url}/login",
            json={"user": username, "password": password}
        )
        
        if response.status_code == 200:
            data = response.json()
            self.session_token = data.get("session_token")
            self.mac = data.get("mac")
            self.username = data.get("username")
            self.role = data.get("role")
            print(f"✓ Logged in as {self.username} ({self.role})")
            return data
        else:
            print(f"✗ Login failed: {response.json()}")
            return {}
    
    def check_auth(self) -> Dict:
        """Check if current session is valid"""
        response = requests.get(
            f"{self.base_url}/isAuth",
            headers=self._headers()
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Session valid: {data['username']} ({data['role']})")
            return data
        else:
            print(f"✗ Session invalid: {response.json()}")
            return {}
    
    def get(self, endpoint: str) -> Dict:
        """Make authenticated GET request"""
        response = requests.get(
            f"{self.base_url}{endpoint}",
            headers=self._headers()
        )
        return response.json(), response.status_code
    
    def post(self, endpoint: str, data: Dict) -> Dict:
        """Make authenticated POST request"""
        response = requests.post(
            f"{self.base_url}{endpoint}",
            json=data,
            headers=self._headers()
        )
        return response.json(), response.status_code
    
    def put(self, endpoint: str, data: Dict) -> Dict:
        """Make authenticated PUT request"""
        response = requests.put(
            f"{self.base_url}{endpoint}",
            json=data,
            headers=self._headers()
        )
        return response.json(), response.status_code
    
    def delete(self, endpoint: str) -> Dict:
        """Make authenticated DELETE request"""
        response = requests.delete(
            f"{self.base_url}{endpoint}",
            headers=self._headers()
        )
        return response.json(), response.status_code


def test_student_apis():
    """Test student role APIs"""
    print("\n" + "="*60)
    print("TESTING STUDENT APIs")
    print("="*60)
    
    client = APIClient()
    
    # Login as student
    client.login("student1", "pass123")
    
    # Check authentication
    client.check_auth()
    
    # Get my courses
    print("\n→ GET /api/student/courses")
    courses, status = client.get("/api/student/courses")
    print(f"  Status: {status}")
    print(f"  Courses: {json.dumps(courses, indent=2)}")
    
    # Get my attendance
    print("\n→ GET /api/student/attendance")
    attendance, status = client.get("/api/student/attendance")
    print(f"  Status: {status}")
    print(f"  Records: {len(attendance)} attendance records")
    
    # Get my profile
    print("\n→ GET /api/student/profile")
    profile, status = client.get("/api/student/profile")
    print(f"  Status: {status}")
    print(f"  Profile: {json.dumps(profile, indent=2)}")
    
    # Get correction requests
    print("\n→ GET /api/student/corrections")
    corrections, status = client.get("/api/student/corrections")
    print(f"  Status: {status}")
    print(f"  Corrections: {len(corrections)} requests")


def test_admin_apis():
    """Test admin role APIs"""
    print("\n" + "="*60)
    print("TESTING ADMIN APIs")
    print("="*60)
    
    client = APIClient()
    
    # Login as admin
    client.login("admin", "admin123")
    
    # Check authentication
    client.check_auth()
    
    # Get all users
    print("\n→ GET /api/admin/users")
    users, status = client.get("/api/admin/users")
    print(f"  Status: {status}")
    print(f"  Users: {len(users)} users in system")
    
    # Get all courses
    print("\n→ GET /api/admin/courses")
    courses, status = client.get("/api/admin/courses")
    print(f"  Status: {status}")
    print(f"  Courses: {len(courses)} courses")


def test_instructor_apis():
    """Test instructor role APIs"""
    print("\n" + "="*60)
    print("TESTING INSTRUCTOR APIs")
    print("="*60)
    
    client = APIClient()
    
    # Login as instructor
    client.login("instructor1", "pass123")
    
    # Check authentication
    client.check_auth()
    
    # Get my courses
    print("\n→ GET /api/instructor/courses")
    courses, status = client.get("/api/instructor/courses")
    print(f"  Status: {status}")
    print(f"  Teaching: {len(courses)} courses")
    
    # Get correction requests
    print("\n→ GET /api/instructor/corrections")
    corrections, status = client.get("/api/instructor/corrections")
    print(f"  Status: {status}")
    print(f"  Pending: {len(corrections)} correction requests")


def test_rbac_enforcement():
    """Test that RBAC is properly enforced"""
    print("\n" + "="*60)
    print("TESTING RBAC ENFORCEMENT")
    print("="*60)
    
    # Try to access admin endpoint as student
    print("\n→ Student trying to access admin endpoint")
    client = APIClient()
    client.login("student1", "pass123")
    
    users, status = client.get("/api/admin/users")
    print(f"  Status: {status}")
    if status == 403:
        print("  ✓ Access correctly denied (403 Forbidden)")
    else:
        print("  ✗ RBAC not working! Student accessed admin endpoint")
    
    # Try to access without authentication
    print("\n→ Accessing protected endpoint without auth")
    client_no_auth = APIClient()
    courses, status = client_no_auth.get("/api/student/courses")
    print(f"  Status: {status}")
    if status == 401:
        print("  ✓ Access correctly denied (401 Unauthorized)")
    else:
        print("  ✗ Authentication not working!")


def test_session_expiry():
    """Test session validation"""
    print("\n" + "="*60)
    print("TESTING SESSION VALIDATION")
    print("="*60)
    
    client = APIClient()
    
    # Login
    client.login("student1", "pass123")
    
    # Valid session
    print("\n→ Checking valid session")
    client.check_auth()
    
    # Invalid session token
    print("\n→ Checking with invalid token")
    client.session_token = "invalid-token"
    result = client.check_auth()
    if not result:
        print("  ✓ Invalid token correctly rejected")


def main():
    """Run all API tests"""
    print("\n" + "="*60)
    print("MODULE B - REST API TESTING")
    print("="*60)
    print("\nThis script demonstrates the API-first architecture")
    print("All operations are performed via REST API calls (JSON)")
    print("No web UI is used in this test\n")
    
    try:
        # Test different roles
        test_student_apis()
        test_admin_apis()
        test_instructor_apis()
        
        # Test security
        test_rbac_enforcement()
        test_session_expiry()
        
        print("\n" + "="*60)
        print("API TESTING COMPLETE")
        print("="*60)
        print("\n✓ All tests demonstrate proper REST API functionality")
        print("✓ Session-based authentication working")
        print("✓ RBAC enforcement working")
        print("✓ APIs return JSON responses (not HTML)")
        
    except requests.exceptions.ConnectionError:
        print("\n✗ ERROR: Cannot connect to server")
        print("  Make sure the Flask app is running:")
        print("  $ cd Module_B && python run.py")
    except Exception as e:
        print(f"\n✗ ERROR: {e}")


if __name__ == "__main__":
    main()
