"""SQLite persistence and server-side authorization for class merit tracking."""

from __future__ import annotations

import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

from security import hash_password, verify_password

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "class_tracker.sqlite3")))
GROUPS = (1, 2, 3, 4)
ROLES = ("founder", "teacher", "leader", "member")
ROLE_LABELS = {
    "founder": "Người sáng lập",
    "teacher": "Giáo viên chủ nhiệm",
    "leader": "Tổ trưởng",
    "member": "Thành viên",
}


class PermissionDenied(Exception):
    pass


class ValidationError(Exception):
    pass


@contextmanager
def connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with connection() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_code TEXT NOT NULL COLLATE NOCASE UNIQUE,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                phone TEXT COLLATE NOCASE,
                full_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('founder','teacher','leader','member')),
                group_no INTEGER,
                is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
                session_version INTEGER NOT NULL DEFAULT 0 CHECK(session_version >= 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CHECK (
                    (role IN ('leader','member') AND group_no BETWEEN 1 AND 4)
                    OR (role IN ('founder','teacher') AND group_no IS NULL)
                )
            );
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_leader_per_group
                ON users(group_no) WHERE role='leader' AND is_active=1;
            CREATE UNIQUE INDEX IF NOT EXISTS one_founder
                ON users(role) WHERE role='founder';
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_teacher
                ON users(role) WHERE role='teacher' AND is_active=1;

            CREATE TABLE IF NOT EXISTS scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_id INTEGER NOT NULL REFERENCES users(id),
                points REAL NOT NULL CHECK(points >= -100 AND points <= 100),
                category TEXT NOT NULL,
                note TEXT NOT NULL,
                created_by INTEGER NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT,
                is_deleted INTEGER NOT NULL DEFAULT 0 CHECK(is_deleted IN (0,1)),
                deleted_by INTEGER REFERENCES users(id),
                deleted_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_scores_member_time ON scores(member_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_id INTEGER NOT NULL REFERENCES users(id),
                content TEXT NOT NULL,
                evaluator_id INTEGER NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT,
                is_deleted INTEGER NOT NULL DEFAULT 0 CHECK(is_deleted IN (0,1)),
                deleted_by INTEGER REFERENCES users(id),
                deleted_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_evaluations_member_time ON evaluations(member_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS login_throttle (
                username_key TEXT PRIMARY KEY COLLATE NOCASE,
                failed_count INTEGER NOT NULL DEFAULT 0,
                locked_until REAL NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_id INTEGER REFERENCES users(id),
                action TEXT NOT NULL,
                target_user_id INTEGER REFERENCES users(id),
                details TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_logs(created_at DESC);
            """
        )
        user_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "session_version" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0")
        if "phone" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN phone TEXT COLLATE NOCASE")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone_unique "
            "ON users(phone) WHERE phone IS NOT NULL"
        )


def _user_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    hidden_fields = {"password_hash", "username", "person_code"}
    return {key: row[key] for key in row.keys() if key not in hidden_fields}


def _get_user_by_id(conn: sqlite3.Connection, user_id: int) -> dict[str, Any] | None:
    return _user_dict(conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    with connection() as conn:
        return _get_user_by_id(conn, user_id)


def founder_exists() -> bool:
    with connection() as conn:
        return conn.execute("SELECT 1 FROM users WHERE role='founder' LIMIT 1").fetchone() is not None


def _audit(conn: sqlite3.Connection, actor_id: int | None, action: str,
           target_user_id: int | None = None, details: str = "") -> None:
    conn.execute(
        "INSERT INTO audit_logs(actor_id, action, target_user_id, details) VALUES(?,?,?,?)",
        (actor_id, action, target_user_id, details[:1000]),
    )


def _legacy_identity_values() -> tuple[str, str]:
    """Fill legacy NOT NULL columns for databases created by older releases."""
    return secrets.token_hex(16), secrets.token_hex(16)


def _legacy_identity_values() -> tuple[str, str]:
    """Fill legacy NOT NULL columns for databases created by older releases."""
    return secrets.token_hex(16), secrets.token_hex(16)


def create_founder(full_name: str, phone: str, password: str, *,
                   local_setup_allowed: bool = False) -> int:
    if not local_setup_allowed:
        raise PermissionDenied("Tài khoản người sáng lập đầu tiên chỉ được tạo từ kết nối cục bộ.")
    if founder_exists():
        raise ValidationError("Tài khoản người sáng lập đã được khởi tạo.")
    full_name, phone = _validate_identity(full_name, phone)
    password_hash = hash_password(password)
    legacy_person_code, legacy_username = _legacy_identity_values()
    with connection() as conn:
        if conn.execute("SELECT 1 FROM users WHERE role='founder'").fetchone():
            raise ValidationError("Tài khoản người sáng lập đã được tạo bởi một phiên khác.")
        cursor = conn.execute(
            "INSERT INTO users(person_code, username, phone, full_name, password_hash, role, group_no) "
            "VALUES(?,?,?,?,?, 'founder', NULL)",
            (legacy_person_code, legacy_username, phone, full_name, password_hash),
        )
        user_id = int(cursor.lastrowid)
        _audit(conn, user_id, "founder_bootstrap", user_id, "Khởi tạo tài khoản người sáng lập")
        return user_id


def _validate_identity(full_name: str, phone: str) -> tuple[str, str]:
    full_name = (full_name or "").strip()
    phone = (phone or "").strip()
    phone = re.sub(r"[\s().-]", "", phone)
    digits = phone[1:] if phone.startswith("+") else phone
    if not 2 <= len(full_name) <= 100:
        raise ValidationError("Họ và tên phải có từ 2 đến 100 ký tự.")
    if not digits.isdigit() or not 9 <= len(digits) <= 15:
        raise ValidationError("Số điện thoại phải có từ 9 đến 15 chữ số; dấu + chỉ được đặt ở đầu.")
    return full_name, phone


def authenticate(phone: str, password: str) -> tuple[dict[str, Any] | None, str]:
    """Authenticate by phone number, retaining temporary login for legacy accounts."""
    login_value = (phone or "").strip()
    normalized_phone = re.sub(r"[\s().-]", "", login_value)
    key = normalized_phone.casefold()[:100] or "<empty>"
    now = time.time()
    with connection() as conn:
        throttle = conn.execute(
            "SELECT failed_count, locked_until FROM login_throttle WHERE username_key=?", (key,)
        ).fetchone()
        if throttle and float(throttle["locked_until"]) > now:
            remain = max(1, int((float(throttle["locked_until"]) - now + 59) // 60))
            return None, f"Tài khoản đang tạm khóa do đăng nhập sai nhiều lần. Thử lại sau khoảng {remain} phút."

        row = conn.execute(
            "SELECT * FROM users WHERE (phone=? COLLATE NOCASE OR "
            "(phone IS NULL AND username=? COLLATE NOCASE)) AND is_active=1 LIMIT 1",
            (normalized_phone, login_value),
        ).fetchone()
        valid = bool(row and verify_password(row["password_hash"], password or ""))
        if valid:
            conn.execute("DELETE FROM login_throttle WHERE username_key=?", (key,))
            return _user_dict(row), ""

        count = (int(throttle["failed_count"]) if throttle else 0) + 1
        locked_until = now + 15 * 60 if count >= 5 else 0
        conn.execute(
            "INSERT INTO login_throttle(username_key, failed_count, locked_until, updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(username_key) DO UPDATE SET failed_count=excluded.failed_count, "
            "locked_until=excluded.locked_until, updated_at=excluded.updated_at",
            (key, min(count, 5), locked_until, now),
        )
        if locked_until:
            return None, "Tài khoản đang tạm khóa 15 phút do đăng nhập sai nhiều lần."
        return None, "Số điện thoại hoặc mật khẩu không chính xác."


def _refresh_actor(actor: dict[str, Any]) -> dict[str, Any]:
    """Re-read role, team and active status from SQLite; do not trust stale UI state."""
    if not actor or not actor.get("id"):
        raise PermissionDenied("Phiên đăng nhập không hợp lệ.")
    latest = get_user_by_id(int(actor["id"]))
    if not latest or not latest.get("is_active"):
        raise PermissionDenied("Tài khoản đã bị khóa hoặc phiên đăng nhập hết hiệu lực.")
    return latest


def _check_actor(actor: dict[str, Any], allowed: Iterable[str]) -> None:
    if not actor or not actor.get("is_active") or actor.get("role") not in set(allowed):
        raise PermissionDenied("Bạn không có quyền thực hiện thao tác này.")


def _check_member_scope(actor: dict[str, Any], member: sqlite3.Row | dict[str, Any]) -> None:
    """Server-side record visibility check; never trust a group/member ID from the browser."""
    role = actor.get("role")
    if member["role"] != "member":
        raise PermissionDenied("Chỉ có thể xem hồ sơ thi đua của tài khoản thành viên.")
    if role in ("founder", "teacher"):
        return
    if role == "leader" and int(member["group_no"]) == int(actor["group_no"]):
        return
    if role == "member" and int(member["id"]) == int(actor["id"]):
        return
    raise PermissionDenied("Bạn không có quyền truy cập dữ liệu của thành viên này.")


def create_user(actor: dict[str, Any], full_name: str, phone: str,
                password: str, role: str, group_no: int | None) -> int:
    actor = _refresh_actor(actor)
    _check_actor(actor, ("founder", "teacher", "leader"))
    full_name, phone = _validate_identity(full_name, phone)
    if role not in ("teacher", "leader", "member"):
        raise PermissionDenied("Không thể tạo tài khoản với vai trò này.")
    actor_role = actor["role"]
    if actor_role == "leader":
        if role != "member" or group_no != actor["group_no"]:
            raise PermissionDenied("Tổ trưởng chỉ được thêm thành viên vào chính tổ của mình.")
    elif actor_role == "teacher" and role == "teacher":
        raise PermissionDenied("Chỉ người sáng lập mới được tạo tài khoản giáo viên chủ nhiệm.")
    if role in ("leader", "member"):
        if group_no not in GROUPS:
            raise ValidationError("Vui lòng chọn tổ từ 1 đến 4.")
    else:
        group_no = None
    password_hash = hash_password(password)
    legacy_person_code, legacy_username = _legacy_identity_values()
    with connection() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO users(person_code, username, phone, full_name, password_hash, role, group_no) "
                "VALUES(?,?,?,?,?,?,?)",
                (legacy_person_code, legacy_username, phone, full_name, password_hash, role, group_no),
            )
        except sqlite3.IntegrityError as exc:
            msg = str(exc).lower()
            if "one_active_leader" in msg or "users.group_no" in msg:
                raise ValidationError("Tổ này đã có tổ trưởng đang hoạt động.") from exc
            if "one_active_teacher" in msg:
                raise ValidationError("Lớp đã có tài khoản giáo viên chủ nhiệm đang hoạt động.") from exc
            if "one_founder" in msg:
                raise ValidationError("Hệ thống đã có người sáng lập.") from exc
            if "phone" in msg:
                raise ValidationError("Số điện thoại này đã được dùng cho một tài khoản khác.") from exc
            raise ValidationError("Không thể tạo tài khoản do dữ liệu bị trùng hoặc không hợp lệ.") from exc
        user_id = int(cursor.lastrowid)
        _audit(conn, int(actor["id"]), "create_user", user_id,
               f"Tạo tài khoản với số điện thoại {phone}; vai trò={role}; tổ={group_no or 'Không áp dụng'}")
        return user_id


def list_visible_accounts(actor: dict[str, Any], group_no: int | None = None) -> list[dict[str, Any]]:
    actor = _refresh_actor(actor)
    role = actor.get("role")
    with connection() as conn:
        if role == "founder":
            sql = "SELECT id, phone, full_name, role, group_no, is_active, created_at FROM users"
            params: tuple[Any, ...] = ()
            if group_no in GROUPS:
                sql += " WHERE group_no=?"
                params = (group_no,)
        elif role == "teacher":
            sql = "SELECT id, phone, full_name, role, group_no, is_active, created_at FROM users WHERE role IN ('leader','member')"
            params = ()
            if group_no in GROUPS:
                sql += " AND group_no=?"
                params = (group_no,)
        elif role == "leader":
            # Strictly limited to the leader's own group; never returns other groups' accounts.
            sql = "SELECT id, phone, full_name, role, group_no, is_active, created_at FROM users WHERE role='member' AND group_no=?"
            params = (int(actor["group_no"]),)
        else:
            sql = "SELECT id, phone, full_name, role, group_no, is_active, created_at FROM users WHERE id=?"
            params = (int(actor["id"]),)
        rows = conn.execute(sql + " ORDER BY group_no, role, full_name", params).fetchall()
        return [dict(row) for row in rows]


def list_group_members(actor: dict[str, Any], group_no: int) -> list[dict[str, Any]]:
    actor = _refresh_actor(actor)
    if group_no not in GROUPS:
        raise ValidationError("Tổ không hợp lệ.")
    if actor["role"] == "leader" and group_no != actor["group_no"]:
        raise PermissionDenied("Tổ trưởng chỉ được truy cập tổ của mình.")
    if actor["role"] not in ("founder", "teacher", "leader"):
        raise PermissionDenied("Bạn không có quyền xem danh sách thành viên của tổ.")
    with connection() as conn:
        rows = conn.execute(
            "SELECT id, phone, full_name, role, group_no, is_active, created_at "
            "FROM users WHERE role='member' AND group_no=? AND is_active=1 ORDER BY full_name",
            (group_no,),
        ).fetchall()
        return [dict(row) for row in rows]


def group_summaries(actor: dict[str, Any]) -> list[dict[str, Any]]:
    actor = _refresh_actor(actor)
    if actor["role"] in ("founder", "teacher"):
        groups = GROUPS
    elif actor["role"] == "leader":
        groups = (int(actor["group_no"]),)
    else:
        raise PermissionDenied("Bạn không có quyền xem bảng tổng hợp các tổ.")
    result = []
    with connection() as conn:
        for group_no in groups:
            row = conn.execute(
                "SELECT COUNT(DISTINCT u.id) AS member_count, "
                "COALESCE(SUM(CASE WHEN s.is_deleted=0 THEN s.points ELSE 0 END),0) AS total_points "
                "FROM users u LEFT JOIN scores s ON s.member_id=u.id "
                "WHERE u.role='member' AND u.group_no=? AND u.is_active=1",
                (group_no,),
            ).fetchone()
            result.append({"group_no": group_no, "member_count": int(row["member_count"]),
                           "total_points": float(row["total_points"])})
    return result


def _target_for_action(conn: sqlite3.Connection, actor: dict[str, Any], member_id: int) -> sqlite3.Row:
    actor = _refresh_actor(actor)
    row = conn.execute("SELECT id, role, group_no, full_name FROM users WHERE id=? AND is_active=1", (member_id,)).fetchone()
    if not row:
        raise ValidationError("Không tìm thấy thành viên hoặc tài khoản đã bị khóa.")
    _check_member_scope(actor, row)
    return row


def member_summary(actor: dict[str, Any], member_id: int) -> dict[str, Any]:
    with connection() as conn:
        member = _target_for_action(conn, actor, member_id)
        row = conn.execute(
            "SELECT COALESCE(SUM(points),0) AS total, COUNT(*) AS entries "
            "FROM scores WHERE member_id=? AND is_deleted=0", (member_id,)
        ).fetchone()
        return {"id": int(member["id"]), "full_name": member["full_name"],
                "group_no": int(member["group_no"]), "total_points": float(row["total"]),
                "score_entries": int(row["entries"])}


def records_for_member(actor: dict[str, Any], member_id: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    with connection() as conn:
        _target_for_action(conn, actor, member_id)
        scores = conn.execute(
            "SELECT s.id, s.points, s.category, s.note, s.created_at, u.full_name AS created_by_name "
            "FROM scores s JOIN users u ON u.id=s.created_by "
            "WHERE s.member_id=? AND s.is_deleted=0 ORDER BY s.created_at DESC, s.id DESC LIMIT 100",
            (member_id,),
        ).fetchall()
        evaluations = conn.execute(
            "SELECT e.id, e.content, e.created_at, u.full_name AS evaluator_name "
            "FROM evaluations e JOIN users u ON u.id=e.evaluator_id "
            "WHERE e.member_id=? AND e.is_deleted=0 ORDER BY e.created_at DESC, e.id DESC LIMIT 100",
            (member_id,),
        ).fetchall()
        return [dict(row) for row in scores], [dict(row) for row in evaluations]


def my_records(user_id: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float]:
    """A self-only query: caller cannot supply another person's identifier."""
    with connection() as conn:
        user = conn.execute("SELECT id FROM users WHERE id=? AND is_active=1", (user_id,)).fetchone()
        if not user:
            raise PermissionDenied("Phiên đăng nhập không còn hợp lệ.")
        scores = conn.execute(
            "SELECT id, points, category, note, created_at FROM scores "
            "WHERE member_id=? AND is_deleted=0 ORDER BY created_at DESC, id DESC LIMIT 100", (user_id,)
        ).fetchall()
        evaluations = conn.execute(
            "SELECT id, content, created_at FROM evaluations "
            "WHERE member_id=? AND is_deleted=0 ORDER BY created_at DESC, id DESC LIMIT 100", (user_id,)
        ).fetchall()
        total = conn.execute(
            "SELECT COALESCE(SUM(points),0) FROM scores WHERE member_id=? AND is_deleted=0", (user_id,)
        ).fetchone()[0]
        return [dict(x) for x in scores], [dict(x) for x in evaluations], float(total)


def add_score(actor: dict[str, Any], member_id: int, points: float, category: str, note: str) -> int:
    actor = _refresh_actor(actor)
    _check_actor(actor, ("founder", "teacher", "leader"))
    points = float(points)
    if not -100 <= points <= 100 or points == 0:
        raise ValidationError("Điểm cộng/trừ phải khác 0 và nằm trong khoảng -100 đến 100.")
    category, note = (category or "").strip(), (note or "").strip()
    if not category or len(category) > 60:
        raise ValidationError("Vui lòng nhập loại vi phạm/khen thưởng (tối đa 60 ký tự).")
    if not note or len(note) > 1000:
        raise ValidationError("Lý do phải có từ 1 đến 1.000 ký tự.")
    with connection() as conn:
        member = _target_for_action(conn, actor, member_id)
        cursor = conn.execute(
            "INSERT INTO scores(member_id, points, category, note, created_by) VALUES(?,?,?,?,?)",
            (member_id, points, category, note, int(actor["id"])),
        )
        score_id = int(cursor.lastrowid)
        _audit(conn, int(actor["id"]), "add_score", member_id,
               f"Mã điểm={score_id}; điểm={points}; lý do={note[:180]}")
        return score_id


def edit_score(actor: dict[str, Any], member_id: int, score_id: int,
               points: float, category: str, note: str) -> None:
    actor = _refresh_actor(actor)
    _check_actor(actor, ("founder", "teacher", "leader"))
    points = float(points)
    if not -100 <= points <= 100 or points == 0:
        raise ValidationError("Điểm cộng/trừ phải khác 0 và nằm trong khoảng -100 đến 100.")
    category, note = (category or "").strip(), (note or "").strip()
    if not category or len(category) > 60 or not note or len(note) > 1000:
        raise ValidationError("Loại điểm hoặc lý do không hợp lệ.")
    with connection() as conn:
        _target_for_action(conn, actor, member_id)
        existing = conn.execute("SELECT id FROM scores WHERE id=? AND member_id=? AND is_deleted=0", (score_id, member_id)).fetchone()
        if not existing:
            raise ValidationError("Không tìm thấy khoản điểm cần chỉnh sửa.")
        conn.execute("UPDATE scores SET points=?, category=?, note=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                     (points, category, note, score_id))
        _audit(conn, int(actor["id"]), "edit_score", member_id, f"Sửa khoản điểm={score_id}; điểm mới={points}")


def delete_score(actor: dict[str, Any], member_id: int, score_id: int) -> None:
    actor = _refresh_actor(actor)
    _check_actor(actor, ("founder", "teacher", "leader"))
    with connection() as conn:
        _target_for_action(conn, actor, member_id)
        existing = conn.execute("SELECT id FROM scores WHERE id=? AND member_id=? AND is_deleted=0", (score_id, member_id)).fetchone()
        if not existing:
            raise ValidationError("Không tìm thấy khoản điểm cần xóa.")
        conn.execute("UPDATE scores SET is_deleted=1, deleted_by=?, deleted_at=CURRENT_TIMESTAMP WHERE id=?",
                     (int(actor["id"]), score_id))
        _audit(conn, int(actor["id"]), "delete_score", member_id, f"Ẩn khoản điểm={score_id}")


def add_evaluation(actor: dict[str, Any], member_id: int, content: str) -> int:
    actor = _refresh_actor(actor)
    _check_actor(actor, ("founder", "teacher", "leader"))
    content = (content or "").strip()
    if not content or len(content) > 2000:
        raise ValidationError("Đánh giá phải có từ 1 đến 2.000 ký tự.")
    with connection() as conn:
        _target_for_action(conn, actor, member_id)
        cursor = conn.execute(
            "INSERT INTO evaluations(member_id, content, evaluator_id) VALUES(?,?,?)",
            (member_id, content, int(actor["id"])),
        )
        evaluation_id = int(cursor.lastrowid)
        _audit(conn, int(actor["id"]), "add_evaluation", member_id, f"Tạo đánh giá={evaluation_id}")
        return evaluation_id


def edit_evaluation(actor: dict[str, Any], member_id: int, evaluation_id: int, content: str) -> None:
    actor = _refresh_actor(actor)
    _check_actor(actor, ("founder", "teacher", "leader"))
    content = (content or "").strip()
    if not content or len(content) > 2000:
        raise ValidationError("Đánh giá phải có từ 1 đến 2.000 ký tự.")
    with connection() as conn:
        _target_for_action(conn, actor, member_id)
        existing = conn.execute("SELECT id FROM evaluations WHERE id=? AND member_id=? AND is_deleted=0", (evaluation_id, member_id)).fetchone()
        if not existing:
            raise ValidationError("Không tìm thấy đánh giá cần chỉnh sửa.")
        conn.execute("UPDATE evaluations SET content=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (content, evaluation_id))
        _audit(conn, int(actor["id"]), "edit_evaluation", member_id, f"Sửa đánh giá={evaluation_id}")


def delete_evaluation(actor: dict[str, Any], member_id: int, evaluation_id: int) -> None:
    actor = _refresh_actor(actor)
    _check_actor(actor, ("founder", "teacher", "leader"))
    with connection() as conn:
        _target_for_action(conn, actor, member_id)
        existing = conn.execute("SELECT id FROM evaluations WHERE id=? AND member_id=? AND is_deleted=0", (evaluation_id, member_id)).fetchone()
        if not existing:
            raise ValidationError("Không tìm thấy đánh giá cần xóa.")
        conn.execute("UPDATE evaluations SET is_deleted=1, deleted_by=?, deleted_at=CURRENT_TIMESTAMP WHERE id=?",
                     (int(actor["id"]), evaluation_id))
        _audit(conn, int(actor["id"]), "delete_evaluation", member_id, f"Ẩn đánh giá={evaluation_id}")


def update_account(actor: dict[str, Any], target_id: int, full_name: str,
                   phone: str, role: str, group_no: int | None) -> None:
    actor = _refresh_actor(actor)
    _check_actor(actor, ("founder", "teacher"))
    full_name, phone = _validate_identity(full_name, phone)
    if role not in ("teacher", "leader", "member"):
        raise PermissionDenied("Không thể gán vai trò này.")
    if actor["role"] == "teacher" and role == "teacher":
        raise PermissionDenied("Chỉ người sáng lập mới được quản lý tài khoản giáo viên chủ nhiệm.")
    if role in ("leader", "member") and group_no not in GROUPS:
        raise ValidationError("Vui lòng chọn tổ từ 1 đến 4.")
    if role == "teacher":
        group_no = None
    with connection() as conn:
        target = conn.execute("SELECT id, role, group_no FROM users WHERE id=?", (target_id,)).fetchone()
        if not target:
            raise ValidationError("Không tìm thấy tài khoản.")
        _check_account_admin_scope(actor, target)
        if target["id"] == actor["id"]:
            raise ValidationError("Không thể tự đổi vai trò hoặc số điện thoại của tài khoản đang đăng nhập.")
        try:
            conn.execute(
                "UPDATE users SET full_name=?, phone=?, role=?, group_no=?, "
                "session_version=session_version+1 WHERE id=?",
                (full_name, phone, role, group_no, target_id),
            )
        except sqlite3.IntegrityError as exc:
            msg = str(exc).lower()
            if "phone" in msg:
                raise ValidationError("Số điện thoại này đã thuộc về một tài khoản khác.") from exc
            if "one_active_leader" in msg or "users.group_no" in msg:
                raise ValidationError("Tổ được chọn đã có tổ trưởng đang hoạt động.") from exc
            if "one_active_teacher" in msg:
                raise ValidationError("Lớp đã có giáo viên chủ nhiệm đang hoạt động.") from exc
            raise ValidationError("Không thể cập nhật tài khoản do dữ liệu bị trùng hoặc không hợp lệ.") from exc
        _audit(conn, int(actor["id"]), "update_account", target_id,
               f"Cập nhật thông tin; vai trò={role}; tổ={group_no or 'Không áp dụng'}")


def _check_account_admin_scope(actor: dict[str, Any], target: sqlite3.Row) -> None:
    if actor["role"] == "founder":
        if target["role"] == "founder":
            raise PermissionDenied("Không thể thay đổi tài khoản người sáng lập từ màn hình quản lý thông thường.")
        return
    if actor["role"] == "teacher":
        if target["role"] not in ("leader", "member"):
            raise PermissionDenied("Giáo viên chủ nhiệm không thể quản lý tài khoản người sáng lập/giáo viên khác.")
        return
    raise PermissionDenied("Bạn không có quyền quản lý tài khoản này.")


def set_account_active(actor: dict[str, Any], target_id: int, is_active: bool) -> None:
    actor = _refresh_actor(actor)
    _check_actor(actor, ("founder", "teacher"))
    if int(actor["id"]) == int(target_id):
        raise ValidationError("Không thể tự khóa tài khoản đang đăng nhập.")
    with connection() as conn:
        target = conn.execute("SELECT id, role, group_no FROM users WHERE id=?", (target_id,)).fetchone()
        if not target:
            raise ValidationError("Không tìm thấy tài khoản.")
        _check_account_admin_scope(actor, target)
        try:
            conn.execute("UPDATE users SET is_active=?, session_version=session_version+1 WHERE id=?",
                     (1 if is_active else 0, target_id))
        except sqlite3.IntegrityError as exc:
            raise ValidationError("Không thể mở khóa: tổ này hoặc lớp đã có tài khoản quản lý đang hoạt động.") from exc
        _audit(conn, int(actor["id"]), "activate_account" if is_active else "deactivate_account",
               target_id, "Thay đổi trạng thái tài khoản")


def admin_reset_password(actor: dict[str, Any], target_id: int, new_password: str) -> None:
    actor = _refresh_actor(actor)
    _check_actor(actor, ("founder", "teacher"))
    with connection() as conn:
        target = conn.execute("SELECT id, role FROM users WHERE id=?", (target_id,)).fetchone()
        if not target:
            raise ValidationError("Không tìm thấy tài khoản.")
        _check_account_admin_scope(actor, target)
        password_hash = hash_password(new_password)
        conn.execute("UPDATE users SET password_hash=?, session_version=session_version+1 WHERE id=?",
                     (password_hash, target_id))
        _audit(conn, int(actor["id"]), "admin_reset_password", target_id,
               "Người sáng lập/Giáo viên chủ nhiệm đặt lại mật khẩu")


def change_own_password(actor: dict[str, Any], user_id: int,
                        current_password: str, new_password: str) -> None:
    actor = _refresh_actor(actor)
    _check_actor(actor, ("founder", "teacher"))
    if int(actor["id"]) != int(user_id):
        raise PermissionDenied("Chỉ Người sáng lập hoặc Giáo viên chủ nhiệm được đổi mật khẩu của chính mình.")
    with connection() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE id=? AND is_active=1", (user_id,)).fetchone()
        if not row or not verify_password(row["password_hash"], current_password or ""):
            raise ValidationError("Mật khẩu hiện tại không chính xác.")
        password_hash = hash_password(new_password)
        conn.execute("UPDATE users SET password_hash=?, session_version=session_version+1 WHERE id=?",
                     (password_hash, user_id))
        _audit(conn, user_id, "change_own_password", user_id, "Người quản trị tự đổi mật khẩu")


def recent_audit(actor: dict[str, Any], limit: int = 50) -> list[dict[str, Any]]:
    actor = _refresh_actor(actor)
    if actor["role"] not in ("founder", "teacher"):
        raise PermissionDenied("Bạn không có quyền xem nhật ký toàn lớp.")
    limit = max(1, min(int(limit), 200))
    with connection() as conn:
        rows = conn.execute(
            "SELECT a.id, a.action, a.details, a.created_at, u.full_name AS actor_name, "
            "t.full_name AS target_name FROM audit_logs a "
            "LEFT JOIN users u ON u.id=a.actor_id LEFT JOIN users t ON t.id=a.target_user_id "
            "ORDER BY a.id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]
