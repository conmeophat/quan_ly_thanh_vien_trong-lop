# Đưa Class Merit Hub lên Internet — hướng dẫn Windows

Mục tiêu: website chạy trên máy chủ Internet độc lập với máy tính cá nhân. Thành viên ở bất kỳ quốc gia nào có thể truy cập bằng điện thoại hoặc máy tính qua HTTPS.

Kiến trúc:

```text
Điện thoại / Máy tính ở mọi nơi
              |
        HTTPS :443
              |
      DuckDNS + Caddy
              |
      127.0.0.1:8080
              |
       NiceGUI + SQLite
              |
       Ổ đĩa VM bền vững
```

Không mở cổng 8080 ra Internet. Người dùng chỉ truy cập domain HTTPS.

## 1. Tạo tài khoản và máy chủ Oracle Cloud

1. Đăng ký Oracle Cloud Free Tier tại https://www.oracle.com/cloud/free/.
2. Chọn đúng home region của tài khoản. Tạo Compute Instance với:
   - Shape: `VM.Standard.A1.Flex` (ARM64), chỉ tiếp tục nếu Console hiển thị **Always Free Eligible**.
   - CPU/RAM: tối đa 2 OCPU và 12 GB RAM tổng hạn mức Always Free.
   - Image: Ubuntu 24.04 LTS ARM64.
   - Boot Volume: 50 GB.
   - Public IPv4: bật.
3. Tạo SSH key pair. Giữ private key trên máy tính cá nhân; chỉ đưa public key cho Oracle.
4. Tạo VCN/public subnet có Internet Gateway và route ra Internet.

Oracle công bố A1 Always Free tương đương tối đa 2 OCPU/12 GB RAM, và tối đa 200 GB Block Volume tổng (boot + data) trong home region. Hạn mức và nhãn Always Free phải được kiểm tra ngay trong Console trước khi tạo tài nguyên.

Tài liệu chính thức:
- https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/launchinginstance.htm

## 2. Mở đúng cổng mạng

Trong Network Security Group hoặc Security List của VM, tạo các quy tắc inbound:

| Source | Protocol | Port | Mục đích |
|---|---|---:|---|
| IP công cộng của bạn/32 | TCP | 22 | SSH quản trị |
| 0.0.0.0/0 | TCP | 80 | Cấp/chuyển hướng HTTPS |
| 0.0.0.0/0 | TCP | 443 | Website toàn cầu |

Không mở cổng 8080. Bộ cài sẽ cấu hình UFW trên Ubuntu và chỉ cho Caddy nhận lưu lượng web công khai.

## 3. Tạo địa chỉ web miễn phí

1. Mở https://www.duckdns.org/ và tạo tài khoản.
2. Tạo một subdomain dễ nhớ, ví dụ `class-merit-phat`.
3. Giữ DuckDNS token riêng tư. Bạn sẽ tự nhập token trong phiên SSH; không gửi token qua chat hoặc commit lên GitHub.

Địa chỉ website sau khi triển khai sẽ có dạng:

`https://TEN-SUBDOMAIN.duckdns.org`

## 4. Kết nối VM bằng PowerShell

Trên Windows, mở PowerShell. Thay đường dẫn private key và IP bằng giá trị thực tế:

```powershell
ssh -i "$HOME\.ssh\id_ed25519" ubuntu@PUBLIC_IP
```

Nếu bạn đặt tên private key khác, thay `id_ed25519` cho đúng.

Nếu SSH hỏi xác nhận fingerprint lần đầu, chỉ chấp nhận khi bạn đang kết nối đúng IP VM vừa tạo trong Oracle Console.

## 5. Cài website tự động

Trong cửa sổ SSH đang kết nối vào Ubuntu, chạy:

```bash
sudo apt-get update
sudo apt-get install -y git
git clone https://github.com/conmeophat/quan_ly_thanh_vien_trong-lop.git
cd quan_ly_thanh_vien_trong-lop
sudo bash deploy/oracle/install_ubuntu.sh
```

