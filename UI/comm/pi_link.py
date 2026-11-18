"""
pi_link.py — Giao tiếp PC ↔ Raspberry Pi (TCP/IP), dùng trong app master.

Lõi giao thức (PiLink, NoResponse, LinkLost, các hằng số) lấy từ "Raspberry Pi/pi_tcp_test_ui.py" — bản đã thử với Pi
thật. Giao thức (PC là client, Pi là server, cổng mặc định 5000):
  Mỗi gói = [4 byte big-endian: độ dài JSON][JSON utf-8]
  Nếu JSON có "image_size": N thì N byte JPEG thô nối ngay sau JSON.
  PC -> Pi : {"id": 1, "cmd": "ping" | "capture" | "inspect"}
  Pi -> PC : gửi lại cùng "id"
    ping    -> {"id":1,"cmd":"ping","status":"ok"}
    capture -> {"id":2,"cmd":"capture","status":"ok","image_size":N}  + N byte JPEG
    inspect -> {"id":3,"cmd":"inspect","status":"ok","result":"PASS"|"FAIL1"|"FAIL2","process_time_ms":123.4, ...}
               (có thể kèm "image_size" + ảnh JPEG đã dùng để kết luận)
    lỗi     -> {"id":N,"status":"error","message":"..."}

PiClient bọc PiLink cho app giao diện: một luồng riêng giữ socket và chạy lệnh TUẦN TỰ (giao thức hỏi–đáp), kết quả
đưa về luồng giao diện qua hàng đợi — app gọi poll() đều đặn (vd mỗi 50 ms) để nhận callback. Khi rảnh, PiClient tự
gửi ping (không ghi Log) để phát hiện mất kết nối.
"""

import json
import queue
import socket
import struct
import threading
import time

# ============================================================
# Hằng số giao thức (giống pi_tcp_test_ui.py)
# ============================================================
DEFAULT_HOST, DEFAULT_PORT = "192.168.1.100", 5000
MAX_JSON = 1 << 20                                   # 1 MB
MAX_IMAGE = 20 << 20                                 # 20 MB
TIMEOUT = {"ping": 3, "capture": 10, "inspect": 20}  # giây, chờ phản hồi
RESULTS = ("PASS", "FAIL1", "FAIL2")
HEARTBEAT_S = 5.0                                    # rảnh quá lâu thì ping 1 lần để biết Pi còn sống


class NoResponse(Exception):
    """Hết thời gian chờ phản hồi (kết nối vẫn còn)."""


class LinkLost(Exception):
    """Mất kết nối hoặc gói tin sai khung."""


class PiLink:
    """Giữ nguyên từ pi_tcp_test_ui.py: hỏi–đáp tuần tự, chặn (blocking) — chỉ gọi từ luồng nền."""

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
        """Gửi lệnh, trả về (dict phản hồi, bytes ảnh hoặc None). log(level, message)."""
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
            log("RX", json.dumps(msg, ensure_ascii=False) + (f"  [+{size} byte ảnh]" if size else ""))
            if "id" in msg and msg["id"] != self.seq:
                log("WARN", f"Bỏ qua phản hồi cũ (id={msg['id']}, đang chờ id={self.seq})")
                continue
            return msg, img


