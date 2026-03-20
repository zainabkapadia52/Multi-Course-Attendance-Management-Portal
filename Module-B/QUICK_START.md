# Quick Start Guide - Module B REST API

## 🚀 Get Started in 3 Steps

### Step 1: Setup
```bash
cd Module_B
pip install -r requirements.txt
python init_db.py
```

### Step 2: Run Server
```bash
python run.py
```
Server runs at: `http://localhost:5000`

### Step 3: Test API
```bash
# In another terminal
python test_api.py
```

## 📋 Quick API Examples

### Login
```bash
curl -X POST http://localhost:5000/login \
  -H "Content-Type: application/json" \
  -d '{"user": "student1", "password": "pass123"}'
```

### Get Student Courses (with auth)
```bash
# Save token from login response
TOKEN="your-session-token-here"
MAC="your-mac-here"

curl -X GET http://localhost:5000/api/student/courses \
  -H "X-Session-Id: $TOKEN" \
  -H "X-Session-Mac: $MAC"
```

### Check Authentication
```bash
curl -X GET http://localhost:5000/isAuth \
  -H "X-Session-Id: $TOKEN" \
  -H "X-Session-Mac: $MAC"
```

## 🔑 Sample Credentials

| Username    | Password | Role       |
|-------------|----------|------------|
| admin       | admin123 | admin      |
| student1    | pass123  | student    |
| instructor1 | pass123  | instructor |

## 📚 Key Endpoints

### Authentication
- `POST /login` - Get session token
- `GET /isAuth` - Verify session
- `POST /logout` - End session

### Student APIs
- `GET /api/student/courses` - My courses
- `GET /api/student/attendance` - My attendance
- `GET /api/student/profile` - My profile
- `POST /api/student/corrections` - Submit correction request

### Admin APIs
- `GET /api/admin/users` - All users
- `POST /api/admin/users` - Create user
- `GET /api/admin/courses` - All courses
- `POST /api/admin/courses` - Create course

### Instructor APIs
- `GET /api/instructor/courses` - My courses
- `POST /api/instructor/attendance` - Create attendance session
- `GET /api/instructor/corrections` - Pending corrections

## 🔒 Security Features

✅ Session-based authentication  
✅ HMAC signature validation  
✅ Role-based access control  
✅ Audit logging (logs/audit.log)  
✅ Password hashing  

## 📊 Performance Optimization

✅ Strategic database indexes  
✅ Query optimization  
✅ Benchmarking script included  

Run benchmarks:
```bash
python benchmark.py
```

## 🧪 Testing

### Automated Tests
```bash
python test_api.py
```

### Manual Testing
1. Login via API
2. Save session_token and mac
3. Use tokens in subsequent requests
4. Check audit.log for logged operations

## 📖 Full Documentation

- [API_DOCUMENTATION.md](./API_DOCUMENTATION.md) - Complete API reference
- [README.md](./README.md) - Detailed architecture and setup

## ✅ Assignment Requirements Met

✅ Local Database & UI Setup  
✅ Secure API Integration  
✅ RBAC Implementation  
✅ Security Audit Logs  
✅ SQL Indexing  
✅ Performance Benchmarking  

## 🎯 Key Difference: API-First Architecture

### Before (Centralized)
```
Browser → Server (renders HTML with data) → Browser displays
```

### After (API-First)
```
Browser → API (returns JSON) → JavaScript displays data
Mobile App → API (returns JSON) → App displays data
CLI Tool → API (returns JSON) → Terminal displays data
```

The API can now be consumed by:
- Web browsers (current HTML UI)
- Mobile applications
- Command-line tools
- Third-party integrations

## 🐛 Troubleshooting

**"Connection refused"**
- Start server: `python run.py`

**"401 Unauthorized"**
- Include session tokens in headers
- Re-login if session expired

**"403 Forbidden"**
- Check user role matches endpoint
- Student cannot access admin endpoints

## 💡 Pro Tips

1. Use `jq` for pretty JSON output:
   ```bash
   curl ... | jq
   ```

2. Save tokens to variables:
   ```bash
   TOKEN=$(curl -s ... | jq -r '.session_token')
   ```

3. Check audit log in real-time:
   ```bash
   tail -f logs/audit.log
   ```

4. Use Postman/Insomnia for GUI testing

---

Need help? Check the full documentation or run `python test_api.py` to see working examples!