Bộ cài sẽ hỏi:
- DuckDNS subdomain (chỉ tên, không thêm `.duckdns.org`).
- DuckDNS token (khi nhập sẽ không hiển thị).
- SSH source CIDR: nhập IP công cộng hiện tại của bạn kèm `/32`. Không để trống nếu bạn có thể xác định IP.

Bộ cài tạo khóa phiên, cài Python/NiceGUI, cấu hình SQLite, systemd tự khởi động lại, Caddy HTTPS, DuckDNS cập nhật IP và UFW/Fail2ban. Khóa bí mật được tạo trên VM, không cần đưa vào GitHub.

Giữ nguyên cửa sổ SSH đến khi bộ cài báo hoàn tất. Sau đó kiểm tra trên VM:

```bash
sudo systemctl status class-merit-hub caddy --no-pager
curl -i http://127.0.0.1:8080/healthz
```

Khi DNS đã trỏ về đúng public IP và chứng chỉ HTTPS được cấp, thử:

```bash
curl -i https://TEN-SUBDOMAIN.duckdns.org/healthz
```

Kết quả mong đợi là HTTP 200 và `{"status":"ok"}`.

## 6. Tạo Người sáng lập lần đầu một cách an toàn

Ứng dụng chỉ cho phép tạo tài khoản Người sáng lập đầu tiên từ kết nối loopback. Đây là lớp bảo vệ để người lạ không thể chiếm quyền quản trị qua domain công khai.

Đóng phiên SSH cài đặt hoặc mở thêm một cửa sổ PowerShell mới trên Windows. Tạo SSH tunnel:

```powershell
ssh -i "$HOME\.ssh\id_ed25519" -L 8080:127.0.0.1:8080 ubuntu@PUBLIC_IP
```

Giữ cửa sổ tunnel mở. Trên Chrome ở máy tính của bạn, truy cập:

`http://127.0.0.1:8080`

Tạo Người sáng lập bằng ba trường:
- Họ và tên
- Số điện thoại
- Mật khẩu (tối thiểu 8 ký tự)

Sau khi tạo thành công, đóng SSH tunnel. Từ đó trở đi hãy đăng nhập và sử dụng qua domain HTTPS công khai, không sử dụng HTTP localhost.

## 7. Cho thành viên trên toàn thế giới truy cập

Trên bất kỳ điện thoại hoặc máy tính nào có Internet, mở domain HTTPS:

`https://TEN-SUBDOMAIN.duckdns.org`

Người sáng lập hoặc Giáo viên chủ nhiệm tạo tài khoản cho từng người. Thành viên đăng nhập bằng số điện thoại và mật khẩu được cấp.

Không có đăng ký tự do, không có nút quên mật khẩu. Khi quên mật khẩu, thành viên liên hệ Người sáng lập hoặc Giáo viên chủ nhiệm.

## 8. Dữ liệu, sao lưu và giới hạn miễn phí

- Cơ sở dữ liệu SQLite nằm trên ổ đĩa bền vững của VM, không nằm trên máy tính cá nhân.
- Không xóa VM, boot volume hoặc data volume nếu chưa xác nhận có bản sao lưu và đã kiểm tra khôi phục.
- Trước khi nhập dữ liệu lớp thật, hãy cấu hình quy trình backup mã hóa trong `deploy/oracle/README.md` và thử khôi phục.
- Oracle Always Free có thể thu hồi máy tính toán nếu trong 7 ngày các ngưỡng CPU, mạng và (với A1) RAM đều ở mức thấp theo chính sách idle-instance. Không có cam kết uptime tuyệt đối; theo dõi email/thông báo Oracle và kiểm tra bản backup định kỳ.
- Chỉ tạo tài nguyên có nhãn **Always Free Eligible**. Không chuyển sang Pay As You Go hoặc tạo dịch vụ trả phí nếu chưa hiểu rõ chi phí.

Chính sách Always Free và idle compute:
https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
