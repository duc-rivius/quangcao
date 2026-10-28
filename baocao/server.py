"""
server.py — máy chủ số liệu quảng cáo của Siêu Nét Player (chạy trên VPS của người phát hành).

  * POST /e            player gửi lượt hiện / lượt bấm / lượt đóng quảng cáo (không cần đăng nhập)
  * GET  /baocao       trang báo cáo (nhập mật khẩu quản trị)
  * GET  /api/report   số liệu cho trang báo cáo (Authorization: Bearer <mật khẩu quản trị>)

Player chỉ gửi: mã máy ngẫu nhiên (tạo một lần trên máy, không gắn với người dùng), mã quảng cáo, loại sự kiện,
số giây quảng cáo hiện, và cấu hình máy (card đồ hoạ, CPU, RAM, Windows, màn hình, phiên bản player).
Không gửi gì về phim đang xem. Máy chủ không lưu địa chỉ IP (chỉ giữ trong RAM vài phút để chặn gửi dồn).

Chạy:  STATS_ADMIN_KEY=<mật khẩu dài> python3 server.py --port 8787 --db /var/lib/sieunet-stats/stats.db
Chỉ dùng thư viện có sẵn của Python 3.8+. Đặt sau Caddy / nginx để có HTTPS (xem README.md).
"""
import argparse
import calendar
import hmac
import json
import os
import re
import sqlite3
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
MAX_BODY = 64 * 1024          # một lần gửi tối đa
MAX_EVENTS = 200              # số sự kiện tối đa mỗi lần gửi
RATE_LIMIT = 120              # số lần gửi tối đa mỗi phút từ một địa chỉ IP
TZ = 7 * 3600                 # ngày / giờ trong báo cáo tính theo giờ Việt Nam (UTC+7)
EVENTS = ("imp", "click", "end")
REASONS = ("ready", "skip", "timeout", "none", "closed")
RE_ID = re.compile(r"^[0-9a-f]{16,40}$")
RE_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS pcs (
    pc TEXT PRIMARY KEY, first_seen INTEGER, last_seen INTEGER,
    app TEXT, os TEXT, gpu TEXT, cpu TEXT, ram INTEGER, screen TEXT);
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY, ts INTEGER, day TEXT, hour INTEGER,
    pc TEXT, ad TEXT, ev TEXT, sec REAL, reason TEXT, app TEXT);
