"""
pi_test_ui.py — Công cụ THỬ giao tiếp PC ↔ Raspberry Pi (TCP/IP) trước khi đưa vào app master (UI/).

    pip install customtkinter pillow
    python pi_test_ui.py

Giao thức (PC là client, Pi là server) — chi tiết trong README.md cùng thư mục:
  Mỗi gói = [4 byte big-endian: độ dài JSON][JSON utf-8]
  Nếu JSON có "image_size": N thì N byte JPEG thô nối ngay sau JSON.
  PC -> Pi : {"id": 1, "cmd": "ping" | "capture" | "inspect"}
  Pi -> PC : gửi lại đúng "id"
    ping    -> {"id":1,"cmd":"ping","status":"ok"}
    capture -> {"id":2,"cmd":"capture","status":"ok","image_size":N}  + N byte JPEG
    inspect -> {"id":3,"cmd":"inspect","status":"ok","result":"PASS"|"FAIL1"|"FAIL2",
                "process_time_ms":123.4, ...trường tuỳ ý...}
    lỗi     -> {"id":N,"status":"error","message":"..."}

Bật "Dùng Pi giả lập" để chạy thử ngay trên PC khi chưa có Pi: công cụ tự mở một server giả trên 127.0.0.1 trả lời
đúng giao thức (lần lượt PASS / FAIL1 / FAIL2) — đây cũng là ví dụ mẫu cho phía Pi.

Cấu trúc: PiLink (giao thức, không phụ thuộc giao diện — sau này chuyển sang UI/comm/ cho app master),
MockPi (server giả), PiTestApp (giao diện).
"""

import io
import json
import queue
import random
import socket
import struct
import threading
import time
from datetime import datetime

import customtkinter as ctk
from PIL import Image, ImageDraw

# ============================================================
# Hằng số giao thức
# ============================================================
DEFAULT_HOST, DEFAULT_PORT = "192.168.1.100", 5000
MAX_JSON = 1 << 20                                   # 1 MB
MAX_IMAGE = 20 << 20                                 # 20 MB
TIMEOUT = {"ping": 3, "capture": 10, "inspect": 20}  # giây, chờ phản hồi
RESULTS = ("PASS", "FAIL1", "FAIL2")
RESULT_TEXT = {"PASS": "ĐẠT", "FAIL1": "LỖI 1 · linh kiện", "FAIL2": "LỖI 2 · chức năng"}


# ============================================================
# Giao tiếp TCP (không phụ thuộc giao diện)
# ============================================================
class NoResponse(Exception):
    """Hết thời gian chờ phản hồi (kết nối vẫn còn)."""


class LinkLost(Exception):
    """Mất kết nối hoặc gói tin sai khung."""


def send_packet(sock, obj, image=b""):
    """Gửi 1 gói: [4 byte độ dài JSON][JSON][ảnh nếu có] — dùng chung cho PC và Pi giả lập."""
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    sock.sendall(struct.pack(">I", len(data)) + data + image)


