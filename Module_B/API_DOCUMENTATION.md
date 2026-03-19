# Module B - REST API Documentation

## Overview
This is a RESTful API implementation for the Course Management System with Role-Based Access Control (RBAC). The API provides secure endpoints for authentication, user management, and course operations.

## Architecture
- **Backend**: Flask REST API (JSON responses only)
- **Authentication**: Session-based with JWT-like tokens (session_id + MAC)
- **Authorization**: Role-Based Access Control (RBAC)
- **Security**: Audit logging for all data modifications
- **Database**: SQLite with optimized indexes

## Base URL
```
http://localhost:5000
```

## Authentication Flow

### 1. Login
**Endpoint**: `POST /login`

**Description**: Authenticates a user and issues a session token.

**Request Body** (JSON):
```json
{
  "user": "string",      // or "username"
  "password": "string"
}
```

**Success Response** (200):
```json
{
  "message": "Login successful",
  "session_token": "uuid-string",
  "mac": "hmac-signature",
  "role": "admin|instructor|student|dean|ta",
  "username": "string"
}
```

**Error Responses**:
- `401`: `{"error": "Invalid credentials"}` - Wrong username/password
- `401`: `{"error": "Missing parameters"}` - Missing required fields

**Example**:
```bash
curl -X POST http://localhost:5000/login \
  -H "Content-Type: application/json" \
  -d '{"user": "admin", "password": "admin123"}'
```

---

### 2. Check Authentication Status
**Endpoint**: `GET /isAuth`

**Description**: Verifies if a user's session is valid.

**Request Headers** (Option 1):
```
X-Session-Id: <session_token>
X-Session-Mac: <mac>
```

**Request Body** (Option 2 - JSON):
```json
{
  "session_token": "uuid-string",
  "mac": "hmac-signature"
}
```

**Success Response** (200):
```json
{
  "message": "User is authenticated",
  "username": "string",
  "role": "string",
  "expiry": "ISO-8601-datetime"
}
```

**Error Responses**:
- `401`: `{"error": "No session found"}` - No session provided
- `401`: `{"error": "Session expired"}` - Session has expired
- `401`: `{"error": "Invalid session token"}` - MAC verification failed

**Example**:
```bash
curl -X GET http://localhost:5000/isAuth \
  -H "X-Session-Id: abc-123-def" \
  -H "X-Session-Mac: hmac-signature"
```

---

### 3. Logout
**Endpoint**: `POST /logout`

**Description**: Invalidates the current session.

**Request**: Session cookies or headers

**Success Response**: Redirects to `/login` with cleared cookies

---

## Role-Based Endpoints

### Admin APIs (`/api/admin/*`)

#### Get All Users
**Endpoint**: `GET /api/admin/users`

**Authorization**: Admin only

**Response** (200):
```json
[
  {
    "user_id": 1,
    "username": "string",
    "role": "string",
    "last_login": "ISO-8601-datetime"
  }
]
```

#### Create User
**Endpoint**: `POST /api/admin/users`

**Authorization**: Admin only

**Request Body**:
```json
{
  "username": "string",
  "password": "string",
  "role": "admin|instructor|student|dean|ta"
}
```

**Success Response** (201):
```json
{
  "message": "User created",
  "user_id": 123
}
```

#### Delete User
**Endpoint**: `DELETE /api/admin/users/<user_id>`

**Authorization**: Admin only

**Success Response** (200):
```json
{
  "message": "User deleted"
}
```

#### Get All Courses
**Endpoint**: `GET /api/admin/courses`

**Authorization**: Admin only

**Response** (200):
```json
[
  {
    "course_id": 1,
    "name": "string",
    "code": "string",
    "semester": "string",
    "instructors": "comma-separated-usernames"
  }
]
```

#### Create Course
**Endpoint**: `POST /api/admin/courses`

**Authorization**: Admin only

**Request Body**:
```json
{
  "name": "string",
  "code": "string",
  "semester_id": 1
}
```

---

