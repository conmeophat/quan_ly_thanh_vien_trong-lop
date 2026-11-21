# Oracle Cloud Always Free — triển khai Class Merit Hub

Kiến trúc này ưu tiên chi phí 0 đồng trong hạn mức Always Free, không cam kết uptime tuyệt đối. Các bước tạo tài khoản Oracle, VM, mạng, bucket và IAM phải được thực hiện trong tài khoản OCI của chủ sở hữu.

## 1. Tài nguyên nên chọn

Trong Oracle Cloud Console, tạo VM tại **home region** của tenancy và chỉ chọn tài nguyên hiển thị nhãn **Always Free Eligible**:

| Thành phần | Cấu hình gợi ý |
|---|---|
| Shape | VM.Standard.A1.Flex (Ampere ARM64) |
| CPU/RAM | 2 OCPU, 12 GB RAM tổng hạn mức A1 Always Free |
| Hệ điều hành | Ubuntu 24.04 LTS ARM64, không chọn Minimal Ubuntu cho Ampere |
| Boot Volume | 50 GB |
| Data Volume | 100 GB, gắn thêm và mount tại /srv/class-merit-data |
| Object Storage | Bucket riêng tư, 20 GB tổng Always Free |
| DNS | DuckDNS subdomain miễn phí |
| HTTPS | Caddy tự cấp chứng chỉ Let's Encrypt |

Oracle hiện công bố 2 OCPU và 12 GB RAM tổng cho A1 Always Free; 200 GB tổng Block Volume (bao gồm boot volume) và tối đa 5 backup volume; Object Storage Always Free là 20 GB tổng hợp các tier Standard, Infrequent và Archive. Tài nguyên phải ở home region. Nếu không còn capacity A1, chờ hoặc thử availability domain khác; không chuyển sang shape trả phí nếu mục tiêu vẫn là 0 đồng.

Tài liệu giới hạn chính thức:
https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm

## 2. Tạo VM và mở mạng

1. Tạo Ubuntu 24.04 LTS ARM64 VM bằng shape A1.Flex (trong Always Free limits).
2. Gán public IPv4 cho VM; lưu lại IP.
3. Dùng SSH key riêng, không bật đăng nhập SSH bằng mật khẩu.
4. Tạo/kiểm tra VCN có Internet Gateway, public subnet và default route đi qua Internet Gateway.
5. Trong Network Security Group hoặc Security List, mở các cổng sau:

| Source | Protocol | Port | Mục đích |
|---|---|---:|---|
| IP công cộng của bạn/32 | TCP | 22 | Quản trị SSH |
| 0.0.0.0/0 | TCP | 80 | Cấp/chuyển hướng HTTPS |
| 0.0.0.0/0 | TCP | 443 | Website HTTPS |

Không mở cổng 8080 ra Internet. Ứng dụng chỉ nghe trên localhost, Caddy nhận HTTPS rồi proxy nội bộ.

Nếu dùng SSH từ IP thay đổi thường xuyên, cập nhật quy tắc trước khi kết nối lại. Không để cổng 22 mở toàn Internet khi có thể giới hạn theo IP của bạn.

## 3. Gắn ổ dữ liệu riêng

Boot volume vẫn lưu bền vững qua việc restart máy ảo và deploy code. Để dễ khôi phục hơn, có thể gắn thêm Block Volume 100 GB (tổng boot + data vẫn không quá 200 GB):

1. Trong OCI Console, tạo Block Volume 100 GB cùng home region, gắn vào VM.
2. SSH vào VM và xác định đúng thiết bị mới bằng:

~~~bash
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT
~~~

3. Chỉ với ổ mới, trống hoàn toàn, chạy script. Tên thiết bị chỉ là ví dụ; cần thay bằng thiết bị vừa xác định:

~~~bash
git clone https://github.com/conmeophat/quan_ly_thanh_vien_trong-lop.git
cd quan_ly_thanh_vien_trong-lop
sudo bash deploy/oracle/attach_data_volume.sh /dev/oracleoci/oraclevdb
~~~

Script yêu cầu nhập xác nhận chính xác trước khi format và sẽ từ chối nếu phát hiện filesystem hoặc mount hiện hữu. Format sẽ xóa dữ liệu trên thiết bị được chọn. Tuyệt đối không chạy với boot disk hoặc ổ có dữ liệu.

Ổ sẽ được mount qua UUID tại /srv/class-merit-data. Nếu không tạo được data volume, trình cài đặt tự dùng boot volume tại /var/lib/class-merit-hub; dữ liệu vẫn tồn tại qua restart thông thường.