class PiLink:
    """Hỏi–đáp tuần tự: mỗi lần request() gửi 1 lệnh rồi chờ đúng phản hồi cùng id. Gọi từ luồng nền."""

    def __init__(self):
        self.sock = None
        self.seq = 0

    def connect(self, host, port):
        self.sock = socket.create_connection((host, port), timeout=3)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.seq = 0

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None

    def _read(self, n, deadline):
        buf = bytearray()
        while len(buf) < n:
            left = deadline - time.monotonic()
            if left <= 0:
                raise NoResponse
            self.sock.settimeout(left)
            try:
                chunk = self.sock.recv(n - len(buf))
            except socket.timeout:
                raise NoResponse
            except OSError as e:
                raise LinkLost(str(e))
            if not chunk:
                raise LinkLost("Pi đã đóng kết nối")
            buf += chunk
        return bytes(buf)

    def request(self, cmd, timeout, log):
        """Gửi lệnh, trả về (dict phản hồi, bytes ảnh hoặc None). log(level, message) ghi vào Log."""
        self.seq += 1
        req = {"id": self.seq, "cmd": cmd}
        try:
            self.sock.settimeout(3)
            send_packet(self.sock, req)
        except OSError as e:
            raise LinkLost(str(e))
        log("TX", json.dumps(req))

        deadline = time.monotonic() + timeout
        while True:
            (n,) = struct.unpack(">I", self._read(4, deadline))
            if not 0 < n <= MAX_JSON:
                raise LinkLost(f"Độ dài JSON không hợp lệ: {n}")
            try:
                msg = json.loads(self._read(n, deadline))
                size = int(msg.get("image_size", 0))
            except (ValueError, TypeError, AttributeError):
                raise LinkLost("Phản hồi không phải JSON hợp lệ")
            if not 0 <= size <= MAX_IMAGE:
                raise LinkLost(f"image_size không hợp lệ: {size}")
            img = self._read(size, deadline) if size else None
            log("RX", json.dumps(msg, ensure_ascii=False) + (f"  [+{size} byte ảnh]" if size else ""))
            if "id" in msg and msg["id"] != self.seq:
                log("WARN", f"Bỏ qua phản hồi cũ (id={msg['id']}, đang chờ id={self.seq})")
                continue
            return msg, img


# ============================================================
# Pi giả lập (127.0.0.1) — trả lời đúng giao thức ở trên
# ============================================================
class MockPi(threading.Thread):
    def __init__(self, port):
        super().__init__(daemon=True)
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", port))
        self.srv.listen(1)
        self.n_inspect = 0

    def stop(self):
        try:
            self.srv.close()
        except OSError:
            pass

    def run(self):
        while True:
            try:
                conn, _ = self.srv.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    @staticmethod
    def _recv(conn, n):
        buf = b""
        while len(buf) < n:
            chunk = conn.recv(n - len(buf))
            if not chunk:
                raise ConnectionError
            buf += chunk
        return buf

    def _serve(self, conn):
        try:
            while True:
                (n,) = struct.unpack(">I", self._recv(conn, 4))
                req = json.loads(self._recv(conn, n))
                rid, cmd = req.get("id"), req.get("cmd")
                if cmd == "ping":
                    send_packet(conn, {"id": rid, "cmd": "ping", "status": "ok"})
                elif cmd == "capture":
                    time.sleep(0.4)
                    jpg = self._fake_image(rid)
                    send_packet(conn, {"id": rid, "cmd": "capture", "status": "ok", "image_size": len(jpg)}, jpg)
                elif cmd == "inspect":
                    t = random.uniform(0.6, 1.4)
                    time.sleep(t)
                    result = RESULTS[self.n_inspect % 3]
                    self.n_inspect += 1
                    extra = {"PASS": {}, "FAIL1": {"defect": "thieu linh kien R12"},
                             "FAIL2": {"led_last_digit": 4}}[result]
                    send_packet(conn, {"id": rid, "cmd": "inspect", "status": "ok", "result": result,
                                       "process_time_ms": round(t * 1000 - random.uniform(30, 80), 1), **extra})
                else:
                    send_packet(conn, {"id": rid, "status": "error", "message": f"lệnh không hỗ trợ: {cmd!r}"})
        except (OSError, ConnectionError, ValueError, struct.error):
            conn.close()

    @staticmethod
    def _fake_image(rid):
        img = Image.new("RGB", (640, 480), "#cbd5e1")
        dr = ImageDraw.Draw(img)
        dr.rectangle((120, 90, 520, 390), fill="#4ade80", outline="#15803d", width=6)
        for k in range(6):
            dr.line((150, 130 + k * 35, 380, 130 + k * 35), fill="#15803d", width=3)
        dr.rectangle((410, 150, 490, 260), fill="#1e293b")
        dr.text((20, 20), f"PI GIA LAP - id {rid}", fill="#1e293b")
        out = io.BytesIO()
        img.save(out, "JPEG", quality=80)
        return out.getvalue()


