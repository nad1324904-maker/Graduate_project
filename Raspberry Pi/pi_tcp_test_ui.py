"""pi_tcp_test_ui.py — UI kiểm tra truyền thông TCP/IP giữa PC và Raspberry Pi (kiểm tra PCB bằng xử lý ảnh).
Giao diện dùng cùng bảng màu / Card / HeaderBadge / SYSTEM LOG với ScaraRobotGUI (ui/theme.py, ui/widgets.py).

Cài đặt:  pip install customtkinter pillow
Chạy:     python pi_tcp_test_ui.py

Giao thức (PC là client, Pi là server):
  Mỗi gói = [4 byte big-endian: độ dài JSON][JSON utf-8]
  Nếu JSON có "image_size": N thì N byte JPEG thô nối ngay sau JSON.
  PC -> Pi : {"id": 1, "cmd": "ping" | "capture" | "inspect"}
  Pi -> PC : phải gửi lại cùng "id"
    ping    -> {"id":1,"cmd":"ping","status":"ok"}
    capture -> {"id":2,"cmd":"capture","status":"ok","image_size":N}  + N byte JPEG
    inspect -> {"id":3,"cmd":"inspect","status":"ok","result":"PASS"|"FAIL1"|"FAIL2",
                "process_time_ms":123.4, ...trường tuỳ ý...}
    lỗi     -> {"id":N,"status":"error","message":"..."}
"""

import io
import json
import socket
import struct
import threading
import time
from datetime import datetime

import customtkinter as ctk
from PIL import Image

# ============================================================
# Theme (sao từ ui/theme.py — khi tích hợp vào GUI chính thì import thay vì sao chép)
# ============================================================
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

COL_BG = "#070d18"
COL_PANEL = "#0d1826"
COL_PANEL_BORDER = "#1c3252"
COL_HEADER = "#060b14"
COL_ACCENT = "#2f8fff"
COL_ACCENT_HOVER = "#1f6fe0"
COL_TEXT = "#eaf1fb"
COL_TEXT_DIM = "#7d90ad"
COL_TEXT_DISABLED = "#44526b"
COL_GREEN = "#22c55e"
COL_GREEN_HOVER = "#1ea34d"
COL_AMBER = "#f59e0b"
COL_RED = "#ef4444"
COL_RED_HOVER = "#dc2f2f"
COL_BTN_DARK = "#132238"
COL_BTN_DARK_HOVER = "#1a2e4a"
COL_INPUT = "#0a1522"

LOG_TAG_COLOR = {"INFO": "#3ba7ff", "WARN": "#f59e0b", "ERROR": "#ef4444", "OK": "#22c55e",
                 "TX": "#2f8fff", "RX": "#22d3ee"}
BTN_COLOR = {"accent": (COL_ACCENT, COL_ACCENT_HOVER), "green": (COL_GREEN, COL_GREEN_HOVER),
             "red": (COL_RED, COL_RED_HOVER), "dark": (COL_BTN_DARK, COL_BTN_DARK_HOVER)}

# ============================================================
# Hằng số giao thức
# ============================================================
MAX_JSON = 1 << 20      # 1 MB
MAX_IMAGE = 20 << 20    # 20 MB
TIMEOUT = {"ping": 3, "capture": 10, "inspect": 20}  # giây, chờ phản hồi
RESULTS = ("PASS", "FAIL1", "FAIL2")
RESULT_COLOR = {"PASS": COL_GREEN, "FAIL1": COL_AMBER, "FAIL2": COL_RED}
MAX_LOG_LINES = 500     # Communication Monitor chỉ giữ 500 dòng gần nhất


# ============================================================
# Widget dùng chung (sao từ ui/widgets.py)
# ============================================================
class Card(ctk.CTkFrame):
    def __init__(self, master, title, icon="🔧", **kwargs):
        super().__init__(master, fg_color=COL_PANEL, border_color=COL_PANEL_BORDER,
                          border_width=1, corner_radius=14, **kwargs)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(header, text=icon, font=("Segoe UI", 15), text_color=COL_ACCENT).pack(side="left")
        ctk.CTkLabel(header, text=title, font=("Segoe UI Semibold", 13),
                     text_color=COL_TEXT).pack(side="left", padx=(8, 0))
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=14, pady=(0, 12))