### Student APIs (`/api/student/*`)

#### Get My Courses
**Endpoint**: `GET /api/student/courses`

**Authorization**: Student only

**Response** (200):
```json
[
  {
    "course_id": 1,
    "name": "Database Systems",
    "code": "CS432",
    "semester": "Spring 2026",
    "instructors": "prof1,prof2"
  }
]
```

#### Get My Attendance
**Endpoint**: `GET /api/student/attendance`

**Authorization**: Student only

**Response** (200):
```json
[
  {
    "status": "present|absent|late",
    "session_date": "YYYY-MM-DD",
    "topic": "string",
    "course_name": "string",
    "code": "string"
  }
]
```

#### Get Course Sessions (Absent/Late only)
**Endpoint**: `GET /api/student/courses/<course_id>/sessions`

**Authorization**: Student only (must be enrolled)

**Response** (200):
```json
[
  {
    "att_session_id": 1,
    "session_date": "YYYY-MM-DD",
    "topic": "string",
    "status": "absent|late"
  }
]
```

#### Get My Correction Requests
**Endpoint**: `GET /api/student/corrections`

**Authorization**: Student only

**Response** (200):
```json
[
  {
    "correction_id": 1,
    "course_name": "string",
    "session_date": "YYYY-MM-DD",
    "topic": "string",
    "reason": "string",
    "proof_url": "string",
    "status": "pending|approved|rejected",
    "created_at": "ISO-8601-datetime"
  }
]
```

#### Submit Correction Request
**Endpoint**: `POST /api/student/corrections`

**Authorization**: Student only

**Request Body**:
```json
{
  "course_id": 1,
  "att_session_id": 1,
  "reason": "string",
  "proof_url": "string (optional)"
}
```

**Success Response** (201):
```json
{
  "message": "Correction request submitted"
}
```

**Error Responses**:
- `400`: Missing required fields
- `403`: Not enrolled in course
- `409`: Duplicate request for same session

#### Get My Profile
**Endpoint**: `GET /api/student/profile`

**Authorization**: Student only

**Response** (200):
```json
{
  "user_id": 1,
  "username": "string",
  "role": "student",
  "last_login": "ISO-8601-datetime",
  "roll_no": "string",
  "program": "string",
  "batch": "string"
}
```

---

### Instructor APIs (`/api/instructor/*`)

#### Get My Courses
**Endpoint**: `GET /api/instructor/courses`

**Authorization**: Instructor only

**Response**: List of courses taught by the instructor

#### Create Attendance Session
**Endpoint**: `POST /api/instructor/attendance`

**Authorization**: Instructor only

**Request Body**:
```json
{
  "course_id": 1,
  "session_date": "YYYY-MM-DD",
  "topic": "string"
}
```

#### Mark Attendance
**Endpoint**: `POST /api/instructor/attendance/<session_id>/mark`

**Authorization**: Instructor only

**Request Body**:
```json
{
  "student_id": 1,
  "status": "present|absent|late"
}
```

#### Get Correction Requests
**Endpoint**: `GET /api/instructor/corrections`

**Authorization**: Instructor only

**Response**: List of pending correction requests for instructor's courses

#### Process Correction Request
**Endpoint**: `PUT /api/instructor/corrections/<correction_id>`

**Authorization**: Instructor only

**Request Body**:
```json
{
  "status": "approved|rejected",
  "remarks": "string (optional)"
}
```

---

### Dean APIs (`/api/dean/*`)

Similar structure to admin but with department-specific restrictions.

---

### TA APIs (`/api/ta/*`)

Limited instructor privileges for assigned courses.

---

## Security Features

### 1. Session Validation
All protected endpoints require valid session tokens. Sessions are validated using:
- Session ID (UUID)
- MAC (HMAC-SHA256 signature)
- Expiry timestamp

### 2. Role-Based Access Control (RBAC)
Each endpoint enforces role requirements:
- **Admin**: Full system access
- **Instructor**: Course management, attendance
- **Student**: View own data, submit requests
- **Dean**: Department-level oversight
- **TA**: Limited instructor privileges

