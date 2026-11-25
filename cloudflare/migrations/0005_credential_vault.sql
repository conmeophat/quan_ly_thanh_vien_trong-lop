-- Encrypted password escrow for founder-only credential recovery.
-- Passwords are encrypted with AES-GCM using a key derived from the Worker secret.
CREATE TABLE IF NOT EXISTS credential_vault (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    iv TEXT NOT NULL,
    ciphertext TEXT NOT NULL,
    password_fingerprint TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