class HeaderBadge(ctk.CTkFrame):
    """1 khối trạng thái trên header: icon + nhãn + giá trị."""

    def __init__(self, master, icon, label):
        super().__init__(master, fg_color="transparent")
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(anchor="w")
        ctk.CTkLabel(top, text=icon, font=("Segoe UI", 13), text_color=COL_TEXT_DIM).pack(side="left")
        ctk.CTkLabel(top, text=label, font=("Segoe UI", 11), text_color=COL_TEXT_DIM).pack(side="left", padx=(5, 0))
        self.value_label = ctk.CTkLabel(self, text="—", font=("Segoe UI Semibold", 13), text_color=COL_TEXT)
        self.value_label.pack(anchor="w")

    def set_value(self, text, color=None):
        self.value_label.configure(text=text, text_color=color or COL_TEXT)


def make_button(parent, text, command, kind="dark", **kw):
    fg, hover = BTN_COLOR[kind]
    kw.setdefault("height", 36)
    return ctk.CTkButton(parent, text=text, command=command, fg_color=fg, hover_color=hover,
                         corner_radius=8, font=("Segoe UI Semibold", 12), text_color="#ffffff",
                         text_color_disabled=COL_TEXT_DISABLED, **kw)


def make_entry(parent, width, text):
    e = ctk.CTkEntry(parent, width=width, height=36, fg_color=COL_INPUT, border_width=0,
                     justify="center", font=("Segoe UI", 13), text_color=COL_TEXT)
    e.insert(0, text)
    return e


# ============================================================
# Giao tiếp TCP (không phụ thuộc giao diện)
# ============================================================
class NoResponse(Exception):
    """Hết thời gian chờ phản hồi (kết nối vẫn còn)."""


class LinkLost(Exception):
    """Mất kết nối hoặc gói tin sai khung."""


class PiLink:
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
        """Gửi lệnh, trả về (dict phản hồi, bytes ảnh hoặc None). log(level, message) ghi vào Monitor."""
        self.seq += 1
        req = {"id": self.seq, "cmd": cmd}
        data = json.dumps(req).encode()
        try:
            self.sock.settimeout(3)
            self.sock.sendall(struct.pack(">I", len(data)) + data)
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
            log("RX", json.dumps(msg) + (f"  [+{size} bytes ảnh]" if size else ""))
            if "id" in msg and msg["id"] != self.seq:
                log("WARN", f"Bỏ qua phản hồi cũ (id={msg['id']}, đang chờ id={self.seq})")
                continue
            return msg, img


