"""
pi_test_ui.py — Công cụ THỬ giao tiếp PC ↔ Raspberry Pi (TCP) trước khi đưa vào app master (UI/).

    pip install customtkinter pillow
    python pi_test_ui.py

Công cụ đóng vai app master: kết nối TCP tới chương trình trên Pi, gửi lệnh Chụp ảnh / Test chức năng, hiển thị kết quả,
ảnh Pi gửi về và thời gian phản hồi so với timeout. Giao thức (Pi phải làm đúng) mô tả trong README.md cùng thư mục.
Bật "Dùng Pi giả lập" để chạy thử ngay trên PC khi chưa có Pi: công cụ tự mở một server giả trên 127.0.0.1 trả lời đúng
giao thức (lần lượt các kết quả ĐẠT / LỖI / không thấy PCB) — đây cũng là ví dụ mẫu cho phía Pi.

Cấu trúc: PiLink (kết nối + tách dòng/ảnh, không phụ thuộc giao diện — sau này chuyển sang UI/comm/ cho app master),
MockPi (server giả), PiTestApp (giao diện).
"""

import io
import queue
import socket
import threading
import time
from datetime import datetime

import customtkinter as ctk
from PIL import Image, ImageDraw

DEFAULT_HOST, DEFAULT_PORT = "192.168.0.20", 5000
TIMEOUT_S = {"VIS": 5.0, "FUNC": 20.0, "IMG": 5.0, "PONG": 2.0}   # khớp tab Cài đặt → Thời gian chờ của app master
MAX_IMAGE_BYTES = 5_000_000


# ============================================================
# Kết nối TCP: gửi lệnh 1 dòng, nhận dòng text + khối ảnh JPEG (sau dòng "IMG <id> <số byte>")
# ============================================================
class PiLink:
    def __init__(self, host, port, events):
        self.events = events                                  # queue: ("line", text) | ("image", id, bytes) | ("closed", lý do)
        self.sock = socket.create_connection((host, port), timeout=3)
        self.sock.settimeout(None)
        self._lock = threading.Lock()
        self._alive = True
        threading.Thread(target=self._reader, daemon=True).start()

    def send(self, line):
        with self._lock:
            self.sock.sendall((line + "\n").encode("utf-8"))

    def close(self):
        self._alive = False
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()

    def _reader(self):
        buf, img = b"", None                                   # img = (id, số byte còn chờ) khi đang nhận ảnh
        try:
            while True:
                data = self.sock.recv(65536)
                if not data:
                    raise ConnectionError("Pi đóng kết nối")
                buf += data
                while True:
                    if img:
                        pid, n = img
                        if len(buf) < n:
                            break
                        self.events.put(("image", pid, buf[:n]))
                        buf, img = buf[n:], None
                        continue
                    if b"\n" not in buf:
                        break
                    line, buf = buf.split(b"\n", 1)
                    text = line.decode("utf-8", "replace").strip()
                    if not text:
                        continue
                    self.events.put(("line", text))
                    parts = text.split()
                    if parts[0] == "IMG" and len(parts) == 3 and parts[2].isdigit():
                        n = int(parts[2])
                        if 0 < n <= MAX_IMAGE_BYTES:
                            img = (parts[1], n)
        except OSError as e:
            if self._alive:
                self.events.put(("closed", str(e)))
        except ConnectionError as e:
            if self._alive:
                self.events.put(("closed", str(e)))


