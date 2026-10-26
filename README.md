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
Bản trên máy (`QuanLyQuangCao.bat`) tự kéo các thay đổi này về mỗi lần mở.
