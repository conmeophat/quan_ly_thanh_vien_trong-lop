-- Persist changes to the official class roster, including students without accounts.
CREATE TABLE IF NOT EXISTS roster_assignments (
    student_key TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    group_no INTEGER NOT NULL CHECK (group_no BETWEEN 1 AND 4),
    updated_by INTEGER REFERENCES users(id),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS roster_assignments_group ON roster_assignments(group_no);