# ============================================================
# Giao diện (bảng màu sáng giống app master)
# ============================================================
BG, PANEL, BORDER, INPUT = "#eef2f7", "#ffffff", "#dbe3ee", "#f1f5f9"
TEXT, DIM, DISABLED = "#1e293b", "#64748b", "#94a3b8"
ACCENT, ACCENT_HOVER, SOFT, SOFT_HOVER = "#2563eb", "#1d4ed8", "#e8eef6", "#d9e2ee"
GREEN, AMBER, RED = "#16a34a", "#d97706", "#dc2626"
RESULT_COLOR = {"PASS": GREEN, "FAIL1": AMBER, "FAIL2": RED}
LOG_COLOR = {"INFO": ACCENT, "OK": GREEN, "WARN": AMBER, "ERROR": RED, "TX": DIM, "RX": "#7c3aed"}
MAX_LOG_LINES = 500
F, FB = "Segoe UI", "Segoe UI Semibold"
ctk.set_appearance_mode("light")


class Card(ctk.CTkFrame):
    def __init__(self, master, title, **kw):
        super().__init__(master, fg_color=PANEL, border_color=BORDER, border_width=1, corner_radius=12, **kw)
        ctk.CTkLabel(self, text=title, font=(FB, 13), text_color=TEXT, anchor="w").pack(fill="x", padx=14, pady=(10, 4))
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=14, pady=(0, 12))


def button(parent, text, cmd, primary=False, **kw):
    kw.setdefault("height", 34)
    return ctk.CTkButton(parent, text=text, command=cmd, corner_radius=8, font=(FB, 12),
                         fg_color=ACCENT if primary else SOFT, hover_color=ACCENT_HOVER if primary else SOFT_HOVER,
                         text_color="#ffffff" if primary else TEXT, text_color_disabled=DISABLED, **kw)