CREATE INDEX IF NOT EXISTS events_day ON events(day);
CREATE INDEX IF NOT EXISTS events_ad ON events(ad, day);
"""


def clip(v, n=120):
    return v.strip()[:n] if isinstance(v, str) else ""


def local_day_hour(ts):
    t = time.gmtime(ts + TZ)
    return time.strftime("%Y-%m-%d", t), t.tm_hour


class Store:
    def __init__(self, path):
        d = os.path.dirname(os.path.abspath(path))
        os.makedirs(d, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        self.lock = threading.Lock()

    def add(self, body):
        """body: {"pc", "app", "os", "gpu", "cpu", "ram", "screen", "events": [{"id", "t", "ev", "ad", "sec", "reason"}]}
        → số sự kiện mới ghi được."""
        pc = clip(body.get("pc"), 40).lower()
        if not RE_ID.match(pc):
            raise ValueError("pc")
        evs = body.get("events")
        if not isinstance(evs, list) or not evs or len(evs) > MAX_EVENTS:
            raise ValueError("events")
        now = int(time.time())
        app = clip(body.get("app"), 40)
        ram = body.get("ram")
        ram = int(ram) if isinstance(ram, (int, float)) and 0 < ram < 4096 else None
        rows = []
        for e in evs:
            if not isinstance(e, dict):
                continue
            eid = clip(e.get("id"), 40).lower()
            ev = e.get("ev")
            ad = clip(e.get("ad"), 80)
            if not RE_ID.match(eid) or ev not in EVENTS or not ad:
                continue
            t = e.get("t")
            # sự kiện gửi bù (máy mất mạng): giữ giờ của máy nếu hợp lý, không thì lấy giờ nhận
            ts = int(t) if isinstance(t, (int, float)) and now - 30 * 86400 < t <= now + 3600 else now
            sec = e.get("sec")
            sec = round(float(sec), 1) if isinstance(sec, (int, float)) and 0 <= sec < 3600 else None
            reason = e.get("reason") if e.get("reason") in REASONS else None
            day, hour = local_day_hour(ts)
            rows.append((pc + ":" + eid, ts, day, hour, pc, ad, ev, sec, reason, app))
        with self.lock:
            self.db.execute("BEGIN")
            try:
                self.db.execute(
                    "INSERT INTO pcs(pc, first_seen, last_seen, app, os, gpu, cpu, ram, screen) "
                    # lần gửi thiếu thông tin máy (chưa đọc xong cấu hình): giữ thông tin cũ
                    "VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(pc) DO UPDATE SET last_seen=excluded.last_seen, "
                    "app=COALESCE(NULLIF(excluded.app,''),app), os=COALESCE(NULLIF(excluded.os,''),os), "
                    "gpu=COALESCE(NULLIF(excluded.gpu,''),gpu), cpu=COALESCE(NULLIF(excluded.cpu,''),cpu), "
                    "ram=COALESCE(excluded.ram,ram), screen=COALESCE(NULLIF(excluded.screen,''),screen)",
                    (pc, now, now, app, clip(body.get("os")), clip(body.get("gpu"), 200), clip(body.get("cpu")),
                     ram, clip(body.get("screen"), 20)))
                before = self.db.total_changes
                self.db.executemany("INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?,?,?,?,?)", rows)
                added = self.db.total_changes - before
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise
        return added

    # ---- báo cáo
    METRICS = """
        SUM(e.ev='imp') AS imp,
        COUNT(DISTINCT CASE WHEN e.ev='imp' THEN e.pc END) AS reach,
        SUM(e.ev='click') AS clicks,
        COUNT(DISTINCT CASE WHEN e.ev='click' THEN e.pc END) AS uclicks,
        SUM(e.ev='end') AS ends,
        SUM(e.ev='end' AND e.reason='skip') AS skips,
        SUM(e.ev='end' AND e.reason IN ('ready','timeout')) AS full,
        AVG(CASE WHEN e.ev='end' THEN e.sec END) AS avg_sec
    """
    GROUPS = {
        "ad": "e.ad", "day": "e.day", "hour": "e.hour", "app": "e.app",
        "gpu": "COALESCE(NULLIF(p.gpu,''),'(không rõ)')", "cpu": "COALESCE(NULLIF(p.cpu,''),'(không rõ)')",
        "os": "COALESCE(NULLIF(p.os,''),'(không rõ)')", "screen": "COALESCE(NULLIF(p.screen,''),'(không rõ)')",
        "ram": "CASE WHEN p.ram IS NULL THEN '(không rõ)' WHEN p.ram < 8 THEN 'dưới 8 GB' "
               "WHEN p.ram < 16 THEN '8–15 GB' WHEN p.ram < 32 THEN '16–31 GB' ELSE 'từ 32 GB' END",
    }

    @staticmethod
    def derive(r):
        imp, reach, clicks = r.get("imp") or 0, r.get("reach") or 0, r.get("clicks") or 0
        r["ctr"] = clicks / imp if imp else 0.0
        r["uctr"] = (r.get("uclicks") or 0) / reach if reach else 0.0
        r["freq"] = imp / reach if reach else 0.0
        ends = r.get("ends") or 0
        r["skip_rate"] = (r.get("skips") or 0) / ends if ends else 0.0
        r["full_rate"] = (r.get("full") or 0) / ends if ends else 0.0
        if r.get("avg_sec") is not None:
            r["avg_sec"] = round(r["avg_sec"], 1)
        return r

    def report(self, d1, d2, ad=None):
        where, args = "e.day BETWEEN ? AND ?", [d1, d2]
        if ad:
            where += " AND e.ad = ?"
            args.append(ad)
        base = "FROM events e LEFT JOIN pcs p ON p.pc = e.pc WHERE " + where

        def rows(sql, a):
            cur = self.db.execute(sql, a)
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, x)) for x in cur.fetchall()]

        with self.lock:
            total = self.derive(rows("SELECT " + self.METRICS + " " + base, args)[0])
            total["pcs"] = rows("SELECT COUNT(DISTINCT e.pc) AS n " + base, args)[0]["n"]
            total["new_pcs"] = rows("SELECT COUNT(*) AS n FROM pcs WHERE pc IN (SELECT DISTINCT e.pc " + base +
                                    ") AND first_seen >= ? AND first_seen < ?",
                                    args + [self.day_start(d1), self.day_start(d2) + 86400])[0]["n"]
            out = {"from": d1, "to": d2, "ad": ad or "", "total": total}
            for name, key in self.GROUPS.items():
                order = "k" if name in ("day", "hour") else "imp DESC"
                out["by_" + name] = [self.derive(r) for r in rows(
                    "SELECT " + key + " AS k, " + self.METRICS + " " + base + " GROUP BY k ORDER BY " + order +
                    " LIMIT 400", args)]
            out["ads"] = [r["ad"] for r in rows("SELECT DISTINCT ad FROM events ORDER BY ad", [])]
        return out

    @staticmethod
    def day_start(day):
        """0 giờ (giờ Việt Nam) của ngày → mốc thời gian Unix."""
        return calendar.timegm(time.strptime(day, "%Y-%m-%d")) - TZ


class Limiter:
    def __init__(self):
        self.hits = {}
        self.lock = threading.Lock()

    def ok(self, ip):
        now = time.time()
        with self.lock:
            if len(self.hits) > 10000:
                self.hits = {k: v for k, v in self.hits.items() if now - v[0] < 60}
            start, n = self.hits.get(ip, (now, 0))
            if now - start >= 60:
                start, n = now, 0
            self.hits[ip] = (start, n + 1)
            return n < RATE_LIMIT


class Handler(BaseHTTPRequestHandler):
    server_version = "SieuNetStats/1"
    store = None
    admin_key = ""
    limiter = Limiter()

    def log_message(self, fmt, *a):
        pass                                  # không ghi nhật ký truy cập (có IP)

    def client_ip(self):
        # sau Caddy / nginx: lấy IP thật từ X-Forwarded-For (chỉ để chặn gửi dồn, không lưu)
        fwd = self.headers.get("X-Forwarded-For", "")
        return fwd.split(",")[0].strip() if fwd else self.client_address[0]

    def send(self, code, body=b"", ctype="application/json; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if body and self.command != "HEAD":
            self.wfile.write(body)

    def send_json(self, code, obj):
        self.send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def do_POST(self):
        if urlparse(self.path).path != "/e":
            return self.send_json(404, {"error": "not found"})
        if not self.limiter.ok(self.client_ip()):
            return self.send_json(429, {"error": "too many requests"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if n <= 0 or n > MAX_BODY:
            return self.send_json(413, {"error": "body size"})
        try:
            body = json.loads(self.rfile.read(n).decode("utf-8"))
            if not isinstance(body, dict):
                raise ValueError("body")
            added = self.store.add(body)
        except (ValueError, UnicodeDecodeError) as e:
            return self.send_json(400, {"error": "bad request: %s" % e})
        except Exception as e:
            sys.stderr.write("lỗi ghi số liệu: %r\n" % e)
            return self.send_json(500, {"error": "server"})
        self.send_json(200, {"ok": True, "added": added})

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/baocao", "/baocao/"):
            try:
                with open(os.path.join(HERE, "dashboard.html"), "rb") as f:
                    page = f.read()
            except OSError:
                return self.send_json(500, {"error": "thiếu dashboard.html"})
            return self.send(200, page, "text/html; charset=utf-8",
                             {"Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline' "
                              "https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline'; "
                              "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'"})
        if u.path == "/health":
            return self.send_json(200, {"ok": True})
        if u.path != "/api/report":
            return self.send_json(404, {"error": "not found"})
        auth = self.headers.get("Authorization", "")
        key = auth[7:] if auth.startswith("Bearer ") else ""
        if not self.admin_key or not hmac.compare_digest(key.encode("utf-8"), self.admin_key.encode("utf-8")):
            time.sleep(0.5)                  # chậm lại mỗi lần sai mật khẩu
            return self.send_json(401, {"error": "sai mật khẩu"})
        q = parse_qs(u.query)
        today = local_day_hour(time.time())[0]
        d1 = (q.get("from") or [""])[0] or today
        d2 = (q.get("to") or [""])[0] or today
        if not RE_DAY.match(d1) or not RE_DAY.match(d2) or d1 > d2:
            return self.send_json(400, {"error": "ngày không hợp lệ"})
        ad = (q.get("ad") or [""])[0][:80] or None
        self.send_json(200, self.store.report(d1, d2, ad))

    do_HEAD = do_GET


def main():
    ap = argparse.ArgumentParser(description="Máy chủ số liệu quảng cáo Siêu Nét Player")
    ap.add_argument("--host", default="127.0.0.1", help="mặc định chỉ nghe trên máy (đặt sau Caddy / nginx)")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--db", default=os.path.join(HERE, "stats.db"))
    a = ap.parse_args()
    key = os.environ.get("STATS_ADMIN_KEY", "")
    if len(key) < 16:
        sys.exit("Đặt biến môi trường STATS_ADMIN_KEY (mật khẩu quản trị, ít nhất 16 ký tự)")
    Handler.store = Store(a.db)
    Handler.admin_key = key
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    srv.daemon_threads = True
    print("SieuNetStats đang chạy ở http://%s:%d (db: %s)" % (a.host, a.port, a.db), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
