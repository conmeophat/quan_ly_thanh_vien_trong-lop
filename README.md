# Class Merit Hub — Website quản lý điểm thi đua lớp học

Ứng dụng Python + NiceGUI + SQLite để quản lý điểm thi đua, nhận xét và tài khoản của bốn tổ trong một lớp.

## 1. Mô hình phân quyền

| Vai trò | Phạm vi được xem | Quyền chính |
|---|---|---|
| Người sáng lập | Toàn bộ lớp và cả bốn tổ | Quyền cao nhất: tạo/chỉnh sửa tài khoản, quản lý tổ, điểm, nhận xét, khóa/mở tài khoản và xem nhật ký |
| Giáo viên chủ nhiệm | Toàn bộ lớp và cả bốn tổ | Quản lý thành viên, tổ trưởng, điểm và nhận xét; không quản lý tài khoản người sáng lập hoặc tài khoản giáo viên khác |
| Tổ trưởng | Chỉ tổ được phân công | Xem danh sách và hồ sơ thi đua của thành viên trong tổ; thêm thành viên; cộng/trừ, sửa/xóa điểm và nhận xét trong tổ mình |
| Thành viên | Chỉ tài khoản của chính mình | Chỉ xem điểm và nhận xét của bản thân; không có quyền đổi hoặc đặt lại mật khẩu |

Các giới hạn trên được kiểm tra ở tầng Python/SQLite mỗi lần truy vấn hoặc thay đổi dữ liệu. Việc thay đổi mã tổ hoặc ID trong trình duyệt không cấp thêm quyền. Tổ trưởng Tổ 2 không thể lấy danh sách, điểm hoặc nhận xét của Tổ 1, 3 hay 4. Chỉ Người sáng lập và Giáo viên chủ nhiệm được đổi mật khẩu của chính mình hoặc đặt lại mật khẩu cho tài khoản thuộc phạm vi quản lý; Tổ trưởng và Thành viên không có chức năng này.

## 2. Quy tắc tài khoản và mật khẩu

- Mỗi tài khoản sử dụng một **số điện thoại duy nhất** để đăng nhập. Số điện thoại được chuẩn hóa và đặt ràng buộc `UNIQUE` trong cơ sở dữ liệu.
- Mỗi lớp chỉ có một người sáng lập và một giáo viên chủ nhiệm đang hoạt động; mỗi tổ chỉ có một tổ trưởng đang hoạt động.
- Không có mật khẩu mặc định được ghi trong mã nguồn hoặc GitHub.
- Mật khẩu có độ dài tối thiểu 8 ký tự (tối đa 128 ký tự).
- Mật khẩu được băm bằng **Argon2id**, không lưu dạng văn bản.
- Sau 5 lần đăng nhập sai liên tiếp, tài khoản bị khóa đăng nhập tạm thời 15 phút.
- Phiên đăng nhập hết hạn sau 8 giờ. Đổi mật khẩu, khóa tài khoản hoặc thay đổi vai trò sẽ thu hồi các phiên cũ của tài khoản đó.
- Các thao tác quản trị quan trọng được ghi vào nhật ký.

> Một số điện thoại chỉ được gắn với một tài khoản. Người tạo tài khoản cần kiểm tra số điện thoại chính xác trước khi lưu.

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

Tạo một khóa bí mật cho phiên đăng nhập:

```powershell
py -c "import secrets; print(secrets.token_urlsafe(48))"
```

Mở file `.env` và thay giá trị `NICEGUI_STORAGE_SECRET` bằng chuỗi vừa tạo. Không gửi khóa này lên GitHub hoặc cho người khác. Không cần cấu hình mã thiết lập riêng.

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