## 4. Chuẩn bị tên miền HTTPS miễn phí

1. Tạo tài khoản và subdomain miễn phí tại https://www.duckdns.org/.
2. Sao chép token DuckDNS. Không gửi token này qua chat và không commit vào GitHub.
3. Trỏ bản ghi A tới public IPv4 của VM. Script sẽ cập nhật IP tự động mỗi 5 phút bằng DuckDNS API.
4. Đảm bảo cổng 80 và 443 được mở ở cả OCI Network Security Group/Security List lẫn UFW trên Ubuntu.

DuckDNS API:
https://www.duckdns.org/spec.jsp

## 5. Cài đặt website

Từ thư mục repository vừa clone, chạy:

~~~bash
sudo bash deploy/oracle/install_ubuntu.sh
~~~

Script sẽ hỏi subdomain và token DuckDNS. Sau đó tự động:

- Cài Python, Caddy, age, sqlite3, UFW, Fail2ban và công cụ hệ thống.
- Clone phiên bản main mới nhất vào /opt/class-merit-hub.
- Tạo virtual environment và cài requirements.
- Tạo user hệ thống riêng classmerit, không có quyền đăng nhập.
- Tạo các bí mật NICEGUI_STORAGE_SECRET và BOOTSTRAP_TOKEN ngẫu nhiên trong /etc/class-merit-hub/app.env.
- Đặt DATABASE_PATH trên data volume nếu đã mount trước; nếu không thì trên boot volume.
- Chạy ứng dụng bằng systemd, tự khởi động lại khi lỗi.
- Chỉ bind ứng dụng ở 127.0.0.1:8080.
- Thiết lập Caddy reverse proxy, HTTPS, security headers và log xoay vòng.
- Cài timer cập nhật DuckDNS và bật Fail2ban/UFW.

Nếu script hỏi SSH source CIDR, nhập public IP hiện tại của bạn với /32. Để trống sẽ mở SSH từ mọi IPv4 và kém an toàn hơn.

Sau khi cài, domain có dạng:

https://TEN-SUBDOMAIN.duckdns.org

Kiểm tra:

~~~bash
curl -i https://TEN-SUBDOMAIN.duckdns.org/healthz
sudo systemctl status class-merit-hub caddy --no-pager
sudo journalctl -u class-merit-hub -n 100 --no-pager
sudo journalctl -u caddy -n 100 --no-pager
~~~

Đầu ra health check mong đợi: {"status":"ok"}. Endpoint kiểm tra cả tiến trình ứng dụng và truy vấn SQLite; lỗi cơ sở dữ liệu sẽ trả HTTP 503.

Nếu chứng chỉ chưa cấp, kiểm tra DNS đã phân giải về đúng public IP và cả hai lớp firewall đều mở cổng 80/443. Việc cấp chứng chỉ cần DNS và mạng hoạt động.

## 6. Tạo tài khoản người sáng lập

Installer tạo một token thiết lập ban đầu và lưu ở file root-only:

~~~bash
sudo cat /root/class-merit-bootstrap-token.txt
~~~

Nhập token tại màn hình thiết lập người sáng lập trên website HTTPS, tạo tên đăng nhập và mật khẩu mạnh, rồi xóa token:

~~~bash
sudo shred -u /root/class-merit-bootstrap-token.txt
~~~

Không gửi token hoặc mật khẩu cho người khác. Lưu thông tin người sáng lập trong trình quản lý mật khẩu.

## 7. Thiết lập backup mã hóa sang Object Storage

### 7.1. Tạo bucket riêng tư

Trong OCI Console:
- Mở Storage → Object Storage & Archive Storage → Buckets.
- Tạo bucket riêng tư ví dụ class-merit-backups tại home region.
- Không bật Public Access.
- Giữ bucket trong compartment mà bạn kiểm soát.

### 7.2. Cấp quyền cho đúng VM

Tạo Dynamic Group, ví dụ ClassMeritBackupWriter. Matching rule chỉ nên khớp đúng instance của website:

~~~text
instance.id = 'ocid1.instance.oc1....'
~~~

Thay bằng OCID thật của VM, không dùng OCID người dùng.

Tạo IAM Policy trong bucket compartment (hoặc compartment tổ tiên) với quyền giới hạn đúng tên bucket:

~~~text
Allow dynamic-group ClassMeritBackupWriter to manage objects in compartment <COMPARTMENT_NAME> where target.bucket.name = 'class-merit-backups'
~~~

