-- ============================================================================
-- FIX: Add Missing Sessions Table
-- ============================================================================
-- This script adds the 'sessions' table that was missing from the database
-- The sessions table is used for user session management in the Flask app

PRAGMA foreign_keys = ON;

-- Create the missing sessions table
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT    PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    mac        TEXT    NOT NULL,
    created_at TEXT    DEFAULT (datetime('now')),
    expires_at TEXT    NOT NULL
);

-- Create an index for faster session lookups by user_id
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);

-- Verify the table was created
.print
.print "Sessions table created successfully!"
.print "Table structure:"
.schema sessions
.print
