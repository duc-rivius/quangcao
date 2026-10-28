# Báo cáo quảng cáo (máy chủ số liệu)

Máy chủ nhỏ chạy trên VPS của người phát hành: nhận số liệu quảng cáo từ mọi máy cài Siêu Nét Player và có trang
báo cáo kiểu Facebook Ads.

- `server.py`: máy chủ (Python 3.8+, chỉ dùng thư viện có sẵn, dữ liệu lưu trong SQLite).
- `dashboard.html`: trang báo cáo, máy chủ phục vụ ở `/baocao`.
- `sieunet-stats.service`: chạy nền bằng systemd. `Caddyfile`: HTTPS bằng Caddy.

## Số liệu có trong báo cáo

Lượt hiển thị · số PC tiếp cận (máy khác nhau) · tần suất (lượt hiện mỗi máy) · lượt click · CTR · số PC click ·
CTR theo PC · tỷ lệ bỏ qua · tỷ lệ xem hết · thời gian xem trung bình · số PC hoạt động · số PC mới.
Chia theo: quảng cáo, ngày, giờ trong ngày, card đồ hoạ (VGA), CPU, RAM, Windows, độ phân giải màn hình, phiên bản
player. Chọn khoảng ngày, lọc một quảng cáo, sắp xếp theo cột, tải CSV để gửi nhà tài trợ.

## Player gửi gì

Mỗi lượt hiện / bấm / đóng quảng cáo: mã quảng cáo, loại sự kiện, số giây quảng cáo hiện, lý do đóng (phim tự phát /
bỏ qua / đóng phim). Kèm một mã máy ngẫu nhiên (tạo một lần trên máy, không lấy từ phần cứng) và cấu hình máy.
Không gửi gì về phim đang xem. Máy chủ không lưu địa chỉ IP. Người xem tắt bằng `stats=no` trong `ads.conf`.
Mất mạng thì player giữ số liệu (tối đa 500 sự kiện) và gửi bù lần sau; gửi lại không bị đếm trùng.

## Cài lên VPS (Ubuntu / Debian)

Cần: một tên miền (hoặc tên miền phụ, vd `stats.rivius.com`) trỏ bản ghi A về IP của VPS, mở cổng 80 và 443.

```bash
# 1. chép mã
sudo mkdir -p /opt/sieunet-stats
sudo cp server.py dashboard.html /opt/sieunet-stats/
sudo useradd --system --no-create-home --shell /usr/sbin/nologin sieunet-stats

# 2. mật khẩu quản trị (dùng để vào trang báo cáo) — giữ kín
echo "STATS_ADMIN_KEY=$(openssl rand -base64 24)" | sudo tee /etc/sieunet-stats.env
sudo chmod 600 /etc/sieunet-stats.env

# 3. chạy nền
sudo cp sieunet-stats.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sieunet-stats
curl http://127.0.0.1:8787/health          # → {"ok": true}

# 4. HTTPS bằng Caddy
sudo apt install -y caddy
sudo cp Caddyfile /etc/caddy/Caddyfile      # sửa tên miền trong tệp trước
sudo systemctl reload caddy
```

Rồi điền vào `ads.json` của repo này (hoặc ô **stats_url** trong trang quản lý quảng cáo):

```json
"stats_url": "https://stats.ten-mien-cua-ban/e"
```

Mọi máy nhận địa chỉ này ở lần tải danh sách quảng cáo kế tiếp. Xem báo cáo: `https://stats.ten-mien-cua-ban/baocao`
(nhập mật khẩu trong `/etc/sieunet-stats.env`).

## Cập nhật, sao lưu

- Cập nhật mã: chép lại `server.py`, `dashboard.html` vào `/opt/sieunet-stats/` rồi
  `sudo systemctl restart sieunet-stats`.
- Sao lưu: `sqlite3 /var/lib/sieunet-stats/stats.db ".backup /root/stats-$(date +%F).db"`.
- Chạy thử trên máy: `STATS_ADMIN_KEY=thu-nghiem-1234567890 python3 server.py` rồi mở `http://127.0.0.1:8787/baocao`.