Thay bằng dynamic group, compartment và bucket thật. Quyền manage objects cho phép thao tác đối tượng trong bucket chỉ định; giữ bảo mật tài khoản OCI và không chia sẻ quyền quản trị tenancy.

OCI có thể cần thời gian để cập nhật matching rule/policy. Sau khi cấp quyền, vào VM và chạy script cấu hình backup.

### 7.3. Cấu hình tự động

Từ thư mục repository trên VM:

~~~bash
cd /opt/class-merit-hub
sudo bash deploy/oracle/configure_backup.sh
~~~

Script sẽ:
1. Cài OCI CLI trong virtual environment riêng.
2. Xác minh VM có thể dùng Instance Principal.
3. Xác minh bucket đã tồn tại và có quyền truy cập.
4. Tạo khóa age: máy chủ chỉ dùng khóa công khai để mã hóa.
5. Cấu hình systemd timer chạy mỗi ngày khoảng 02:30 giờ Việt Nam (19:30 UTC).
6. Thực hiện một bản backup đầu tiên ngay lúc cài.

Mỗi bản backup dùng SQLite online backup API để tạo bản nhất quán, chạy PRAGMA integrity_check, gzip rồi mã hóa age trước khi upload. Bucket chỉ nhận file mã hóa, không nhận database plaintext. Mỗi file mã hóa có thêm checksum SHA-256 để phát hiện lỗi truyền tải hoặc hỏng file.

Script giữ 14 ngày bản mã hóa trên máy chủ và 60 bản backup mới nhất trên Object Storage. Hạn mức Object Storage Always Free hiện là 20 GB; cần theo dõi dung lượng bucket và số lượng backup thực tế.

### 7.4. Cất khóa giải mã ngoại tuyến

Khóa riêng được tạo ở:

/root/class-merit-backup-identity.txt

Sao chép **cả khóa riêng và khóa công khai (recipient)** ra máy tính cá nhân/USB an toàn, tách khỏi VM và GitHub. Khóa công khai không bí mật nhưng cần giữ để VM mới tiếp tục mã hóa bằng đúng khóa cũ. Ví dụ nếu tài khoản SSH mặc định là ubuntu:

~~~bash
sudo cp /root/class-merit-backup-identity.txt /home/ubuntu/
sudo chown ubuntu:ubuntu /home/ubuntu/class-merit-backup-identity.txt
sudo chmod 600 /home/ubuntu/class-merit-backup-identity.txt
sudo cp /etc/class-merit-hub/backup-recipient.txt /home/ubuntu/class-merit-backup-recipient.txt
sudo chown ubuntu:ubuntu /home/ubuntu/class-merit-backup-recipient.txt
sudo chmod 600 /home/ubuntu/class-merit-backup-recipient.txt
~~~

Từ PowerShell trên Windows:

~~~powershell
scp ubuntu@YOUR_VM_PUBLIC_IP:/home/ubuntu/class-merit-backup-identity.txt .
scp ubuntu@YOUR_VM_PUBLIC_IP:/home/ubuntu/class-merit-backup-recipient.txt .
~~~

Giữ ít nhất hai bản sao ngoại tuyến an toàn. Mất khóa riêng đồng nghĩa không thể giải mã các bản backup. Khóa recipient có thể được dùng để tiếp tục mã hóa backup mới bằng cùng cặp khóa.

Sau khi tải xuống và xác minh khóa đã lưu an toàn, xóa các bản khóa riêng trên VM:

~~~bash
sudo shred -u /root/class-merit-backup-identity.txt
sudo shred -u /home/ubuntu/class-merit-backup-identity.txt
~~~

Khi đó máy chủ chỉ giữ khóa công khai trong /etc/class-merit-hub/backup-recipient.txt và vẫn mã hóa được backup. Không xóa bản ngoại tuyến. Khi cần khôi phục, tải khóa riêng trở lại VM tạm thời, dùng nó để giải mã, rồi xóa bản tạm sau khi khôi phục thành công.

### 7.5. Kiểm tra backup

~~~bash
sudo systemctl start class-merit-backup.service
sudo systemctl status class-merit-backup.service --no-pager
sudo systemctl list-timers class-merit-backup.timer
sudo ls -lh /var/backups/class-merit-hub/
~~~

Mở OCI Console và xác nhận file mới xuất hiện trong bucket. Phải chạy thử giải mã/khôi phục trên môi trường test trước khi đưa dữ liệu học sinh thật vào sử dụng.

