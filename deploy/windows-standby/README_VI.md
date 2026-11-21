# Oracle Cloud chính + Windows tại nhà dự phòng

Cập nhật: 22/11/2026

Tài liệu này triển khai mô hình **cold standby**: Oracle Cloud phục vụ website chính; máy Windows tại nhà tự tải các bản backup mã hóa và có thể khôi phục ứng dụng khi VM Oracle bị mất.

Đây không phải failover tự động. Người quản trị phải quyết định chuyển đổi, phục hồi database, đổi DNS và bật reverse proxy. Không cho hai máy cùng lúc ghi vào một database hoặc cùng cập nhật một hostname.

## 1. Kiến trúc

~~~text
                  GitHub
          (mã nguồn + kiểm thử)
                    |
                    v
           Oracle Cloud VM A1
             (website chính)
                    |
         SQLite online backup
           + gzip + age
                    |
          +---------+----------+
          |                    |
          v                    v
    OCI Object Storage    Kho rclone độc lập
    (cùng tenancy)        (tài khoản khác)
                               |
                         Đồng bộ mỗi ngày
                               |
                               v
                       Windows tại nhà
                    (bản sao mã hóa cục bộ)
                               |
                    Khi Oracle bị sự cố
                               |
                    xác minh + giải mã
                               |
                    SQLite trên Windows
                               |
                    Python + NiceGUI
                               |
                DuckDNS + Caddy HTTPS (tùy
                điều kiện router/ISP tại nhà)
~~~

Windows không cần chạy website thường trực. Nó chỉ cần bật định kỳ để tải và kiểm tra bản backup. Điều này giảm điện năng và không phụ thuộc vào lượng truy cập của website chính.

## 2. Điều kiện trước khi thực hiện

- Repository đã được clone trên máy Windows.
- Python launcher py và Git đã cài.
- Có quyền truy cập kho rclone độc lập đã được cấu hình trên Oracle.
- Có **khóa age riêng** tương ứng với backup recipient đã dùng khi mã hóa. Khóa riêng phải được lấy từ bản sao ngoại tuyến do chủ dự án tự giữ. Không tải khóa riêng từ GitHub và không gửi qua chat.
- Windows có đủ dung lượng đĩa để lưu vài bản backup.
- Máy Windows được bật và có Internet tại thời điểm đồng bộ.

Nếu chưa cấu hình kho rclone độc lập trên Oracle, làm theo mục 7.6 trong [Oracle deployment README](../oracle/README.md). Đích rclone phải thuộc nhà cung cấp/tài khoản độc lập với OCI tenancy. Script backup trên Oracle lưu file dạng class-merit-YYYYMMDDTHHMMSSZ.sqlite3.gz.age và file .sha256 bên cạnh.

## 3. Cài công cụ trên Windows

Mở PowerShell:

~~~powershell
winget install --id Rclone.Rclone
~~~

Đóng và mở lại PowerShell, kiểm tra:

~~~powershell
rclone version
~~~

Cài age từ trang phát hành chính thức: https://github.com/FiloSottile/age/releases. Tải gói Windows đúng kiến trúc (thông thường windows-amd64), giải nén age.exe vào thư mục riêng, rồi thêm thư mục đó vào PATH. Kiểm tra:

~~~powershell
age --version
~~~

Tài liệu rclone chính thức có hướng dẫn cài bản Windows và cấu hình remote: https://rclone.org/install/.

## 4. Cấu hình quyền đọc backup trên máy Windows

Trên máy Windows, chạy:

~~~powershell
rclone config
~~~

Tạo remote trỏ tới **cùng tài khoản lưu trữ độc lập** đang nhận backup từ Oracle. Ví dụ tên remote là gdrive và thư mục backup là ClassMeritHub; đường dẫn đầy đủ:

~~~text
gdrive:ClassMeritHub
~~~

Tên trên chỉ là ví dụ. Dùng đúng remote/path đã cấu hình trên máy chủ. Rclone lưu thông tin OAuth/API trong hồ sơ người dùng Windows; giữ file cấu hình ở chế độ riêng tư, không đưa lên GitHub hoặc gửi qua chat.

Kiểm tra remote có nhìn thấy file:

~~~powershell
rclone lsf --files-only gdrive:ClassMeritHub
~~~

Thay gdrive:ClassMeritHub bằng RemotePath của bạn. Cần thấy file backup và file checksum. Nếu không có file, hãy cấu hình và chạy thành công backup trên Oracle trước.

## 5. Chuẩn bị ứng dụng dự phòng

Từ thư mục gốc repository:

~~~powershell
.\deploy\windows-standby\setup_standby.ps1
~~~

Nếu PowerShell chặn script trong phiên hiện tại, chỉ cho phép script ở đúng cửa sổ này:

~~~powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
~~~

Script tạo .venv, cài thư viện và tạo .env riêng cho Windows khi chưa có. Nếu .env đã tồn tại, script không ghi đè khóa bí mật hoặc cấu hình hiện tại.

