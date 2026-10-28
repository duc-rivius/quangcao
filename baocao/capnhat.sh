#!/bin/sh
# Cập nhật máy chủ báo cáo + trang quản lý quảng cáo trên VPS từ GitHub, rồi chạy lại.
# Dùng:  curl -fsSL https://raw.githubusercontent.com/duc-rivius/quangcao/main/baocao/capnhat.sh | sh
set -e
D=/opt/sieunet-stats
R=https://raw.githubusercontent.com/duc-rivius/quangcao/main
mkdir -p "$D/quanly"
for f in baocao/server.py baocao/dashboard.html quanly/index.html quanly/auth.json; do
    out="$D/${f#baocao/}"
    curl -fsSL "$R/$f?t=$(date +%s)" -o "$out.tmp"
    mv "$out.tmp" "$out"
done
systemctl restart sieunet-stats
sleep 1
systemctl is-active sieunet-stats
curl -s http://127.0.0.1:8787/health
echo