### 7.6. Thêm một bản sao ở nhà cung cấp độc lập (khuyến nghị)

OCI Object Storage và VM nằm trong cùng tenancy, vì vậy chúng không đủ độc lập nếu toàn bộ tài khoản OCI bị khóa hoặc mất quyền truy cập. Có thể thêm một kho lưu trữ của nhà cung cấp khác, ở một tài khoản riêng. Script dùng rclone; dữ liệu được age mã hóa trước khi rời VM.

~~~bash
sudo bash /opt/class-merit-hub/deploy/oracle/configure_rclone_backup.sh
~~~

Trong giao diện rclone, cấu hình remote của dịch vụ lưu trữ thứ hai. Ví dụ tên remote/path có thể là `gdrive:ClassMeritHub`; đây chỉ là ví dụ, không phải khẳng định mọi dịch vụ đều có gói miễn phí vĩnh viễn. Sau khi cấu hình, nhập remote/path vào script.

- Dùng nhà cung cấp và tài khoản độc lập với OCI; một bucket thứ hai trong cùng tenancy không giải quyết rủi ro mất tenancy.
- Chỉ file `.age` đã mã hóa và checksum được tải lên; database SQLite thô và khóa giải mã không được tải lên.
- Rclone xác minh checksum sau khi upload và giữ tối đa 60 bản backup mới nhất theo mặc định.
- Quota, giới hạn API, chính sách tài khoản và điều kiện miễn phí của nhà cung cấp thứ hai có thể thay đổi. Kiểm tra dung lượng và điều khoản; không xem đây là cam kết lưu trữ miễn phí vĩnh viễn.
- Cấu hình rclone có thể chứa OAuth token. Script chạy bằng root; giữ file cấu hình trong thư mục root, không đưa lên GitHub và không gửi token qua chat.

Có thể kiểm tra backup đã được gửi tới cả hai nơi bằng cách chạy backup rồi xem log:

~~~bash
sudo systemctl start class-merit-backup.service
sudo journalctl -u class-merit-backup.service -n 100 --no-pager
~~~

### 7.7. Kiểm tra bản backup mà không ghi đè dữ liệu đang chạy

Khi khóa riêng age đang nằm tạm thời trên VM, chạy:

~~~bash
sudo bash /opt/class-merit-hub/deploy/oracle/verify_backup.sh \
  /var/backups/class-merit-hub/TEN_FILE.sqlite3.gz.age \
  /home/ubuntu/class-merit-backup-identity.txt
~~~

Bỏ đối số đường dẫn backup để kiểm tra bản local mới nhất:

~~~bash
sudo bash /opt/class-merit-hub/deploy/oracle/verify_backup.sh \
  "" /home/ubuntu/class-merit-backup-identity.txt
~~~

Công cụ kiểm tra SHA-256 (nếu có sidecar), giải mã age, kiểm tra gzip, chạy SQLite integrity check và xác nhận các bảng cốt lõi. Nó **không thay đổi database đang chạy**. Hãy diễn tập xác minh và phục hồi trên môi trường thử nghiệm định kỳ, không chờ đến lúc VM gặp sự cố.

### 7.8. Khôi phục

Khi cần khôi phục, tải file mã hóa từ bucket về VM, tải khóa age riêng từ bản sao ngoại tuyến lên VM tạm thời. Ví dụ:

~~~bash
oci os object get --auth instance_principal \
  --namespace-name YOUR_NAMESPACE \
  --bucket-name class-merit-backups \
  --name class-merit-hub/class-merit-YYYYMMDDTHHMMSSZ.sqlite3.gz.age \
  --file /tmp/class-merit-restore.sqlite3.gz.age
~~~

Chuyển khóa riêng lên VM bằng SCP từ máy Windows (thay IP và tên người dùng SSH):

~~~powershell
scp .\class-merit-backup-identity.txt ubuntu@YOUR_VM_PUBLIC_IP:/home/ubuntu/
~~~

Sau đó chạy trên VM:

~~~bash
sudo chmod 600 /home/ubuntu/class-merit-backup-identity.txt
sudo bash /opt/class-merit-hub/deploy/oracle/restore.sh /tmp/class-merit-restore.sqlite3.gz.age /home/ubuntu/class-merit-backup-identity.txt
~~~

Sau khi xác nhận ứng dụng đã khôi phục bình thường, xóa bản khóa riêng tạm trên VM bằng shred.