Mặc định ứng dụng Windows nghe ở 127.0.0.1:8080 và database nằm ở data\class_tracker.sqlite3. Đây là cấu hình local an toàn; chưa công khai website ra Internet.

## 6. Lưu khóa giải mã age an toàn

Khóa riêng age thường có tên như class-merit-backup-identity.txt. Đặt file này ngoài thư mục Git, ưu tiên USB ngoại tuyến có bảo vệ, ví dụ:

~~~text
E:\ClassMeritRecovery\class-merit-backup-identity.txt
~~~

Không đặt khóa riêng trong repository hoặc thư mục được đồng bộ công khai. Giữ ít nhất một bản ngoại tuyến thứ hai ở nơi an toàn. Nếu mất khóa riêng, file backup mã hóa không thể giải mã.

Không dùng khóa riêng do một script mới tự tạo nếu backup trên Oracle đã mã hóa với recipient khác. Khóa phải khớp với bản backup hiện có.

## 7. Tải và xác minh backup mới nhất

Chạy thủ công lần đầu, thay remote path cho đúng:

~~~powershell
.\deploy\windows-standby\sync_backup.ps1 -RemotePath "gdrive:ClassMeritHub"
~~~

File được tải vào:

~~~text
%LOCALAPPDATA%\ClassMeritHub\backups
~~~

Script chọn file backup mới nhất theo timestamp UTC, tải cả .sha256, tính lại SHA-256 và từ chối file sai checksum. Mặc định chỉ giữ 30 bản trên Windows.

### Tự động đồng bộ mỗi ngày

Sau khi chạy đồng bộ thành công ít nhất một lần, đăng ký Scheduled Task:

~~~powershell
.\deploy\windows-standby\register_backup_sync_task.ps1 -RemotePath "gdrive:ClassMeritHub" -RunAt "04:00"
~~~

Task chạy mỗi ngày lúc 04:00 theo giờ Windows với tài khoản người dùng hiện tại. Windows phải bật và người dùng phải đăng nhập. Nếu lỡ thời điểm chạy, Task Scheduler được cấu hình StartWhenAvailable để chạy bù khi điều kiện cho phép.

Kiểm tra trạng thái:

~~~powershell
Get-ScheduledTask -TaskName "ClassMeritHub-BackupSync"
Get-ScheduledTaskInfo -TaskName "ClassMeritHub-BackupSync"
~~~

Xem log tại %LOCALAPPDATA%\ClassMeritHub\backups\sync.log.

## 8. Diễn tập phục hồi trên môi trường dự phòng

Không nên đợi Oracle bị thu hồi mới thử lần đầu. Hãy thực hiện một lần trước khi đưa dữ liệu lớp thật vào hệ thống.

Trong lần diễn tập đầu tiên, cần nhớ thao tác phục hồi thay thế file database tại đích. Nếu đã có dữ liệu trên Windows, snapshot cũ sẽ được tạo trước khi thay.

~~~powershell
.\deploy\windows-standby\restore_latest.ps1 -RemotePath "gdrive:ClassMeritHub" -AgeIdentity "E:\ClassMeritRecovery\class-merit-backup-identity.txt"
~~~

Script:
1. Đồng bộ bản backup mới nhất và kiểm tra SHA-256.
2. Dùng age giải mã file.
3. Giải nén gzip.
4. Chạy SQLite PRAGMA integrity_check và kiểm tra các bảng cốt lõi.
5. Kiểm tra cổng 8080 chưa có ứng dụng đang chạy.
6. Tạo snapshot SQLite nhất quán của database cũ nếu có.
7. Chỉ sau các bước trên mới thay database dự phòng.

Sau khi phục hồi thành công, chạy:

~~~powershell
.\deploy\windows-standby\run_standby.ps1
~~~

Mở http://127.0.0.1:8080/healthz; kết quả mong đợi là {"status":"ok"}. Đăng nhập bằng tài khoản lớp và kiểm tra một số hồ sơ, điểm và nhật ký. Không dùng dữ liệu giả để ghi lên database thật.

## 9. Chuyển website công khai từ Oracle sang Windows khi có sự cố

Đây là quy trình **chuyển đổi thủ công**, không phải DNS failover tự động.

### 9.1. Xác định Oracle thực sự không còn phục vụ

- Kiểm tra domain và /healthz từ mạng khác.
- Kiểm tra trạng thái VM và dịch vụ trong OCI Console.
- Nếu VM vẫn hoạt động nhưng ứng dụng lỗi, xử lý/restart Oracle trước khi chuyển.
- Nếu Oracle còn truy cập được, dừng DuckDNS timer để nó không ghi đè IP nhà sau khi chuyển:

~~~bash
sudo systemctl disable --now class-merit-duckdns.timer
~~~

Nếu VM đã bị thu hồi và không thể SSH, không cần cố chạy lệnh này; kiểm tra DNS để đảm bảo IP nhà không bị một máy cũ còn sống cập nhật lại.

### 9.2. Phục hồi database mới nhất

