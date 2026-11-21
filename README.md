# Class Merit Hub — Website quản lý điểm thi đua lớp học

Ứng dụng Python + NiceGUI + SQLite để quản lý điểm thi đua, nhận xét và tài khoản của bốn tổ trong một lớp.

## 1. Mô hình phân quyền

| Vai trò | Phạm vi được xem | Quyền chính |
|---|---|---|
| Người sáng lập | Toàn bộ lớp và cả bốn tổ | Quyền cao nhất: tạo/chỉnh sửa tài khoản, quản lý tổ, điểm, nhận xét, khóa/mở tài khoản và xem nhật ký |
| Giáo viên chủ nhiệm | Toàn bộ lớp và cả bốn tổ | Quản lý thành viên, tổ trưởng, điểm và nhận xét; không quản lý tài khoản người sáng lập hoặc tài khoản giáo viên khác |
| Tổ trưởng | Chỉ tổ được phân công | Xem danh sách và hồ sơ thi đua của thành viên trong tổ; thêm thành viên; cộng/trừ, sửa/xóa điểm và nhận xét trong tổ mình |
| Thành viên | Chỉ tài khoản của chính mình | Chỉ xem điểm và nhận xét của bản thân; được tự đổi mật khẩu |

Các giới hạn trên được kiểm tra ở tầng Python/SQLite mỗi lần truy vấn hoặc thay đổi dữ liệu. Việc thay đổi mã tổ hoặc ID trong trình duyệt không cấp thêm quyền. Tổ trưởng Tổ 2 không thể lấy danh sách, điểm hoặc nhận xét của Tổ 1, 3 hay 4.

## 2. Quy tắc tài khoản và mật khẩu

- Mỗi người cần một **mã định danh cá nhân duy nhất** (ví dụ mã học sinh). Cơ sở dữ liệu đặt ràng buộc `UNIQUE` cho cả mã định danh và tên đăng nhập để ngăn cấp trùng tài khoản.
- Mỗi lớp chỉ có một người sáng lập và một giáo viên chủ nhiệm đang hoạt động; mỗi tổ chỉ có một tổ trưởng đang hoạt động.
- Không có mật khẩu mặc định được ghi trong mã nguồn hoặc GitHub.
- Mật khẩu dài tối thiểu 14 ký tự, phải có chữ hoa, chữ thường, chữ số và ký tự đặc biệt; mật khẩu không được chứa tên đăng nhập.
- Mật khẩu được băm bằng **Argon2id**, không lưu dạng văn bản.
- Sau 5 lần đăng nhập sai liên tiếp, tài khoản bị khóa đăng nhập tạm thời 15 phút.
- Phiên đăng nhập hết hạn sau 8 giờ. Đổi mật khẩu, khóa tài khoản hoặc thay đổi vai trò sẽ thu hồi các phiên cũ của tài khoản đó.
- Các thao tác quản trị quan trọng được ghi vào nhật ký.

> Mã định danh cá nhân là khóa để phát hiện một người bị tạo nhiều tài khoản. Người sáng lập/giáo viên cần nhập cùng một mã cho cùng một học sinh, không tự ý đổi mã để tạo tài khoản thứ hai.

## 3. Cài đặt trên Windows / PowerShell

Yêu cầu Python 3.11 trở lên và Git (nếu tải dự án bằng Git).

