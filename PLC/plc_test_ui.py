"""
plc_test_ui.py — Công cụ THỬ giao tiếp PC ↔ PLC Mitsubishi FX0N qua RS422, trước khi đưa vào app master (UI/).

    pip install customtkinter pyserial
    python plc_test_ui.py

PC nói chuyện với FX0N qua CỔNG LẬP TRÌNH RS422 bằng giao thức FX gốc (9600 baud, 7E1, khung STX ... ETX + tổng kiểm).
PLC KHÔNG cần viết code giao tiếp: PC đọc/ghi thẳng X, Y, M, S, T, C, D. PC ra lệnh bằng cách ÉP bit M; chương trình
ladder đọc các bit M đó rồi tự điều khiển Y (nhờ vậy liên động an toàn — E-Stop, CB2 dừng băng tải — vẫn nằm ở PLC).
Bảng gán X / Y / M bên dưới (INPUTS, OUTPUTS, PC_CMDS, PLC_STATUS) là ĐỀ XUẤT: sửa theo đấu dây và ladder thật.
Xem README.md cùng thư mục.

Cấu trúc: FxLink (giao thức, không phụ thuộc giao diện — sau này chuyển sang UI/comm/ cho app master dùng lại),
Worker (luồng riêng giữ cổng COM, chạy lệnh tuần tự để giao diện không bị đơ), PlcTestApp (giao diện).
"""

import queue
import threading
import time
from datetime import datetime

import customtkinter as ctk
import serial
import serial.tools.list_ports

# ============================================================
# Bảng gán tín hiệu — ĐỀ XUẤT, sửa theo đấu dây / ladder thật
# ============================================================
INPUTS = {                                   # X đánh số BÁT PHÂN (X0..X7, X10..X17)
    "X0": "CB1 · PCB ở đầu băng tải", "X1": "CB2 · PCB tới trạm kiểm tra", "X2": "CB3 · PCB tới vị trí gắp",
    "X3": "Xi lanh 1 · S1 (đã thu)", "X4": "Xi lanh 1 · S2 (đã hạ)",
    "X5": "Xi lanh 2 · S1 (đã thu)", "X6": "Xi lanh 2 · S2 (đã hạ)",
    "X7": "E-Stop (NC: 1 = bình thường)", "X10": "Nút START (tủ)", "X11": "Nút STOP (tủ)", "X12": "Nút RESET (tủ)",
}
OUTPUTS = {
    "Y0": "Động cơ bước cấp PCB (xung)", "Y1": "Động cơ băng tải", "Y2": "Van xi lanh 1 (chặn PCB)",
    "Y3": "Van xi lanh 2 (cấp nguồn PCB)", "Y4": "Đèn xanh", "Y5": "Đèn vàng", "Y6": "Đèn đỏ", "Y7": "Còi",
}
# Lệnh PC -> PLC (PC ép bit M). "giu": PC giữ ON/OFF; "xung": PC bật ON ~0.3 s rồi tắt (ladder bắt cạnh lên).
PC_CMDS = [
    ("M100", "Băng tải chạy", "giu"),
    ("M101", "Cấp 1 PCB", "xung"),
    ("M102", "Xi lanh 1 hạ (chặn PCB)", "giu"),
    ("M103", "Xi lanh 2 hạ (cấp nguồn PCB · test chức năng)", "giu"),
    ("M110", "START", "xung"),
    ("M111", "STOP", "xung"),
    ("M112", "RESET", "xung"),
]
# Trạng thái PLC -> PC (ladder ghi, PC chỉ đọc)
PLC_STATUS = {"M200": "E-Stop đang chốt", "M201": "Có lỗi", "M202": "Đang cấp PCB", "M203": "Sẵn sàng"}

PULSE_S = 0.3          # độ dài xung cho lệnh kiểu "xung"
POLL_S = 0.3           # chu kỳ đọc giám sát X / Y / M

# ============================================================
# Giao thức FX (cổng lập trình) — FX0N / FX0 / FX1S / FX1N / FX2N dùng chung bảng địa chỉ dưới đây
# ============================================================
STX, ETX, ENQ, ACK, NAK = 0x02, 0x03, 0x05, 0x06, 0x15
BYTE_BASE = {"S": 0x0000, "X": 0x0080, "Y": 0x00A0, "T": 0x00C0, "M": 0x0100, "C": 0x01C0}   # lệnh đọc '0' / ghi '1'
M8000_BYTE_BASE = 0x01E0                                                                      # M8000..M8255
FORCE_BASE = {"S": 0x0000, "X": 0x0400, "Y": 0x0500, "T": 0x0600, "M": 0x0800, "C": 0x0E00}  # lệnh ép bit '7' / '8'
M8000_FORCE_BASE = 0x0F00
D_BASE, D8000_BASE = 0x1000, 0x0E00                                                           # D0.., D8000..
CTRL_NAMES = {STX: "<STX>", ETX: "<ETX>", ENQ: "<ENQ>", ACK: "<ACK>", NAK: "<NAK>"}