### 3. Audit Logging
All data modifications are logged to `logs/audit.log`:
```
[2026-03-19 10:30:45] LOGIN_OK | /login | user_id=5 | username=student1
[2026-03-19 10:31:12] SUBMIT_CORRECTION | /api/student/corrections | user_id=5
```

### 4. Unauthorized Access Detection
Direct database modifications bypass session validation and are flagged in audit logs.

---

## Database Optimization

### Applied Indexes
```sql
-- User lookups
CREATE INDEX idx_users_username ON users(username);

-- Session validation
CREATE INDEX idx_sessions_session_id ON sessions(session_id);
CREATE INDEX idx_sessions_expires ON sessions(expires_at);

-- Course queries
CREATE INDEX idx_courses_semester ON courses(semester_id);
CREATE INDEX idx_course_enrollments_student ON course_enrollments(student_id);
CREATE INDEX idx_course_enrollments_course ON course_enrollments(course_id);

-- Attendance queries
CREATE INDEX idx_attendance_records_student ON attendance_records(student_id);
CREATE INDEX idx_attendance_sessions_course ON attendance_sessions(course_id);

-- Correction requests
CREATE INDEX idx_corrections_student ON correction_requests(student_id);
CREATE INDEX idx_corrections_status ON correction_requests(status);
```

### Performance Benchmarking
See `benchmark.py` for before/after indexing performance metrics.

---

## Error Handling

### Standard Error Response Format
```json
{
  "error": "Error message description"
}
```

### HTTP Status Codes
- `200`: Success
- `201`: Created
- `400`: Bad Request (missing/invalid parameters)
- `401`: Unauthorized (authentication failed)
- `403`: Forbidden (insufficient permissions)
- `404`: Not Found
- `409`: Conflict (duplicate resource)
- `500`: Internal Server Error

---

## Testing the API

### Using cURL
```bash
# Login
TOKEN=$(curl -s -X POST http://localhost:5000/login \
  -H "Content-Type: application/json" \
  -d '{"user":"student1","password":"pass123"}' \
  | jq -r '.session_token')

MAC=$(curl -s -X POST http://localhost:5000/login \
  -H "Content-Type: application/json" \
  -d '{"user":"student1","password":"pass123"}' \
  | jq -r '.mac')

# Use authenticated endpoint
curl -X GET http://localhost:5000/api/student/courses \
  -H "X-Session-Id: $TOKEN" \
  -H "X-Session-Mac: $MAC"
```

### Using Python
```python
import requests

# Login
response = requests.post('http://localhost:5000/login', json={
    'user': 'student1',
    'password': 'pass123'
})
session = response.json()

# Use authenticated endpoint
headers = {
    'X-Session-Id': session['session_token'],
    'X-Session-Mac': session['mac']
}
courses = requests.get('http://localhost:5000/api/student/courses', headers=headers)
print(courses.json())
```

---

## Frontend Integration

The web UI (HTML templates) should be treated as a separate client that:
1. Calls `/login` to authenticate
2. Stores session tokens (localStorage or cookies)
3. Includes tokens in all API requests
4. Handles 401 responses by redirecting to login
5. Displays data from JSON responses

This separation ensures the API can be consumed by:
- Web browsers (current HTML UI)
- Mobile apps
- Third-party integrations
- Command-line tools

---

## Compliance with Assignment Requirements

✅ **Local Database & UI Setup**: SQLite database with web-based UI
✅ **Secure API Integration**: REST APIs with session validation
✅ **RBAC**: Strict role enforcement on all endpoints
✅ **Security Audit Logs**: All modifications logged to `logs/audit.log`
✅ **SQL Indexing**: Strategic indexes on frequently queried columns
✅ **Performance Benchmarking**: Before/after metrics in `benchmark.py`
✅ **Member Portfolio**: `/api/student/profile` and similar endpoints
✅ **Session Validation**: Every API call validates session tokens
