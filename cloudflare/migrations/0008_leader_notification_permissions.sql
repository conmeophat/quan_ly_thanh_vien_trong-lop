-- Leaders must grant browser notification permission on their bound device before accessing the app.
CREATE TABLE IF NOT EXISTS leader_notification_permissions (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    device_hash TEXT NOT NULL UNIQUE,
    granted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
