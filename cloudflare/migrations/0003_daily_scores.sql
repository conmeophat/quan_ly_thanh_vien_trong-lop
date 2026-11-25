-- Store one editable score per member for each calendar day.
CREATE TABLE IF NOT EXISTS daily_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL REFERENCES users(id),
    score_date TEXT NOT NULL,
    points REAL NOT NULL CHECK (points BETWEEN -100 AND 100),
    created_by INTEGER NOT NULL REFERENCES users(id),
    updated_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (member_id, score_date)
);
CREATE INDEX IF NOT EXISTS daily_scores_date_member ON daily_scores(score_date, member_id);