# ============================================================
# Pi giả lập (chạy trên 127.0.0.1) — trả lời đúng giao thức trong README.md
# ============================================================
class MockPi(threading.Thread):
    def __init__(self, port):
        super().__init__(daemon=True)
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", port))
        self.srv.listen(1)
        self.n_vis = self.n_func = 0
        self.last_id = "0"

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

    def _serve(self, conn):
        buf = b""
        lock = threading.Lock()

        def send(line, raw=b""):
            with lock:
                conn.sendall(line.encode("utf-8") + b"\n" + raw)
        try:
            send("HELLO PI-MOCK 1.0")
            while True:
                data = conn.recv(4096)
                if not data:
                    return
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    parts = line.decode("utf-8", "replace").split()
                    if parts:
                        threading.Thread(target=self._handle, args=(parts, send), daemon=True).start()
        except OSError:
            return

    def _handle(self, parts, send):
        cmd, pid = parts[0].upper(), (parts[1] if len(parts) > 1 else "0")
        if cmd == "PING":
            send("PONG")
        elif cmd == "STATUS":
            send("STATUS READY camera=ok")
        elif cmd == "CAPTURE":
            self.last_id = pid
            k = self.n_vis % 3
            self.n_vis += 1
            time.sleep(0.8)
            send([f"VIS {pid} OK", f"VIS {pid} NG thieu_linh_kien_R12", f"VIS {pid} NOPCB"][k])
        elif cmd == "FUNC":
            ok = self.n_func % 2 == 0
            self.n_func += 1
            last = 9 if ok else 4
            for d in range(1, last + 1):
                time.sleep(0.35)
                send(f"FUNCSTEP {pid} {d}")
            time.sleep(0.5)
            send(f"FUNC {pid} OK" if ok else f"FUNC {pid} NG dung_o_so_4")
        elif cmd == "IMAGE":
            img = Image.new("RGB", (640, 480), "#cbd5e1")
            dr = ImageDraw.Draw(img)
            dr.rectangle((120, 90, 520, 390), fill="#4ade80", outline="#15803d", width=6)
            for k in range(6):
                dr.line((150, 130 + k * 35, 380, 130 + k * 35), fill="#15803d", width=3)
            dr.rectangle((410, 150, 490, 260), fill="#1e293b")
            dr.text((20, 20), f"PI GIA LAP - PCB #{pid}", fill="#1e293b")
            out = io.BytesIO()
            img.save(out, "JPEG", quality=80)
            data = out.getvalue()
            send(f"IMG {pid} {len(data)}", data)
        else:
            send(f"ERR {pid} unknown_command")


# ============================================================
# Giao diện
# ============================================================
BG, PANEL, BORDER, INPUT = "#eef2f7", "#ffffff", "#dbe3ee", "#f1f5f9"
TEXT, DIM, DISABLED = "#1e293b", "#64748b", "#94a3b8"
ACCENT, ACCENT_HOVER, SOFT, SOFT_HOVER = "#2563eb", "#1d4ed8", "#e8eef6", "#d9e2ee"
GREEN, AMBER, RED = "#16a34a", "#d97706", "#dc2626"
PILL = {"green": ("#dcfce7", "#166534"), "amber": ("#fef3c7", "#92400e"), "red": ("#fee2e2", "#991b1b"),
        "blue": ("#dbeafe", "#1e40af"), "gray": (INPUT, DIM)}
LOG_COLOR = {"INFO": ACCENT, "OK": GREEN, "WARN": AMBER, "ERROR": RED, "TX": DIM, "RX": "#7c3aed"}
F, FB = "Segoe UI", "Segoe UI Semibold"
ctk.set_appearance_mode("light")


class Card(ctk.CTkFrame):
    def __init__(self, master, title, **kw):
        super().__init__(master, fg_color=PANEL, border_color=BORDER, border_width=1, corner_radius=12, **kw)
        ctk.CTkLabel(self, text=title, font=(FB, 13), text_color=TEXT, anchor="w").pack(fill="x", padx=14, pady=(10, 4))
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=14, pady=(0, 12))


def button(parent, text, cmd, primary=False, **kw):
    return ctk.CTkButton(parent, text=text, command=cmd, height=34, corner_radius=8, font=(FB, 12),
                         fg_color=ACCENT if primary else SOFT, hover_color=ACCENT_HOVER if primary else SOFT_HOVER,
                         text_color="#ffffff" if primary else TEXT, **kw)


def set_pill(label, text, kind):
    bg, fg = PILL[kind]
    label.configure(text=text, fg_color=bg, text_color=fg)


