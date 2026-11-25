-- One student/leader account per browser device, and one student/leader account per device.
CREATE TABLE IF NOT EXISTS device_bindings (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    device_hash TEXT NOT NULL UNIQUE,
    bound_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