class FxError(Exception):
    """Lỗi giao tiếp / dữ liệu với PLC — giao diện bắt và ghi Log, không làm app chết."""


def parse_device(text):
    """'X10' -> ('X', 8) (X/Y bát phân), 'M100' -> ('M', 100), 'D8000' -> ('D', 8000)."""
    t = text.strip().upper()
    dev, num = t[:1], t[1:]
    if dev not in ("X", "Y", "M", "S", "T", "C", "D") or not num.isdigit():
        raise FxError(f"Tên thiết bị không hợp lệ: {text!r} (vd X0, Y3, M100, D10)")
    if dev in ("X", "Y"):
        if any(ch in "89" for ch in num):
            raise FxError(f"{dev} đánh số hệ BÁT PHÂN (chỉ có chữ số 0-7): {text!r}")
        return dev, int(num, 8)
    return dev, int(num)


def device_name(dev, idx):
    return f"{dev}{idx:o}" if dev in ("X", "Y") else f"{dev}{idx}"


def show_bytes(data):
    """Bytes -> chuỗi dễ đọc cho Log: ký tự điều khiển hiện bằng tên, vd <STX>00080 02<ETX>5A."""
    return "".join(CTRL_NAMES.get(b, chr(b) if 32 <= b < 127 else f"<{b:02X}>") for b in data)


def _checksum(body):
    return f"{sum(body) & 0xFF:02X}".encode("ascii")


def build_frame(cmd, payload=b""):
    """STX + lệnh + dữ liệu + ETX + tổng kiểm (2 ký tự hex = byte thấp của tổng các byte SAU STX, gồm cả ETX)."""
    body = cmd + payload + bytes([ETX])
    return bytes([STX]) + body + _checksum(body)


