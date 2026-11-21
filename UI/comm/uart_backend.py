"""
uart_backend.py — UartRobotBackend: nói chuyện THẬT với firmware STM32 qua UART (giao thức: PROTOCOL.md).
------------------------------------------------------------------------
Implement đầy đủ RobotBackendBase — GUI/ProgramExecutor dùng qua đúng các hàm public của interface.

Thiết kế chính:
  - Thread đọc (_rx_loop) chỉ tách dòng đẩy vào queue; MỌI xử lý (parse, sửa state, gọi callback) nằm
    trong update(dt) chạy ở main thread -> an toàn với Tkinter.
  - Mỗi lệnh STM32 trả "OK <lệnh> <số>" hoặc "ERR <lệnh> <số> <lý do>", theo ĐÚNG thứ tự gửi. Không có
    phản hồi sau 0.5 s => coi như mất liên lạc. Không nhận dòng trạng thái S quá 1 s => mất liên lạc.
  - Dòng S (20 Hz) mang trạng thái cả 4 động cơ. BUSY->READY chỉ được chấp nhận khi (a) mọi lệnh chuyển
    động đã có OK VÀ (b) đã nhận thêm ít nhất 1 dòng S SAU OK cuối cùng. Vì OK luôn xếp sau các dòng S đã
    chụp trước khi lệnh được xử lý, một dòng S "cũ" (busy=0) không bao giờ bị hiểu nhầm là Step đã xong.
  - Đơn vị: GUI dùng độ/mm; trên dây là counts so với vị trí lúc cấp nguồn (= Home: J=0°, Z=300 mm).
"""

import copy
import queue
import threading
from collections import deque

import serial
import serial.tools.list_ports

from comm.backend_base import RobotBackendBase, RobotStatus
from comm.errors import LimitError, UartError
from comm.uart_protocol import (AXES, AXIS_OF_MOTOR, MOTOR_OF_AXIS, ST_BUSY, ST_EN, ST_ESTOP, ST_FAULT, ST_HOMED,
                           ST_HOMING, ST_HSENSOR, ST_PAUSED, ProtocolError, build_cmd, fmt_float, parse_line)
from core import robot_config
from core.robot_config import HOME_POSITION

# Mặc định trước khi Apply từ Settings — khớp robot thật (J1-J3: 0..120°, Z: 150..300 mm).
DEFAULT_JOINT_LIMITS = {
    "J1": (0.0, 120.0), "J2": (0.0, 120.0),
    "J3": (0.0, 120.0), "Z": (150.0, 300.0),
}
DEFAULT_MAX_VELOCITY = {"J1": 30.0, "J2": 30.0, "J3": 30.0, "Z": 5.0}

ACK_TIMEOUT_S = 0.5          # chờ OK/ERR cho mỗi lệnh
STATUS_TIMEOUT_S = 1.0       # im lặng (không có dòng S) quá lâu sau khi đã nhận S đầu tiên
FIRST_STATUS_TIMEOUT_S = 2.0 # chưa nhận được S nào kể từ lúc kết nối
HEARTBEAT_PERIOD_S = 0.2     # PC gửi PING mỗi 0.2 s (luồng riêng, không phụ thuộc giao diện có đang bận hay không)
WATCHDOG_MS = 600            # STM32 không nhận được gì quá 0.6 s (= 3 PING liên tiếp bị mất) -> tự dừng an toàn
LIMIT_EPS = 0.01             # độ / mm: đích vượt giới hạn khớp dưới mức này coi như sai số làm tròn -> kẹp đúng về biên
TRACE_SECONDS = 60           # giữ 60 s telemetry gần nhất (50 Hz) cho đồ thị / xuất CSV
# lệnh làm đổi trạng thái chạy/dừng (GRIP cũng tính: Step GRIP chỉ xong khi STM32 đã OK + có dòng S mới)
MOTION_CMDS = ("GOTO", "JOG", "HOME", "HOMING", "STOP", "PAUSE", "RESUME", "GRIP")

ERR_TEXT = {
    "arg": "tham số không hợp lệ",
    "range": "ngoài giới hạn hành trình (LIMIT)",
    "fault": "động cơ đang có FAULT — bấm RESET để xóa lỗi",
    "unknown": "firmware không biết lệnh này (firmware cũ?)",
    "id": "số động cơ không hợp lệ",
    "homing": "động cơ đang HOMING — đợi xong hoặc bấm STOP để hủy",
    "nosensor": "động cơ này chưa được gắn cảm biến home trong firmware (HomeSen_Init ở main.c)",
    "nogrip": "firmware chưa gắn kẹp (Gripper_Init ở main.c)",
    "estop": "STM32 đang E-STOP — bấm RESET (gửi ESTOP 0) rồi HOME lại",
}
FAULT_TEXT = {
    "trip": "sai số bám vượt ngưỡng Trip (kẹt cơ khí / sai chiều encoder / mất encoder / Vmax-Amax quá cao) — đã phanh và tắt PID",
    "home": "HOMING thất bại (quá thời gian chưa thấy cảm biến, hoặc sai số bám vượt ngưỡng Home Trip vì bị chặn/kẹt) — đã phanh và tắt PID",
    "stall": "motor bị KẸT / QUÁ TẢI: PWM cao kéo dài mà trục gần như không di chuyển (chạm đầu hành trình, kẹt cơ khí, "
             "hoặc PID đang 'săn' qua lại — giảm Kp / tăng Deadband) — đã phanh và tắt PID",
}


