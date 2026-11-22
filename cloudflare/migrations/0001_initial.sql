-- Class Merit Hub schema for Cloudflare D1.
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT NOT NULL, phone TEXT NOT NULL UNIQUE,
 password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('founder','teacher','leader','member')),
 group_no INTEGER, is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
 registration_status TEXT NOT NULL DEFAULT 'approved' CHECK(registration_status IN ('pending','approved','rejected')),
 session_version INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CHECK ((role IN ('leader','member') AND group_no BETWEEN 1 AND 4) OR (role IN ('founder','teacher') AND group_no IS NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS one_founder ON users(role) WHERE role='founder';
CREATE UNIQUE INDEX IF NOT EXISTS one_active_teacher ON users(role) WHERE role='teacher' AND is_active=1;
CREATE UNIQUE INDEX IF NOT EXISTS one_active_leader_per_group ON users(group_no) WHERE role='leader' AND is_active=1;
CREATE INDEX IF NOT EXISTS users_group_role_status ON users(group_no,role,registration_status,is_active);
CREATE TABLE IF NOT EXISTS score_entries (
 id INTEGER PRIMARY KEY AUTOINCREMENT, member_id INTEGER NOT NULL REFERENCES users(id),
 points REAL NOT NULL CHECK(points<>0 AND points BETWEEN -100 AND 100), category TEXT NOT NULL,
 note TEXT NOT NULL, created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT, is_deleted INTEGER NOT NULL DEFAULT 0 CHECK(is_deleted IN (0,1)),
 deleted_by INTEGER REFERENCES users(id), deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS scores_member_time ON score_entries(member_id,is_deleted,created_at DESC);
CREATE TABLE IF NOT EXISTS evaluations (
 id INTEGER PRIMARY KEY AUTOINCREMENT, member_id INTEGER NOT NULL REFERENCES users(id),
 content TEXT NOT NULL, evaluator_id INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT, is_deleted INTEGER NOT NULL DEFAULT 0 CHECK(is_deleted IN (0,1)),
 deleted_by INTEGER REFERENCES users(id), deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS evaluations_member_time ON evaluations(member_id,is_deleted,created_at DESC);
CREATE TABLE IF NOT EXISTS login_throttle (
 username_key TEXT PRIMARY KEY, failed_count INTEGER NOT NULL DEFAULT 0,
 locked_until INTEGER NOT NULL DEFAULT 0, updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_logs (
 id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id INTEGER REFERENCES users(id),
 action TEXT NOT NULL, target_user_id INTEGER REFERENCES users(id),
 details TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS audit_logs_time ON audit_logs(created_at DESC);