class FxLink:
    """Nói chuyện với FX0N qua cổng lập trình. Mọi hàm chặn (blocking) tối đa `timeout` giây — gọi từ luồng Worker."""

    def __init__(self, port, baud=9600, fmt="7E1", timeout=0.8, trace=None):
        bits = {"7": serial.SEVENBITS, "8": serial.EIGHTBITS}[fmt[0]]
        parity = {"E": serial.PARITY_EVEN, "O": serial.PARITY_ODD, "N": serial.PARITY_NONE}[fmt[1]]
        stop = serial.STOPBITS_TWO if fmt[2] == "2" else serial.STOPBITS_ONE
        try:
            self.ser = serial.Serial(port, baud, bytesize=bits, parity=parity, stopbits=stop, timeout=0.02)
        except serial.SerialException as e:
            raise FxError(f"Không mở được {port}: {e}")
        self.timeout = timeout
        self.trace_fn = trace or (lambda direction, data: None)
        self.quiet = False            # True khi Worker đang đọc giám sát: không ghi TX/RX vào Log cho đỡ ngập

    def trace(self, direction, data):
        if not self.quiet:
            self.trace_fn(direction, data)

    def close(self):
        try:
            self.ser.close()
        except serial.SerialException:
            pass

    # ---------- truyền / nhận ----------
    def _tx(self, data):
        self.ser.reset_input_buffer()
        try:
            self.ser.write(data)
        except serial.SerialException as e:
            raise FxError(f"Lỗi ghi cổng COM: {e}")
        self.trace("TX", data)

    def _rx(self, complete):
        """Đọc tới khi complete(buf) đúng hoặc hết thời gian."""
        buf, t_end = b"", time.time() + self.timeout
        while time.time() < t_end:
            try:
                buf += self.ser.read(64)
            except serial.SerialException as e:
                raise FxError(f"Lỗi đọc cổng COM: {e}")
            if complete(buf):
                self.trace("RX", buf)
                return buf
        if buf:
            self.trace("RX", buf)
        raise FxError("PLC không trả lời (kiểm tra cáp RS422, cổng COM, baud 9600 7E1, PLC đã cấp nguồn)."
                      if not buf else f"Phản hồi không đầy đủ: {show_bytes(buf)}")

    def _expect_ack(self):
        buf = self._rx(lambda b: ACK in b or NAK in b)
        if NAK in buf:
            raise FxError("PLC trả NAK (từ chối lệnh: sai địa chỉ / sai tổng kiểm / thiết bị không tồn tại).")

    # ---------- lệnh cơ bản ----------
    def enq(self):
        """Gửi ENQ, PLC sẵn sàng thì trả ACK — kiểm tra nhanh đường truyền."""
        self._tx(bytes([ENQ]))
        self._expect_ack()

    def read_bytes(self, addr, n):
        """Lệnh '0': đọc n byte từ địa chỉ addr."""
        self._tx(build_frame(b"0", f"{addr:04X}{n:02X}".encode("ascii")))

        def complete(b):
            if NAK in b[:1]:
                return True
            i = b.find(bytes([STX]))
            j = b.find(bytes([ETX]), i + 1) if i >= 0 else -1
            return j >= 0 and len(b) >= j + 3
        buf = self._rx(complete)
        if buf[:1] == bytes([NAK]):
            raise FxError(f"PLC trả NAK khi đọc địa chỉ {addr:04X}h.")
        i = buf.find(bytes([STX]))
        j = buf.find(bytes([ETX]), i + 1)
        if _checksum(buf[i + 1:j + 1]) != buf[j + 1:j + 3]:
            raise FxError(f"Sai tổng kiểm trong phản hồi: {show_bytes(buf)}")
        hexdata = buf[i + 1:j].decode("ascii", "replace")
        if len(hexdata) != 2 * n:
            raise FxError(f"Phản hồi có {len(hexdata) // 2} byte, cần {n}: {show_bytes(buf)}")
        try:
            return bytes.fromhex(hexdata)
        except ValueError:
            raise FxError(f"Dữ liệu không phải hex: {show_bytes(buf)}")

    def write_bytes(self, addr, data):
        """Lệnh '1': ghi các byte vào địa chỉ addr."""
        payload = f"{addr:04X}{len(data):02X}".encode("ascii") + data.hex().upper().encode("ascii")
        self._tx(build_frame(b"1", payload))
        self._expect_ack()

    def force(self, dev, idx, on):
        """Lệnh '7' (ép ON) / '8' (ép OFF) một bit. Địa chỉ gửi đảo byte: byte thấp trước."""
        if dev not in FORCE_BASE:
            raise FxError(f"Không ép bit được thiết bị {dev}.")
        base = M8000_FORCE_BASE + (idx - 8000) if dev == "M" and idx >= 8000 else FORCE_BASE[dev] + idx
        a = f"{base:04X}"
        self._tx(build_frame(b"7" if on else b"8", (a[2:] + a[:2]).encode("ascii")))
        self._expect_ack()

    # ---------- tiện ích ----------
    @staticmethod
    def _byte_addr(dev, idx):
        if dev == "M" and idx >= 8000:
            return M8000_BYTE_BASE + (idx - 8000) // 8, (idx - 8000) % 8
        if dev not in BYTE_BASE:
            raise FxError(f"{dev} không phải thiết bị bit.")
        return BYTE_BASE[dev] + idx // 8, idx % 8

    def read_bit(self, dev, idx):
        addr, bit = self._byte_addr(dev, idx)
        return (self.read_bytes(addr, 1)[0] >> bit) & 1

    def read_bits(self, dev, start, count):
        """Đọc count bit liên tiếp từ start (1 lần đọc) -> list 0/1."""
        a0, _ = self._byte_addr(dev, start)
        a1, _ = self._byte_addr(dev, start + count - 1)
        data = self.read_bytes(a0, a1 - a0 + 1)
        out = []
        for k in range(count):
            a, bit = self._byte_addr(dev, start + k)
            out.append((data[a - a0] >> bit) & 1)
        return out

    @staticmethod
    def _d_addr(n):
        return D8000_BASE + 2 * (n - 8000) if n >= 8000 else D_BASE + 2 * n

    def read_d(self, n):
        lo, hi = self.read_bytes(self._d_addr(n), 2)
        v = lo | (hi << 8)
        return v - 0x10000 if v >= 0x8000 else v

    def write_d(self, n, value):
        if not -32768 <= value <= 65535:
            raise FxError("Giá trị D phải trong -32768..65535 (16 bit).")
        v = value & 0xFFFF
        self.write_bytes(self._d_addr(n), bytes([v & 0xFF, v >> 8]))


