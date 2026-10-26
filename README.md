# quangcao

Nguồn quảng cáo của Siêu Nét Player (`ads.json` + ảnh). Chỉ người phát hành quản lý repo này.

## Quản lý quảng cáo

Chạy `QuanLyQuangCao.bat`: mở app trên máy, sửa quảng cáo, kéo thả ảnh, xem trước màn hình chờ.
Bấm **Lưu**, rồi **Đăng lên web** (commit và push). Mọi máy cài player nhận quảng cáo mới sau khoảng `refresh_hours`.

Cần cài Git và Chrome hoặc Edge. Thư mục `quanly/` là mã của app, không ảnh hưởng người xem.

## Bản chạy trên web

Mở https://duc-rivius.github.io/quangcao/quanly/ từ máy nào cũng được, không cần cài gì.
Lần đầu dán một token GitHub (Fine-grained, chỉ chọn repo `quangcao`, quyền **Contents: Read and write**).
Token chỉ lưu trong trình duyệt đó. Sửa xong bấm **Đăng lên web**: trang tự commit thẳng lên `main`.

Điền thêm tên đăng nhập và mật khẩu ở bước dán token thì lần sau chỉ cần gõ hai thứ đó. Token được mã hoá bằng mật khẩu rồi lưu ở `quanly/auth.json`. File này ai cũng tải được, nên mật khẩu phải dài và khó đoán. Token hết hạn thì bấm "Dùng token GitHub", dán token mới và đặt lại mật khẩu. Đổi mật khẩu: nút **Mật khẩu** sau khi đăng nhập.
Bản trên máy (`QuanLyQuangCao.bat`) tự kéo các thay đổi này về mỗi lần mở.