class PiTestApp(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=BG)
        self.title("Thử Raspberry Pi — TCP")
        self.geometry("1280x740")
        self.minsize(1100, 660)
        try:                                  # sau khi cửa sổ hiện ra (customtkinter đặt lại kích thước lúc khởi tạo)
            self.after(50, lambda: self.state("zoomed"))              # Windows: mở toàn màn hình
        except Exception:
            pass
        self.events = queue.Queue()
        self.link = None
        self.mock = None
        self.pending = {}                     # loại phản hồi chờ ("VIS"/"FUNC"/"IMG"/"PONG") -> (id, t_gửi)
        self.grid_columnconfigure((0, 1, 2), weight=1, uniform="c")
        self.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=3, sticky="ew", padx=16, pady=(12, 6))
        ctk.CTkLabel(head, text="Thử giao tiếp Raspberry Pi (kiểm tra ngoại quan + chức năng)", font=(FB, 18),
                     text_color=TEXT).pack(side="left")
        self.status = ctk.CTkLabel(head, text="● CHƯA KẾT NỐI", font=(FB, 12), text_color=DIM)
        self.status.pack(side="right")

        self._build_connection().grid(row=1, column=0, sticky="nsew", padx=(16, 6))
        mid = ctk.CTkFrame(self, fg_color="transparent")
        mid.grid(row=1, column=1, sticky="nsew", padx=6)
        self._build_vis(mid)
        self._build_func(mid)
        self._build_image().grid(row=1, column=2, sticky="nsew", padx=(6, 16))
        self._build_log()
        self._set_connected(False)
        self.after(40, self._drain)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------- Kết nối ----------------
    def _build_connection(self):
        c = Card(self, "1. Kết nối TCP tới Raspberry Pi")
        b = c.body

        def row(label, default, width=150):
            r = ctk.CTkFrame(b, fg_color="transparent")
            r.pack(fill="x", pady=3)
            ctk.CTkLabel(r, text=label, font=(F, 12), text_color=TEXT, width=90, anchor="w").pack(side="left")
            e = ctk.CTkEntry(r, width=width, height=30, fg_color=INPUT, border_color=BORDER, text_color=TEXT)
            e.insert(0, default)
            e.pack(side="left")
            return e
        self.host_entry = row("Địa chỉ IP", DEFAULT_HOST)
        self.port_entry = row("Cổng", str(DEFAULT_PORT))
        self.mock_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(b, text="Dùng Pi giả lập (127.0.0.1, chạy thử khi chưa có Pi)", variable=self.mock_var,
                      font=(F, 11), text_color=DIM).pack(anchor="w", pady=(6, 0))
        self.connect_btn = button(b, "Connect", self._toggle_connect, primary=True)
        self.connect_btn.pack(fill="x", pady=(10, 4))
        self.ping_btn = button(b, "PING (Pi còn sống?)", lambda: self._send("PING", "PONG"))
        self.ping_btn.pack(fill="x", pady=2)
        self.status_btn = button(b, "STATUS (camera sẵn sàng?)", lambda: self._send("STATUS"))
        self.status_btn.pack(fill="x", pady=2)

        r = ctk.CTkFrame(b, fg_color="transparent")
        r.pack(fill="x", pady=(14, 3))
        ctk.CTkLabel(r, text="Mã PCB", font=(F, 12), text_color=TEXT, width=90, anchor="w").pack(side="left")
        self.id_entry = ctk.CTkEntry(r, width=90, height=30, fg_color=INPUT, border_color=BORDER, text_color=TEXT)
        self.id_entry.insert(0, "1")
        self.id_entry.pack(side="left")
        ctk.CTkLabel(b, text="CAPTURE, FUNC, IMAGE của cùng 1 PCB dùng chung mã này.", font=(F, 10), text_color=DISABLED,
                     anchor="w").pack(fill="x")

        r = ctk.CTkFrame(b, fg_color="transparent")
        r.pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(r, text="Gửi lệnh tự gõ", font=(FB, 11), text_color=DIM, anchor="w").pack(fill="x")
        self.raw_entry = ctk.CTkEntry(r, height=30, fg_color=INPUT, border_color=BORDER, text_color=TEXT,
                                      placeholder_text="vd: CAPTURE 7")
        self.raw_entry.pack(side="left", fill="x", expand=True, pady=(2, 0))
        self.raw_entry.bind("<Return>", lambda e: self._send_raw())
        self.raw_btn = button(r, "Gửi", self._send_raw, width=60)
        self.raw_btn.pack(side="left", padx=(4, 0), pady=(2, 0))
        ctk.CTkLabel(b, text="Giao thức: mỗi lệnh 1 dòng text kết thúc '\\n' (UTF-8). Chi tiết trong README.md.",
                     font=(F, 10), text_color=DISABLED, wraplength=360, justify="left", anchor="w").pack(fill="x", pady=(10, 0))
        return c

    def _toggle_connect(self):
        if self.link:
            self._disconnect("Đã ngắt kết nối.")
            return
        host, port = self.host_entry.get().strip(), self.port_entry.get().strip()
        try:
            port = int(port)
        except ValueError:
            self.log("Cổng phải là số.", "ERROR")
            return
        if self.mock_var.get():
            host = "127.0.0.1"
            try:
                self.mock = MockPi(port)
                self.mock.start()
                self.log(f"Đã mở Pi giả lập ở 127.0.0.1:{port}.", "INFO")
            except OSError as e:
                self.log(f"Không mở được Pi giả lập ở cổng {port}: {e}", "ERROR")
                self.mock = None
                return
        try:
            self.link = PiLink(host, port, self.events)
        except OSError as e:
            self.log(f"Không kết nối được {host}:{port} — {e}. Kiểm tra Pi đã chạy chương trình, cùng mạng LAN, "
                     "đúng IP / cổng, tường lửa.", "ERROR")
            self._stop_mock()
            return
        self.log(f"Đã kết nối {host}:{port}.", "OK")
        self._set_connected(True)

    def _disconnect(self, reason, level="INFO"):
        if self.link:
            self.link.close()
            self.link = None
        self._stop_mock()
        self.pending.clear()
        self._set_connected(False)
        self.log(reason, level)

    def _stop_mock(self):
        if self.mock:
            self.mock.stop()
            self.mock = None

    def _set_connected(self, on):
        self.connect_btn.configure(text="Disconnect" if on else "Connect", fg_color=SOFT if on else ACCENT,
                                   hover_color=SOFT_HOVER if on else ACCENT_HOVER, text_color=TEXT if on else "#ffffff")
        for w in (self.host_entry, self.port_entry):
            w.configure(state="disabled" if on else "normal")
        for w in (self.ping_btn, self.status_btn, self.raw_btn, self.vis_btn, self.func_btn, self.img_btn):
            w.configure(state="normal" if on else "disabled")
        self.status.configure(text="● ĐÃ KẾT NỐI" if on else "● CHƯA KẾT NỐI", text_color=GREEN if on else DIM)

    def _on_close(self):
        if self.link:
            self.link.close()
        self._stop_mock()
        self.destroy()

    # ---------------- Gửi lệnh ----------------
    def _pcb_id(self):
        pid = self.id_entry.get().strip() or "0"
        return pid if pid.replace("-", "").isalnum() else "0"

    def _send(self, line, expect=None, pid=None):
        if not self.link:
            self.log("Chưa kết nối.", "WARN")
            return False
        try:
            self.link.send(line)
        except OSError as e:
            self._disconnect(f"Mất kết nối khi gửi: {e}", "ERROR")
            return False
        self.log(line, "TX")
        if expect:
            self.pending[expect] = (pid, time.time())
        return True

    def _send_raw(self):
        line = self.raw_entry.get().strip()
        if line:
            self._send(line)

    # ---------------- Kiểm tra ngoại quan ----------------
    def _build_vis(self, parent):
        c = Card(parent, "2. Kiểm tra ngoại quan (camera)")
        c.pack(fill="x")
        b = c.body
        self.vis_btn = button(b, "📷  CAPTURE — chụp + xử lý ảnh", self._do_vis, primary=True)
        self.vis_btn.pack(fill="x")
        r = ctk.CTkFrame(b, fg_color="transparent")
        r.pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(r, text="Kết quả", font=(F, 12), text_color=DIM).pack(side="left")
        self.vis_pill = ctk.CTkLabel(r, text="—", corner_radius=8, height=26, padx=12, font=(FB, 12))
        self.vis_pill.pack(side="right")
        set_pill(self.vis_pill, "CHƯA CHẠY", "gray")
        self.vis_detail = ctk.CTkLabel(b, text="", font=(F, 11), text_color=DIM, anchor="w")
        self.vis_detail.pack(fill="x", pady=(4, 0))
        self.vis_time = ctk.CTkLabel(b, text=f"Timeout {TIMEOUT_S['VIS']:g} s", font=(F, 10), text_color=DISABLED,
                                     anchor="w")
        self.vis_time.pack(fill="x")

    def _do_vis(self):
        pid = self._pcb_id()
        if self._send(f"CAPTURE {pid}", "VIS", pid):
            set_pill(self.vis_pill, "ĐANG XỬ LÝ...", "blue")
            self.vis_detail.configure(text=f"PCB #{pid}")

    # ---------------- Kiểm tra chức năng ----------------
    def _build_func(self, parent):
        c = Card(parent, "3. Kiểm tra chức năng (LED 7 đoạn đếm 1 → 9)")
        c.pack(fill="x", pady=(12, 0))
        b = c.body
        ctk.CTkLabel(b, text="Trước khi bấm: PCB phải đang được cấp nguồn (PLC hạ xi lanh 2 — dùng PLC/plc_test_ui.py, "
                            "hoặc cấp nguồn tay khi thử). Pi xem LED và báo từng số đếm được.",
                     font=(F, 10), text_color=DISABLED, wraplength=380, justify="left", anchor="w").pack(fill="x")
        self.func_btn = button(b, "🔌  FUNC — đọc LED 7 đoạn", self._do_func, primary=True)
        self.func_btn.pack(fill="x", pady=(6, 0))
        digits = ctk.CTkFrame(b, fg_color="transparent")
        digits.pack(fill="x", pady=(10, 0))
        self.digit_boxes = []
        for d in range(1, 10):
            digits.grid_columnconfigure(d - 1, weight=1, uniform="d")
            lb = ctk.CTkLabel(digits, text=str(d), height=36, corner_radius=6, font=("Consolas", 18, "bold"),
                              fg_color=INPUT, text_color=DISABLED)
            lb.grid(row=0, column=d - 1, sticky="ew", padx=2)
            self.digit_boxes.append(lb)
        r = ctk.CTkFrame(b, fg_color="transparent")
        r.pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(r, text="Kết quả", font=(F, 12), text_color=DIM).pack(side="left")
        self.func_pill = ctk.CTkLabel(r, text="—", corner_radius=8, height=26, padx=12, font=(FB, 12))
        self.func_pill.pack(side="right")
        set_pill(self.func_pill, "CHƯA CHẠY", "gray")
        self.func_detail = ctk.CTkLabel(b, text="", font=(F, 11), text_color=DIM, anchor="w")
        self.func_detail.pack(fill="x", pady=(4, 0))
        self.func_time = ctk.CTkLabel(b, text=f"Timeout {TIMEOUT_S['FUNC']:g} s", font=(F, 10), text_color=DISABLED,
                                      anchor="w")
        self.func_time.pack(fill="x")

    def _do_func(self):
        pid = self._pcb_id()
        if self._send(f"FUNC {pid}", "FUNC", pid):
            for lb in self.digit_boxes:
                lb.configure(fg_color=INPUT, text_color=DISABLED)
            set_pill(self.func_pill, "ĐANG ĐỌC LED...", "blue")
            self.func_detail.configure(text=f"PCB #{pid}")

    # ---------------- Ảnh ----------------
    def _build_image(self):
        c = Card(self, "4. Ảnh Pi gửi về")
        b = c.body
        self.img_btn = button(b, "🖼  IMAGE — lấy ảnh vừa chụp", self._do_image)
        self.img_btn.pack(fill="x")
        self.img_label = ctk.CTkLabel(b, text="(chưa có ảnh)", fg_color=INPUT, corner_radius=8, text_color=DISABLED,
                                      height=300)
        self.img_label.pack(fill="both", expand=True, pady=(8, 0))
        self.img_info = ctk.CTkLabel(b, text="", font=(F, 10), text_color=DIM, anchor="w")
        self.img_info.pack(fill="x", pady=(4, 0))
        return c

    def _do_image(self):
        pid = self._pcb_id()
        self._send(f"IMAGE {pid}", "IMG", pid)

    def _show_image(self, pid, data):
        try:
            img = Image.open(io.BytesIO(data))
            img.load()
        except Exception as e:
            self.log(f"Ảnh của PCB #{pid} không đọc được ({len(data)} byte): {e}", "ERROR")
            return
        w = max(200, self.img_label.winfo_width() - 8)
        h = max(150, self.img_label.winfo_height() - 8)
        scale = min(w / img.width, h / img.height)
        self._img_ref = ctk.CTkImage(light_image=img, size=(int(img.width * scale), int(img.height * scale)))
        self.img_label.configure(image=self._img_ref, text="")
        self.img_info.configure(text=f"PCB #{pid} · {img.width}×{img.height} · {len(data) / 1024:.0f} KB")

    # ---------------- Nhận phản hồi ----------------
    def _elapsed(self, key):
        p = self.pending.pop(key, None)
        return (time.time() - p[1]) if p else None

    def _handle_line(self, text):
        self.log(text, "RX")
        parts = text.split()
        head = parts[0].upper()
        if head == "PONG":
            dt = self._elapsed("PONG")
            self.log("Pi trả lời PING" + (f" sau {dt * 1000:.0f} ms." if dt is not None else "."), "OK")
        elif head == "VIS" and len(parts) >= 3:
            dt = self._elapsed("VIS")
            result, why = parts[2].upper(), " ".join(parts[3:]).replace("_", " ")
            kind, label = {"OK": ("green", "ĐẠT"), "NG": ("amber", "LỖI 1"), "NOPCB": ("gray", "KHÔNG THẤY PCB")}.get(
                result, ("red", f"SAI: {result}"))
            set_pill(self.vis_pill, label, kind)
            self.vis_detail.configure(text=f"PCB #{parts[1]}" + (f" — {why}" if why else ""))
            self._show_time(self.vis_time, "VIS", dt)
        elif head == "FUNCSTEP" and len(parts) >= 3 and parts[2].isdigit():
            d = int(parts[2])
            if 1 <= d <= 9:
                self.digit_boxes[d - 1].configure(fg_color=GREEN, text_color="#ffffff")
        elif head == "FUNC" and len(parts) >= 3:
            dt = self._elapsed("FUNC")
            result, why = parts[2].upper(), " ".join(parts[3:]).replace("_", " ")
            ok = result == "OK"
            set_pill(self.func_pill, "ĐẠT" if ok else ("LỖI 2" if result == "NG" else f"SAI: {result}"),
                     "green" if ok else "red")
            self.func_detail.configure(text=f"PCB #{parts[1]}" + (f" — {why}" if why else ""))
            self._show_time(self.func_time, "FUNC", dt)
        elif head == "IMG":
            pass                                                   # khối ảnh tới ngay sau, xử lý ở sự kiện "image"
        elif head == "ERR":
            self.log(f"Pi báo lỗi: {' '.join(parts[1:])}", "ERROR")
        elif head in ("STATUS", "HELLO"):
            self.log(f"Pi: {' '.join(parts[1:])}", "OK")
        else:
            self.log("Dòng không đúng giao thức (xem README.md).", "WARN")

    def _show_time(self, label, key, dt):
        if dt is None:
            label.configure(text=f"Timeout {TIMEOUT_S[key]:g} s", text_color=DISABLED)
            return
        late = dt > TIMEOUT_S[key]
        label.configure(text=f"Phản hồi sau {dt:.2f} s / timeout {TIMEOUT_S[key]:g} s" + ("  ⚠ QUÁ HẠN" if late else ""),
                        text_color=RED if late else DIM)

    def _drain(self):
        while True:
            try:
                ev = self.events.get_nowait()
            except queue.Empty:
                break
            if ev[0] == "line":
                self._handle_line(ev[1])
            elif ev[0] == "image":
                dt = self._elapsed("IMG")
                self.log(f"Nhận ảnh PCB #{ev[1]}: {len(ev[2])} byte" + (f" sau {dt:.2f} s" if dt else ""), "OK")
                self._show_image(ev[1], ev[2])
            elif ev[0] == "closed" and self.link:
                self._disconnect(f"Mất kết nối với Pi: {ev[1]}", "ERROR")
        now = time.time()                                         # báo quá thời gian chờ (giống app master sẽ làm)
        for key, (pid, t0) in list(self.pending.items()):
            if now - t0 > TIMEOUT_S[key]:
                self.pending.pop(key)
                self.log(f"Quá {TIMEOUT_S[key]:g} s chưa nhận được {key} cho PCB #{pid} — app master sẽ báo lỗi và "
                         "dừng hệ thống ở trường hợp này.", "ERROR")
                pill = {"VIS": self.vis_pill, "FUNC": self.func_pill}.get(key)
                if pill:
                    set_pill(pill, "QUÁ THỜI GIAN", "red")
        self.after(40, self._drain)

    # ---------------- Log ----------------
    def _build_log(self):
        c = Card(self, "Log (TX = PC gửi, RX = Pi trả lời)")
        c.grid(row=2, column=0, columnspan=3, sticky="ew", padx=16, pady=12)
        bar = ctk.CTkFrame(c.body, fg_color="transparent")
        bar.pack(fill="x")
        button(bar, "Xóa", lambda: self.log_box.delete("1.0", "end"), width=60).pack(side="right")
        self.log_box = ctk.CTkTextbox(c.body, height=110, fg_color=INPUT, text_color=TEXT, font=("Consolas", 11))
        self.log_box.pack(fill="x", pady=(4, 0))
        for lvl, col in LOG_COLOR.items():
            self.log_box.tag_config(lvl, foreground=col)

    def log(self, msg, level="INFO"):
        self.log_box.insert("end", f"{datetime.now():%H:%M:%S}  ")
        self.log_box.insert("end", f"[{level:<5}] ", level)
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")


if __name__ == "__main__":
    PiTestApp().mainloop()
