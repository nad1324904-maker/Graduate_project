"""
uart_protocol.py — Giao thức PC <-> STM32 (text, mỗi lệnh 1 dòng kết thúc '\\n'). Thuần Python, không
phụ thuộc serial/GUI. Phải khớp với control.c / control.h ở firmware.

  PC -> STM32 : <LỆNH> <số động cơ 1..4> [tham số]        vd  "GOTO 2 12750"   "PID 3 4.2 0 0"
                GRIP <0|1>  (kẹp: KHÔNG có số động cơ; 1 = ĐÓNG, 0 = MỞ) -> "OK GRIP <0|1>" / "ERR GRIP ? <lý do>"
  STM32 -> PC : OK <lệnh> <số>            |  ERR <lệnh> <số> <lý do>
                S <ms> (st goal sp pos) x4 <grip> |  FAULT <số> trip|home  |  BOOT  |  T ... (telemetry 1 động cơ, bỏ qua)

Đơn vị trên dây: counts, counts/s, counts/s^2 (backend đổi từ độ/mm). Không có checksum: dòng hỏng sẽ bị
parse_line() từ chối (ProtocolError) hoặc bị bỏ qua, không làm chương trình chết.
"""

# Động cơ <-> trục (theo main.c): Motor1 = Z (vít-me), Motor2..4 = J1..J3 (khớp quay)
MOTOR_OF_AXIS = {"Z": 1, "J1": 2, "J2": 3, "J3": 4}
AXIS_OF_MOTOR = {v: k for k, v in MOTOR_OF_AXIS.items()}
AXES = ("J1", "J2", "J3", "Z")

# Các bit trong trường st của dòng S
ST_EN, ST_PAUSED, ST_BUSY, ST_FAULT = 1, 2, 4, 8
ST_HOMED, ST_HOMING, ST_HSENSOR = 16, 32, 64     # đã HOME thật | đang tìm cảm biến home | cảm biến home đang kích hoạt


class ProtocolError(Exception):
    """Dòng nhận được không đúng định dạng."""


def fmt_float(value: float) -> str:
    """Số thực gọn cho lệnh PID (đủ chính xác cho float32 ở firmware)."""
    return format(float(value), ".9g")


def build_cmd(cmd: str, motor: int, *args) -> bytes:
    """build_cmd('GOTO', 2, 12750) -> b'GOTO 2 12750\\n'. Dòng tối đa 63 ký tự (COMM_LINE_SZ = 64 ở firmware)."""
    parts = [cmd, str(int(motor))] + [str(a) for a in args]
    line = " ".join(parts)
    if len(line) > 63:
        raise ProtocolError(f"Lệnh quá dài ({len(line)} ký tự): {line!r}")
    return (line + "\n").encode("ascii")


def _to_int(tok):
    try:
        return int(tok)
    except ValueError:
        raise ProtocolError(f"Không phải số nguyên: {tok!r}")


def parse_line(text: str):
    """Trả về (kind, data):
         ("S", {"ms": int, "motors": {1: (st, goal, sp, pos), ... 4: ...}, "grip": 0|1|None})
         ("OK", (cmd, motor))            ("ERR", (cmd, motor_or_None, reason))
         ("FAULT", (motor, kind))        ("BOOT", None)
         ("T", None)  telemetry 1 động cơ (GUI không dùng)
       Raise ProtocolError nếu dòng hỏng."""
    tokens = text.strip().split()
    if not tokens:
        raise ProtocolError("Dòng rỗng")
    head = tokens[0]
    if head == "S":
        # 18 trường: firmware cũ (chưa có kẹp) | 19 trường: thêm <grip> (1 = kẹp ĐÓNG, 0 = MỞ) ở cuối
        if len(tokens) not in (2 + 4 * 4, 3 + 4 * 4):
            raise ProtocolError(f"Dòng S sai số trường ({len(tokens)}): {text!r}")
        vals = [_to_int(t) for t in tokens[1:]]
        motors = {m + 1: tuple(vals[1 + 4 * m: 5 + 4 * m]) for m in range(4)}
        grip = vals[17] if len(vals) > 17 else None
        return "S", {"ms": vals[0], "motors": motors, "grip": grip}
    if head == "OK":
        if len(tokens) != 3:
            raise ProtocolError(f"Dòng OK sai định dạng: {text!r}")
        return "OK", (tokens[1], _to_int(tokens[2]))
    if head == "ERR":
        if len(tokens) < 4:
            raise ProtocolError(f"Dòng ERR sai định dạng: {text!r}")
        motor = None if tokens[2] == "?" else _to_int(tokens[2])
        return "ERR", (tokens[1], motor, " ".join(tokens[3:]))
    if head == "FAULT":
        if len(tokens) != 3:
            raise ProtocolError(f"Dòng FAULT sai định dạng: {text!r}")
        return "FAULT", (_to_int(tokens[1]), tokens[2])
    if head == "BOOT":
        return "BOOT", None
    if head == "T":
        return "T", None
    raise ProtocolError(f"Dòng không nhận ra: {text!r}")