```powershell
git clone https://github.com/conmeophat/quan_ly_thanh_vien_trong-lop.git
cd quan_ly_thanh_vien_trong-lop
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Tạo **hai chuỗi bí mật khác nhau**. Mỗi lần chạy lệnh sẽ tạo một chuỗi ngẫu nhiên mới:

```powershell
py -c "import secrets; print(secrets.token_urlsafe(48))"
py -c "import secrets; print(secrets.token_urlsafe(48))"
```

Mở file `.env`, thay `NICEGUI_STORAGE_SECRET` bằng chuỗi thứ nhất và `BOOTSTRAP_TOKEN` bằng chuỗi thứ hai. Không gửi hai chuỗi này lên GitHub hoặc cho người khác.

Chạy website:

```powershell
py main.py
```

Mở trình duyệt tại: <http://127.0.0.1:8080>

Có thể dùng script PowerShell:

```powershell
.\run.ps1
```

## 4. Thiết lập tài khoản lần đầu

1. Ở màn hình thiết lập, tạo tài khoản **Người sáng lập**. Nhập đúng `BOOTSTRAP_TOKEN` trong file `.env`; bước này chỉ thực hiện được một lần.
2. Đăng nhập bằng tài khoản người sáng lập.
3. Trong mục **Tài khoản**, tạo tài khoản Giáo viên chủ nhiệm.
4. Tạo lần lượt 4 tài khoản Tổ trưởng, mỗi tài khoản gắn đúng một tổ. Hệ thống từ chối tạo hai tổ trưởng đang hoạt động cho cùng một tổ.
5. Mở mục **Các tổ**, chọn **Thêm thành viên** trong từng tổ để tạo tài khoản cho học sinh. Điền mã định danh riêng, tên đăng nhập và mật khẩu khởi tạo mạnh.
6. Gửi tên đăng nhập và mật khẩu riêng cho đúng người nhận. Không đăng mật khẩu trong nhóm chat chung.

Danh sách học sinh và tên thật chưa được tự điền sẵn vì người vận hành cần cung cấp danh sách chính xác. Bốn tổ 1–4 đã được tích hợp trong ứng dụng.

## 5. Cập nhật điểm và nhận xét

- Tổ trưởng mở tổ của mình, chọn một thành viên, sau đó cộng/trừ điểm và viết nhận xét.
- Giáo viên chủ nhiệm và người sáng lập có thể chọn bất kỳ tổ nào.
- Mỗi lần ghi điểm yêu cầu loại điểm và lý do/minh chứng. Điểm phải khác 0 và nằm trong khoảng -100 đến +100.
- Điểm và nhận xét có thể được sửa hoặc ẩn khỏi hồ sơ; các thao tác này được ghi vào nhật ký quản trị.
- Thành viên chỉ nhìn thấy hồ sơ của tài khoản mình, không có trang tra cứu thành viên khác.

## 6. Kiểm thử phân quyền

Chạy:

```powershell
py -m unittest -v
```

Bộ kiểm thử bao gồm quyền xem dữ liệu giữa các tổ, giới hạn của thành viên, quyền của giáo viên/người sáng lập, trùng tài khoản, khóa đăng nhập và việc thu hồi quyền sau khi tài khoản bị khóa hoặc chỉnh sửa.

## 7. Lưu ý khi triển khai cho cả lớp truy cập

- Repository GitHub chỉ lưu **mã nguồn**. Website cần được chạy trên một máy chủ Python hoặc máy tính luôn bật; GitHub Pages không chạy ứng dụng Python/NiceGUI.
- Bản hiện tại dùng SQLite và phù hợp với một tiến trình ứng dụng trên một máy chủ. Không chạy nhiều bản sao ứng dụng cùng ghi vào một file SQLite.
- Khi đưa lên Internet, cần HTTPS, đặt `COOKIE_SECURE=true`, giữ bí mật `.env`, dùng ổ đĩa bền vững cho thư mục chứa cơ sở dữ liệu và sao lưu định kỳ. Không sử dụng máy chủ có ổ đĩa tạm thời để lưu dữ liệu học sinh.
- Trước khi dùng dữ liệu thật, nên triển khai trên môi trường riêng, kiểm tra HTTPS, sao lưu/khôi phục dữ liệu và rà soát bảo mật theo cấu hình máy chủ thực tế.

## Cấu trúc chính

```text
main.py              # Giao diện NiceGUI và luồng đăng nhập
database.py          # SQLite, dữ liệu, kiểm tra quyền ở máy chủ
security.py          # Argon2id, chính sách mật khẩu, mã thiết lập
test_permissions.py  # Kiểm thử quyền truy cập
requirements.txt     # Thư viện cần cài
.env.example         # Mẫu cấu hình bí mật (không chứa bí mật thật)
run.ps1              # Khởi chạy từ PowerShell
```