Script kiểm tra checksum nếu có sidecar, giải mã, kiểm tra gzip, SQLite integrity và bảng bắt buộc trước khi hỏi xác nhận. Trước khi thay database, script dừng ứng dụng và tạo một bản snapshot SQLite online nhất quán (bao gồm WAL). Nếu health check sau restore thất bại, script thử quay lại snapshot trước đó. File database trước restore được giữ lại với hậu tố pre-restore khi restore thành công. Sau khôi phục, kiểm tra health check, đăng nhập và hồ sơ điểm.

Điểm quan trọng cho tình huống VM cũ đã mất: `restore.sh` có thể chạy ngay sau khi cài ứng dụng mới, kể cả khi `backup.env` chưa được tạo. Chỉ cần `app.env` đã có DATABASE_PATH, file backup mã hóa và khóa riêng tương ứng. Không cần chạy cấu hình backup trước bước restore.

## 8. Cập nhật website an toàn

~~~bash
sudo bash /opt/class-merit-hub/deploy/oracle/update.sh
~~~

Script sẽ tạo backup trước (nếu đã cấu hình), kéo mã nguồn mới, cài dependencies, tự cập nhật các lệnh backup/verify trong `/usr/local/sbin`, khởi động lại service và gọi health check.

Trạng thái dịch vụ và watchdog:

~~~bash
sudo systemctl status class-merit-hub caddy --no-pager
sudo systemctl list-timers class-merit-healthcheck.timer class-merit-backup.timer
sudo journalctl -u class-merit-healthcheck -n 100 --no-pager
sudo journalctl -u class-merit-hub -f
~~~

## 9. Dựng lại hệ thống khi VM cũ bị thu hồi hoặc hỏng

Quy trình này phục hồi ứng dụng trên VM mới, không cần lấy lại VM cũ:

1. Tạo VM Always Free mới trong home region nếu OCI vẫn cấp được capacity. Tạo lại VCN/Network Security Group và mở đúng TCP 22, 80, 443.
2. Nếu dùng OCI Object Storage, cập nhật Dynamic Group matching rule để bao gồm **OCID instance mới**; giữ policy chỉ cho phép ghi/đọc bucket backup cần thiết. Nếu dùng kho rclone độc lập, cài và cấu hình lại remote trên VM mới:

~~~bash
sudo apt-get update
sudo apt-get install -y rclone
sudo rclone config
~~~

Cấu hình remote bằng đúng tài khoản lưu trữ thứ hai. File cấu hình root-owned sẽ nằm trong `/root/.config/rclone/rclone.conf`; không đưa file này lên GitHub.
3. Cài Ubuntu 24.04, clone repository và chạy `install_ubuntu.sh`. Nhập lại DuckDNS subdomain/token; kiểm tra DuckDNS phân giải về IP mới. Chưa tạo tài khoản founder trước khi restore.
4. Lấy file backup mã hóa mới nhất từ OCI Console/CLI hoặc kho rclone thứ hai. Với rclone, liệt kê file rồi tải đúng file mới nhất (thay REMOTE và FILENAME bằng giá trị thực tế):

~~~bash
sudo rclone lsf --files-only REMOTE
sudo rclone copyto REMOTE/FILENAME /tmp/FILENAME
sudo rclone copyto REMOTE/FILENAME.sha256 /tmp/FILENAME.sha256
~~~

Cũng có thể dùng một bản đã lưu ngoại tuyến trên máy tính cá nhân.
5. Chép khóa riêng age từ bản ngoại tuyến lên VM mới qua SCP. Đưa file backup vào VM, sau đó giải mã/khôi phục bằng lệnh bên dưới. `restore.sh` không cần `backup.env` ở bước này.

~~~bash
sudo bash /opt/class-merit-hub/deploy/oracle/restore.sh \
  /tmp/class-merit-latest.sqlite3.gz.age \
  /home/ubuntu/class-merit-backup-identity.txt
~~~

6. Khi restore báo thành công, kiểm tra `https://TEN-SUBDOMAIN.duckdns.org/healthz`, đăng nhập bằng tài khoản cũ và kiểm tra một số hồ sơ/nhật ký.
7. Khôi phục file recipient công khai cũ trước khi cấu hình backup tiếp tục. Ví dụ nếu đã tải recipient file về cùng thư mục:

~~~bash
sudo install -m 0640 -o root -g root \
  /home/ubuntu/class-merit-backup-recipient.txt \
  /etc/class-merit-hub/backup-recipient.txt
sudo bash /opt/class-merit-hub/deploy/oracle/configure_backup.sh
~~~