# ============================================================
# PiClient: luồng nền + hàng đợi cho app giao diện
# ============================================================
class PiClient:
    """Mọi hàm public gọi từ luồng giao diện; callback cũng chạy ở luồng giao diện (trong poll()).
      connect(host, port, on_done)      on_done(ok: bool, message)
      disconnect()
      request(cmd, on_done)             on_done(reply: dict | None, image: bytes | None, rtt_ms, error: str | None)
      set_state_callback(cb)            cb(connected: bool, message) — đổi trạng thái kết nối (kể cả mất kết nối)
    """

    def __init__(self, log=None):
        self.link = PiLink()
        self.log = log or (lambda level, message: None)
        self.timeouts = dict(TIMEOUT)
        self.connected = False
        self.peer = None
        self.pending = 0                       # số lệnh đã gửi vào hàng đợi, chưa có kết quả
        self._on_state = None
        self._jobs = queue.Queue()
        self._events = queue.Queue()
        self._last_io = time.monotonic()
        threading.Thread(target=self._worker, daemon=True).start()

    # ---------- API cho giao diện ----------
    def set_state_callback(self, cb):
        self._on_state = cb

    def busy(self):
        return self.pending > 0

    def connect(self, host, port, on_done=None):
        self._submit("connect", (host, port), on_done)

    def disconnect(self):
        self._submit("close", None, None)

    def request(self, cmd, on_done=None):
        if not self.connected:
            if on_done:
                on_done(None, None, 0.0, "Chưa kết nối Raspberry Pi.")
            return
        self._submit("req", cmd, on_done)

    def poll(self):
        """Gọi đều đặn từ luồng giao diện: ghi Log và chạy callback cho các kết quả đã xong."""
        while True:
            try:
                ev = self._events.get_nowait()
            except queue.Empty:
                return
            if ev[0] == "log":
                self.log(ev[1], ev[2])
                continue
            kind, arg, cb, res, err = ev[1:]
            if kind != "beat":                 # ping tự động lúc rảnh không tính vào pending
                self.pending = max(0, self.pending - 1)
            self._handle_result(kind, arg, cb, res, err)

    # ---------- nội bộ ----------
    def _submit(self, kind, arg, cb):
        self.pending += 1
        self._jobs.put((kind, arg, cb))

    def _set_state(self, connected, message):
        changed = connected != self.connected
        self.connected = connected
        if changed and self._on_state:
            self._on_state(connected, message)

    def _handle_result(self, kind, arg, cb, res, err):
        if kind == "connect":
            if err is None:
                self.peer = arg
                self._set_state(True, f"Đã kết nối {arg[0]}:{arg[1]}.")
            if cb:
                cb(err is None, f"Đã kết nối {arg[0]}:{arg[1]}." if err is None else
                   f"Không kết nối được {arg[0]}:{arg[1]} — {err}")
            return
        if kind == "close":
            self._set_state(False, "Đã ngắt kết nối Raspberry Pi.")
            return
        message = None
        if isinstance(err, LinkLost):
            message = f"Mất kết nối Raspberry Pi: {err}"
            self._set_state(False, message)
        elif isinstance(err, NoResponse):
            message = f"Raspberry Pi không phản hồi lệnh {arg} (quá {self.timeouts.get(arg, 10):g} s)."
            if kind == "beat":                 # ping lúc rảnh không trả lời: coi như Pi treo -> ngắt
                self._set_state(False, message)
        elif err is not None:
            message = f"{type(err).__name__}: {err}"
        if cb:
            reply, img, rtt = res if res else (None, None, 0.0)
            cb(reply, img, rtt, message)
        elif message and kind != "beat":
            self.log("ERROR", message)

    def _worker(self):
        while True:
            try:
                kind, arg, cb = self._jobs.get(timeout=1.0)
            except queue.Empty:
                if self.link.sock is None or time.monotonic() - self._last_io < HEARTBEAT_S:
                    continue
                kind, arg, cb = "beat", "ping", None
            res, err = None, None
            try:
                if kind == "connect":
                    self.link.close()
                    self.link.connect(*arg)
                elif kind == "close":
                    self.link.close()
                elif self.link.sock is None:
                    raise LinkLost("chưa kết nối")
                else:
                    quiet = kind == "beat"
                    t0 = time.monotonic()
                    reply, img = self.link.request(arg, self.timeouts.get(arg, 10),
                                                   (lambda lv, m: None) if quiet else self._tlog)
                    res = (reply, img, (time.monotonic() - t0) * 1000)
            except Exception as e:  # noqa: BLE001 - mọi lỗi đều báo về giao diện
                err = e
                if kind == "connect" or isinstance(e, LinkLost) or (kind == "beat" and isinstance(e, NoResponse)):
                    self.link.close()
            self._last_io = time.monotonic()
            self._events.put(("done", kind, arg, cb, res, err))

    def _tlog(self, level, message):
        self._events.put(("log", level, message))