class PiTestApp(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=BG)
        self.title("Thử Raspberry Pi — TCP/IP")
        self.geometry("1280x740")
        self.minsize(1100, 660)
        try:                                  # sau khi cửa sổ hiện ra (customtkinter đặt lại kích thước lúc khởi tạo)
            self.after(50, lambda: self.state("zoomed"))
        except Exception:
            pass
        self.link = PiLink()
        self.mock = None
        self.peer = None
        self.busy = False
        self.stats = {"total": 0, "PASS": 0, "FAIL1": 0, "FAIL2": 0}
        self.ui_q = queue.Queue()             # luồng nền -> giao diện (Tk chỉ được gọi từ luồng chính)
        self._img = None

        self.grid_columnconfigure(0, weight=4, uniform="c")
        self.grid_columnconfigure(1, weight=5, uniform="c")
        self.grid_columnconfigure(2, weight=5, uniform="c")
        self.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=3, sticky="ew", padx=16, pady=(12, 6))
        ctk.CTkLabel(head, text="Thử giao tiếp Raspberry Pi (kiểm tra PCB bằng xử lý ảnh)", font=(FB, 18),
                     text_color=TEXT).pack(side="left")
        self.status = ctk.CTkLabel(head, text="● CHƯA KẾT NỐI", font=(FB, 12), text_color=DIM)
        self.status.pack(side="right")

        col0 = ctk.CTkFrame(self, fg_color="transparent")
        col0.grid(row=1, column=0, sticky="nsew", padx=(16, 6))
        self._build_connection(col0)
        self._build_stats(col0)
        self._build_camera().grid(row=1, column=1, sticky="nsew", padx=6)
        self._build_inspection().grid(row=1, column=2, sticky="nsew", padx=(6, 16))
        self._build_log()
        self._refresh_enabled_states()
        self.after(30, self._drain)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------- 1. Kết nối ----------------
    def _build_connection(self, parent):
        c = Card(parent, "1. Kết nối TCP tới Raspberry Pi")
        c.pack(fill="x")
        b = c.body

        def row(label, default):
            r = ctk.CTkFrame(b, fg_color="transparent")
            r.pack(fill="x", pady=3)
            ctk.CTkLabel(r, text=label, font=(F, 12), text_color=TEXT, width=80, anchor="w").pack(side="left")
            e = ctk.CTkEntry(r, width=160, height=30, fg_color=INPUT, border_color=BORDER, text_color=TEXT)
            e.insert(0, default)
            e.pack(side="left")
            return e
        self.ip = row("Địa chỉ IP", DEFAULT_HOST)
        self.port = row("Cổng", str(DEFAULT_PORT))
        self.mock_var = ctk.BooleanVar(value=False)
        self.mock_sw = ctk.CTkSwitch(b, text="Dùng Pi giả lập (127.0.0.1, chạy thử khi chưa có Pi)",
                                     variable=self.mock_var, font=(F, 11), text_color=DIM)
        self.mock_sw.pack(anchor="w", pady=(6, 0))
        self.btn_conn = button(b, "Connect", self.toggle_connect, primary=True)
        self.btn_conn.pack(fill="x", pady=(10, 4))
        self.btn_test = button(b, "Test Connection (ping)", self.test_connection)
        self.btn_test.pack(fill="x", pady=2)
        ctk.CTkLabel(b, text="Chưa Connect: Test chỉ kiểm tra cổng TCP có mở. Đã Connect: gửi ping, đo thời gian "
                            "khứ hồi.", font=(F, 10), text_color=DISABLED, wraplength=330, justify="left",
                     anchor="w").pack(fill="x", pady=(4, 0))

    # ---------------- Thống kê ----------------
    def _build_stats(self, parent):
        c = Card(parent, "4. Thống kê")
        c.pack(fill="x", pady=(12, 0))
        b = c.body
        b.grid_columnconfigure((0, 1, 2), weight=1, uniform="s")
        self.stat_lbl = {}
        for i, (key, label, color) in enumerate((("Total", "Tổng số", TEXT), ("PASS", "PASS · đạt", GREEN),
                                                 ("FAIL1", "FAIL1 · linh kiện", AMBER),
                                                 ("FAIL2", "FAIL2 · chức năng", RED), ("Pass Rate", "Tỉ lệ đạt", ACCENT))):
            box = ctk.CTkFrame(b, fg_color=INPUT, corner_radius=8)
            box.grid(row=i // 3, column=i % 3, sticky="ew", padx=3, pady=3)
            ctk.CTkLabel(box, text=label, font=(F, 10), text_color=DIM, height=18).pack(anchor="w", padx=8, pady=(4, 0))
            self.stat_lbl[key] = ctk.CTkLabel(box, text="0", font=(FB, 18), text_color=color, height=26)
            self.stat_lbl[key].pack(anchor="w", padx=8, pady=(0, 4))
        self.stat_lbl["Pass Rate"].configure(text="—")
        button(b, "⟳ Reset", self.reset_stats).grid(row=1, column=2, sticky="ew", padx=3, pady=3)

    # ---------------- 2. Camera ----------------
    def _build_camera(self):
        c = Card(self, "2. Camera (capture)")
        b = c.body
        top = ctk.CTkFrame(b, fg_color="transparent")
        top.pack(fill="x")
        self.cam_lbl = ctk.CTkLabel(top, text="Camera: chưa kiểm tra", font=(F, 11), text_color=DIM, anchor="w")
        self.cam_lbl.pack(side="left", fill="x", expand=True)
        self.btn_cap = button(top, "📸 Capture", self.capture, primary=True, width=130)
        self.btn_cap.pack(side="right")
        self.preview = ctk.CTkLabel(b, text="(chưa có ảnh)", fg_color=INPUT, corner_radius=8, text_color=DISABLED)
        self.preview.pack(fill="both", expand=True, pady=(8, 0))
        return c

    # ---------------- 3. Kết quả kiểm tra ----------------
    def _build_inspection(self):
        c = Card(self, "3. Kiểm tra PCB (inspect)")
        b = c.body
        self.btn_ins = button(b, "▶ Start Inspection", self.inspect, primary=True, height=40)
        self.btn_ins.pack(fill="x")
        res = ctk.CTkFrame(b, fg_color=INPUT, corner_radius=10)
        res.pack(fill="x", pady=(10, 0))
        self.res_lbl = ctk.CTkLabel(res, text="—", font=(FB, 30), text_color=DISABLED)
        self.res_lbl.pack(pady=(6, 0))
        self.res_sub = ctk.CTkLabel(res, text="", font=(F, 12), text_color=DIM)
        self.res_sub.pack(pady=(0, 8))
        self.pi_time = ctk.CTkLabel(b, text="Thời gian xử lý ảnh (Pi): — ms", font=(FB, 12), text_color=TEXT, anchor="w")
        self.pi_time.pack(fill="x", pady=(10, 0))
        self.rtt = ctk.CTkLabel(b, text=f"Tổng thời gian phản hồi (PC đo): — ms · timeout {TIMEOUT['inspect']} s",
                                font=(F, 11), text_color=DIM, anchor="w")
        self.rtt.pack(fill="x", pady=(2, 6))
        ctk.CTkLabel(b, text="JSON phản hồi", font=(FB, 11), text_color=DIM, anchor="w").pack(fill="x")
        self.json_box = ctk.CTkTextbox(b, fg_color=INPUT, text_color=TEXT, font=("Consolas", 11), corner_radius=8)
        self.json_box.pack(fill="both", expand=True, pady=(2, 0))
        return c

    # ---------------- Log ----------------
    def _build_log(self):
        c = Card(self, "Log (TX = PC gửi, RX = Pi trả lời)")
        c.grid(row=2, column=0, columnspan=3, sticky="ew", padx=16, pady=12)
        bar = ctk.CTkFrame(c.body, fg_color="transparent")
        bar.pack(fill="x")
        button(bar, "Xóa", lambda: self.log_box.delete("1.0", "end"), width=60, height=28).pack(side="right")
        self.log_box = ctk.CTkTextbox(c.body, height=110, fg_color=INPUT, text_color=TEXT, font=("Consolas", 11))
        self.log_box.pack(fill="x", pady=(4, 0))
        for lvl, col in LOG_COLOR.items():
            self.log_box.tag_config(lvl, foreground=col)

    def log(self, msg, level="INFO"):
        self.log_box.insert("end", f"{datetime.now():%H:%M:%S.%f}"[:-3] + "  ")
        self.log_box.insert("end", f"[{level:<5}] ", level)
        self.log_box.insert("end", msg + "\n")
        lines = int(self.log_box.index("end-1c").split(".")[0])
        if lines > MAX_LOG_LINES:
            self.log_box.delete("1.0", f"{lines - MAX_LOG_LINES + 1}.0")
        self.log_box.see("end")

    def _log_threadsafe(self, level, message):
        """Callback cho PiLink.request (chạy ở luồng nền) — chuyển về luồng giao diện qua hàng đợi."""
        self.ui_q.put((self.log, (message, level)))

    # ---------------- Trạng thái nút ----------------
    def _refresh_enabled_states(self):
        on = self.link.sock is not None
        free = not self.busy
        self.btn_conn.configure(text="Disconnect" if on else "Connect", fg_color=SOFT if on else ACCENT,
                                hover_color=SOFT_HOVER if on else ACCENT_HOVER, text_color=TEXT if on else "#ffffff",
                                state="normal" if free else "disabled")
        self.btn_test.configure(state="normal" if free else "disabled")
        for w in (self.btn_cap, self.btn_ins):
            w.configure(state="normal" if on and free else "disabled")
        for w in (self.ip, self.port, self.mock_sw):
            w.configure(state="disabled" if on else "normal")
        if on:
            self.status.configure(text=f"● ĐÃ KẾT NỐI {self.peer[0]}:{self.peer[1]}", text_color=GREEN)
        else:
            self.status.configure(text="● CHƯA KẾT NỐI", text_color=DIM)

    # ---------------- Chạy tác vụ mạng ở luồng nền ----------------
    def _run(self, work, done, fail=None):
        """work() chạy ở luồng nền (giao diện không đơ); done(kết quả) / fail() chạy ở luồng giao diện."""
        if self.busy:
            return
        self.busy = True
        self._refresh_enabled_states()

        def task():
            try:
                res, err = work(), None
            except Exception as e:  # noqa: BLE001 - mọi lỗi đều phải hiện lên Log
                res, err = None, e
            self.ui_q.put((self._finish, (done, fail, res, err)))
        threading.Thread(target=task, daemon=True).start()

    def _finish(self, done, fail, res, err):
        self.busy = False
        if err is None:
            done(res)
        else:
            if isinstance(err, LinkLost):
                self.link.close()
                self._stop_mock()
                self.log(f"Mất kết nối: {err}", "ERROR")
            elif isinstance(err, NoResponse):
                self.log("Không nhận được phản hồi từ Pi (quá thời gian chờ) — app master sẽ báo lỗi, dừng hệ thống.",
                         "ERROR")
            else:
                self.log(f"{type(err).__name__}: {err}", "ERROR")
            if fail:
                fail()
        self._refresh_enabled_states()

    def _drain(self):
        while True:
            try:
                fn, args = self.ui_q.get_nowait()
            except queue.Empty:
                break
            fn(*args)
        self.after(30, self._drain)

    # ============================================================
    # Hành động
    # ============================================================
    def _addr(self):
        host = "127.0.0.1" if self.mock_var.get() else self.ip.get().strip()
        try:
            port = int(self.port.get())
            if not host or not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            self.log("IP hoặc cổng không hợp lệ.", "ERROR")
            return None
        return host, port

    def _start_mock(self, port):
        if self.mock or not self.mock_var.get():
            return True
        try:
            self.mock = MockPi(port)
            self.mock.start()
            self.log(f"Đã mở Pi giả lập ở 127.0.0.1:{port}.")
            return True
        except OSError as e:
            self.log(f"Không mở được Pi giả lập ở cổng {port}: {e}", "ERROR")
            self.mock = None
            return False

    def _stop_mock(self):
        if self.mock:
            self.mock.stop()
            self.mock = None

    def toggle_connect(self):
        if self.link.sock:
            self.link.close()
            self._stop_mock()
            self.log("Đã ngắt kết nối.")
            self._refresh_enabled_states()
            return
        addr = self._addr()
        if not addr or not self._start_mock(addr[1]):
            return

        def done(_):
            self.peer = addr
            self.log(f"Đã kết nối {addr[0]}:{addr[1]}.", "OK")

        def fail():
            self.log("Kiểm tra: Pi đã chạy chương trình server, cùng mạng LAN, đúng IP / cổng, tường lửa.", "WARN")
            self._stop_mock()
        self._run(lambda: self.link.connect(*addr), done, fail)

    def test_connection(self):
        if self.link.sock:
            def work():
                t = time.monotonic()
                r, _ = self.link.request("ping", TIMEOUT["ping"], self._log_threadsafe)
                return r, (time.monotonic() - t) * 1000

            def done(res):
                r, ms = res
                ok = r.get("status") == "ok"
                self.log(f"Test Connection {'OK' if ok else 'FAIL'} — khứ hồi {ms:.0f} ms", "OK" if ok else "ERROR")
            self._run(work, done)
            return
        addr = self._addr()                    # chưa Connect: chỉ kiểm tra cổng TCP có mở không
        if addr and self._start_mock(addr[1]):
            self._run(lambda: socket.create_connection(addr, timeout=3).close(),
                      lambda _: self.log("Cổng TCP đang mở (chưa Connect, chưa kiểm tra giao thức).", "OK"))

    def capture(self):
        self.cam_lbl.configure(text="Camera: đang chụp…", text_color=DIM)

        def done(res):
            r, img = res
            if r.get("status") != "ok" or not img:
                self.cam_lbl.configure(text="Camera: LỖI", text_color=RED)
                self.log(f"Capture thất bại: {r.get('message', 'không có ảnh')}", "ERROR")
                return
            try:
                pil = Image.open(io.BytesIO(img))
                pil.load()
            except Exception as e:  # noqa: BLE001
                self.cam_lbl.configure(text="Camera: ảnh lỗi", text_color=RED)
                self.log(f"Không giải mã được ảnh: {e}", "ERROR")
                return
            w = max(240, self.preview.winfo_width() - 8)
            h = max(180, self.preview.winfo_height() - 8)
            s = min(w / pil.width, h / pil.height)
            self._img = ctk.CTkImage(light_image=pil, size=(int(pil.width * s), int(pil.height * s)))
            self.preview.configure(image=self._img, text="")
            self.cam_lbl.configure(text=f"Camera: OK — {pil.width}×{pil.height}, {len(img) / 1024:.0f} KB",
                                   text_color=GREEN)
            self.log(f"Nhận ảnh {pil.width}×{pil.height} ({len(img) / 1024:.0f} KB).", "OK")

        self._run(lambda: self.link.request("capture", TIMEOUT["capture"], self._log_threadsafe), done,
                  fail=lambda: self.cam_lbl.configure(text="Camera: không phản hồi", text_color=RED))

    def inspect(self):
        self.res_lbl.configure(text="…", text_color=DIM)
        self.res_sub.configure(text="Pi đang xử lý")

        def work():
            t = time.monotonic()
            r, _ = self.link.request("inspect", TIMEOUT["inspect"], self._log_threadsafe)
            return r, (time.monotonic() - t) * 1000

        def done(res):
            r, rtt = res
            self.json_box.delete("1.0", "end")
            self.json_box.insert("end", json.dumps(r, indent=2, ensure_ascii=False))
            code = r.get("result")
            if r.get("status") != "ok" or code not in RESULTS:
                self.res_lbl.configure(text="ERROR", text_color=RED)
                self.res_sub.configure(text=str(r.get("message", "phản hồi không hợp lệ")))
                self.log(f"Phản hồi inspect không hợp lệ (status={r.get('status')!r}, result={code!r}) "
                         "— không tính vào thống kê.", "ERROR")
                return
            pt = r.get("process_time_ms")
            self.res_lbl.configure(text=code, text_color=RESULT_COLOR[code])
            self.res_sub.configure(text=RESULT_TEXT[code])
            self.pi_time.configure(text="Thời gian xử lý ảnh (Pi): " + (
                f"{pt:.0f} ms" if isinstance(pt, (int, float)) else "— (thiếu process_time_ms)"))
            self.rtt.configure(text=f"Tổng thời gian phản hồi (PC đo): {rtt:.0f} ms · timeout {TIMEOUT['inspect']} s")
            self.stats["total"] += 1
            self.stats[code] += 1
            self._show_stats()
            self.log(f"Kết quả kiểm tra: {code} ({RESULT_TEXT[code]})", "OK" if code == "PASS" else "WARN")

        self._run(work, done, fail=lambda: (self.res_lbl.configure(text="ERROR", text_color=RED),
                                             self.res_sub.configure(text="không có phản hồi")))

    # ---------------- Thống kê ----------------
    def _show_stats(self):
        s = self.stats
        for k, v in (("Total", s["total"]), ("PASS", s["PASS"]), ("FAIL1", s["FAIL1"]), ("FAIL2", s["FAIL2"])):
            self.stat_lbl[k].configure(text=str(v))
        self.stat_lbl["Pass Rate"].configure(text=f"{100 * s['PASS'] / s['total']:.1f} %" if s["total"] else "—")

    def reset_stats(self):
        self.stats = dict.fromkeys(self.stats, 0)
        self._show_stats()
        self.log("Đã reset thống kê.")

    def _on_close(self):
        self.link.close()
        self._stop_mock()
        self.destroy()


if __name__ == "__main__":
    PiTestApp().mainloop()
