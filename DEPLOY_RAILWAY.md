# Triển khai Class Merit Hub lên Railway

Hướng dẫn này triển khai ứng dụng từ GitHub bằng Dockerfile hiện có, bật HTTPS và lưu SQLite trên Railway Volume.

> **Khuyến nghị:** Nếu dùng với điểm thi đua và thông tin học sinh thật, hãy chọn Railway Hobby hoặc gói có uptime/volume phù hợp. Free có thể ngủ khi không có truy cập, chỉ có 1 USD tín dụng tài nguyên/tháng và dung lượng volume thấp; Trial có thời hạn. Không coi Trial/Free là nơi lưu hồ sơ lớp học lâu dài.

## A. Chuẩn bị hai bí mật

Tạo hai chuỗi độc lập trên máy Windows bằng PowerShell. Chạy lệnh mỗi dòng một lần, lưu kết quả trong trình quản lý mật khẩu:

```powershell
py -c "import secrets; print(secrets.token_urlsafe(48))"
py -c "import secrets; print(secrets.token_urlsafe(48))"
```

Dòng thứ nhất dùng cho `NICEGUI_STORAGE_SECRET`; dòng thứ hai dùng cho `BOOTSTRAP_TOKEN`. **Không gửi hai giá trị này trong chat, không commit vào GitHub và không đặt trong file mã nguồn.**

## B. Tạo dịch vụ từ GitHub

1. Đăng nhập Railway bằng tài khoản của bạn.
2. Chọn **New Project** → **Deploy from GitHub Repo**.
3. Kết nối GitHub nếu Railway yêu cầu, rồi chọn repository `conmeophat/quan_ly_thanh_vien_trong-lop`, nhánh `main`.
4. Để Railway build bằng `Dockerfile` ở thư mục gốc. Không chọn static site.
5. Sau khi dịch vụ được tạo, mở dịch vụ đó và chọn tab **Variables**. Thêm các biến dưới đây.

| Variable | Value |
|---|---|
| `HOST` | `0.0.0.0` |
| `COOKIE_SECURE` | `true` |
| `DATABASE_PATH` | `/data/class_tracker.sqlite3` |
| `NICEGUI_STORAGE_SECRET` | Chuỗi bí mật thứ nhất đã tạo |
| `BOOTSTRAP_TOKEN` | Chuỗi bí mật thứ hai đã tạo |

Railway tự cấp biến `PORT`; không đặt một giá trị cố định cho biến này. Ứng dụng đọc `PORT` do Railway cấp.

## C. Gắn ổ dữ liệu bền vững

Đây là bước bắt buộc để dữ liệu không nằm trên ổ đĩa tạm của container.

1. Trong Project Canvas, mở menu tạo tài nguyên hoặc Command Palette và tạo **Volume**.
2. Kết nối Volume với đúng service chạy ứng dụng.
3. Đặt **Mount Path** chính xác là `/data`.
4. Giữ nguyên Volume này giữa các lần deploy. Không chọn Wipe Volume, không xóa Volume khi tạo deployment mới.

Ứng dụng đã cấu hình đường dẫn SQLite theo biến `DATABASE_PATH`. Khi Volume được gắn vào `/data`, cơ sở dữ liệu sẽ nằm tại `/data/class_tracker.sqlite3`.

## D. Cấu hình kiểm tra sức khỏe và khởi động

Trong Settings/Deploy của service, kiểm tra:

- Start command: `python main.py` (hoặc để Dockerfile chạy lệnh CMD mặc định).
- Healthcheck path: `/healthz`.
- Restart policy: `On Failure`.
- Chỉ chạy **một replica**. SQLite trên một Volume không được chia sẻ cho nhiều replica ứng dụng cùng ghi đồng thời.

Mã nguồn đã có endpoint `/healthz`, endpoint này chỉ trả về trạng thái sức khỏe và không tiết lộ dữ liệu người dùng.

## E. Cấp tên miền HTTPS