# ============================================================
# Luồng làm việc: giữ cổng COM, chạy lệnh tuần tự, tự đọc giám sát khi rảnh
# ============================================================
class Worker(threading.Thread):
    def __init__(self, link, results):
        super().__init__(daemon=True)
        self.link, self.results = link, results
        self.jobs = queue.Queue()
        self.stop_evt = threading.Event()
        self.monitor = True

    def submit(self, fn, on_ok=None, label=""):
        self.jobs.put((fn, on_ok, label))

    def run(self):
        while not self.stop_evt.is_set():
            try:
                fn, on_ok, label = self.jobs.get(timeout=POLL_S)
            except queue.Empty:
                if self.monitor:
                    self.link.quiet = True
                    self._do(self._poll, None, "monitor")
                    self.link.quiet = False
                continue
            self._do(fn, on_ok, label)
        self.link.close()

    def _do(self, fn, on_ok, label):
        try:
            self.results.put(("ok", on_ok, fn(self.link), label))
        except FxError as e:
            self.results.put(("err", None, str(e), label))
        except Exception as e:                            # lỗi lạ: báo ra Log, không làm chết luồng
            self.results.put(("err", None, f"{type(e).__name__}: {e}", label))

    @staticmethod
    def _poll(link):
        return {"X": link.read_bits("X", 0, 16), "Y": link.read_bits("Y", 0, 16),
                "M100": link.read_bits("M", 100, 16), "M200": link.read_bits("M", 200, 8)}


# ============================================================
# Giao diện
# ============================================================
BG, PANEL, BORDER, INPUT = "#eef2f7", "#ffffff", "#dbe3ee", "#f1f5f9"
TEXT, DIM, DISABLED = "#1e293b", "#64748b", "#94a3b8"
ACCENT, ACCENT_HOVER, SOFT, SOFT_HOVER = "#2563eb", "#1d4ed8", "#e8eef6", "#d9e2ee"
GREEN, AMBER, RED = "#16a34a", "#d97706", "#dc2626"
LOG_COLOR = {"INFO": ACCENT, "OK": GREEN, "WARN": AMBER, "ERROR": RED, "TX": DIM, "RX": "#7c3aed"}
F, FB = "Segoe UI", "Segoe UI Semibold"
ctk.set_appearance_mode("light")


class Card(ctk.CTkFrame):
    def __init__(self, master, title, **kw):
        super().__init__(master, fg_color=PANEL, border_color=BORDER, border_width=1, corner_radius=12, **kw)
        ctk.CTkLabel(self, text=title, font=(FB, 13), text_color=TEXT, anchor="w").pack(fill="x", padx=14, pady=(10, 4))
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=14, pady=(0, 12))


def soft_btn(parent, text, cmd, **kw):
    kw.setdefault("fg_color", SOFT)
    kw.setdefault("hover_color", SOFT_HOVER)
    kw.setdefault("text_color", TEXT if kw["fg_color"] == SOFT else "#ffffff")
    return ctk.CTkButton(parent, text=text, command=cmd, height=30, corner_radius=8, font=(FB, 11), **kw)


class Lamp(ctk.CTkFrame):
    """Đèn trạng thái 1 bit: ● + tên thiết bị + mô tả."""

    def __init__(self, master, name, desc):
        super().__init__(master, fg_color="transparent")
        self.dot = ctk.CTkLabel(self, text="●", font=(F, 14), text_color=DISABLED, width=16, height=20)
        self.dot.pack(side="left")
        ctk.CTkLabel(self, text=name, font=(FB, 11), text_color=TEXT, width=40, height=20, anchor="w").pack(side="left")
        ctk.CTkLabel(self, text=desc, font=(F, 11), text_color=DIM if desc else DISABLED, height=20,
                     anchor="w").pack(side="left")
        self.value = None

    def set(self, value, on_color=GREEN):
        if value != self.value:
            self.value = value
            self.dot.configure(text_color=DISABLED if value is None else (on_color if value else "#cbd5e1"))


