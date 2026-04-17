# Sharding Implementation Summary

## Overview
The database now shards **2 tables** across 3 MySQL servers using **modulo 3 partitioning** on `student_id`.

---

## Sharded Tables

### 1. **attendance_records** ✅
- **Volume**: ~2,370 records initially, grows to millions
- **Schema**:
  ```sql
  shard_{0,1,2}_attendance_records (
      record_id      INT AUTO_INCREMENT PRIMARY KEY,
      att_session_id INT NOT NULL,
      student_id     INT NOT NULL,
      status         ENUM('present', 'absent', 'late'),
      INDEX idx_student (student_id),
      INDEX idx_session (att_session_id)
  )
  ```

### 2. **correction_requests** ✅ NEW
- **Volume**: ~40 requests initially, can grow to hundreds of thousands
- **Schema**:
  ```sql
  shard_{0,1,2}_correction_requests (
      req_id         INT AUTO_INCREMENT PRIMARY KEY,
      student_id     INT NOT NULL,
      course_id      INT NOT NULL,
      att_session_id INT NOT NULL,
      reason         TEXT NOT NULL,
      proof_url      TEXT,
      status         ENUM('pending', 'accepted', 'rejected'),
      created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
      INDEX idx_student (student_id),
      INDEX idx_session (att_session_id),
      INDEX idx_status (status),
      UNIQUE KEY unique_student_session (student_id, att_session_id)
  )
  ```

---

## Shard Configuration

```python
SHARD_CONFIGS = {
    0: {"host": "10.0.116.184", "port": 3307, "database": "Scalix"},
    1: {"host": "10.0.116.184", "port": 3308, "database": "Scalix"},
    2: {"host": "10.0.116.184", "port": 3309, "database": "Scalix"},
}
```

**Partitioning Logic**:
```python
def get_shard_id(student_id: int) -> int:
    return student_id % 3
```

**Distribution**:
- Shard 0: student_id % 3 == 0 (students 3, 6, 9, 12, 15, 18, 21...)
- Shard 1: student_id % 3 == 1 (students 1, 4, 7, 10, 13, 16, 19...)
- Shard 2: student_id % 3 == 2 (students 2, 5, 8, 11, 14, 17, 20...)

---

## Migration Process (init_db.py)

### Phase 1: SQLite Setup
1. Create SQLite database with all tables
2. Populate users, courses, sessions, enrollments
3. Generate ~2,370 attendance records
4. Generate ~40 correction requests

### Phase 2: MySQL Shards Migration
1. **Read** attendance_records and correction_requests from SQLite
2. **Partition** by student_id % 3 into 3 groups
3. **Connect** to MySQL shards and drop old tables
4. **Create** fresh tables with proper schema
5. **Bulk insert** records into each shard
6. **Delete** migrated data from SQLite (cleanup)

### Expected Output:
```
✓  Found 2370 attendance records
✓  Found 40 correction requests

Attendance records per shard:
  Shard 0 (student_id % 3 == 0): 790 records
  Shard 1 (student_id % 3 == 1): 790 records
  Shard 2 (student_id % 3 == 2): 790 records

Correction requests per shard:
  Shard 0 (student_id % 3 == 0): 13 requests
  Shard 1 (student_id % 3 == 1): 14 requests
  Shard 2 (student_id % 3 == 2): 13 requests

Bulk inserting records...
  ✓  Shard 0: 790 attendance records inserted
  ✓  Shard 0: 13 correction requests inserted
  ✓  Shard 1: 790 attendance records inserted
  ✓  Shard 1: 14 correction requests inserted
  ✓  Shard 2: 790 attendance records inserted
  ✓  Shard 2: 13 correction requests inserted

✓  Total migrated to MySQL shards:
   - Attendance records: 2370
   - Correction requests: 40

Cleaning up SQLite...
✓  Deleted attendance_records from SQLite (remaining: 0)
✓  Deleted correction_requests from SQLite (remaining: 0)
```

---

## Data Architecture

### SQLite (module_b.db) - Metadata
- users, user_profiles
- courses, course_instructors, course_tas, course_enrollments
- semesters, attendance_sessions
- correction_logs (references req_id from shards)
- sessions, raw_changes

### MySQL Shards - High-Volume Transactional Data
- shard_0_attendance_records, shard_0_correction_requests
- shard_1_attendance_records, shard_1_correction_requests
- shard_2_attendance_records, shard_2_correction_requests

---

## Query Patterns

### Fast (Single Shard) ✓
- Student dashboard: "Get MY attendance" → Query shard for student_id
- Student corrections: "Get MY correction requests" → Query shard for student_id
- Update attendance for student X → Route to correct shard
- Create correction request for student X → Route to correct shard

### Parallelizable (Cross-Shard) ✓
- Session attendance: "Who attended session Y" → Query all 3 shards in parallel
- Course corrections: "Pending requests for course Z" → Query all 3 shards in parallel
- Instructor dashboard: "All pending requests for my courses" → Query all 3 shards in parallel

---

## Benefits

1. **Scalability**: Can handle millions of records per table
2. **Performance**: Student queries hit single shard (fast)
3. **Co-location**: Related data (attendance + corrections) on same shard
4. **Load Distribution**: Each shard handles ~1/3 of traffic
5. **Uniform Distribution**: Modulo ensures even data spread
6. **Data Cleanup**: SQLite only stores metadata, shards store transactional data

---

## Running the Migration

```bash
cd Module-B
python init_db.py
```

This will:
1. Create fresh SQLite database
2. Populate with test data
3. Migrate attendance_records and correction_requests to MySQL shards
4. Delete migrated data from SQLite
5. Display summary statistics

---

## Verification

### Check SQLite (should be 0):
```bash
sqlite3 module_b.db "SELECT COUNT(*) FROM attendance_records"
sqlite3 module_b.db "SELECT COUNT(*) FROM correction_requests"
```

### Check MySQL Shards:
```bash
# Shard 0
mysql -h 10.0.116.184 -P 3307 -u Scalix -p -e \
  "SELECT COUNT(*) FROM Scalix.shard_0_attendance_records"
mysql -h 10.0.116.184 -P 3307 -u Scalix -p -e \
  "SELECT COUNT(*) FROM Scalix.shard_0_correction_requests"

# Shard 1
mysql -h 10.0.116.184 -P 3308 -u Scalix -p -e \
  "SELECT COUNT(*) FROM Scalix.shard_1_attendance_records"
mysql -h 10.0.116.184 -P 3308 -u Scalix -p -e \
  "SELECT COUNT(*) FROM Scalix.shard_1_correction_requests"

# Shard 2
mysql -h 10.0.116.184 -P 3309 -u Scalix -p -e \
  "SELECT COUNT(*) FROM Scalix.shard_2_attendance_records"
mysql -h 10.0.116.184 -P 3309 -u Scalix -p -e \
  "SELECT COUNT(*) FROM Scalix.shard_2_correction_requests"
```

---

## Future Considerations

### Phase 3 (Optional):
- Shard `correction_logs` if it grows large
- Consider sharding `course_enrollments` if it becomes a bottleneck
- Move `raw_changes` to separate audit database

### Production Enhancements:
- Add replication for each shard (high availability)
- Implement connection pooling
- Add caching layer (Redis)
- Monitor shard health and data distribution
- Implement backup strategy per shard
