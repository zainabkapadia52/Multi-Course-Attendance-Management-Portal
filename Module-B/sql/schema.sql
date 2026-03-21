PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    user_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    username   TEXT    UNIQUE NOT NULL,
    pwd_hash   TEXT    NOT NULL,
    role       TEXT    CHECK(role IN ('admin','instructor','student','ta','dean')) NOT NULL,
    last_login TEXT
);

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id     INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    roll_no     TEXT,
    program     TEXT,
    batch       TEXT,
    department  TEXT,
    designation TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT    PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    mac        TEXT    NOT NULL,
    created_at TEXT    DEFAULT (datetime('now')),
    expires_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS semesters (
    semester_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    start_date  TEXT,
    end_date    TEXT,
    is_active   INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS courses (
    course_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    code        TEXT    NOT NULL,
    semester_id INTEGER REFERENCES semesters(semester_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS course_instructors (
    course_id     INTEGER REFERENCES courses(course_id) ON DELETE CASCADE,
    instructor_id INTEGER REFERENCES users(user_id)     ON DELETE CASCADE,
    PRIMARY KEY (course_id, instructor_id)
);

CREATE TABLE IF NOT EXISTS course_tas (
    course_id INTEGER REFERENCES courses(course_id) ON DELETE CASCADE,
    ta_id     INTEGER REFERENCES users(user_id)     ON DELETE CASCADE,
    PRIMARY KEY (course_id, ta_id)
);

CREATE TABLE IF NOT EXISTS course_enrollments (
    course_id  INTEGER REFERENCES courses(course_id) ON DELETE CASCADE,
    student_id INTEGER REFERENCES users(user_id)     ON DELETE CASCADE,
    PRIMARY KEY (course_id, student_id)
);

CREATE TABLE IF NOT EXISTS attendance_sessions (
    att_session_id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id      INTEGER NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
    session_date   TEXT    NOT NULL,
    topic          TEXT,
    created_by     INTEGER REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS attendance_records (
    record_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    att_session_id INTEGER NOT NULL REFERENCES attendance_sessions(att_session_id) ON DELETE CASCADE,
    student_id     INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    status         TEXT    CHECK(status IN ('present','absent','late')) NOT NULL DEFAULT 'absent'
);

CREATE TABLE IF NOT EXISTS correction_requests (
    req_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id     INTEGER NOT NULL REFERENCES users(user_id)                       ON DELETE CASCADE,
    course_id      INTEGER NOT NULL REFERENCES courses(course_id)                   ON DELETE CASCADE,
    att_session_id INTEGER NOT NULL REFERENCES attendance_sessions(att_session_id)  ON DELETE CASCADE,
    reason         TEXT    NOT NULL,
    proof_url      TEXT,
    status         TEXT    CHECK(status IN ('pending','accepted','rejected')) DEFAULT 'pending',
    created_at     TEXT    DEFAULT (datetime('now')),
    UNIQUE (student_id, att_session_id)
);

CREATE TABLE IF NOT EXISTS correction_logs (
    log_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    req_id   INTEGER NOT NULL REFERENCES correction_requests(req_id) ON DELETE CASCADE,
    action   TEXT    NOT NULL CHECK(action IN ('accepted','rejected')),
    acted_by INTEGER NOT NULL REFERENCES users(user_id),
    role     TEXT    NOT NULL,
    acted_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS raw_changes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name  TEXT NOT NULL,
    record_id   INTEGER NOT NULL,
    old_value   TEXT,
    new_value   TEXT,
    changed_at  DATETIME DEFAULT (datetime('now'))
);