# ============================================================
# Cửa sổ chính
# ============================================================
class PiTcpTestGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Pi TCP Test — PC ↔ Raspberry Pi")
        self.geometry("1360x900")
        self.minsize(1200, 700)
        self.configure(fg_color=COL_BG)

        self.link = PiLink()
        self.peer = None                    # (host, port) đang kết nối
        self.busy = False
        self.stats = {"total": 0, "PASS": 0, "FAIL1": 0, "FAIL2": 0}
        self._img = None                    # giữ tham chiếu ảnh để Tk không xoá

        self._build_layout()
        self._tick_clock()
        self._refresh_enabled_states()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_layout(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._build_header()

        outer = ctk.CTkScrollableFrame(self, fg_color=COL_BG,
                                        scrollbar_button_color=COL_BTN_DARK,
                                        scrollbar_button_hover_color=COL_BTN_DARK_HOVER)
        outer.grid(row=1, column=0, sticky="nsew")
        outer.grid_columnconfigure(0, weight=1)

        main_area = ctk.CTkFrame(outer, fg_color="transparent")
        main_area.grid(row=0, column=0, sticky="new", pady=4)

        self._build_connection_card(main_area).pack(fill="x", padx=4)

        row = ctk.CTkFrame(main_area, fg_color="transparent")
        row.pack(fill="x", pady=(8, 0))
        row.grid_columnconfigure(0, weight=5)
        row.grid_columnconfigure(1, weight=6)
        row.grid_rowconfigure(0, weight=1)
        self._build_camera_card(row).grid(row=0, column=0, sticky="nsew", padx=4)
        self._build_inspection_card(row).grid(row=0, column=1, sticky="nsew", padx=4)

        self._build_stats_card(main_area).pack(fill="x", padx=4, pady=(8, 0))
        self._build_monitor_card(outer).grid(row=1, column=0, sticky="ew", padx=4, pady=(8, 4))

    # ---------------- HEADER ----------------
    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color=COL_HEADER, height=76, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)

        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left", padx=20, pady=12)
        ctk.CTkLabel(left, text="📡", font=("Segoe UI", 26)).pack(side="left")
        title_box = ctk.CTkFrame(left, fg_color="transparent")
        title_box.pack(side="left", padx=(10, 0))
        ctk.CTkLabel(title_box, text="PI TCP TEST", font=("Segoe UI Semibold", 18),
                     text_color=COL_TEXT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(title_box, text="PC ↔ Raspberry Pi — kiểm tra PCB bằng xử lý ảnh",
                     font=("Segoe UI", 11), text_color=COL_TEXT_DIM, anchor="w").pack(anchor="w")

        badges = ctk.CTkFrame(header, fg_color="transparent")
        badges.pack(side="right", padx=20, pady=12)
        self.clock_badge = HeaderBadge(badges, "🕐", "")
        self.clock_badge.pack(side="right", padx=(24, 0))
        self.cam_badge = HeaderBadge(badges, "📷", "Camera")
        self.cam_badge.set_value("—", COL_TEXT_DIM)
        self.cam_badge.pack(side="right", padx=(24, 0))
        self.link_badge = HeaderBadge(badges, "🔌", "Kết nối")
        self.link_badge.pack(side="right", padx=(24, 0))

    def _tick_clock(self):
        self.clock_badge.set_value(datetime.now().strftime("%H:%M:%S"))
        self.after(1000, self._tick_clock)

    # ---------------- 1. CONNECTION SETTINGS ----------------
    def _build_connection_card(self, parent):
        card = Card(parent, "CONNECTION SETTINGS", "🔗")
        row = ctk.CTkFrame(card.body, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkLabel(row, text="IP", font=("Segoe UI", 12), text_color=COL_TEXT, width=24,
                     anchor="w").pack(side="left")
        self.ip = make_entry(row, 170, "192.168.1.100")
        self.ip.pack(side="left", padx=(6, 16))
        ctk.CTkLabel(row, text="Port", font=("Segoe UI", 12), text_color=COL_TEXT, width=36,
                     anchor="w").pack(side="left")
        self.port = make_entry(row, 90, "5000")
        self.port.pack(side="left", padx=(6, 16))
        self.btn_conn = make_button(row, "🔌 Connect", self.toggle_connect, "green", width=140)
        self.btn_conn.pack(side="left")
        self.btn_test = make_button(row, "Test Connection", self.test_connection, "dark", width=140)
        self.btn_test.pack(side="left", padx=8)
        self.conn_lbl = ctk.CTkLabel(row, text="● Chưa kết nối", font=("Segoe UI Semibold", 11),
                                      text_color=COL_TEXT_DIM)
        self.conn_lbl.pack(side="left", padx=12)
        return card

    # ---------------- 2. CAMERA TEST ----------------
    def _build_camera_card(self, parent):
        card = Card(parent, "CAMERA TEST", "📷")
        top = ctk.CTkFrame(card.body, fg_color="transparent")
        top.pack(fill="x")
        self.cam_lbl = ctk.CTkLabel(top, text="Camera: chưa kiểm tra", font=("Segoe UI", 11),
                                     text_color=COL_TEXT_DIM, anchor="w")
        self.cam_lbl.pack(side="left", fill="x", expand=True)
        self.btn_cap = make_button(top, "📸 Capture Image", self.capture, "accent", width=150)
        self.btn_cap.pack(side="right")
        self.preview = ctk.CTkLabel(card.body, text="Chưa có ảnh", font=("Segoe UI", 11),
                                    text_color=COL_TEXT_DIM, width=400, height=300,
                                    fg_color=COL_INPUT, corner_radius=10)
        self.preview.pack(pady=(10, 0))
        return card

    # ---------------- 3. INSPECTION RESULT ----------------
    def _build_inspection_card(self, parent):
        card = Card(parent, "INSPECTION RESULT", "🔍")
        body = card.body
        top = ctk.CTkFrame(body, fg_color="transparent")
        top.pack(fill="x")
        self.btn_ins = make_button(top, "▶ Start Inspection", self.inspect, "accent", width=160, height=44)
        self.btn_ins.pack(side="left")
        res_box = ctk.CTkFrame(top, fg_color=COL_INPUT, corner_radius=10)
        res_box.pack(side="left", fill="x", expand=True, padx=(12, 0))
        self.res_lbl = ctk.CTkLabel(res_box, text="—", font=("Segoe UI Semibold", 28), text_color=COL_TEXT_DIM)
        self.res_lbl.pack(pady=4)

        self.pi_time = ctk.CTkLabel(body, text="Thời gian xử lý ảnh (Pi): — ms", font=("Segoe UI Semibold", 12),
                                    text_color=COL_TEXT, anchor="w")
        self.pi_time.pack(fill="x", pady=(10, 0))
        self.rtt = ctk.CTkLabel(body, text="Tổng thời gian phản hồi (PC đo): — ms", font=("Segoe UI", 11),
                                text_color=COL_TEXT_DIM, anchor="w")
        self.rtt.pack(fill="x", pady=(2, 8))
        self.json_box = ctk.CTkTextbox(body, height=150, fg_color=COL_INPUT, text_color=COL_TEXT_DIM,
                                       font=("Consolas", 11), corner_radius=8)
        self.json_box.pack(fill="both", expand=True)
        return card

    # ---------------- 5. STATISTICS ----------------
    def _build_stats_card(self, parent):
        card = Card(parent, "STATISTICS", "📊")
        body = card.body
        for i in range(5):
            body.grid_columnconfigure(i, weight=1)
        self.stat_lbl = {}
        for i, (key, icon, label, color) in enumerate((
                ("Total", "🧮", "Total", COL_TEXT),
                ("PASS", "✅", "PASS", COL_GREEN),
                ("FAIL1", "🔧", "FAIL1 · Lỗi linh kiện", COL_AMBER),
                ("FAIL2", "⚠", "FAIL2 · Lỗi chức năng", COL_RED),
                ("Pass Rate", "📈", "Pass Rate", COL_ACCENT))):
            box = ctk.CTkFrame(body, fg_color=COL_INPUT, corner_radius=8)
            box.grid(row=0, column=i, sticky="ew", padx=3)
            ctk.CTkLabel(box, text=f"{icon} {label}", font=("Segoe UI", 10),
                         text_color=COL_TEXT_DIM).pack(anchor="w", padx=10, pady=(8, 0))
            self.stat_lbl[key] = ctk.CTkLabel(box, text="0", font=("Segoe UI Semibold", 20), text_color=color)
            self.stat_lbl[key].pack(anchor="w", padx=10, pady=(0, 8))
        self.stat_lbl["Pass Rate"].configure(text="—")
        make_button(body, "⟳ Reset", self.reset_stats, "dark", width=90).grid(row=0, column=5, padx=(8, 0))
        return card

    # ---------------- 4. COMMUNICATION MONITOR ----------------
    def _build_monitor_card(self, parent):
        card = Card(parent, "COMMUNICATION MONITOR", "📄")
        self.log_box = ctk.CTkTextbox(card.body, height=170, fg_color=COL_INPUT, text_color=COL_TEXT_DIM,
                                      font=("Consolas", 11), corner_radius=8)
        self.log_box.pack(fill="both", expand=True)
        for tag, color in LOG_TAG_COLOR.items():
            self.log_box.tag_config(tag, foreground=color)
        self.log_box.tag_config("TS", foreground=COL_GREEN)
        self.log_box.configure(state="disabled")
        make_button(card.body, "Clear", self.clear_log, "dark", width=70, height=28).pack(anchor="e", pady=(6, 0))
        return card

    def _log(self, message, level="INFO"):
        self.log_box.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log_box.insert("end", ts, "TS")
        self.log_box.insert("end", "  |  ")
        self.log_box.insert("end", f"[{level}]", level)
        self.log_box.insert("end", f"  {message}\n")
        lines = int(self.log_box.index("end-1c").split(".")[0])
        if lines > MAX_LOG_LINES:                    # giữ Monitor gọn: xóa dòng cũ nhất
            self.log_box.delete("1.0", f"{lines - MAX_LOG_LINES + 1}.0")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _log_threadsafe(self, level, message):
        """Callback cho PiLink.request (chạy ở thread nền)."""
        self.after(0, self._log, message, level)

    def clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    # ---------------- Bật/tắt điều khiển theo trạng thái ----------------
    def _refresh_enabled_states(self):
        on = self.link.sock is not None
        free = not self.busy
        if on:
            self.btn_conn.configure(text="🔌 Disconnect", fg_color=COL_RED, hover_color=COL_RED_HOVER)
            self.conn_lbl.configure(text=f"● Đã kết nối {self.peer[0]}:{self.peer[1]}", text_color=COL_GREEN)
            self.link_badge.set_value(f"{self.peer[0]}:{self.peer[1]}", COL_GREEN)
        else:
            self.btn_conn.configure(text="🔌 Connect", fg_color=COL_GREEN, hover_color=COL_GREEN_HOVER)
            self.conn_lbl.configure(text="● Chưa kết nối", text_color=COL_TEXT_DIM)
            self.link_badge.set_value("CHƯA KẾT NỐI", COL_TEXT_DIM)
        self.btn_conn.configure(state="normal" if free else "disabled")
        self.btn_test.configure(state="normal" if free else "disabled")
        for b in (self.btn_cap, self.btn_ins):
            b.configure(state="normal" if (on and free) else "disabled")
        for e in (self.ip, self.port):
            e.configure(state="disabled" if on else "normal")

    # ---------------- Chạy tác vụ mạng ở thread riêng ----------------
    def _run(self, work, done, fail=None):
        """Chạy work() ở thread nền (không đơ UI); done(kết quả) chạy ở thread UI."""
        if self.busy:
            return
        self.busy = True
        self._refresh_enabled_states()

        def task():
            try:
                res, err = work(), None
            except Exception as e:  # noqa: BLE001 - mọi lỗi đều phải hiện lên Monitor
                res, err = None, e
            self.after(0, self._finish, done, fail, res, err)

        threading.Thread(target=task, daemon=True).start()

    def _finish(self, done, fail, res, err):
        self.busy = False
        if err is None:
            done(res)
        else:
            if isinstance(err, LinkLost):
                self.link.close()
                self._log(f"Mất kết nối: {err}", "ERROR")
            elif isinstance(err, NoResponse):
                self._log("Không nhận được phản hồi từ Pi (timeout).", "ERROR")
            else:
                self._log(f"{type(err).__name__}: {err}", "ERROR")
            if fail:
                fail()
        self._refresh_enabled_states()

    # ============================================================
    # Hành động
    # ============================================================
    def _addr(self):
        host = self.ip.get().strip()
        try:
            port = int(self.port.get())
            if not host or not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            self._log("IP hoặc Port không hợp lệ.", "ERROR")
            return None
        return host, port

    def toggle_connect(self):
        if self.link.sock:
            self.link.close()
            self._log("Đã ngắt kết nối.")
            self._refresh_enabled_states()
            return
        addr = self._addr()
        if not addr:
            return

        def done(_):
            self.peer = addr
            self._log(f"Đã kết nối {addr[0]}:{addr[1]}.", "OK")

        self._run(lambda: self.link.connect(*addr), done)

    def test_connection(self):
        if self.link.sock:
            def work():
                t = time.monotonic()
                r, _ = self.link.request("ping", TIMEOUT["ping"], self._log_threadsafe)
                return r, (time.monotonic() - t) * 1000

            def done(res):
                r, ms = res
                ok = r.get("status") == "ok"
                self._log(f"Test Connection {'OK' if ok else 'FAIL'} — RTT {ms:.0f} ms", "OK" if ok else "ERROR")

            self._run(work, done)
            return
        addr = self._addr()  # chưa Connect: chỉ kiểm tra cổng TCP có mở không
        if addr:
            self._run(lambda: socket.create_connection(addr, timeout=3).close(),
                      lambda _: self._log("Cổng TCP mở (chưa Connect, chưa kiểm tra giao thức).", "OK"))

    def _set_camera(self, detail, short, color):
        self.cam_lbl.configure(text=f"Camera: {detail}", text_color=color)
        self.cam_badge.set_value(short, color)

    def capture(self):
        self._set_camera("đang chụp…", "…", COL_TEXT_DIM)

        def done(res):
            r, img = res
            if r.get("status") != "ok" or not img:
                self._set_camera("LỖI", "LỖI", COL_RED)
                self._log(f"Capture thất bại: {r.get('message', 'không có ảnh')}", "ERROR")
                return
            try:
                pil = Image.open(io.BytesIO(img))
                pil.load()
            except Exception as e:  # noqa: BLE001
                self._set_camera("ảnh lỗi", "ẢNH LỖI", COL_RED)
                self._log(f"Không giải mã được ảnh: {e}", "ERROR")
                return
            s = min(400 / pil.width, 300 / pil.height)
            self._img = ctk.CTkImage(pil, size=(int(pil.width * s), int(pil.height * s)))
            self.preview.configure(image=self._img, text="")
            self._set_camera(f"OK — {pil.width}x{pil.height}, {len(img) / 1024:.0f} KB", "OK", COL_GREEN)
            self._log(f"Nhận ảnh {pil.width}x{pil.height} ({len(img) / 1024:.0f} KB).", "OK")

        self._run(lambda: self.link.request("capture", TIMEOUT["capture"], self._log_threadsafe), done,
                  fail=lambda: self._set_camera("không phản hồi", "LỖI", COL_RED))

    def inspect(self):
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
                self.res_lbl.configure(text="ERROR", text_color=COL_RED)
                self._log(f"Phản hồi inspect không hợp lệ (status={r.get('status')!r}, result={code!r}) "
                          f"— không tính vào thống kê.", "ERROR")
                return
            pt = r.get("process_time_ms")
            self.res_lbl.configure(text=code, text_color=RESULT_COLOR[code])
            self.pi_time.configure(text="Thời gian xử lý ảnh (Pi): " + (
                f"{pt:.0f} ms" if isinstance(pt, (int, float)) else "— (thiếu process_time_ms)"))
            self.rtt.configure(text=f"Tổng thời gian phản hồi (PC đo): {rtt:.0f} ms")
            self.stats["total"] += 1
            self.stats[code] += 1
            self._show_stats()
            self._log(f"Kết quả kiểm tra: {code}", "OK" if code == "PASS" else "WARN")

        self._run(work, done)

    # ---------------- Statistics ----------------
    def _show_stats(self):
        s = self.stats
        for k, v in (("Total", s["total"]), ("PASS", s["PASS"]), ("FAIL1", s["FAIL1"]), ("FAIL2", s["FAIL2"])):
            self.stat_lbl[k].configure(text=str(v))
        self.stat_lbl["Pass Rate"].configure(
            text=f"{100 * s['PASS'] / s['total']:.1f}%" if s["total"] else "—")

    def reset_stats(self):
        self.stats = dict.fromkeys(self.stats, 0)
        self._show_stats()
        self._log("Đã reset thống kê.")

    def _on_close(self):
        self.link.close()
        self.destroy()


if __name__ == "__main__":
    PiTcpTestGUI().mainloop()