def list_available_ports():
    """Tên các cổng COM hiện có, vd ['COM3'] (Windows) hoặc ['/dev/ttyUSB0'] (Linux)."""
    return [p.device for p in serial.tools.list_ports.comports()]


class UartRobotBackend(RobotBackendBase):

    def __init__(self, port, baudrate=115200, timeout=0.05, serial_factory=None):
        self.port_name = port
        self.baudrate = baudrate
        self._serial_timeout = timeout
        self._serial_factory = serial_factory or serial.Serial
        self._ser = None
        self._write_lock = threading.Lock()

        self._enc = robot_config.get_default_config()["encoder"]      # cập nhật bởi configure()
        self._origin = dict(HOME_POSITION)    # độ/mm ứng với 0 counts; = Settings Home khi Connect (configure lần đầu)
        self.actual = dict(HOME_POSITION)
        self.target = dict(HOME_POSITION)
        self.status = RobotStatus.READY
        self.joint_limits = dict(DEFAULT_JOINT_LIMITS)
        self.max_velocity = dict(DEFAULT_MAX_VELOCITY)

        # Đồng bộ khớp: Vmax/Amax ĐẦY ĐỦ từng trục (độ, mm) theo Settings, và giá trị VMAX/AMAX (counts) đã gửi gần nhất.
        mp = robot_config.get_default_config()["motion_profile"]
        self._profile = {a: (float(mp[a]["vmax"]), float(mp[a]["amax"])) for a in AXES}     # cập nhật bởi configure()
        self._sent_profile = {}           # axis -> (vmax_counts, amax_counts) STM32 đang dùng

        # Kẹp PD9 không có cảm biến: commanded = trạng thái chân output firmware báo về (OK GRIP / dòng S), actual luôn None.
        self.gripper_commanded = "OFF"
        self.gripper_actual = None

        self._pending_home = False        # đang HOMING (đã gửi HOMING, chưa xong)
        self._home_failed = False         # có trục báo lỗi trong lần HOMING hiện tại
        self._no_sensor = set()           # trục firmware báo chưa có cảm biến home (bỏ qua khi HOME, không phải lỗi)
        self._is_homed = False            # cả 4 trục báo bit homed trong dòng S
        self._motion_paused = False

        self._on_status_change = None
        self._on_home_done = None
        self._on_gripper_change = None
        self._on_connection_lost = None
        self._on_command_error = None     # callback(message) — ERR / FAULT từ STM32
        self._on_info = None              # callback(message) — thông tin thường (không phải lỗi)

        # Giao thức
        self._pending = deque()           # các lệnh đã gửi, chưa có OK/ERR (đúng thứ tự gửi)
        self._need_fresh_status = False   # vừa có OK cho lệnh chuyển động -> chờ 1 dòng S mới
        self._resync_pending = True       # lần READY kế tiếp: target := actual
        self._any_fault = False
        self._any_busy = False
        self._any_estop = False           # STM32 báo bit E-STOP trong dòng S
        self._estop_seen = False          # đã báo lỗi cho lần E-STOP hiện tại (chỉ báo 1 lần ở cạnh lên)
        self._telemetry = {a: {"flags": 0, "goal": 0, "sp": 0, "pos": 0} for a in AXES}
        self._since_status = 0.0
        self._have_status = False
        self._configured = False
        self._config_cb = None
        self._config_left = 0
        self._config_err = None

        self._rx_queue = queue.Queue()
        self._rx_buf = b""
        self._rx_thread = None
        self._rx_stop = threading.Event()
        self._hb_thread = None            # luồng gửi PING (bắt đầu sau khi STM32 nhận cấu hình, gồm WDT)
        self.bad_lines = 0                # số dòng hỏng/không nhận ra (chẩn đoán nhiễu)

        # Telemetry T (đồ thị): trục đang theo dõi (None = tắt) và các mẫu gần nhất (đơn vị độ/mm)
        self._trace_axis = None
        self._trace = deque(maxlen=TRACE_SECONDS * 50)

    # ==================== Kết nối cổng COM ====================
    def connect(self):
        if self.is_connected():
            return
        try:
            self._ser = self._serial_factory(self.port_name, self.baudrate, timeout=self._serial_timeout)
        except serial.SerialException as e:
            self._ser = None
            raise UartError(f"Không mở được cổng {self.port_name}: {e}")
        self._since_status = 0.0
        self._have_status = False
        self._rx_stop.clear()
        self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self._rx_thread.start()

    def disconnect(self):
        """Phanh cả 4 động cơ (best-effort) rồi đóng cổng. An toàn gọi nhiều lần."""
        if self.is_connected():
            for motor in AXIS_OF_MOTOR:
                try:
                    self._write(build_cmd("STOP", motor))
                except Exception:
                    break
        self._rx_stop.set()
        if self._rx_thread is not None:
            self._rx_thread.join(timeout=1.0)
            self._rx_thread = None
        if self._hb_thread is not None:
            self._hb_thread.join(timeout=1.0)
            self._hb_thread = None
        self._trace_axis = None
        if self._ser is not None:
            try:
                self._ser.close()
            except serial.SerialException:
                pass
            self._ser = None
        self._configured = False
        self._pending.clear()

    def is_connected(self):
        return self._ser is not None and self._ser.is_open

    def set_connection_lost_callback(self, callback):
        """callback(reason: str) — gọi từ update() khi mất kết nối ngoài ý muốn."""
        self._on_connection_lost = callback

    def set_command_error_callback(self, callback):
        """callback(message: str) — STM32 từ chối một lệnh (ERR) hoặc báo FAULT."""
        self._on_command_error = callback

    def set_info_callback(self, callback):
        """callback(message: str) — thông tin thường (vd: trục chưa có cảm biến home nên được bỏ qua)."""
        self._on_info = callback

    def _rx_loop(self):
        while not self._rx_stop.is_set():
            try:
                chunk = self._ser.read(256)
            except (serial.SerialException, OSError, AttributeError) as e:
                self._rx_queue.put(("DISCONNECTED", str(e)))
                return
            if chunk:
                self._feed(chunk)

    def _feed(self, chunk: bytes):
        """Tách dòng theo '\\n' rồi đẩy vào queue (gọi từ thread đọc; test gọi trực tiếp)."""
        self._rx_buf += chunk
        while b"\n" in self._rx_buf:
            line, self._rx_buf = self._rx_buf.split(b"\n", 1)
            text = line.decode("ascii", errors="replace").strip()
            if text:
                self._rx_queue.put(("LINE", text))

    # ==================== Gửi lệnh ====================
    def _write(self, data: bytes):
        try:
            with self._write_lock:
                self._ser.write(data)
        except (serial.SerialException, OSError, AttributeError) as e:
            raise UartError(f"Lỗi ghi cổng {self.port_name}: {e}")

    def _send(self, cmd, motor, *args, tag="misc"):
        """Gửi 1 lệnh cho 1 động cơ và ghi nhớ để khớp với OK/ERR. Raise UartError nếu chưa kết nối."""
        if not self.is_connected():
            raise UartError("Chưa kết nối UART — không gửi được lệnh.")
        self._write(build_cmd(cmd, motor, *args))
        self._pending.append({"cmd": cmd, "motor": motor, "age": 0.0, "tag": tag})

    def _send_motion(self, cmd, motor, *args):
        self._send(cmd, motor, *args, tag="motion")
        self._set_status(RobotStatus.BUSY)   # lạc quan: executor cần is_moving()=True ngay sau khi gửi

    def _motion_pending(self):
        return any(e["cmd"] in MOTION_CMDS for e in self._pending)

    # ==================== Cấu hình Settings -> STM32 ====================
    def configure(self, cfg, on_result=None):
        """Gửi cấu hình xuống STM32, mỗi động cơ: PID, VMAX, AMAX, DB, LIMIT, HPOS, TRIP, STALL (đơn vị counts).
        HPOS = vị trí home (độ/mm trong cfg['home_position']) đổi ra counts bằng ĐÚNG hệ số encoder dùng cho GOTO,
        nên sau HOMING vị trí hiển thị trên GUI khớp giá trị đã đặt.
        on_result(ok: bool, message: str) được gọi từ update() khi đã có phản hồi cho TẤT CẢ lệnh."""
        self._enc = copy.deepcopy(cfg["encoder"])
        if not self._configured:
            # Lần cấu hình đầu sau Connect: gốc đổi đơn vị = Home trong Settings -> vị trí lúc cấp nguồn (encoder = 0)
            # nằm trong giới hạn khớp. Apply sau đó KHÔNG đổi gốc (đang chạy mà đổi gốc thì vị trí hiển thị bị nhảy).
            self._origin = {a: float(cfg["home_position"][a]) for a in AXES}
            self._resync_pending = True
        self._config_cb = on_result
        self._config_err = None
        self._config_left = 0
        for axis in AXES:
            m = MOTOR_OF_AXIS[axis]
            enc, lim = self._enc[axis], cfg["joint_limits"][axis]
            mp, pid = cfg["motion_profile"][axis], cfg["pid"][axis]
            cpu = robot_config.counts_per_unit(axis, enc)
            lo = self._u2c(axis, lim["min"])
            hi = self._u2c(axis, lim["max"])
            lo, hi = min(lo, hi), max(lo, hi)
            home = self._u2c(axis, cfg["home_position"][axis])
            fl = cfg["fault_limits"][axis]
            trip, home_trip = int(round(fl["trip"] * cpu)), int(round(fl["home_trip"] * cpu))
            if trip <= 0 or home_trip <= 0:
                raise ValueError(f"{axis}: ngưỡng Trip/Home Trip quá nhỏ (đổi ra counts ≤ 0).")
            stall = (int(fl["stall_pct"]), int(fl["stall_ms"]), max(1, int(round(float(fl["stall_dist"]) * cpu))))
            vmax, amax = int(round(mp["vmax"] * cpu)), int(round(mp["amax"] * cpu))
            if vmax <= 0 or amax <= 0:
                raise ValueError(f"{axis}: Vmax/Amax quá nhỏ (đổi ra counts ≤ 0).")
            cmds = [("PID", (fmt_float(pid["kp"]), fmt_float(pid["ki"]), fmt_float(pid["kd"]))),
                    ("VMAX", (vmax,)), ("AMAX", (amax,)),
                    ("DB", (int(round(float(pid["deadband"]))),)),
                    ("LIMIT", (lo, hi)),
                    ("HPOS", (home,)),
                    ("TRIP", (trip, home_trip)),
                    ("STALL", stall)]
            for cmd, args in cmds:
                self._send(cmd, m, *args, tag="cfg")
                self._config_left += 1
            self._profile[axis] = (float(mp["vmax"]), float(mp["amax"]))
            self._sent_profile[axis] = (vmax, amax)
        # Tắt telemetry T (STM32 có thể còn giữ SEL từ lần kết nối trước) và bật watchdog mất kết nối
        for cmd, arg in (("SEL", 0), ("WDT", WATCHDOG_MS)):
            self._send(cmd, arg, tag="cfg")
            self._config_left += 1

    # ==================== Watchdog mất kết nối ====================
    def _heartbeat_loop(self):
        """Gửi PING mỗi HEARTBEAT_PERIOD_S. Chạy ở luồng riêng: cửa sổ đang bị kéo/đơ một lúc vẫn không làm robot dừng
        oan. Nếu dây USB tuột hoặc chương trình PC chết, PING ngừng và STM32 tự dừng sau WATCHDOG_MS."""
        while not self._rx_stop.wait(HEARTBEAT_PERIOD_S):
            try:
                self._write(b"PING\n")
            except UartError:
                return

    def _start_heartbeat(self):
        if self._hb_thread is None and self.is_connected():
            self._hb_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
            self._hb_thread.start()

    def _on_link_lost(self):
        """STM32 báo LINKLOST: quá WATCHDOG_MS không nhận được gì từ PC nên đã cho các trục đang chạy giảm tốc dừng
        và giữ vị trí. Báo lỗi (dừng chương trình nếu đang chạy) — KHÔNG được coi là 'Step đã xong'."""
        self._resync_pending = True
        self._need_fresh_status = True
        self._report(f"STM32 tự dừng vì quá {WATCHDOG_MS / 1000:g} s không nhận được tín hiệu từ PC (máy tính bị treo "
                     "hoặc đường truyền gián đoạn). Các trục đã giảm tốc dừng và giữ vị trí, mốc vị trí vẫn đúng.")
        if self._pending_home:
            self._abort_homing()

    # ==================== Telemetry T (đồ thị PID) ====================
    def set_trace_axis(self, axis):
        """Chọn trục gửi telemetry T 50 Hz (axis = 'J1'..'Z'), hoặc None để tắt (SEL 0). Xóa dữ liệu cũ."""
        motor = MOTOR_OF_AXIS[axis] if axis else 0
        self._send("SEL", motor)
        self._trace_axis = axis
        self._trace.clear()

    def get_trace(self):
        """(trục, [(t_s, goal, setpoint, actual, v_đặt, v_thực), ...]) — đơn vị độ, độ/s (J) hoặc mm, mm/s (Z)."""
        return self._trace_axis, list(self._trace)

    def _on_telemetry(self, d):
        axis = self._trace_axis
        if axis is None or d["motor"] != MOTOR_OF_AXIS[axis]:
            return
        enc = self._enc[axis]
        k = robot_config.axis_sign(enc) / robot_config.counts_per_unit(axis, enc)
        self._trace.append((d["ms"] / 1000.0,
                            self._c2u(axis, d["goal"]),
                            self._c2u(axis, d["sp"]),
                            self._c2u(axis, d["pos"]),
                            d["sv"] * k, d["v"] * k))

    # ==================== E-STOP / RESET (báo cho STM32 biết) ====================
    def emergency_stop(self):
        """E-STOP: PC báo cho STM32 (khi PLC báo E-Stop). STM32 phanh cả 4 động cơ, tắt PID, BỎ mốc vị trí (homed = 0) và
        KHÓA mọi lệnh chuyển động (kể cả kẹp) cho tới reset_estop(). Không chờ trạng thái READY: trạng thái chuyển sang ERROR
        khi dòng S kế tiếp mang bit E-STOP."""
        self._send("ESTOP", 1, tag="estop")
        self._motion_paused = False
        self._is_homed = False
        self.target = dict(self.actual)
        self._resync_pending = True
        if self._pending_home:
            self._finish_home(success=False)

    def reset_estop(self):
        """RESET sau E-Stop (ESTOP 0): STM32 mở khóa và xóa mọi FAULT. Robot CHƯA có mốc vị trí → phải home() lại."""
        self._send("ESTOP", 0, tag="estop")
        self._is_homed = False
        self._resync_pending = True

    def is_estop(self):
        return self._any_estop

    def clear_fault(self):
        """Xóa FAULT đã chốt trên cả 4 động cơ (CLEAR). Motor không tự chạy lại; mốc vị trí vẫn là encoder."""
        for motor in AXIS_OF_MOTOR:
            self._send("CLEAR", motor)
        self._resync_pending = True
        self._is_homed = False

    # ==================== Tạm dừng/tiếp tục/hủy ====================
    def pause_motion(self):
        """PAUSE: mỗi động cơ giảm tốc (theo Amax) về điểm dừng rồi giữ vị trí; đích cũ được giữ để RESUME."""
        for motor in AXIS_OF_MOTOR:
            self._send_motion("PAUSE", motor)
        self._motion_paused = True

    def resume_motion(self):
        for motor in AXIS_OF_MOTOR:
            self._send_motion("RESUME", motor)
        self._motion_paused = False

    def is_motion_paused(self):
        return self._motion_paused

    def abort_motion(self):
        """STOP: phanh gấp cả 4 động cơ, tắt PID tại vị trí hiện tại. Status chỉ về READY khi STM32 xác nhận."""
        for motor in AXIS_OF_MOTOR:
            self._send_motion("STOP", motor)
        self._motion_paused = False
        self.target = dict(self.actual)
        self._resync_pending = True
        if self._pending_home:
            self._finish_home(success=False)     # bị STOP giữa chừng -> HOME_ERROR

    # ==================== Di chuyển khớp ====================
    def _u2c(self, axis, value):
        return robot_config.units_to_counts(axis, value, self._enc[axis], self._origin[axis])

    def _c2u(self, axis, counts):
        return robot_config.counts_to_units(axis, counts, self._enc[axis], self._origin[axis])

    def _check_joint(self, axis, value, jog=False):
        """Kiểm tra đích 1 trục theo giới hạn khớp, trả về đích (độ/mm) được phép gửi; vi phạm -> LimitError.
        - Đích trong giới hạn (dung sai làm tròn LIMIT_EPS): nhận, kẹp đúng về biên.
        - JOG khi trục đang TRONG giới hạn mà bước vượt biên: chỉ chạy tới đúng biên (quãng đi < 1 bước).
        - JOG khi trục đang NGOÀI giới hạn: chỉ cho đi VÀO phía trong (cùng phía, gần giới hạn hơn), đúng 1 bước.
        - Còn lại (MOVE / chương trình tới điểm ngoài giới hạn, JOG ra xa hơn): chặn hẳn, KHÔNG kẹp về biên."""
        lo, hi = self.joint_limits[axis]
        if lo - LIMIT_EPS <= value <= hi + LIMIT_EPS:
            return max(lo, min(hi, value))
        cur = self.target[axis]
        unit = "mm" if axis == "Z" else "°"
        if jog:
            if lo - LIMIT_EPS <= cur <= hi + LIMIT_EPS:
                return lo if value < lo else hi
            if (cur > hi and hi < value < cur) or (cur < lo and cur < value < lo):
                return value
            raise LimitError(f"{axis} đang ở {cur:.2f} {unit}, NGOÀI giới hạn [{lo:g}, {hi:g}] — chỉ JOG được về "
                             f"phía trong giới hạn (hoặc HOME / kiểm tra Settings → Joint Limits + Home).")
        raise LimitError(f"{axis} = {value:.2f} {unit} nằm ngoài giới hạn [{lo:g}, {hi:g}] — lệnh bị chặn, robot "
                         f"không chạy (kiểm tra Point / Settings → Joint Limits).")

    def send_absolute_target(self, targets: dict, jog=False):
        """GOTO tuyệt đối cho từng trục có trong `targets`, sau khi kiểm tra giới hạn khớp (_check_joint: đích ngoài
        giới hạn bị CHẶN, không kẹp về biên). Các trục được ĐỒNG BỘ: cùng xuất phát và cùng tới đích (xem _sync_profiles),
        nên đầu công tác đi gần đường thẳng khi bước ngắn."""
        checked = {axis: self._check_joint(axis, float(value), jog)
                   for axis, value in targets.items() if axis in MOTOR_OF_AXIS}   # kiểm tra HẾT trước khi gửi trục nào
        goals = {}
        for axis, value in checked.items():
            goals[axis] = (value, self._u2c(axis, value))
        self._sync_profiles({axis: abs(counts - self._u2c(axis, self.target[axis]))
                             for axis, (_, counts) in goals.items()})
        for axis, (value, counts) in goals.items():
            self._send_motion("GOTO", MOTOR_OF_AXIS[axis], counts)
            self.target[axis] = value

    # ==================== Đồng bộ khớp ====================
    def _full_profile_counts(self, axis):
        """(VMAX, AMAX) đầy đủ của trục theo Settings, đổi ra counts/s, counts/s²."""
        vmax, amax = self._profile[axis]
        cpu = robot_config.counts_per_unit(axis, self._enc[axis])
        return max(1, int(round(vmax * cpu))), max(1, int(round(amax * cpu)))

    def _send_profile(self, axis, vmax, amax):
        """Gửi VMAX/AMAX (counts) cho 1 trục — chỉ gửi giá trị nào khác với giá trị STM32 đang dùng."""
        last = self._sent_profile.get(axis, (None, None))
        motor = MOTOR_OF_AXIS[axis]
        if last[0] != vmax:
            self._send("VMAX", motor, vmax)
        if last[1] != amax:
            self._send("AMAX", motor, amax)
        self._sent_profile[axis] = (vmax, amax)

    def _restore_full_profiles(self):
        """Trả mọi trục về Vmax/Amax đầy đủ (vd trước HOMING: tốc độ tìm = speed_pct % của VMAX đang dùng)."""
        for axis in AXES:
            self._send_profile(axis, *self._full_profile_counts(axis))

    def _sync_profiles(self, distances):
        """Đồng bộ khớp: distances = {axis: quãng đường (counts)}. Tìm một quỹ đạo hình thang CHUNG theo tỉ lệ quãng
        đường (V = phần quãng đường / s, A = phần quãng đường / s²) nhanh nhất mà không trục nào vượt Vmax/Amax của nó:
            V = min_i (Vmax_i / d_i),   A = min_i (Amax_i / d_i)
        rồi đặt cho trục i:  VMAX_i = d_i·V,  AMAX_i = d_i·A.
        Mọi trục có cùng hình dạng quỹ đạo (chỉ khác tỉ lệ) -> cùng xuất phát, cùng tới đích, đi thẳng trong không gian
        khớp. Tổng thời gian bằng thời gian của trục chậm nhất (không chậm hơn khi chạy độc lập)."""
        moving = {a: d for a, d in distances.items() if d > 0}
        if not moving:
            return
        full = {a: self._full_profile_counts(a) for a in moving}
        v = min(full[a][0] / d for a, d in moving.items())
        acc = min(full[a][1] / d for a, d in moving.items())
        for a, d in moving.items():
            self._send_profile(a, max(1, min(full[a][0], int(round(d * v)))),
                               max(1, min(full[a][1], int(round(d * acc)))))

    def jog(self, axis, direction, step):
        if axis not in MOTOR_OF_AXIS:
            return
        self.send_absolute_target({axis: self.target[axis] + direction * step}, jog=True)

    # ==================== HOME ====================
    def home(self):
        """HOME = tìm cảm biến home (lệnh HOMING) trên cả 4 động cơ cùng lúc. Mỗi trục chạy chậm về phía cảm biến của nó,
        chạm thì dừng ngay và firmware đặt vị trí = vị trí home đã cấu hình (main.c). HOME_DONE khi cả 4 trục báo `homed`;
        HOME_ERROR nếu có trục bị từ chối / FAULT home / bị STOP giữa chừng."""
        self._home_failed = False
        self._no_sensor = set()
        self._pending_home = True
        self._is_homed = False
        try:
            self._restore_full_profiles()          # tốc độ tìm home tính theo VMAX đầy đủ, không theo VMAX đã thu nhỏ khi đồng bộ
            for motor in AXIS_OF_MOTOR:
                self._send_motion("HOMING", motor)
        except UartError:
            self._pending_home = False
            raise
        self.target = dict(self.actual)

    def go_home_position(self):
        """(Cách HOME cũ, không dùng cảm biến) đi tới vị trí 0 counts = gốc đổi đơn vị (vị trí lúc cấp nguồn) bằng
        lệnh HOME (GOTO 0)."""
        self._restore_full_profiles()
        for motor in AXIS_OF_MOTOR:
            self._send_motion("HOME", motor)
        self.target = dict(self._origin)

    def is_homed(self):
        return self._is_homed

    def is_homing(self):
        return self._pending_home

    def _abort_homing(self):
        """Một trục HOMING thất bại (ERR/FAULT): dừng cả 4 động cơ để các trục còn lại không chạy tiếp, rồi báo HOME_ERROR.
        Chỉ làm một lần cho mỗi lần HOME (nhiều ERR/FAULT dồn tới cũng không gửi STOP lặp lại)."""
        if not self._pending_home:
            return
        self._home_failed = True
        try:
            self.abort_motion()             # STOP cả 4; abort_motion tự gọi _finish_home(False) vì còn _pending_home
        except UartError:
            pass
        if self._pending_home:              # abort_motion lỗi giữa chừng
            self._finish_home(success=False)

    def _on_nosensor(self, axis):
        """Firmware báo trục này chưa có cảm biến home: BỎ QUA (không phải lỗi), các trục còn lại vẫn HOME bình thường.
        Trục bị bỏ qua giữ mốc vị trí lúc cấp nguồn và không tính vào điều kiện 'đã HOME'."""
        self._no_sensor.add(axis)
        if len(self._no_sensor) >= len(AXES):
            self._report("Không có trục nào được gắn cảm biến home trong firmware (HomeSen_Init ở main.c) — không thể HOME.")
            self._abort_homing()
            return
        if self._on_info:
            self._on_info(f"{axis}: chưa có cảm biến home — bỏ qua. {axis} giữ mốc vị trí lúc cấp nguồn "
                          f"(hãy đặt {axis} về vị trí home bằng tay trước khi cấp nguồn).")

    def _finish_home(self, success):
        self._pending_home = False
        self._resync_pending = True         # vị trí actual vừa được đặt lại theo cảm biến -> target theo actual
        if self._on_home_done:
            self._on_home_done(success)

    # ==================== GRIP (kẹp PD9) ====================
    def grip(self, action):
        """GRIP ON = đóng kẹp, OFF = mở kẹp (lệnh 'GRIP 1' / 'GRIP 0'). Robot BUSY cho tới khi STM32 trả OK và có
        thêm 1 dòng S, nên Step GRIP xong ngay sau khi kẹp đã được ra lệnh (không chờ thời gian đóng/mở cơ khí)."""
        if action not in ("ON", "OFF"):
            raise ValueError("grip() chỉ nhận 'ON' hoặc 'OFF'.")
        self._send_motion("GRIP", 1 if action == "ON" else 0)

    def _set_gripper(self, commanded):
        if commanded == self.gripper_commanded:
            return
        self.gripper_commanded = commanded
        if self._on_gripper_change:
            self._on_gripper_change(self.gripper_commanded, self.gripper_actual)

    def get_gripper_state(self):
        return {"commanded": self.gripper_commanded, "actual": self.gripper_actual}

    # ==================== Cấu hình runtime ====================
    def set_joint_limits(self, limits: dict):
        """Lưu giới hạn phía PC (kiểm tra đích khi JOG/MOVE). Giới hạn trên STM32 được gửi bằng configure().
        KHÔNG kẹp target hiện tại vào giới hạn mới: trục đang ở ngoài giới hạn mà kẹp target về biên thì lần JOG kế tiếp
        sẽ tính từ biên -> trục nhảy một đoạn dài (lỗi trục Z chạy 58 mm)."""
        for axis, (lo, hi) in limits.items():
            if axis not in self.actual:
                continue
            self.joint_limits[axis] = (float(lo), float(hi))

    def set_max_velocity(self, velocities: dict):
        for axis, value in velocities.items():
            if axis in self.actual:
                self.max_velocity[axis] = float(value)

    # ==================== Vòng lặp xử lý (main thread) ====================
    def update(self, dt: float):
        while True:
            try:
                kind, payload = self._rx_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "LINE":
                self._handle_line(payload)
            elif kind == "DISCONNECTED":
                self._handle_unexpected_disconnect(payload)
                return
            if not self.is_connected():      # callback vừa ngắt kết nối
                return
        if not self.is_connected():
            return

        dt = min(dt, 0.1)    # GUI đơ một lúc không được gây timeout giả
        for entry in self._pending:
            entry["age"] += dt
            if entry["age"] > ACK_TIMEOUT_S:
                self._handle_unexpected_disconnect(
                    f"STM32 không phản hồi lệnh {entry['cmd']} {entry['motor']} trong {ACK_TIMEOUT_S} s.")
                return
        self._since_status += dt
        limit = STATUS_TIMEOUT_S if self._have_status else FIRST_STATUS_TIMEOUT_S
        if self._since_status > limit:
            self._handle_unexpected_disconnect(
                "Không nhận được dòng trạng thái (S) từ STM32 — kiểm tra cổng COM, baud rate và firmware.")

    def _handle_unexpected_disconnect(self, reason):
        self.disconnect()
        self._set_status(RobotStatus.ERROR)
        if self._on_connection_lost:
            self._on_connection_lost(reason)

    # ---------------- Phân tích dòng nhận về ----------------
    def _handle_line(self, text):
        try:
            kind, data = parse_line(text)
        except ProtocolError:
            self.bad_lines += 1
            return
        if kind == "S":
            self._on_status_msg(data)
        elif kind == "OK":
            self._on_ok(*data)
        elif kind == "ERR":
            self._on_err(*data)
        elif kind == "FAULT":
            self._on_fault(*data)
        elif kind == "T":
            self._on_telemetry(data)
        elif kind == "LINKLOST":
            self._on_link_lost()
        elif kind == "BOOT":
            if self._configured:
                self._handle_unexpected_disconnect(
                    "STM32 vừa reset (BOOT) — mất mốc vị trí. Hãy Connect lại rồi bấm HOME để tìm lại vị trí gốc.")

    def _pop_pending(self, cmd, motor):
        """Lấy lệnh cũ nhất khớp (cmd, motor); ERR '?' (lệnh lạ) khớp theo số động cơ."""
        for entry in self._pending:
            if (cmd == "?" or entry["cmd"] == cmd) and (motor is None or entry["motor"] == motor):
                self._pending.remove(entry)
                return entry
        return None

    def _on_ok(self, cmd, motor):
        entry = self._pop_pending(cmd, motor)
        if entry is None:
            return
        if entry["tag"] == "cfg":
            self._config_ack()
        if cmd == "GRIP":
            self._set_gripper("ON" if motor else "OFF")   # "OK GRIP <0|1>": số = trạng thái kẹp mới
        if cmd in MOTION_CMDS or cmd in ("CLEAR", "ESTOP"):
            self._need_fresh_status = True       # trạng thái S đã nhận trước OK có thể là "cũ"

    def _on_err(self, cmd, motor, reason):
        entry = self._pop_pending(cmd, motor)
        axis = AXIS_OF_MOTOR.get(motor, "?")
        text = ERR_TEXT.get(reason, reason)
        if entry is not None and entry["tag"] == "cfg":
            self._config_err = f"{cmd} {axis}: {text}"
            self._config_ack()
            return
        if entry is not None and entry["cmd"] in MOTION_CMDS:
            self._need_fresh_status = True
            if reason == "homing":                # JOG/GOTO bị từ chối vì đang HOMING: đích bên PC đã đổi nhưng STM32 giữ nguyên
                self._resync_pending = True
        if entry is not None and entry["cmd"] == "HOMING" and reason == "nosensor":
            self._on_nosensor(axis)               # chưa có cảm biến cho trục này: bỏ qua, KHÔNG báo lỗi
            return
        if cmd == "GRIP":
            self._report(f"STM32 từ chối lệnh GRIP: {text}.")
            return
        self._report(f"STM32 từ chối lệnh {cmd} (động cơ {motor} = {axis}): {text}.")
        if entry is not None and entry["cmd"] == "HOMING":
            self._abort_homing()                  # 1 trục không HOMING được -> dừng cả 4 trục, báo HOME_ERROR

    def _on_fault(self, motor, kind):
        axis = AXIS_OF_MOTOR.get(motor, "?")
        self._is_homed = False
        self._resync_pending = True
        self._report(f"STM32 báo FAULT ở {axis} (động cơ {motor}): {FAULT_TEXT.get(kind, kind)}.")
        if self._pending_home:
            self._abort_homing()                  # đang HOMING mà có trục FAULT -> dừng cả 4 trục

    def _config_ack(self):
        self._config_left -= 1
        if self._config_left > 0:
            return
        ok = self._config_err is None
        self._configured = self._configured or ok
        if ok:
            self._start_heartbeat()              # STM32 đã bật watchdog -> bắt đầu PING
        cb, self._config_cb = self._config_cb, None
        if cb:
            cb(ok, "CONFIG_OK" if ok else self._config_err)

    def _report(self, message):
        if self._on_command_error:
            self._on_command_error(message)

    def _on_status_msg(self, data):
        self._since_status = 0.0
        self._have_status = True
        self._need_fresh_status = False
        any_fault = any_busy = any_estop = False
        all_homed = True
        sensor_axes = 0
        for motor, (st, goal, sp, pos) in data["motors"].items():
            axis = AXIS_OF_MOTOR[motor]
            enc = self._enc[axis]
            self.actual[axis] = self._c2u(axis, pos)
            self._telemetry[axis] = {"flags": st, "goal": goal, "sp": sp, "pos": pos}
            any_fault |= bool(st & ST_FAULT)
            any_busy |= bool(st & ST_BUSY)
            any_estop |= bool(st & ST_ESTOP)
            if axis not in self._no_sensor:       # trục chưa có cảm biến home (vd J3) không tính vào "đã HOME"
                sensor_axes += 1
                all_homed &= bool(st & ST_HOMED)
        self._any_fault, self._any_busy, self._any_estop = any_fault, any_busy, any_estop
        if any_estop and not self._estop_seen:                       # cạnh lên: báo 1 lần (dừng chương trình đang chạy)
            self._estop_seen = True
            self._report("STM32 đang ở trạng thái E-STOP: mọi lệnh chuyển động bị khóa. "
                         "Bấm RESET rồi HOME lại để chạy tiếp (robot đã mất mốc vị trí).")
        elif not any_estop:
            self._estop_seen = False
        if data.get("grip") is not None:                             # firmware có kẹp: trạng thái chân PD9 thật
            self._set_gripper("ON" if data["grip"] else "OFF")
        self._is_homed = sensor_axes > 0 and all_homed               # "đã HOME" = cả 4 trục đã tham chiếu theo cảm biến (firmware xóa khi FAULT/HOMING lại)
        self._evaluate_status()

    def _evaluate_status(self):
        if self._any_fault or self._any_estop:
            new = RobotStatus.ERROR
        elif self._motion_pending() or self._need_fresh_status or self._any_busy:
            new = RobotStatus.BUSY
        else:
            new = RobotStatus.READY
        self._set_status(new)
        if new == RobotStatus.ERROR and self._pending_home:
            self._abort_homing()                 # có trục FAULT (kể cả khi dòng FAULT bị mất) -> dừng HOMING
        if new == RobotStatus.READY:
            if self._resync_pending:
                self.target = dict(self.actual)
                self._resync_pending = False
            if self._pending_home:
                self._finish_home(success=self._is_homed and not self._home_failed)

    # ==================== Trạng thái đọc ra ====================
    def get_actual_position(self):
        return dict(self.actual)

    def get_target_position(self):
        return dict(self.target)

    def get_status(self):
        return self.status

    def is_moving(self):
        return self.status == RobotStatus.BUSY

    def get_telemetry(self):
        """Telemetry thật của từng trục (đơn vị độ/mm): state, goal, setpoint, actual, error = setpoint - actual."""
        out = {}
        for axis in AXES:
            t, enc = self._telemetry[axis], self._enc[axis]
            flags = t["flags"]
            if flags & ST_ESTOP:
                state = "E-STOP"
            elif flags & ST_FAULT:
                state = "FAULT"
            elif flags & ST_HOMING:
                state = "HOMING"
            elif flags & ST_PAUSED:
                state = "PAUSED"
            elif flags & ST_BUSY:
                state = "MOVING"
            elif flags & ST_EN:
                state = "HOLD"
            else:
                state = "OFF"
            goal = self._c2u(axis, t["goal"])
            sp = self._c2u(axis, t["sp"])
            actual = self._c2u(axis, t["pos"])
            out[axis] = {"state": state, "goal": goal, "setpoint": sp, "actual": actual,
                         "error": sp - actual, "counts": t["pos"],
                         "homed": bool(flags & ST_HOMED), "home_sensor": bool(flags & ST_HSENSOR)}
        return out

    def _set_status(self, new_status):
        old = self.status
        if old == new_status:
            return
        self.status = new_status
        if self._on_status_change:
            self._on_status_change(old, new_status)

    # ==================== Đăng ký callback ====================
    def set_status_change_callback(self, callback):
        """callback(old_status, new_status)."""
        self._on_status_change = callback

    def set_home_done_callback(self, callback):
        """callback(success: bool)."""
        self._on_home_done = callback

    def set_gripper_change_callback(self, callback):
        """callback(commanded, actual)."""
        self._on_gripper_change = callback
