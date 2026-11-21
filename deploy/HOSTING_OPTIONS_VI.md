# Chọn nơi chạy Class Merit Hub lâu dài

Cập nhật: 22/11/2026

## Kết luận trước

Không có cách hợp lệ nào biến một gói hosting miễn phí thành tài nguyên máy chủ vô tận, không giới hạn và bảo đảm chạy 24/7 mãi mãi. Nhà cung cấp có thể thay quota, dừng gói miễn phí, thu hồi máy ảo, giới hạn băng thông hoặc khóa tài khoản theo điều khoản dịch vụ.

Với Class Merit Hub (Python + NiceGUI + SQLite), có ba lựa chọn thực tế:

1. **Không mất phí thuê máy chủ:** dùng máy tính/mini PC của chính bạn chạy 24/7. Uptime phụ thuộc điện, Internet và phần cứng tại nhà.
2. **Không mất phí máy chủ cloud trong hạn mức:** dùng Oracle Cloud Always Free. Đây là lựa chọn cloud phù hợp nhất với kiến trúc hiện tại, nhưng VM có thể bị thu hồi khi idle.
3. **Ưu tiên hoạt động liên tục:** thuê VPS luôn bật, dùng ổ đĩa bền vững và backup độc lập. Đây là lựa chọn thực tế hơn nếu website được dùng cho dữ liệu lớp học quan trọng.

GitHub giữ mã nguồn, kiểm thử và hỗ trợ tự động triển khai; GitHub không phải nơi chạy tiến trình NiceGUI liên tục.

## 1. So sánh các phương án

| Nền tảng | Có chạy Python/NiceGUI? | Giới hạn đáng chú ý | Đánh giá cho dự án |
|---|---|---|---|
| Oracle Cloud Always Free A1 | Có, chạy nguyên ứng dụng trên VM Ubuntu | Tối đa tương đương 2 OCPU/12 GB RAM; VM idle có thể bị thu hồi theo quy tắc 7 ngày; có thể thiếu capacity | **Phù hợp nhất trong các lựa chọn cloud miễn phí**, nếu chấp nhận best-effort |
| Máy tính/mini PC tại nhà | Có, chạy nguyên ứng dụng | Cần bật máy 24/7, Internet ổn định, nguồn điện và cấu hình truy cập HTTPS | **Không bị cloud thu hồi vì idle**; phù hợp nếu đã có thiết bị |
| Google Cloud Run | Có, bằng container | Container có filesystem tạm; WebSocket bị giới hạn thời gian request tối đa 60 phút; cần reconnect và dữ liệu ngoài container; vượt quota sẽ tính phí | Chỉ nên cân nhắc sau khi thiết kế lại lưu trữ và phiên |
| Render Free | Có | Ngủ sau 15 phút không có traffic; filesystem tạm; không có persistent disk trên free web service; free Postgres hết hạn sau 30 ngày | Không phù hợp để giữ SQLite và dữ liệu lớp lâu dài |
| Koyeb Free | Có | 0.1 vCPU, 512 MB RAM, 2 GB SSD; không hỗ trợ volume; scale về 0 sau 1 giờ không có traffic | Chỉ hợp demo/thử nghiệm |
| Hugging Face Spaces CPU miễn phí | Có thể chạy app dạng Space | Tự sleep sau khoảng 48 giờ không hoạt động; chạy liên tục cần phần cứng trả phí | Không phù hợp làm website lớp học chính |
| PythonAnywhere Free | Có giới hạn | 100 CPU giây, 512 MiB dung lượng, một web app/worker và thời hạn một tháng theo chính sách hiện tại | Không đủ cho vận hành lâu dài |
| Fly.io | Có | Các gói free cũ đã ngừng cho khách hàng mới; máy ảo và lưu trữ tính phí | Không xem là lựa chọn miễn phí mới |
| GitHub Pages | **Không** | Chỉ phục vụ nội dung tĩnh; không chạy mã Python phía máy chủ | Không thể host backend NiceGUI |
| GitHub Actions | Chạy tác vụ CI/CD | Runner chỉ chạy job rồi kết thúc; không phải máy chủ website liên tục | Dùng để test/build/deploy, không dùng để giữ web server |

Các quota và chính sách trong bảng có thể thay đổi; mở tài liệu chính thức ở phần Nguồn trước khi tạo tài khoản hoặc tài nguyên.

## 2. Vì sao không thể chạy website trực tiếp “vĩnh viễn” trên GitHub?

Repository GitHub lưu các file mã nguồn. GitHub Pages không hỗ trợ ngôn ngữ server-side như Python. GitHub Actions có thể chạy test, đóng gói và gửi phiên bản mới lên máy chủ, nhưng runner là môi trường thực thi job, không phải VPS được cấp liên tục cho ứng dụng.

Vì vậy, kiến trúc đúng là:

~~~text
GitHub repository
  ├── Lưu mã nguồn
  ├── Chạy kiểm thử tự động
  └── Kích hoạt quy trình deploy
             |
             v
       Máy chủ thực tế
       ├── Python + NiceGUI
       ├── SQLite trên ổ đĩa bền vững
       ├── HTTPS reverse proxy
       └── Backup mã hóa ngoài máy chủ
