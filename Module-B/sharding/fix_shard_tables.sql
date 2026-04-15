-- ============================================================================
-- Update Shard Table Schemas - Run this on EACH shard
-- ============================================================================
-- Shard 0: mysql -h 10.0.116.184 -P 3307 -u Scalix -p < fix_shard_0.sql
-- Shard 1: mysql -h 10.0.116.184 -P 3308 -u Scalix -p < fix_shard_1.sql
-- Shard 2: mysql -h 10.0.116.184 -P 3309 -u Scalix -p < fix_shard_2.sql
-- Password: password@123
-- ============================================================================

USE Scalix;

-- ── DROP and RECREATE shard_0_attendance_records ───────────────────────────
-- This preserves existing data while adding AUTO_INCREMENT and indexes
DROP TABLE IF EXISTS shard_0_attendance_records;

CREATE TABLE shard_0_attendance_records (
    record_id       INT          PRIMARY KEY AUTO_INCREMENT,
    att_session_id  INT          NOT NULL,
    student_id      INT          NOT NULL,
    status          VARCHAR(10)  NOT NULL,
    CONSTRAINT chk_shard_0 CHECK (student_id BETWEEN 12 AND 30),
    INDEX idx_att_session (att_session_id),
    INDEX idx_student_id (student_id),
    INDEX idx_session_student (att_session_id, student_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ── DROP and RECREATE shard_1_attendance_records ───────────────────────────
DROP TABLE IF EXISTS shard_1_attendance_records;

CREATE TABLE shard_1_attendance_records (
    record_id       INT          PRIMARY KEY AUTO_INCREMENT,
    att_session_id  INT          NOT NULL,
    student_id      INT          NOT NULL,
    status          VARCHAR(10)  NOT NULL,
    CONSTRAINT chk_shard_1 CHECK (student_id BETWEEN 31 AND 50),
    INDEX idx_att_session (att_session_id),
    INDEX idx_student_id (student_id),
    INDEX idx_session_student (att_session_id, student_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ── DROP and RECREATE shard_2_attendance_records ───────────────────────────
DROP TABLE IF EXISTS shard_2_attendance_records;

CREATE TABLE shard_2_attendance_records (
    record_id       INT          PRIMARY KEY AUTO_INCREMENT,
    att_session_id  INT          NOT NULL,
    student_id      INT          NOT NULL,
    status          VARCHAR(10)  NOT NULL,
    CONSTRAINT chk_shard_2 CHECK (student_id BETWEEN 51 AND 71),
    INDEX idx_att_session (att_session_id),
    INDEX idx_student_id (student_id),
    INDEX idx_session_student (att_session_id, student_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SELECT "✓ Shard tables recreated with AUTO_INCREMENT and indexes" AS status;
