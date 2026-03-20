# Module B: Local API Development, RBAC, and Database Optimization

## Overview

This module implements a **REST API-first architecture** for a Course Management System with:
- ✅ Secure session-based authentication
- ✅ Role-Based Access Control (RBAC)
- ✅ Comprehensive audit logging
- ✅ SQL indexing for performance optimization
- ✅ Pure JSON API responses (no server-side rendering for API endpoints)

## Architecture

### API-First Design

The application follows a **separation of concerns** approach:

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend (UI)                         │
│  - HTML templates (login.html, dashboards)                  │
│  - JavaScript for API calls                                 │
│  - Displays data from JSON responses                        │
└─────────────────────────────────────────────────────────────┘
                              ↓ HTTP/JSON
┌─────────────────────────────────────────────────────────────┐
│                     REST API Layer                           │
│  - /login, /isAuth (authentication)                         │
│  - /api/admin/* (admin operations)                          │
│  - /api/student/* (student operations)                      │
│  - /api/instructor/* (instructor operations)                │
│  - All endpoints return JSON                                │
│  - Session validation on every request                      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                   Business Logic Layer                       │
│  - auth.py (session management)                             │
│  - middleware.py (RBAC enforcement)                         │
│  - logger.py (audit logging)                                │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Database Layer (SQLite)                   │
│  - Optimized with strategic indexes                         │
│  - Tables: users, sessions, courses, attendance, etc.       │
└─────────────────────────────────────────────────────────────┘
```

### Key Features

1. **Pure REST APIs**: All data operations return JSON (not HTML)
2. **Session-Based Auth**: Secure token + MAC validation
3. **RBAC**: Role enforcement at middleware level
4. **Audit Logging**: All modifications logged to `logs/audit.log`
5. **Database Optimization**: Strategic indexes for query performance

## Project Structure

```
Module_B/
├── app/
│   ├── __init__.py              # Flask app factory
│   ├── auth.py                  # Authentication logic
│   ├── db.py                    # Database connection
│   ├── middleware.py            # RBAC middleware
│   ├── logger.py                # Audit logging
│   ├── events.py                # Event broadcasting
│   ├── routes/
│   │   ├── auth_routes.py       # /login, /isAuth, /logout
│   │   ├── admin.py             # /api/admin/*
│   │   ├── student.py           # /api/student/*
│   │   ├── instructor.py        # /api/instructor/*
│   │   ├── dean.py              # /api/dean/*
│   │   ├── ta.py                # /api/ta/*
│   │   ├── page_routes.py       # HTML page rendering (UI)
│   │   └── stream.py            # Server-sent events
│   └── templates/               # HTML templates (frontend)
├── sql/
│   ├── schema.sql               # Database schema with indexes
│   └── seed.sql                 # Sample data
├── logs/
│   └── audit.log                # Security audit log
├── init_db.py                   # Database initialization
├── run.py                       # Application entry point
├── test_api.py                  # API testing script
├── benchmark.py                 # Performance benchmarking
├── API_DOCUMENTATION.md         # Complete API reference
├── README.md                    # This file
└── requirements.txt             # Python dependencies
```

## Installation & Setup

### 1. Install Dependencies

```bash
cd Module_B
pip install -r requirements.txt
```

### 2. Initialize Database

```bash
python init_db.py
```

This creates:
- Database schema with optimized indexes
- Sample users (admin, instructors, students, dean, TAs)
- Sample courses and enrollments
- Sample attendance records

### 3. Run the Application

```bash
python run.py
```

Server starts at: `http://localhost:5000`

## API Usage

### Authentication Flow

#### 1. Login (Get Session Token)

```bash
curl -X POST http://localhost:5000/login \
  -H "Content-Type: application/json" \
  -d '{"user": "student1", "password": "pass123"}'
```

Response:
```json
{
  "message": "Login successful",
  "session_token": "abc-123-def-456",
  "mac": "hmac-signature-here",
  "role": "student",
  "username": "student1"
}
```

#### 2. Use Authenticated Endpoints

Include session tokens in headers:

```bash
curl -X GET http://localhost:5000/api/student/courses \
  -H "X-Session-Id: abc-123-def-456" \
  -H "X-Session-Mac: hmac-signature-here"
```

Response:
```json
[
  {
    "course_id": 1,
    "name": "Database Systems",
    "code": "CS432",
    "semester": "Spring 2026",
    "instructors": "instructor1"
  }
]
```

### Testing the API

Run the automated test script:

```bash
python test_api.py
```

This demonstrates:
- ✅ Login and session management
- ✅ Student APIs (courses, attendance, profile)
- ✅ Admin APIs (user management, course management)
- ✅ Instructor APIs (attendance, corrections)
- ✅ RBAC enforcement (403 for unauthorized access)
- ✅ Session validation (401 for invalid tokens)

## Role-Based Access Control (RBAC)

### Roles and Permissions

| Role       | Permissions                                          |
|------------|------------------------------------------------------|
| Admin      | Full system access, user management, course creation |
| Instructor | Course management, attendance, correction approval   |
| Student    | View own data, submit correction requests            |
| Dean       | Department-level oversight                           |
| TA         | Limited instructor privileges for assigned courses   |

### RBAC Implementation

```python
# In middleware.py
@require_role("student")
def my_courses():
    # Only students can access this endpoint
    pass

@require_role("admin")
def create_user():
    # Only admins can access this endpoint
    pass
```

### Testing RBAC

```bash
# Login as student
TOKEN=$(curl -s -X POST http://localhost:5000/login \
  -H "Content-Type: application/json" \
  -d '{"user":"student1","password":"pass123"}' | jq -r '.session_token')

# Try to access admin endpoint (should fail with 403)
curl -X GET http://localhost:5000/api/admin/users \
  -H "X-Session-Id: $TOKEN"
```

## Security Features

### 1. Session Management

- **Session ID**: UUID v4 (cryptographically random)
- **MAC**: HMAC-SHA256 signature for integrity
- **Expiry**: Configurable timeout (default: 2 hours)
- **Validation**: Every API call validates session

### 2. Audit Logging

All data modifications are logged to `logs/audit.log`:

```
[2026-03-19 10:30:45] LOGIN_OK | /login | user_id=5 | username=student1
[2026-03-19 10:31:12] SUBMIT_CORRECTION | /api/student/corrections | user_id=5
[2026-03-19 10:32:00] APPROVE_CORRECTION | /api/instructor/corrections/1 | user_id=2
```

### 3. Unauthorized Access Detection

Direct database modifications (bypassing APIs) are detectable:
- API calls are logged with user_id
- Direct DB changes have no corresponding log entry
- Audit review can identify unauthorized modifications

### 4. Password Security

- Passwords hashed with `werkzeug.security.generate_password_hash`
- Uses PBKDF2-SHA256 with salt
- Never stored in plaintext

## Database Optimization

### Applied Indexes

```sql
-- User authentication (speeds up login)
CREATE INDEX idx_users_username ON users(username);

-- Session validation (speeds up every API call)
CREATE INDEX idx_sessions_session_id ON sessions(session_id);
CREATE INDEX idx_sessions_expires ON sessions(expires_at);

-- Course queries (speeds up enrollment lookups)
CREATE INDEX idx_courses_semester ON courses(semester_id);
CREATE INDEX idx_course_enrollments_student ON course_enrollments(student_id);
CREATE INDEX idx_course_enrollments_course ON course_enrollments(course_id);

-- Attendance queries (speeds up student attendance history)
CREATE INDEX idx_attendance_records_student ON attendance_records(student_id);
CREATE INDEX idx_attendance_sessions_course ON attendance_sessions(course_id);

-- Correction requests (speeds up filtering by status)
CREATE INDEX idx_corrections_student ON correction_requests(student_id);
CREATE INDEX idx_corrections_status ON correction_requests(status);
```

### Performance Benchmarking

Run benchmarks to measure index impact:

```bash
python benchmark.py
```

Results saved to `benchmark_results.txt` showing:
- Query execution time before indexing
- Query execution time after indexing
- Speedup percentage
- EXPLAIN plan analysis

## API Documentation

See [API_DOCUMENTATION.md](./API_DOCUMENTATION.md) for complete API reference including:
- All endpoints with request/response formats
- Authentication flow
- Error handling
- Example requests (cURL, Python)
- RBAC rules per endpoint

## Sample Users

| Username    | Password | Role       |
|-------------|----------|------------|
| admin       | admin123 | admin      |
| instructor1 | pass123  | instructor |
| instructor2 | pass123  | instructor |
| student1    | pass123  | student    |
| student2    | pass123  | student    |
| student3    | pass123  | student    |
| dean1       | pass123  | dean       |
| ta1         | pass123  | ta         |

## Web UI (Frontend)

The web UI is a **separate client** that consumes the REST APIs:

1. **Login Page** (`/login`): Calls `/login` API
2. **Dashboards**: Call role-specific APIs to fetch data
3. **Forms**: Submit data via POST/PUT APIs
4. **JavaScript**: Handles API calls and displays JSON responses

### Accessing the UI

1. Start the server: `python run.py`
2. Open browser: `http://localhost:5000`
3. Login with sample credentials
4. Dashboard loads data via API calls

## Assignment Compliance

### ✅ SubTask 1: Local Environment Setup & Data Management
- SQLite database with project-specific tables
- Core system tables (users, sessions, courses)
- Proper data integrity (foreign keys, constraints)

### ✅ SubTask 2: API and UI Development
- REST APIs for CRUD operations
- Session validation on every API call
- Member portfolio feature (`/api/student/profile`)

### ✅ SubTask 3: Role-Based Access Control (RBAC)
- Admin: Full access
- Regular Users: Restricted access
- Middleware enforcement (`@require_role` decorator)
- Audit logging for all modifications

### ✅ SubTask 4: SQL Indexing and Query Optimization
- Strategic indexes on frequently queried columns
- Targets WHERE, JOIN, ORDER BY clauses
- Documented in `sql/schema.sql`

### ✅ SubTask 5: Performance Benchmarking
- Before/after indexing metrics
- EXPLAIN plan analysis
- Results in `benchmark.py`

### ✅ SubTask 6: Video Demonstration
- Record screen capture showing:
  - UI navigation and CRUD operations
  - Admin vs Regular User access
  - Audit log capturing operations
- Include audio explanation

## Key Differences from Centralized App

### Before (Centralized):
- Server renders HTML with data embedded
- Session managed via cookies only
- Tight coupling between UI and backend

### After (API-First):
- Server returns JSON data only
- Session tokens in headers or cookies
- Loose coupling: UI is just another API client
- Can be consumed by mobile apps, CLI tools, etc.

## Testing Checklist

- [ ] Login with different roles
- [ ] Verify session validation works
- [ ] Test RBAC (student cannot access admin endpoints)
- [ ] Submit data via API (e.g., correction request)
- [ ] Check audit log for recorded operations
- [ ] Try invalid session token (should get 401)
- [ ] Try accessing endpoint without auth (should get 401)
- [ ] Run `test_api.py` successfully
- [ ] Run `benchmark.py` to verify indexes

## Troubleshooting

### "Connection refused" error
- Make sure Flask app is running: `python run.py`
- Check port 5000 is not in use

### "401 Unauthorized" on API calls
- Verify session token is included in headers
- Check token hasn't expired (2 hour default)
- Re-login to get fresh token

### "403 Forbidden" on API calls
- Check user role matches endpoint requirements
- Admin endpoints require admin role
- Student endpoints require student role

## Future Enhancements

- [ ] JWT tokens instead of session table
- [ ] OAuth2 integration
- [ ] Rate limiting
- [ ] API versioning (/api/v1/*)
- [ ] GraphQL endpoint
- [ ] WebSocket for real-time updates
- [ ] API key authentication for third-party apps

## References

- Flask Documentation: https://flask.palletsprojects.com/
- REST API Best Practices: https://restfulapi.net/
- SQLite Indexing: https://www.sqlite.org/queryplanner.html
- OWASP Security: https://owasp.org/www-project-api-security/

---

**Assignment**: CS 432 - Databases (Course Project/Assignment 2)  
**Module**: B - Local API Development, RBAC, and Database Optimization  
**Deadline**: 6:00 PM, 22 March 2026