1. Mở website trực tiếp trên máy tính đang chạy ứng dụng tại `http://127.0.0.1:8080`. Lần tạo đầu tiên chỉ được phép từ kết nối cục bộ.
2. Tạo tài khoản **Người sáng lập** bằng đúng ba trường: họ và tên, số điện thoại, mật khẩu.
3. Đăng nhập bằng số điện thoại và mật khẩu vừa tạo.
4. Trong mục **Tài khoản**, tạo tài khoản Giáo viên chủ nhiệm.
5. Tạo lần lượt 4 tài khoản Tổ trưởng, mỗi tài khoản gắn đúng một tổ. Hệ thống từ chối tạo hai tổ trưởng đang hoạt động cho cùng một tổ.
6. Mở mục **Các tổ**, chọn **Thêm thành viên** để tạo tài khoản. Mỗi tài khoản gồm họ và tên, số điện thoại, mật khẩu; người quản trị chọn thêm vai trò và tổ phù hợp.
7. Gửi số điện thoại và mật khẩu riêng cho đúng người nhận. Không đăng mật khẩu trong nhóm chat chung.

Không có nút quên mật khẩu. Khi thành viên hoặc tổ trưởng quên mật khẩu, họ cần liên hệ Người sáng lập hoặc Giáo viên chủ nhiệm để được đặt lại. Người sáng lập và Giáo viên chủ nhiệm có thể đổi mật khẩu của chính mình.

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
security.py          # Argon2id và chính sách mật khẩu
test_permissions.py  # Kiểm thử quyền truy cập
requirements.txt     # Thư viện cần cài
.env.example         # Mẫu cấu hình khóa phiên (không chứa bí mật thật)
run.ps1              # Khởi chạy từ PowerShell
```


## 8. Triển khai Oracle Cloud Always Free

Dự án đã chuẩn bị hướng dẫn và script triển khai trên Oracle Cloud Always Free: Ubuntu 24.04 ARM64, systemd auto-restart, Caddy HTTPS, DuckDNS miễn phí và SQLite trên ổ lưu trữ bền vững. Hệ thống backup tạo bản SQLite nhất quán, gzip, mã hóa age, kèm checksum SHA-256; lưu bản gần trên VM và OCI Object Storage, đồng thời có thể gửi thêm bản mã hóa sang nhà cung cấp độc lập qua rclone.

Đã bổ sung:
- [deploy/oracle/backup.sh](deploy/oracle/backup.sh): backup mã hóa, checksum, OCI và đích rclone tùy chọn.
- [deploy/oracle/configure_rclone_backup.sh](deploy/oracle/configure_rclone_backup.sh): cấu hình kho sao lưu thứ hai.
- [deploy/oracle/verify_backup.sh](deploy/oracle/verify_backup.sh): kiểm tra checksum, giải mã và SQLite integrity mà không ghi đè dữ liệu chạy.
- [deploy/oracle/restore.sh](deploy/oracle/restore.sh): khôi phục ngay cả khi VM mới chưa cấu hình backup.
- [deploy/oracle/README.md](deploy/oracle/README.md): quy trình phục hồi sau khi VM bị thu hồi/hỏng.

Bắt đầu tại [deploy/oracle/README.md](deploy/oracle/README.md). Các script cài đặt nằm trong [deploy/oracle](deploy/oracle/).

**Giới hạn quan trọng:** Oracle có thể thu hồi máy ảo Always Free bị coi là idle; nhà cung cấp lưu trữ có thể thay đổi quota/chính sách; VM mới có thể không còn capacity. Một VM không có failover/SLA 24/7. Các lớp backup giúp giảm nguy cơ mất dữ liệu và dựng lại hệ thống, nhưng không bảo đảm uptime tuyệt đối hay lưu trữ vĩnh viễn. Dịch vụ lưu trữ thứ hai cần được cấu hình trong tài khoản riêng và vẫn chịu giới hạn của nhà cung cấp đó.

**Không đưa .env, app.env, token DuckDNS, mật khẩu, khóa age riêng, token rclone hoặc file SQLite plaintext lên GitHub.** Chỉ chạy một tiến trình ứng dụng ghi vào SQLite. Giữ khóa age riêng và recipient công khai ở ít nhất hai nơi ngoại tuyến an toàn; nếu mất khóa riêng, các bản backup mã hóa không thể giải mã.
