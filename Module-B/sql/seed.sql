-- Passwords are all "password123" hashed with werkzeug
INSERT OR IGNORE INTO users (username, pwd_hash, role) VALUES
  ('admin',      'scrypt:32768:8:1$salt$hash_placeholder', 'admin'),
  ('prof_singh', 'scrypt:32768:8:1$salt$hash_placeholder', 'instructor'),
  ('prof_rao',   'scrypt:32768:8:1$salt$hash_placeholder', 'instructor'),
  ('student_a',  'scrypt:32768:8:1$salt$hash_placeholder', 'student'),
  ('student_b',  'scrypt:32768:8:1$salt$hash_placeholder', 'student'),
  ('student_c',  'scrypt:32768:8:1$salt$hash_placeholder', 'student');

-- NOTE: Run init_db.py instead — it hashes passwords properly