Nếu không còn file recipient công khai nhưng vẫn có khóa riêng cũ, có thể tái tạo recipient từ khóa riêng:

~~~bash
age-keygen -y -i /home/ubuntu/class-merit-backup-identity.txt \
  | sudo tee /etc/class-merit-hub/backup-recipient.txt >/dev/null
sudo chmod 0640 /etc/class-merit-hub/backup-recipient.txt
sudo chown root:root /etc/class-merit-hub/backup-recipient.txt
~~~

Script cấu hình backup kiểm tra bucket. Nếu đã có backup cũ nhưng chưa có recipient file, nó yêu cầu recipient cũ thay vì âm thầm sinh khóa mới. Điều này giúp tránh làm các backup hiện có không thể giải mã. Chỉ sau khi khôi phục thành công mới xóa bản khóa riêng tạm trên VM.

**Giới hạn:** quy trình này cần còn quyền truy cập ít nhất một bản backup và khóa riêng age. Nếu mất cả hai, dữ liệu mã hóa không thể khôi phục. Nếu OCI không cấp VM mới hoặc nhà cung cấp lưu trữ thứ hai cũng khóa tài khoản, thời gian khôi phục không được bảo đảm.

## 10. Giới hạn uptime và độ bền dữ liệu — phải hiểu trước khi sử dụng

- Oracle ghi rõ máy ảo Always Free nhàn rỗi có thể bị thu hồi. Một instance bị coi là idle nếu trong 7 ngày liên tục: CPU utilization ở percentile 95 dưới 20%, network utilization dưới 20%, và riêng A1 thì memory utilization dưới 20%.
- Website lớp học ít truy cập có thể rơi vào ngưỡng này. Không có cách hợp lệ để đảm bảo Oracle không thu hồi máy bằng cách giả lập tải.
- Chỉ có một VM và một Caddy reverse proxy. VM lỗi, bảo trì, lỗi mạng, lỗi vùng trung tâm dữ liệu, hết capacity, lỗi tài khoản hoặc thay đổi điều khoản nhà cung cấp đều có thể làm website ngừng hoạt động.
- systemd tự khởi động lại tiến trình ứng dụng khi lỗi. Watchdog nội bộ kiểm tra mỗi phút và thử restart ứng dụng/Caddy khi health check thất bại; cơ chế này không thể sửa chữa hỏng phần cứng hoặc khôi phục VM đã bị thu hồi.
- Boot/Block Volume tồn tại qua restart thông thường, nhưng không phải lưu trữ vĩnh viễn bất khả xâm phạm. Nếu tenancy bị đóng, tài nguyên bị xóa hoặc vùng gặp sự cố, dữ liệu có thể không truy cập được.
- Backup vào Object Storage cùng tenancy giúp khôi phục khi VM hỏng, nhưng không bảo vệ đầy đủ trước việc tài khoản OCI bị khóa hoặc mất quyền toàn tenancy. Giữ bản mã hóa ngoại tuyến ở nơi khác và thử phục hồi định kỳ.
- Hệ thống một máy chủ không có failover tự động, không có cam kết SLA 24/7 và không có RPO/RTO được bảo đảm.

Vì vậy, kiến trúc này có thể hướng tới chi phí hosting 0 đồng trong hạn mức, nhưng không thể bảo đảm website hoạt động 24/7 tuyệt đối hoặc dữ liệu tồn tại vĩnh viễn.

## 11. Kiểm soát để không phát sinh phí ngoài ý muốn

- Chỉ tạo tài nguyên có nhãn Always Free Eligible và ở home region.
- Không tạo Paid Load Balancer, NAT Gateway, shape trả phí, volume vượt giới hạn, bucket/tier vượt quota hoặc dịch vụ trial-only.
- Không nâng tài khoản lên Pay As You Go nếu chưa chấp nhận rủi ro tính phí vượt hạn mức.
- Kiểm tra Billing & Cost Management → Cost Analysis và Governance & Administration → Limits, Quotas and Usage thường xuyên.
- Cảnh báo ngân sách không phải hard spending cap.
- Dung lượng backup cần được kiểm tra; script giữ 60 bản remote nhưng bucket cũng có thể chứa đối tượng khác.
- DuckDNS miễn phí và cung cấp subdomain, nhưng không có SLA ngang nhà cung cấp DNS trả phí.

**Đây là cấu hình best-effort 0 đồng, không phải cam kết uptime hoặc lưu trữ vĩnh viễn.**