1. Mở Settings → Networking → Public Networking.
2. Chọn **Generate Domain**.
3. Dùng hostname `.up.railway.app` do Railway cung cấp. Railway tự cấp và gia hạn chứng chỉ SSL cho domain được tạo.
4. Khi deployment đã Ready, mở `https://TEN-MIEN.up.railway.app/healthz`. Kết quả mong đợi là:

```json
{"status":"ok"}
```

5. Mở `https://TEN-MIEN.up.railway.app/`. Nếu chưa có người sáng lập, màn hình **Thiết lập hệ thống lần đầu** sẽ xuất hiện.

Không gửi mật khẩu hoặc mã thiết lập lên chat. Hãy nhập `BOOTSTRAP_TOKEN` trong màn hình khởi tạo, tạo mật khẩu người sáng lập mạnh và giữ lại thông tin đăng nhập ở nơi an toàn.

## F. Tạo tài khoản lớp

Đăng nhập bằng người sáng lập, sau đó:

1. Tạo tài khoản giáo viên chủ nhiệm.
2. Tạo một tổ trưởng cho từng tổ 1, 2, 3, 4.
3. Trong mỗi tổ, dùng nút **Thêm thành viên** để tạo từng tài khoản học sinh.
4. Gửi thông tin đăng nhập riêng cho đúng người nhận; yêu cầu mỗi người đổi mật khẩu sau lần đăng nhập đầu tiên.

## G. Kiểm tra trước khi dùng dữ liệu thật

Tạo tài khoản thử nghiệm và kiểm tra tất cả các tình huống sau:

- Thành viên chỉ xem được trang điểm và nhận xét của chính mình.
- Tổ trưởng Tổ 2 chỉ thấy danh sách Tổ 2; thử mở ID của thành viên Tổ 1 phải bị từ chối.
- Tổ trưởng Tổ 2 không tạo, sửa, cộng/trừ hay xóa được điểm của thành viên Tổ 1.
- Tổ trưởng Tổ 2 không thấy tab quản lý tài khoản của toàn lớp hoặc nhật ký quản trị.
- Giáo viên chủ nhiệm xem và quản lý được cả bốn tổ.
- Người sáng lập xem và quản lý được cả bốn tổ và nhật ký.
- Khóa một tài khoản đang đăng nhập phải khiến phiên cũ bị thu hồi.
- Thử thêm một bản ghi điểm, khởi động lại/redeploy service rồi xác nhận bản ghi vẫn còn. Đây là phép thử quan trọng cho Volume.

Chỉ nhập danh sách học sinh thật sau khi các tình huống trên đã được xác minh trên domain HTTPS.

## H. Sao lưu và vận hành

- Sao lưu Volume định kỳ và giữ ít nhất một bản sao ngoài Railway. Thử khôi phục bản sao trên môi trường thử nghiệm trước khi cần dùng thật.
- Không xóa Volume hoặc thay `DATABASE_PATH` khi đang có dữ liệu.
- Không tăng replicas vượt 1 với cấu hình SQLite hiện tại.
- Bảo vệ tài khoản Railway bằng mật khẩu mạnh và xác thực đa yếu tố nếu có.
- Theo dõi usage/billing. Hobby có mức phí tối thiểu 5 USD/tháng và bao gồm 5 USD tín dụng tài nguyên; nếu mức tiêu thụ vượt phần bao gồm thì chi phí có thể tăng.
- Trước khi cập nhật lớn, sao lưu file SQLite và kiểm tra khả năng khôi phục.

## Trạng thái

Repository đã có Dockerfile, cấu hình host mặc định phù hợp container, health endpoint `/healthz`, và file loại trừ dữ liệu/mật khẩu cục bộ. Việc tạo Project, gắn Volume, nhập Variables và sinh domain phải thực hiện trong tài khoản Railway của chủ sở hữu; không có bí mật hoặc dữ liệu học sinh nào được đưa vào GitHub.
