-- Last activity timestamps used to display authenticated class accounts online.
CREATE TABLE IF NOT EXISTS online_presence (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    last_seen INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS online_presence_last_seen ON online_presence(last_seen);
