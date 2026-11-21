"""Website quản lý điểm thi đua lớp học, built with NiceGUI and SQLite."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from nicegui import app, ui

import database as db
from database import PermissionDenied, ValidationError, ROLE_LABELS, GROUPS
from security import PasswordPolicyError, generate_password

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

STORAGE_SECRET = os.getenv("NICEGUI_STORAGE_SECRET", "")
BOOTSTRAP_TOKEN = os.getenv("BOOTSTRAP_TOKEN", "")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").strip().lower() == "true"
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8080"))

if len(STORAGE_SECRET) < 32:
    raise RuntimeError("NICEGUI_STORAGE_SECRET chưa được cấu hình hoặc ngắn hơn 32 ký tự. Hãy tạo file .env theo README.md.")
if len(BOOTSTRAP_TOKEN) < 32:
    raise RuntimeError("BOOTSTRAP_TOKEN chưa được cấu hình hoặc ngắn hơn 32 ký tự. Hãy tạo file .env theo README.md.")

ui.colors(primary="#2457A6", secondary="#64748B", accent="#0F766E", positive="#15803D", negative="#B91C1C")
PAGE_STYLES = """
<style>
  body { background: #f4f7fb; }
  .app-shell { max-width: 1180px; margin: 0 auto; }
  .soft-card { border: 1px solid #e4eaf2; border-radius: 18px; box-shadow: 0 5px 20px rgba(24, 50, 90, .045); }
  .muted { color: #64748b; }
  .section-title { color: #172b4d; font-weight: 700; }
  .score-positive { color: #15803d; font-weight: 700; }
  .score-negative { color: #b91c1c; font-weight: 700; }
  .q-tab { font-weight: 600; }
  @media (max-width: 640px) { .app-shell { padding: 12px !important; } }
</style>
"""


def notify_error(error: Exception | str) -> None:
    ui.notify(str(error), type="negative", position="top")


def notify_success(message: str) -> None:
    ui.notify(message, type="positive", position="top")


def fresh_actor() -> dict:
    """Reload the account from SQLite before handling every sensitive UI action."""
    user_id = app.storage.user.get("user_id")
    user = db.get_user_by_id(int(user_id)) if user_id else None
    if not user or not user.get("is_active"):
        app.storage.user.pop("user_id", None)
        app.storage.user.pop("session_version", None)
        raise PermissionDenied("Phiên đăng nhập không còn hợp lệ. Vui lòng đăng nhập lại.")
    stored_version = app.storage.user.get("session_version")
    if stored_version is None or int(stored_version) != int(user.get("session_version", 0)):
        app.storage.user.pop("user_id", None)
        app.storage.user.pop("session_version", None)
        refresh_page()
        raise PermissionDenied("Phiên đăng nhập đã bị thu hồi. Vui lòng đăng nhập lại.")
    return user


def refresh_page() -> None:
    ui.navigate.reload()


def render_brand(subtitle: str = "Quản lý thi đua lớp học") -> None:
    with ui.row().classes("items-center gap-3"):
        with ui.element("div").classes("w-12 h-12 rounded-2xl flex items-center justify-center").style("background:#e5efff"):
            ui.icon("school", size="28px").style("color:#2457a6")
        with ui.column().classes("gap-0"):
            ui.label("CLASS MERIT HUB").classes("text-xl font-extrabold tracking-wide").style("color:#172b4d")
            ui.label(subtitle).classes("text-sm muted")


def render_login() -> None:
    with ui.column().classes("w-full min-h-screen items-center justify-center p-4"):
        with ui.card().classes("soft-card w-full max-w-md p-7 gap-5"):
            render_brand("Cổng thông tin thi đua nội bộ")
            ui.separator()
            ui.label("Đăng nhập tài khoản").classes("text-2xl font-bold").style("color:#172b4d")
            ui.label("Mỗi người sử dụng tài khoản riêng được cấp bởi quản trị viên.").classes("muted text-sm")
            username = ui.input("Tên đăng nhập", placeholder="Nhập tên tài khoản").classes("w-full")
            password = ui.input("Mật khẩu", password=True, password_toggle_button=True).classes("w-full")

            def do_login() -> None:
                user, message = db.authenticate(username.value or "", password.value or "")
                if user:
                    app.storage.user["user_id"] = int(user["id"])
                    app.storage.user["session_version"] = int(user.get("session_version", 0))
                    app.storage.user.pop("login_time", None)
                    refresh_page()
                else:
                    notify_error(message)

            password.on("keydown.enter", do_login)
            ui.button("Đăng nhập", on_click=do_login, icon="login").classes("w-full mt-2")
            ui.label("Bảo mật: mật khẩu được băm Argon2id; đăng nhập sai 5 lần sẽ khóa tạm thời 15 phút.").classes("text-xs muted")


def render_bootstrap() -> None:
    with ui.column().classes("w-full min-h-screen items-center justify-center p-4"):
        with ui.card().classes("soft-card w-full max-w-xl p-7 gap-4"):
            render_brand("Thiết lập hệ thống lần đầu")
            ui.separator()
            ui.label("Tạo tài khoản người sáng lập").classes("text-2xl font-bold").style("color:#172b4d")
            ui.label("Đây là tài khoản có quyền cao nhất. Chỉ có thể thực hiện bước này một lần.").classes("muted")
            full_name = ui.input("Họ và tên")
            username = ui.input("Tên đăng nhập", placeholder="Ví dụ: founder.phat")
            person_code = ui.input("Mã định danh cá nhân", placeholder="Mã riêng, không được trùng với người khác")
            token = ui.input("Mã thiết lập một lần", password=True, password_toggle_button=True)
            password = ui.input("Mật khẩu mạnh", password=True, password_toggle_button=True)
            password2 = ui.input("Nhập lại mật khẩu", password=True, password_toggle_button=True)
            ui.label("Mật khẩu tối thiểu 14 ký tự, gồm chữ hoa, chữ thường, số và ký tự đặc biệt.").classes("text-xs muted")

            def create_founder_account() -> None:
                try:
                    if password.value != password2.value:
                        raise ValidationError("Hai mật khẩu không trùng khớp.")
                    user_id = db.create_founder(full_name.value or "", username.value or "",
                                                person_code.value or "", password.value or "",
                                                token.value or "", BOOTSTRAP_TOKEN)
                    app.storage.user["user_id"] = user_id
                    created_user = db.get_user_by_id(user_id)
                    app.storage.user["session_version"] = int(created_user.get("session_version", 0))
                    notify_success("Đã khởi tạo tài khoản người sáng lập.")
                    refresh_page()
                except (ValidationError, PermissionDenied, PasswordPolicyError) as exc:
                    notify_error(exc)

            ui.button("Khởi tạo người sáng lập", on_click=create_founder_account, icon="verified_user").classes("w-full")
            ui.label("Nếu không có mã thiết lập, hãy kiểm tra biến BOOTSTRAP_TOKEN trong file .env.").classes("text-xs muted")


def role_text(user: dict) -> str:
    label = ROLE_LABELS.get(user["role"], user["role"])
    if user.get("group_no"):
        return f"{label} · Tổ {user['group_no']}"
    return label


def render_header(user: dict) -> None:
    with ui.row().classes("w-full items-center justify-between flex-wrap gap-3"):
        render_brand("Sổ điểm thi đua và nhận xét")
        with ui.row().classes("items-center gap-2"):
            with ui.column().classes("items-end gap-0"):
                ui.label(user["full_name"]).classes("font-bold")
                ui.label(role_text(user)).classes("text-xs muted")
            ui.button(icon="logout", on_click=lambda: logout(), color="grey-7").props("flat round").tooltip("Đăng xuất")


def logout() -> None:
    app.storage.user.pop("user_id", None)
    app.storage.user.pop("session_version", None)
    refresh_page()


def open_change_password_dialog(user_id: int) -> None:
    dialog = ui.dialog()
    with dialog, ui.card().classes("w-full max-w-md p-5"):
        ui.label("Đổi mật khẩu").classes("text-xl font-bold")
        current = ui.input("Mật khẩu hiện tại", password=True, password_toggle_button=True).classes("w-full")
        new = ui.input("Mật khẩu mới", password=True, password_toggle_button=True).classes("w-full")
        confirm = ui.input("Nhập lại mật khẩu mới", password=True, password_toggle_button=True).classes("w-full")

        def save() -> None:
            try:
                if new.value != confirm.value:
                    raise ValidationError("Hai mật khẩu mới không trùng khớp.")
                db.change_own_password(user_id, current.value or "", new.value or "")
                updated_user = db.get_user_by_id(user_id)
                app.storage.user["session_version"] = int(updated_user.get("session_version", 0))
                dialog.close()
                notify_success("Đổi mật khẩu thành công.")
            except (ValidationError, PasswordPolicyError) as exc:
                notify_error(exc)

        with ui.row().classes("w-full justify-end"):
            ui.button("Hủy", on_click=dialog.close, color="grey")
            ui.button("Lưu mật khẩu", on_click=save, icon="lock")
    dialog.open()


def open_create_user_dialog(actor: dict, default_group: int | None = None) -> None:
    actor = fresh_actor()
    dialog = ui.dialog()
    with dialog, ui.card().classes("w-full max-w-lg p-5"):
        ui.label("Thêm tài khoản mới").classes("text-xl font-bold")
        full_name = ui.input("Họ và tên", placeholder="Tên thành viên").classes("w-full")
        person_code = ui.input("Mã định danh cá nhân", placeholder="Ví dụ: HS001").classes("w-full")
        username = ui.input("Tên đăng nhập", placeholder="Không trùng với tài khoản khác").classes("w-full")
        if actor["role"] == "founder":
            role_options = {"teacher": "Giáo viên chủ nhiệm", "leader": "Tổ trưởng", "member": "Thành viên"}
        elif actor["role"] == "teacher":
            role_options = {"leader": "Tổ trưởng", "member": "Thành viên"}
        else:
            role_options = {"member": "Thành viên"}
        role_select = ui.select(role_options, value="member", label="Vai trò").classes("w-full")
        group_select = ui.select({1: "Tổ 1", 2: "Tổ 2", 3: "Tổ 3", 4: "Tổ 4"},
                                 value=default_group or actor.get("group_no") or 1,
                                 label="Tổ phụ trách").classes("w-full")
        if actor["role"] == "leader":
            group_select.disable()
        initial_password = ui.input("Mật khẩu khởi tạo", password=True, password_toggle_button=True).classes("w-full")
        ui.button("Sinh mật khẩu ngẫu nhiên", icon="casino",
                  on_click=lambda: initial_password.set_value(generate_password())).props("outline dense")
        ui.label("Hãy gửi mật khẩu khởi tạo riêng cho đúng người nhận. Không dùng chung một tài khoản.").classes("text-xs muted")

        def update_group_visibility() -> None:
            if role_select.value == "teacher":
                group_select.set_visibility(False)
            else:
                group_select.set_visibility(True)

        role_select.on_value_change(lambda _: update_group_visibility())
        update_group_visibility()

        def save() -> None:
            try:
                latest_actor = fresh_actor()
                role = str(role_select.value)
                group_no = None if role == "teacher" else int(group_select.value)
                db.create_user(latest_actor, full_name.value or "", username.value or "",
                               person_code.value or "", initial_password.value or "", role, group_no)
                dialog.close()
                notify_success("Đã tạo tài khoản. Mã định danh và tên đăng nhập được bảo vệ duy nhất trong hệ thống.")
                refresh_page()
            except (ValidationError, PermissionDenied, PasswordPolicyError) as exc:
                notify_error(exc)

        with ui.row().classes("w-full justify-end"):
            ui.button("Hủy", on_click=dialog.close, color="grey")
            ui.button("Tạo tài khoản", on_click=save, icon="person_add")
    dialog.open()


def open_score_dialog(member_id: int, member_name: str, existing: dict | None = None) -> None:
    actor = fresh_actor()
    dialog = ui.dialog()
    is_edit = existing is not None
    with dialog, ui.card().classes("w-full max-w-md p-5"):
        ui.label("Chỉnh sửa điểm thi đua" if is_edit else f"Cập nhật điểm · {member_name}").classes("text-xl font-bold")
        points = ui.input("Điểm cộng/trừ", value=str(existing["points"] if is_edit else 1)).classes("w-full")
        category = ui.input("Loại điểm", value=(existing["category"] if is_edit else "Chấp hành nội quy")).classes("w-full")
        note = ui.textarea("Lý do / minh chứng", value=(existing["note"] if is_edit else "")).classes("w-full")
        ui.label("Điểm dương là cộng, điểm âm là trừ. Mỗi lần cập nhật trong khoảng -100 đến +100.").classes("text-xs muted")

        def save() -> None:
            try:
                latest_actor = fresh_actor()
                value = float(points.value)
                if is_edit:
                    db.edit_score(latest_actor, member_id, int(existing["id"]), value,
                                  category.value or "", note.value or "")
                else:
                    db.add_score(latest_actor, member_id, value, category.value or "", note.value or "")
                dialog.close()
                notify_success("Đã lưu điểm thi đua.")
                refresh_page()
            except (ValueError, ValidationError, PermissionDenied) as exc:
                notify_error(exc if not isinstance(exc, ValueError) else "Điểm phải là một con số hợp lệ.")

        with ui.row().classes("w-full justify-end"):
            ui.button("Hủy", on_click=dialog.close, color="grey")
            ui.button("Lưu điểm", on_click=save, icon="save")
    dialog.open()


def open_evaluation_dialog(member_id: int, member_name: str, existing: dict | None = None) -> None:
    dialog = ui.dialog()
    is_edit = existing is not None
    with dialog, ui.card().classes("w-full max-w-lg p-5"):
        ui.label("Chỉnh sửa nhận xét" if is_edit else f"Nhận xét · {member_name}").classes("text-xl font-bold")
        content = ui.textarea("Nội dung đánh giá", value=(existing["content"] if is_edit else "")).classes("w-full")
        content.props("rows=5")

        def save() -> None:
            try:
                actor = fresh_actor()
                if is_edit:
                    db.edit_evaluation(actor, member_id, int(existing["id"]), content.value or "")
                else:
                    db.add_evaluation(actor, member_id, content.value or "")
                dialog.close()
                notify_success("Đã lưu nhận xét.")
                refresh_page()
            except (ValidationError, PermissionDenied) as exc:
                notify_error(exc)

        with ui.row().classes("w-full justify-end"):
            ui.button("Hủy", on_click=dialog.close, color="grey")
            ui.button("Lưu nhận xét", on_click=save, icon="save")
    dialog.open()


def render_member_detail(actor: dict, member: dict) -> None:
    latest_actor = fresh_actor()
    member_id = int(member["id"])
    try:
        summary = db.member_summary(latest_actor, member_id)
        scores, evaluations = db.records_for_member(latest_actor, member_id)
    except (PermissionDenied, ValidationError) as exc:
        notify_error(exc)
        return

    dialog = ui.dialog()
    with dialog, ui.card().classes("w-full max-w-3xl p-5"):
        with ui.row().classes("w-full items-center justify-between"):
            with ui.column().classes("gap-0"):
                ui.label(summary["full_name"]).classes("text-xl font-bold")
                ui.label(f"Tổ {summary['group_no']} · {summary['score_entries']} lần cập nhật điểm").classes("text-sm muted")
            ui.button(icon="close", on_click=dialog.close).props("flat round")
        with ui.row().classes("items-center gap-2"):
            ui.label("Tổng điểm hiện tại:").classes("font-semibold")
            ui.label(f"{summary['total_points']:+g}").classes("text-2xl font-extrabold").style("color:#2457a6")
        if latest_actor["role"] in ("founder", "teacher", "leader"):
            with ui.row().classes("flex-wrap"):
                ui.button("Cộng / trừ điểm", icon="add", on_click=lambda: open_score_dialog(member_id, summary["full_name"]))
                ui.button("Viết nhận xét", icon="rate_review", on_click=lambda: open_evaluation_dialog(member_id, summary["full_name"]), color="secondary")
        ui.separator()
        ui.label("Lịch sử điểm thi đua").classes("font-bold")
        if not scores:
            ui.label("Chưa có bản ghi điểm nào.").classes("muted text-sm")
        for score in scores:
            with ui.row().classes("w-full items-start justify-between border-b border-gray-100 py-2 gap-2"):
                with ui.column().classes("gap-0 flex-1"):
                    point_class = "score-positive" if score["points"] > 0 else "score-negative"
                    ui.label(f"{score['points']:+g} điểm · {score['category']}").classes(point_class)
                    ui.label(score["note"]).classes("text-sm")
                    ui.label(f"{score['created_at']} · {score['created_by_name']}").classes("text-xs muted")
                if latest_actor["role"] in ("founder", "teacher", "leader"):
                    with ui.row().classes("gap-1"):
                        ui.button(icon="edit", on_click=lambda s=score: open_score_dialog(member_id, summary["full_name"], s)).props("flat round dense")
                        ui.button(icon="delete", color="negative", on_click=lambda s=score: confirm_delete_score(member_id, int(s["id"]), dialog)).props("flat round dense")
        ui.separator()
        ui.label("Nhận xét / đánh giá").classes("font-bold")
        if not evaluations:
            ui.label("Chưa có nhận xét nào.").classes("muted text-sm")
        for evaluation in evaluations:
            with ui.card().classes("w-full bg-gray-50 gap-1"):
                ui.label(evaluation["content"]).classes("whitespace-pre-wrap")
                ui.label(f"{evaluation['created_at']} · {evaluation['evaluator_name']}").classes("text-xs muted")
                if latest_actor["role"] in ("founder", "teacher", "leader"):
                    with ui.row().classes("gap-1"):
                        ui.button("Sửa", icon="edit", on_click=lambda e=evaluation: open_evaluation_dialog(member_id, summary["full_name"], e)).props("flat dense")
                        ui.button("Xóa", icon="delete", color="negative", on_click=lambda e=evaluation: confirm_delete_evaluation(member_id, int(e["id"]), dialog)).props("flat dense")
    dialog.open()


def confirm_delete_score(member_id: int, score_id: int, parent_dialog) -> None:
    confirm = ui.dialog()
    with confirm, ui.card().classes("p-4"):
        ui.label("Ẩn khoản điểm này khỏi bảng thi đua?").classes("font-semibold")
        ui.label("Thao tác sẽ được ghi vào nhật ký quản trị.").classes("text-sm muted")
        def do_delete() -> None:
            try:
                db.delete_score(fresh_actor(), member_id, score_id)
                confirm.close()
                parent_dialog.close()
                notify_success("Đã xóa khoản điểm khỏi bảng hiển thị.")
                refresh_page()
            except (PermissionDenied, ValidationError) as exc:
                notify_error(exc)
        with ui.row().classes("w-full justify-end"):
            ui.button("Hủy", on_click=confirm.close, color="grey")
            ui.button("Xác nhận xóa", on_click=do_delete, color="negative")
    confirm.open()


def confirm_delete_evaluation(member_id: int, evaluation_id: int, parent_dialog) -> None:
    confirm = ui.dialog()
    with confirm, ui.card().classes("p-4"):
        ui.label("Ẩn nhận xét này khỏi hồ sơ thành viên?").classes("font-semibold")
        def do_delete() -> None:
            try:
                db.delete_evaluation(fresh_actor(), member_id, evaluation_id)
                confirm.close()
                parent_dialog.close()
                notify_success("Đã xóa nhận xét khỏi bảng hiển thị.")
                refresh_page()
            except (PermissionDenied, ValidationError) as exc:
                notify_error(exc)
        with ui.row().classes("w-full justify-end"):
            ui.button("Hủy", on_click=confirm.close, color="grey")
            ui.button("Xác nhận xóa", on_click=do_delete, color="negative")
    confirm.open()


def render_group_panel(actor: dict, group_no: int) -> None:
    actor = fresh_actor()
    if actor["role"] == "leader" and group_no != actor["group_no"]:
        raise PermissionDenied("Bạn chỉ được xem tổ của mình.")
    members = db.list_group_members(actor, group_no)
    summary = next((x for x in db.group_summaries(actor) if x["group_no"] == group_no), None)
    with ui.card().classes("soft-card w-full p-4 gap-3"):
        with ui.row().classes("w-full items-center justify-between flex-wrap"):
            with ui.column().classes("gap-0"):
                ui.label(f"DANH SÁCH THÀNH VIÊN · TỔ {group_no}").classes("section-title")
                ui.label(f"{len(members)} thành viên đang hoạt động · Tổng điểm {summary['total_points']:+g}" if summary else f"{len(members)} thành viên").classes("text-sm muted")
            ui.button("Thêm thành viên", icon="person_add", on_click=lambda: open_create_user_dialog(fresh_actor(), group_no))
        if not members:
            ui.label("Tổ chưa có thành viên. Sử dụng nút Thêm thành viên để tạo tài khoản.").classes("muted text-sm")
        with ui.grid(columns=2).classes("w-full"):
            for member in members:
                member_summary = db.member_summary(actor, int(member["id"]))
                with ui.card().classes("soft-card w-full p-3 gap-2"):
                    with ui.row().classes("w-full items-start justify-between"):
                        with ui.column().classes("gap-0"):
                            ui.label(member["full_name"]).classes("font-bold")
                            ui.label(f"@{member['username']}").classes("text-xs muted")
                        ui.badge("Đang hoạt động", color="positive")
                    with ui.row().classes("items-center justify-between"):
                        ui.label("Điểm thi đua hiện tại").classes("text-xs muted")
                        ui.label(f"{member_summary['total_points']:+g}").classes("font-extrabold text-lg")
                    ui.button("Xem điểm & đánh giá", icon="visibility",
                              on_click=lambda m=member: render_member_detail(fresh_actor(), m)).classes("w-full")


def render_group_management(actor: dict) -> None:
    if actor["role"] == "leader":
        render_group_panel(actor, int(actor["group_no"]))
    else:
        for group_no in GROUPS:
            render_group_panel(actor, group_no)


def open_edit_account_dialog(account: dict) -> None:
    actor = fresh_actor()
    dialog = ui.dialog()
    with dialog, ui.card().classes("w-full max-w-lg p-5"):
        ui.label(f"Chỉnh sửa tài khoản · {account['full_name']}").classes("text-xl font-bold")
        full_name = ui.input("Họ và tên", value=account["full_name"]).classes("w-full")
        person_code = ui.input("Mã định danh cá nhân", value=account["person_code"]).classes("w-full")
        username = ui.input("Tên đăng nhập", value=account["username"]).classes("w-full")
        role_options = {"leader": "Tổ trưởng", "member": "Thành viên"}
        if actor["role"] == "founder":
            role_options = {"teacher": "Giáo viên chủ nhiệm", **role_options}
        role_select = ui.select(role_options, value=account["role"], label="Vai trò").classes("w-full")
        group_select = ui.select({1: "Tổ 1", 2: "Tổ 2", 3: "Tổ 3", 4: "Tổ 4"},
                                 value=account["group_no"] or 1, label="Tổ").classes("w-full")
        def update_visibility() -> None:
            group_select.set_visibility(role_select.value != "teacher")
        role_select.on_value_change(lambda _: update_visibility())
        update_visibility()
        def save() -> None:
            try:
                role = str(role_select.value)
                group_no = None if role == "teacher" else int(group_select.value)
                db.update_account(fresh_actor(), int(account["id"]), full_name.value or "",
                                  username.value or "", person_code.value or "", role, group_no)
                dialog.close()
                notify_success("Đã cập nhật thông tin tài khoản. Các phiên đăng nhập cũ của tài khoản này đã bị thu hồi.")
                refresh_page()
            except (ValidationError, PermissionDenied) as exc:
                notify_error(exc)
        with ui.row().classes("w-full justify-end"):
            ui.button("Hủy", on_click=dialog.close, color="grey")
            ui.button("Lưu thay đổi", on_click=save, icon="save")
    dialog.open()


def open_admin_reset_dialog(actor: dict, account: dict) -> None:
    dialog = ui.dialog()
    with dialog, ui.card().classes("w-full max-w-md p-5"):
        ui.label(f"Đặt lại mật khẩu · {account['full_name']}").classes("text-lg font-bold")
        new_password = ui.input("Mật khẩu mới", password=True, password_toggle_button=True).classes("w-full")
        confirm_password = ui.input("Nhập lại mật khẩu", password=True, password_toggle_button=True).classes("w-full")
        def save() -> None:
            try:
                if new_password.value != confirm_password.value:
                    raise ValidationError("Hai mật khẩu không trùng khớp.")
                db.admin_reset_password(fresh_actor(), int(account["id"]), new_password.value or "")
                dialog.close()
                notify_success("Đã đặt lại mật khẩu. Hãy chuyển mật khẩu mới riêng cho đúng người nhận.")
            except (ValidationError, PermissionDenied, PasswordPolicyError) as exc:
                notify_error(exc)
        with ui.row().classes("w-full justify-end"):
            ui.button("Hủy", on_click=dialog.close, color="grey")
            ui.button("Đặt lại", on_click=save, icon="lock_reset")
    dialog.open()


def open_toggle_account_dialog(account: dict) -> None:
    dialog = ui.dialog()
    action_text = "mở khóa" if not account["is_active"] else "khóa"
    with dialog, ui.card().classes("p-4"):
        ui.label(f"Bạn có chắc muốn {action_text} tài khoản {account['full_name']}?").classes("font-semibold")
        def execute() -> None:
            try:
                db.set_account_active(fresh_actor(), int(account["id"]), not bool(account["is_active"]))
                dialog.close()
                notify_success("Đã cập nhật trạng thái tài khoản.")
                refresh_page()
            except (ValidationError, PermissionDenied) as exc:
                notify_error(exc)
        with ui.row().classes("w-full justify-end"):
            ui.button("Hủy", on_click=dialog.close, color="grey")
            ui.button("Xác nhận", on_click=execute, color="negative" if account["is_active"] else "positive")
    dialog.open()


def render_account_management(actor: dict) -> None:
    actor = fresh_actor()
    accounts = db.list_visible_accounts(actor)
    with ui.card().classes("soft-card w-full p-4 gap-3"):
        with ui.row().classes("w-full items-center justify-between flex-wrap"):
            with ui.column().classes("gap-0"):
                ui.label("QUẢN LÝ TÀI KHOẢN").classes("section-title")
                ui.label("Tên đăng nhập và mã định danh cá nhân đều được đặt ràng buộc duy nhất trong cơ sở dữ liệu.").classes("text-sm muted")
            ui.button("Tạo tài khoản", icon="person_add", on_click=lambda: open_create_user_dialog(fresh_actor()))
        for account in accounts:
            with ui.row().classes("w-full items-center justify-between border-b border-gray-100 py-3 flex-wrap gap-2"):
                with ui.column().classes("gap-0"):
                    ui.label(account["full_name"]).classes("font-semibold")
                    ui.label(f"@{account['username']} · {role_text(account)} · Mã: {account['person_code']}").classes("text-xs muted")
                with ui.row().classes("items-center gap-1"):
                    ui.badge("Hoạt động" if account["is_active"] else "Đã khóa", color="positive" if account["is_active"] else "grey")
                    if account["role"] != "founder":
                        ui.button(icon="edit", on_click=lambda a=account: open_edit_account_dialog(a)).props("flat round dense").tooltip("Chỉnh sửa tài khoản")
                        ui.button(icon="lock_reset", on_click=lambda a=account: open_admin_reset_dialog(fresh_actor(), a)).props("flat round dense").tooltip("Đặt lại mật khẩu")
                        ui.button(icon="block" if account["is_active"] else "check_circle",
                                  color="negative" if account["is_active"] else "positive",
                                  on_click=lambda a=account: open_toggle_account_dialog(a)).props("flat round dense").tooltip("Khóa / mở khóa")


def render_audit_page(actor: dict) -> None:
    logs = db.recent_audit(fresh_actor(), 100)
    with ui.card().classes("soft-card w-full p-4 gap-2"):
        ui.label("NHẬT KÝ HOẠT ĐỘNG QUẢN TRỊ").classes("section-title")
        ui.label("Ghi lại thao tác tạo tài khoản, thay đổi điểm, nhận xét và quản lý tài khoản.").classes("text-sm muted")
        if not logs:
            ui.label("Chưa có hoạt động.").classes("muted")
        for log in logs:
            with ui.row().classes("w-full items-start justify-between border-b border-gray-100 py-2 gap-2"):
                with ui.column().classes("gap-0 flex-1"):
                    ui.label(log["action"]).classes("font-semibold")
                    ui.label(log["details"]).classes("text-sm")
                    ui.label(f"Người thực hiện: {log['actor_name'] or 'Hệ thống'} · Đối tượng: {log['target_name'] or '—'}").classes("text-xs muted")
                ui.label(log["created_at"]).classes("text-xs muted")


def render_personal_records(user: dict) -> None:
    scores, evaluations, total = db.my_records(int(user["id"]))
    with ui.card().classes("soft-card w-full p-4 gap-3"):
        ui.label("HỒ SƠ THI ĐUA CỦA TÔI").classes("section-title")
        with ui.row().classes("items-center gap-2"):
            ui.label("Tổng điểm hiện tại").classes("muted")
            ui.label(f"{total:+g}").classes("text-3xl font-extrabold").style("color:#2457a6")
        ui.separator()
        ui.label("Lịch sử điểm").classes("font-bold")
        if not scores:
            ui.label("Bạn chưa có bản ghi điểm thi đua nào.").classes("text-sm muted")
        for score in scores:
            with ui.row().classes("w-full items-start justify-between border-b border-gray-100 py-2"):
                with ui.column().classes("gap-0 flex-1"):
                    ui.label(f"{score['points']:+g} điểm · {score['category']}").classes("score-positive" if score["points"] > 0 else "score-negative")
                    ui.label(score["note"]).classes("text-sm")
                ui.label(score["created_at"]).classes("text-xs muted")
        ui.separator()
        ui.label("Nhận xét / đánh giá dành cho tôi").classes("font-bold")
        if not evaluations:
            ui.label("Bạn chưa có nhận xét nào.").classes("text-sm muted")
        for evaluation in evaluations:
            with ui.card().classes("w-full bg-gray-50 gap-1"):
                ui.label(evaluation["content"]).classes("whitespace-pre-wrap")
                ui.label(evaluation["created_at"]).classes("text-xs muted")


def render_overview(actor: dict) -> None:
    role = actor["role"]
    with ui.card().classes("soft-card w-full p-4 gap-2"):
        ui.label(f"Xin chào, {actor['full_name']}!").classes("text-2xl font-bold").style("color:#172b4d")
        ui.label(f"Bạn đang đăng nhập với vai trò: {role_text(actor)}.").classes("muted")
        if role == "member":
            ui.label("Bạn chỉ xem được điểm thi đua và nhận xét của chính mình.").classes("text-sm")
    if role in ("founder", "teacher", "leader"):
        summaries = db.group_summaries(actor)
        with ui.grid(columns=2).classes("w-full"):
            for summary in summaries:
                with ui.card().classes("soft-card p-4"):
                    ui.label(f"TỔ {summary['group_no']}").classes("font-bold muted")
                    ui.label(str(summary["member_count"])).classes("text-3xl font-extrabold")
                    ui.label("thành viên đang hoạt động").classes("text-xs muted")
                    ui.label(f"Tổng điểm: {summary['total_points']:+g}").classes("font-semibold")


def render_dashboard(user: dict) -> None:
    with ui.column().classes("app-shell w-full p-5 gap-4"):
        render_header(user)
        ui.separator()
        role = user["role"]
        if role in ("founder", "teacher"):
            with ui.tabs().classes("w-full") as tabs:
                overview_tab = ui.tab("Tổng quan", icon="dashboard")
                group_tab = ui.tab("Các tổ", icon="groups")
                accounts_tab = ui.tab("Tài khoản", icon="manage_accounts")
                audit_tab = ui.tab("Nhật ký", icon="history") if role == "founder" else None
            with ui.tab_panels(tabs, value=overview_tab).classes("w-full bg-transparent"):
                with ui.tab_panel(overview_tab):
                    render_overview(user)
                with ui.tab_panel(group_tab):
                    render_group_management(user)
                with ui.tab_panel(accounts_tab):
                    render_account_management(user)
                if role == "founder" and audit_tab:
                    with ui.tab_panel(audit_tab):
                        render_audit_page(user)
        elif role == "leader":
            with ui.tabs().classes("w-full") as tabs:
                overview_tab = ui.tab("Tổng quan", icon="dashboard")
                group_tab = ui.tab(f"Tổ {user['group_no']} của tôi", icon="groups")
                personal_tab = ui.tab("Điểm của tôi", icon="person")
            with ui.tab_panels(tabs, value=overview_tab).classes("w-full bg-transparent"):
                with ui.tab_panel(overview_tab):
                    render_overview(user)
                with ui.tab_panel(group_tab):
                    render_group_management(user)
                with ui.tab_panel(personal_tab):
                    render_personal_records(user)
        else:
            with ui.tabs().classes("w-full") as tabs:
                overview_tab = ui.tab("Tổng quan", icon="dashboard")
                personal_tab = ui.tab("Điểm & đánh giá của tôi", icon="person")
            with ui.tab_panels(tabs, value=overview_tab).classes("w-full bg-transparent"):
                with ui.tab_panel(overview_tab):
                    render_overview(user)
                    ui.button("Đổi mật khẩu", icon="lock", on_click=lambda: open_change_password_dialog(int(user["id"])) ).props("outline")
                with ui.tab_panel(personal_tab):
                    render_personal_records(user)
        with ui.row().classes("w-full justify-between items-center flex-wrap pt-3"):
            ui.label("Class Merit Hub · Dữ liệu được lưu trong cơ sở dữ liệu riêng của hệ thống.").classes("text-xs muted")
            if role != "member":
                ui.button("Đổi mật khẩu", icon="lock", on_click=lambda: open_change_password_dialog(int(user["id"])) ).props("flat dense")


@ui.page("/")
def index() -> None:
    ui.add_head_html(PAGE_STYLES)
    db.init_db()
    user_id = app.storage.user.get("user_id")
    user = db.get_user_by_id(int(user_id)) if user_id else None
    stored_version = app.storage.user.get("session_version")
    if user and user.get("is_active") and stored_version is not None and int(stored_version) == int(user.get("session_version", 0)):
        render_dashboard(user)
        return
    if user_id:
        app.storage.user.pop("user_id", None)
        app.storage.user.pop("session_version", None)
    if db.founder_exists():
        render_login()
    else:
        render_bootstrap()


if __name__ in {"__main__", "__mp_main__"}:
    db.init_db()
    ui.run(
        title="Class Merit Hub - Quản lý điểm thi đua",
        host=HOST,
        port=PORT,
        storage_secret=STORAGE_SECRET,
        session_middleware_kwargs={"same_site": "lax", "https_only": COOKIE_SECURE, "max_age": 28800},
        reload=False,
        show_welcome_message=True,
    )