~~~

Không đưa file SQLite, mật khẩu, token, khóa mã hóa hoặc dữ liệu học sinh lên GitHub.

## 3. Phương án A — Oracle Cloud Always Free

Repository đã có bộ triển khai ở thư mục deploy/oracle:

- install_ubuntu.sh: cài ứng dụng, Caddy HTTPS, DuckDNS, UFW, Fail2ban và systemd.
- systemd: tự khởi động tiến trình sau reboot hoặc khi tiến trình lỗi.
- healthcheck.sh: kiểm tra ứng dụng và reverse proxy mỗi phút, thử khởi động lại khi lỗi.
- backup.sh: tạo bản SQLite nhất quán, nén, mã hóa age và kiểm tra checksum.
- configure_backup.sh: lên lịch backup tới OCI Object Storage.
- configure_rclone_backup.sh: thêm bản sao mã hóa ở nhà cung cấp độc lập.
- verify_backup.sh và restore.sh: kiểm tra và khôi phục dữ liệu.

### Rủi ro idle không thể loại bỏ bằng cấu hình ứng dụng

Oracle quy định một VM Always Free có thể bị thu hồi nếu trong cùng giai đoạn 7 ngày:
- CPU utilization ở percentile 95 dưới 20%;
- Network utilization dưới 20%;
- Với A1, Memory utilization cũng dưới 20%.

Website lớp học thường có lượng truy cập thấp, do đó có thể đáp ứng điều kiện idle. Không nên tạo CPU load, ping hoặc lưu lượng giả để cố vượt ngưỡng. Cách đó không tạo ra bảo đảm uptime, lãng phí tài nguyên và có thể không phù hợp điều khoản sử dụng.

### Quy trình giảm thiểu thiệt hại

1. Dùng A1 trong đúng home region và chỉ tạo tài nguyên có nhãn Always Free Eligible.
2. Hoàn tất backup mã hóa ra OCI Object Storage.
3. Cấu hình thêm rclone sang tài khoản/nhà cung cấp độc lập. Không coi hai bucket trong cùng tenancy là hai bản sao độc lập.
4. Giữ khóa riêng age ở ít nhất hai nơi ngoại tuyến an toàn.
5. Thử verify và restore trên môi trường kiểm thử trước khi lưu dữ liệu lớp thật.
6. Theo dõi tình trạng VM, dung lượng backup, email cảnh báo và hạn mức OCI.
7. Khi VM mất, tạo VM thay thế, cài lại từ GitHub rồi restore bản backup mới nhất.

**Lưu ý:** có backup giúp khôi phục dữ liệu, không làm website tự hoạt động trở lại và không bảo đảm VM mới luôn có sẵn. Quy trình hiện tại là khôi phục có thao tác thủ công, không phải failover tự động.

Hướng dẫn từng bước: [Oracle deployment README](oracle/README.md) và [Windows quickstart](oracle/WINDOWS_QUICKSTART_VI.md).

## 4. Phương án B — dùng máy tính riêng hoặc mini PC tại nhà

Nếu mục tiêu là không bị Oracle thu hồi VM do ít traffic và bạn đã có một máy tính có thể bật liên tục, đây là hướng không phải trả phí thuê compute.

Mô hình:

~~~text
Người dùng trên Internet
          |
       HTTPS
          |
   Router / Tunnel
          |
     Máy tính ở nhà
          |
  NiceGUI + SQLite
          |
  Ổ đĩa của chính bạn
~~~

Có hai cách đưa website ra Internet:

**Cách 1: DuckDNS + Caddy + port forwarding**
- Dùng subdomain DuckDNS.
- Trỏ DNS về IP Internet của nhà.
- Chuyển tiếp TCP 80 và 443 từ router về máy chủ.
- Caddy cấp và tự gia hạn chứng chỉ HTTPS.
- Chỉ để ứng dụng nghe trong mạng nội bộ; không mở cổng 8080 ra Internet.

Cách này có thể không hoạt động nếu nhà mạng dùng CGNAT hoặc chặn inbound ports. Cần kiểm tra WAN IP trên router có khớp IP Internet công khai hay không.

**Cách 2: Cloudflare Tunnel**
- Không cần mở inbound port trên router.
- Cần tài khoản Cloudflare, một domain được quản lý trên Cloudflare và máy chủ đang chạy.
- Tunnel chỉ tạo đường kết nối từ máy chủ của bạn tới Cloudflare; nó không cấp máy tính hoặc lưu trữ ứng dụng.
- Domain riêng có thể phát sinh phí mua/gia hạn.

Máy tính tại nhà vẫn có thể mất điện, mất mạng, hỏng ổ cứng hoặc tự khởi động lại. Cần cấu hình Windows Task Scheduler hoặc dịch vụ hệ thống để ứng dụng tự chạy khi boot, cùng backup ra ổ/nhà cung cấp khác.