class PlcTestApp(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=BG)
        self.title("Thử PLC FX0N — RS422")
        self.geometry("1280x740")
        self.minsize(1100, 660)
        try:                                  # sau khi cửa sổ hiện ra (customtkinter đặt lại kích thước lúc khởi tạo)
            self.after(50, lambda: self.state("zoomed"))              # Windows: mở toàn màn hình
        except Exception:
            pass
        self.results = queue.Queue()
        self.trace_q = queue.Queue()
        self.worker = None
        self.grid_columnconfigure((0, 1, 2), weight=1, uniform="c")
        self.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=3, sticky="ew", padx=16, pady=(12, 6))
        ctk.CTkLabel(head, text="Thử giao tiếp PLC Mitsubishi FX0N qua RS422", font=(FB, 18), text_color=TEXT
                     ).pack(side="left")
        self.status = ctk.CTkLabel(head, text="● CHƯA KẾT NỐI", font=(FB, 12), text_color=DIM)
        self.status.pack(side="right")

        col0 = ctk.CTkFrame(self, fg_color="transparent")
        col0.grid(row=1, column=0, sticky="nsew", padx=(16, 6))
        self._build_connection(col0)
        self._build_device_rw(col0)
        self._build_monitor().grid(row=1, column=1, sticky="nsew", padx=6)
        self._build_commands().grid(row=1, column=2, sticky="nsew", padx=(6, 16))
        self._build_log()
        self._set_connected(False)
        self._poll_failing = False
        self.after(40, self._drain)

    # ---------------- Kết nối ----------------
    def _build_connection(self, parent):
        c = Card(parent, "1. Kết nối (cổng lập trình RS422)")
        c.pack(fill="x")
        b = c.body

        def row(label):
            r = ctk.CTkFrame(b, fg_color="transparent")
            r.pack(fill="x", pady=3)
            ctk.CTkLabel(r, text=label, font=(F, 12), text_color=TEXT, width=90, anchor="w").pack(side="left")
            return r
        r = row("Cổng COM")
        self.port_menu = ctk.CTkOptionMenu(r, values=self._ports(), width=150, height=30, fg_color=INPUT,
                                           button_color=SOFT, button_hover_color=SOFT_HOVER, text_color=TEXT)
        self.port_menu.pack(side="left")
        soft_btn(r, "⟳", self._refresh_ports, width=30).pack(side="left", padx=4)
        r = row("Baud rate")
        self.baud_menu = ctk.CTkOptionMenu(r, values=["9600", "19200"], width=150, height=30, fg_color=INPUT,
                                           button_color=SOFT, button_hover_color=SOFT_HOVER, text_color=TEXT)
        self.baud_menu.pack(side="left")
        r = row("Khung dữ liệu")
        self.fmt_menu = ctk.CTkOptionMenu(r, values=["7E1", "8N1", "8E1"], width=150, height=30, fg_color=INPUT,
                                          button_color=SOFT, button_hover_color=SOFT_HOVER, text_color=TEXT)
        self.fmt_menu.pack(side="left")
        ctk.CTkLabel(b, text="FX0N mặc định: 9600 baud, 7E1 (7 bit dữ liệu, parity chẵn, 1 stop).", font=(F, 10),
                     text_color=DISABLED, anchor="w").pack(fill="x")
        self.connect_btn = soft_btn(b, "Connect", self._toggle_connect, fg_color=ACCENT, hover_color=ACCENT_HOVER)
        self.connect_btn.pack(fill="x", pady=(8, 6))

        ctk.CTkLabel(b, text="Kiểm tra nhanh", font=(FB, 11), text_color=DIM, anchor="w").pack(fill="x", pady=(4, 0))
        self.check_btns = []
        for text, fn in (("ENQ → PLC trả ACK?", self._check_enq),
                         ("Đọc M8000 (PLC đang RUN thì = 1)", self._check_m8000),
                         ("Đọc D8000 (watchdog, mặc định 200)", self._check_d8000)):
            btn = soft_btn(b, text, fn)
            btn.pack(fill="x", pady=2)
            self.check_btns.append(btn)

    @staticmethod
    def _ports():
        return [p.device for p in serial.tools.list_ports.comports()] or ["(không có cổng)"]

    def _refresh_ports(self):
        ports = self._ports()
        self.port_menu.configure(values=ports)
        self.port_menu.set(ports[0])
        self.log(f"Cổng COM hiện có: {ports}")

    def _toggle_connect(self):
        if self.worker:
            self.worker.stop_evt.set()
            self.worker = None
            self._set_connected(False)
            self.log("Đã ngắt kết nối.")
            return
        port = self.port_menu.get()
        if port.startswith("("):
            self.log("Không có cổng COM nào.", "ERROR")
            return
        try:
            link = FxLink(port, int(self.baud_menu.get()), self.fmt_menu.get(),
                          trace=lambda d, data: self.trace_q.put((d, data)))
        except FxError as e:
            self.log(str(e), "ERROR")
            return
        self.worker = Worker(link, self.results)
        self.worker.monitor = bool(self.monitor_var.get())
        self.worker.start()
        self._set_connected(True)
        self.log(f"Đã mở {port} @ {self.baud_menu.get()} {self.fmt_menu.get()} — thử ENQ...", "OK")
        self._check_enq()

    def _set_connected(self, on):
        self.connect_btn.configure(text="Disconnect" if on else "Connect", fg_color=SOFT if on else ACCENT,
                                   hover_color=SOFT_HOVER if on else ACCENT_HOVER, text_color=TEXT if on else "#ffffff")
        for w in (self.port_menu, self.baud_menu, self.fmt_menu):
            w.configure(state="disabled" if on else "normal")
        for w in self.check_btns + self.cmd_btns + self.rw_btns:
            w.configure(state="normal" if on else "disabled")
        self.status.configure(text="● ĐÃ MỞ CỔNG" if on else "● CHƯA KẾT NỐI", text_color=GREEN if on else DIM)
        if not on:
            for lamp in self.lamps.values():
                lamp.set(None)

    def _submit(self, fn, on_ok=None, label=""):
        if not self.worker:
            self.log("Chưa kết nối.", "WARN")
            return
        self.worker.submit(fn, on_ok, label)

    def _check_enq(self):
        self._submit(lambda L: L.enq(), lambda _: self.log("ENQ → ACK: PLC có trả lời, đường truyền OK.", "OK"), "ENQ")

    def _check_m8000(self):
        self._submit(lambda L: L.read_bit("M", 8000),
                     lambda v: self.log(f"M8000 = {v} → " + ("PLC đang RUN, bảng địa chỉ bit đúng." if v else
                                        "PLC đang STOP (hoặc sai bảng địa chỉ)."), "OK" if v else "WARN"), "M8000")

    def _check_d8000(self):
        self._submit(lambda L: L.read_d(8000),
                     lambda v: self.log(f"D8000 = {v}" + (" → đúng giá trị mặc định, bảng địa chỉ D đúng." if v == 200
                                        else " (mặc định là 200; khác thì có thể ladder đã đổi watchdog)."),
                                        "OK" if v == 200 else "WARN"), "D8000")

    # ---------------- Đọc / ghi thiết bị bất kỳ ----------------
    def _build_device_rw(self, parent):
        c = Card(parent, "2. Đọc / ghi thiết bị bất kỳ")
        c.pack(fill="x", pady=(12, 0))
        b = c.body
        r = ctk.CTkFrame(b, fg_color="transparent")
        r.pack(fill="x", pady=3)
        ctk.CTkLabel(r, text="Thiết bị", font=(F, 12), text_color=TEXT, width=70, anchor="w").pack(side="left")
        self.dev_entry = ctk.CTkEntry(r, width=90, height=30, fg_color=INPUT, border_color=BORDER, text_color=TEXT)
        self.dev_entry.insert(0, "M100")
        self.dev_entry.pack(side="left")
        ctk.CTkLabel(r, text="Giá trị (D)", font=(F, 12), text_color=TEXT).pack(side="left", padx=(10, 4))
        self.val_entry = ctk.CTkEntry(r, width=70, height=30, fg_color=INPUT, border_color=BORDER, text_color=TEXT)
        self.val_entry.insert(0, "0")
        self.val_entry.pack(side="left")
        r = ctk.CTkFrame(b, fg_color="transparent")
        r.pack(fill="x", pady=(6, 2))
        r.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="rw")
        self.rw_btns = []
        for k, (text, fn) in enumerate((("Đọc", self._rw_read), ("Ép ON", lambda: self._rw_force(True)),
                                        ("Ép OFF", lambda: self._rw_force(False)), ("Ghi D", self._rw_write_d))):
            btn = soft_btn(r, text, fn)
            btn.grid(row=0, column=k, sticky="ew", padx=2)
            self.rw_btns.append(btn)
        self.rw_result = ctk.CTkLabel(b, text="—", font=(FB, 13), text_color=TEXT, anchor="w")
        self.rw_result.pack(fill="x", pady=(6, 0))
        ctk.CTkLabel(b, text="X, Y đánh số bát phân (X10 là ngõ thứ 9). Ép ON/OFF dùng cho M, S, Y (Y do ladder điều "
                            "khiển sẽ bị ghi đè mỗi chu kỳ quét — ra lệnh qua M). Ghi D: số 16 bit.",
                     font=(F, 10), text_color=DISABLED, wraplength=380, justify="left", anchor="w").pack(fill="x")

    def _parse_dev(self):
        try:
            return parse_device(self.dev_entry.get())
        except FxError as e:
            self.log(str(e), "ERROR")
            return None

    def _rw_read(self):
        d = self._parse_dev()
        if not d:
            return
        dev, idx = d
        name = device_name(dev, idx)
        fn = (lambda L: L.read_d(idx)) if dev == "D" else (lambda L: L.read_bit(dev, idx))

        def ok(v):
            self.rw_result.configure(text=f"{name} = {v}")
            self.log(f"Đọc {name} = {v}", "OK")
        self._submit(fn, ok, name)

    def _rw_force(self, on):
        d = self._parse_dev()
        if not d:
            return
        dev, idx = d
        if dev in ("D", "X"):
            self.log("Ép ON/OFF chỉ dùng cho bit M, S, Y, T, C (X là ngõ vào thật, D là thanh ghi).", "WARN")
            return
        name = device_name(dev, idx)
        self._submit(lambda L: L.force(dev, idx, on),
                     lambda _: self.log(f"Ép {name} = {'ON' if on else 'OFF'} — PLC trả ACK.", "OK"), name)

    def _rw_write_d(self):
        d = self._parse_dev()
        if not d:
            return
        dev, idx = d
        if dev != "D":
            self.log("Ghi giá trị chỉ dùng cho thanh ghi D (vd D10).", "WARN")
            return
        try:
            value = int(self.val_entry.get())
        except ValueError:
            self.log("Giá trị phải là số nguyên.", "ERROR")
            return
        self._submit(lambda L: L.write_d(idx, value),
                     lambda _: self.log(f"Ghi D{idx} = {value} — PLC trả ACK.", "OK"), f"D{idx}")

    # ---------------- Giám sát X / Y / M ----------------
    def _build_monitor(self):
        c = Card(self, "3. Giám sát ngõ vào / ngõ ra")
        b = c.body
        top = ctk.CTkFrame(b, fg_color="transparent")
        top.pack(fill="x")
        self.monitor_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(top, text=f"Tự động đọc mỗi {POLL_S:g} s", variable=self.monitor_var, font=(F, 11),
                      text_color=DIM, command=self._toggle_monitor).pack(side="left")
        self.lamps = {}
        grid = ctk.CTkFrame(b, fg_color="transparent")
        grid.pack(fill="both", expand=True, pady=(6, 0))
        grid.grid_columnconfigure((0, 1), weight=1, uniform="io")
        for col, (dev, names) in enumerate((("X", INPUTS), ("Y", OUTPUTS))):
            box = ctk.CTkFrame(grid, fg_color=INPUT, corner_radius=10)
            box.grid(row=0, column=col, sticky="nsew", padx=(0, 4) if col == 0 else (4, 0))
            ctk.CTkLabel(box, text="Ngõ vào X" if dev == "X" else "Ngõ ra Y", font=(FB, 11), text_color=DIM
                         ).pack(anchor="w", padx=8, pady=(6, 2))
            for i in range(16):
                name = device_name(dev, i)
                lamp = Lamp(box, name, names.get(name, ""))
                lamp.pack(fill="x", padx=8)
                self.lamps[name] = lamp
            ctk.CTkFrame(box, fg_color="transparent", height=4).pack()
        return c

    def _toggle_monitor(self):
        if self.worker:
            self.worker.monitor = bool(self.monitor_var.get())

    def _apply_monitor(self, data):
        for dev in ("X", "Y"):
            for i, v in enumerate(data[dev]):
                self.lamps[device_name(dev, i)].set(v)
        m = {f"M{100 + i}": v for i, v in enumerate(data["M100"])}
        m.update({f"M{200 + i}": v for i, v in enumerate(data["M200"])})
        for name, lamp in self.lamps.items():
            if name in m:
                lamp.set(m[name], RED if name in ("M200", "M201") else GREEN)
        for name, (seg, kind) in self.cmd_state.items():
            if kind == "giu" and name in m:
                seg.set("ON" if m[name] else "OFF")

    # ---------------- Lệnh dây chuyền ----------------
    def _build_commands(self):
        c = Card(self, "4. Lệnh cho dây chuyền (PC ép bit M)")
        b = c.body
        self.cmd_btns, self.cmd_state = [], {}
        for name, desc, kind in PC_CMDS:
            r = ctk.CTkFrame(b, fg_color="transparent")
            r.pack(fill="x", pady=3)
            box = ctk.CTkFrame(r, fg_color="transparent")
            box.pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(box, text=desc, font=(FB, 12), text_color=TEXT, anchor="w", height=16).pack(fill="x")
            ctk.CTkLabel(box, text=f"{name} · {'giữ ON/OFF' if kind == 'giu' else 'xung'}", font=(F, 10),
                         text_color=DIM, anchor="w", height=14).pack(fill="x")
            if kind == "giu":
                seg = ctk.CTkSegmentedButton(r, values=["OFF", "ON"], width=110, height=30, font=(FB, 11),
                                             command=lambda v, n=name: self._cmd_hold(n, v == "ON"),
                                             selected_color="#dbeafe", selected_hover_color="#bfdbfe",
                                             unselected_color=SOFT, unselected_hover_color=SOFT_HOVER,
                                             fg_color=SOFT, text_color="#1e40af")
                seg.set("OFF")
                seg.pack(side="right")
                self.cmd_state[name] = (seg, kind)
                self.cmd_btns.append(seg)
            else:
                btn = soft_btn(r, "Gửi xung", lambda n=name: self._cmd_pulse(n), width=110)
                btn.pack(side="right")
                self.cmd_btns.append(btn)
        ctk.CTkLabel(b, text="Ladder phải đọc các bit M này (bit 'xung' bắt cạnh lên bằng PLS/LDP) rồi tự điều khiển Y, "
                            "kèm liên động: E-Stop chặn mọi lệnh, CB2 dừng băng tải + hạ xi lanh 1. Xem README.md.",
                     font=(F, 10), text_color=DISABLED, wraplength=380, justify="left", anchor="w").pack(fill="x", pady=(8, 0))
        box = ctk.CTkFrame(b, fg_color=INPUT, corner_radius=10)
        box.pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(box, text="Trạng thái PLC báo về (ladder ghi, PC chỉ đọc)", font=(FB, 11), text_color=DIM
                     ).pack(anchor="w", padx=8, pady=(6, 2))
        for name, desc in PLC_STATUS.items():
            lamp = Lamp(box, name, desc)
            lamp.pack(fill="x", padx=8)
            self.lamps[name] = lamp
        ctk.CTkFrame(box, fg_color="transparent", height=4).pack()
        return c

    def _cmd_hold(self, name, on):
        dev, idx = parse_device(name)
        self._submit(lambda L: L.force(dev, idx, on), lambda _: self.log(f"{name} = {'ON' if on else 'OFF'}", "OK"), name)

    def _cmd_pulse(self, name):
        dev, idx = parse_device(name)

        def pulse(L):
            L.force(dev, idx, True)
            time.sleep(PULSE_S)
            L.force(dev, idx, False)
        self._submit(pulse, lambda _: self.log(f"{name}: đã gửi xung ON {PULSE_S:g} s → OFF", "OK"), name)

    # ---------------- Log ----------------
    def _build_log(self):
        c = Card(self, "Log (TX = PC gửi, RX = PLC trả lời)")
        c.grid(row=2, column=0, columnspan=3, sticky="ew", padx=16, pady=12)
        top = c.body
        self.show_trace = ctk.BooleanVar(value=True)
        bar = ctk.CTkFrame(top, fg_color="transparent")
        bar.pack(fill="x")
        ctk.CTkSwitch(bar, text="Hiện khung TX/RX (không gồm vòng đọc giám sát)", variable=self.show_trace, font=(F, 11),
                      text_color=DIM).pack(side="left")
        soft_btn(bar, "Xóa", lambda: self.log_box.delete("1.0", "end"), width=60).pack(side="right")
        self.log_box = ctk.CTkTextbox(top, height=110, fg_color=INPUT, text_color=TEXT, font=("Consolas", 11))
        self.log_box.pack(fill="x", pady=(4, 0))
        for lvl, col in LOG_COLOR.items():
            self.log_box.tag_config(lvl, foreground=col)

    def log(self, msg, level="INFO"):
        self.log_box.insert("end", f"{datetime.now():%H:%M:%S}  ")
        self.log_box.insert("end", f"[{level:<5}] ", level)
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")

    # ---------------- Nhận kết quả từ Worker ----------------
    def _drain(self):
        while True:                                    # TX/RX trước rồi tới kết quả -> Log đúng thứ tự
            try:
                direction, data = self.trace_q.get_nowait()
            except queue.Empty:
                break
            if self.show_trace.get():
                self.log(show_bytes(data), direction)
        while True:
            try:
                kind, on_ok, value, label = self.results.get_nowait()
            except queue.Empty:
                break
            if label == "monitor":                     # lỗi giám sát chỉ báo 1 lần cho tới khi đọc lại được
                if kind == "ok":
                    if self._poll_failing:
                        self.log("Giám sát: đọc lại được PLC.", "OK")
                    self._poll_failing = False
                    self._apply_monitor(value)
                elif not self._poll_failing:
                    self._poll_failing = True
                    self.log(f"Giám sát: {value}", "ERROR")
            elif kind == "ok":
                if on_ok:
                    on_ok(value)
            else:
                self.log(f"{label}: {value}" if label else value, "ERROR")
        self.after(40, self._drain)


if __name__ == "__main__":
    PlcTestApp().mainloop()