- Đảm bảo file backup mới nhất đã được đồng bộ sau lần ghi dữ liệu gần nhất có thể lấy được.
- Chạy restore_latest.ps1.
- Mở file .env và đổi COOKIE_SECURE=true trước khi dùng qua HTTPS công khai. Giữ HOST=127.0.0.1.
- Chạy ứng dụng và kiểm tra /healthz, đăng nhập và dữ liệu mẫu.
- Ghi nhận thời điểm backup: các thay đổi sau thời điểm này có thể chưa xuất hiện trên máy dự phòng.

### 9.3. Cấp đường truy cập Internet vào nhà

**Cách A — có public IPv4 và router hỗ trợ port forwarding**

1. Kiểm tra WAN IPv4 hiển thị trên router có trùng với public IPv4 bên ngoài hay không. Nếu khác hoặc nằm trong CGNAT, port forwarding thường không hoạt động.
2. Gán IP LAN cố định cho máy Windows.
3. Trên router, forward TCP 80 và TCP 443 tới IP LAN của máy Windows.
4. Mở TCP 80 và 443 trong Windows Firewall.
5. Cài Caddy trên Windows và đảm bảo caddy.exe có trong PATH.
6. Cập nhật DuckDNS tới IP công khai của mạng nhà:

~~~powershell
.\deploy\windows-standby\update_duckdns.ps1 -Subdomain "TEN-SUBDOMAIN"
~~~

Script hỏi token ở chế độ ẩn, chỉ cập nhật IP và không lưu token ra file. Không gõ token vào URL hoặc gửi qua chat.

7. Mở website trong cửa sổ PowerShell thứ nhất:

~~~powershell
.\deploy\windows-standby\run_standby.ps1
~~~

8. Mở cửa sổ PowerShell thứ hai, chạy Caddy:

~~~powershell
.\deploy\windows-standby\run_public_standby.ps1 -Domain "TEN-SUBDOMAIN.duckdns.org"
~~~

Caddy tự xin/gia hạn HTTPS khi DNS trỏ đúng về IP nhà và cổng 80/443 truy cập được từ Internet. Hướng dẫn chính thức: https://caddyserver.com/docs/automatic-https.

**Cách B — nhà mạng dùng CGNAT hoặc không mở được cổng**

Có thể dùng Cloudflare Tunnel, nhưng để publish hostname ổn định, cần một domain được quản lý trên Cloudflare và thiết lập tunnel riêng trên máy Windows. DuckDNS subdomain không thể thay thế yêu cầu domain trong zone Cloudflare.

Tài liệu chính thức: https://developers.cloudflare.com/tunnel/get-started/. Tunnel tạo kết nối đi ra từ máy nhà, không cần mở inbound port, nhưng không cấp máy tính, điện hoặc Internet. Domain riêng có thể có phí mua/gia hạn.

Nếu chưa có public IPv4 hoặc domain trên Cloudflare, máy Windows vẫn là bản dự phòng dữ liệu và có thể chạy local; chưa thể khẳng định cả thế giới truy cập được từ máy này.

## 10. Bắt buộc kiểm tra sau khi chuyển

- Domain HTTPS trỏ tới máy Windows, không còn trỏ tới Oracle.
- /healthz trả HTTP 200.
- Tài khoản Founder đăng nhập được.
- Điểm, nhận xét, thành viên và nhật ký cũ hiển thị đầy đủ.
- Cập nhật quyền DNS để chỉ máy đang làm primary được phép cập nhật địa chỉ.
- Không bật đồng thời hai website cho người dùng ghi dữ liệu. Khi Oracle phục hồi, giữ nó ở chế độ dừng/maintenance cho tới khi có kế hoạch đồng bộ dữ liệu phát sinh trên Windows ngược về Oracle.

## 11. Giới hạn và bảo vệ dữ liệu

- Đây là cold standby: DNS, restore và khởi động reverse proxy cần thao tác thủ công; không có tự động phát hiện sự cố hay failover không gián đoạn.
- Dữ liệu dự phòng chỉ mới nhất bằng lần backup đã tải. Backup Oracle hiện chạy hàng ngày; vì vậy có thể mất các thay đổi xảy ra sau bản backup cuối.
- Không chạy hai instance NiceGUI cùng ghi vào một file SQLite được đồng bộ qua cloud.
- Không đồng bộ file SQLite đang mở bằng OneDrive/Google Drive; chỉ đồng bộ file backup .age đã đóng và checksum.
- Backup mã hóa ở nhà cung cấp độc lập vẫn không thay thế bản khóa age ngoại tuyến.
- Không có dịch vụ miễn phí nào bảo đảm uptime hoặc lưu trữ vĩnh viễn.

## Nguồn chính thức

- Oracle idle compute reclamation: https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- DuckDNS update API: https://www.duckdns.org/spec.jsp
- Rclone Windows install: https://rclone.org/install/
- age source/releases: https://github.com/FiloSottile/age/releases
- Caddy automatic HTTPS: https://caddyserver.com/docs/automatic-https
- Cloudflare Tunnel requirements: https://developers.cloudflare.com/tunnel/get-started/