## 5. Phương án C — Google Cloud Run

Cloud Run phù hợp hơn nếu ứng dụng có lượng truy cập không liên tục và có thể chấp nhận reconnect WebSocket.

Các điểm cần tính trước:
- Free tier request-based hiện có mức miễn phí theo tháng cho CPU, RAM và số request; tổng sử dụng được cộng gộp theo billing account. Dùng vượt mức sẽ bị tính phí.
- WebSocket được hỗ trợ nhưng request có timeout tối đa 60 phút; client cần tự kết nối lại.
- Filesystem của container là tạm thời. Không đặt file SQLite duy nhất trong container.
- NiceGUI có trạng thái phiên phía server; khi instance thay đổi hoặc dừng, cần thiết kế lại để người dùng kết nối lại an toàn.
- Nên chuyển dữ liệu sang PostgreSQL được quản lý hoặc dịch vụ dữ liệu bền vững. Cơ sở dữ liệu, lưu trữ và minimum instances có thể tạo chi phí riêng.

Không triển khai bản hiện tại lên Cloud Run chỉ bằng cách chuyển Dockerfile và giữ SQLite trong container: dữ liệu có thể mất khi instance dừng.

## 6. Phương án D — VPS trả phí nhỏ

Nếu website lưu điểm, số điện thoại và hồ sơ thành viên quan trọng, một VPS nhỏ luôn bật thường là lựa chọn đơn giản và dễ vận hành hơn việc ghép nhiều gói free.

Yêu cầu tối thiểu:
- Ubuntu LTS;
- ổ SSD bền vững;
- snapshot hoặc backup ngoài VPS;
- HTTPS;
- firewall và SSH key;
- dịch vụ tự khởi động lại;
- kiểm thử phục hồi định kỳ.

VPS trả phí cũng có thể gặp downtime hoặc mất dữ liệu. Vẫn phải duy trì backup độc lập; không có nhà cung cấp nào bảo đảm “vĩnh viễn”.

## 7. Thiết kế độ bền dữ liệu khuyến nghị

Với bản hiện tại dùng SQLite, chỉ chạy **một tiến trình ứng dụng ghi vào một file database**. Không chạy nhiều VM cùng ghi vào một file SQLite được đồng bộ thủ công.

Mục tiêu sao lưu:
- Một bản trên máy chủ để phục hồi nhanh.
- Một bản ở kho object storage của cloud.
- Một bản mã hóa ở nhà cung cấp/tài khoản độc lập hoặc ổ lưu trữ ngoại tuyến.
- Khóa age riêng được giữ độc lập với máy chủ và các file backup.
- Thử giải mã, integrity check và restore định kỳ.

Mọi file backup chứa dữ liệu lớp phải được mã hóa trước khi rời máy chủ. Không commit file database, .env, app.env, token, OAuth config hoặc khóa riêng age vào Git.

## 8. Đề xuất cho repository này

**Nếu ngân sách bắt buộc bằng 0 đồng:** giữ Oracle A1 làm cloud host best-effort, cấu hình bản sao rclone độc lập và chuẩn bị máy tính tại nhà làm phương án phục hồi thủ công. Chấp nhận rằng website có thể gián đoạn khi Oracle thu hồi VM.

**Nếu bắt buộc phải hoạt động liên tục hơn:** chuyển sang VPS trả phí và giữ backup ngoài nhà cung cấp. Không cần thay đổi ứng dụng ngay nếu vẫn dùng một VM và SQLite.

**Không nên:** chạy keep-alive giả, tạo nhiều tài khoản cloud để nhân quota, đặt database trên ổ tạm, hoặc coi GitHub Actions là máy chủ website.

## 9. Tài liệu chính thức đã kiểm tra

- [Oracle Always Free Resources và idle compute reclamation](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
- [GitHub Pages — không hỗ trợ Python phía máy chủ](https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site)
- [GitHub Actions billing and usage](https://docs.github.com/en/actions/concepts/billing-and-usage)
- [GitHub-hosted runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [Google Cloud Run pricing](https://cloud.google.com/run/pricing)
- [Google Cloud Run WebSockets](https://docs.cloud.google.com/run/docs/triggering/websockets)
- [Google Cloud Run disposable filesystem](https://docs.cloud.google.com/run/docs/overview/what-is-cloud-run)
- [Render Free limitations](https://render.com/docs/free)
- [Koyeb instance types and Free Instance limits](https://www.koyeb.com/docs/reference/instances)
- [Hugging Face Spaces sleep behavior](https://huggingface.co/docs/hub/main/en/spaces-gpus)
- [PythonAnywhere Free account limits](https://help.pythonanywhere.com/pages/FreeAccountsFeatures/)
- [Fly.io discontinued plans](https://flyio-landing.fly.dev/docs/about/discontinued-plans/)
- [Cloudflare Tunnel prerequisites](https://developers.cloudflare.com/tunnel/get-started/)

Kiểm tra lại chính sách của nhà cung cấp trước khi triển khai; các quota và điều kiện miễn phí không phải cam kết vĩnh viễn.
