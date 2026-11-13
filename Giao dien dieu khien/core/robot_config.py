"""
robot_config.py — Quản lý cấu hình robot (tab CÀI ĐẶT).
------------------------------------------------------------------------
File cấu hình JSON độc lập, gom tham số "phần cứng" mà trước đây nằm rải
rác hard-code trong kinematics.py (SCARA_PARAMS) và sim_backend.py
(JOINT_LIMITS, DEFAULT_MAX_VELOCITY), theo đúng cấu trúc 5 panel trong
tab Cài đặt:

  - kinematics     : h1, l1, l2, h2 (mm) — truyền trực tiếp vào tham số
                     `params` của forward_kinematics() (kinematics.py
                     KHÔNG bị sửa, vì hàm đã sẵn cho phép override).
  - joint_limits   : min/max từng khớp — Apply sẽ gọi
                     backend.set_joint_limits().
  - home_position  : vị trí (độ/mm) gán cho từng trục khi HOMING chạm cảm biến — gửi xuống STM32 bằng HPOS.
  - encoder        : PPR / Gear Ratio / Direction từng khớp — CHƯA có
                     tác dụng lên SimulationBackend (không mô phỏng
                     encoder/động cơ thật), chỉ lưu lại để dùng khi viết
                     firmware STM32 thật.
  - motion_profile : Vmax/Amax từng khớp (profile hình thang — trapezoidal,
                     không còn Jmax). Chỉ Vmax có tác dụng lên
                     SimulationBackend (Apply -> backend.set_max_velocity).
                     Amax CHƯA dùng vì mô phỏng hiện tại di chuyển thẳng
                     đều theo vận tốc giới hạn, chưa có pha tăng/giảm tốc —
                     lưu sẵn giá trị để dùng cho firmware thật sau này.
  - fault_limits   : ngưỡng sai số bám (độ/mm) khi chạy (trip) và khi HOMING (home_trip) — gửi bằng TRIP.
  - pid            : Kp/Ki/Kd + deadband (counts) từng khớp — vòng PID chạy trên
                     STM32; PC chỉ nạp xuống (PID/DB) khi Connect hoặc Apply.

Module này KHÔNG phụ thuộc GUI/backend — chỉ đọc/ghi JSON + merge với
default, giữ đúng nguyên tắc tách lớp của dự án (giống point_store.py /
program_store.py).
"""

import json
import os

from core.paths import DATA_DIR

DEFAULT_CONFIG_FILE = os.path.join(DATA_DIR, "robot_config.json")

AXES = ["J1", "J2", "J3", "Z"]

# Giá trị mặc định — khớp phần cứng thật của robot (có thể chỉnh trong tab Cài đặt).
#   PPR        : số count trên 1 vòng trục motor SAU hộp số motor và đã nhân x4 (J1/J2/Z: 436800, J3: 76500).
#   Gear Ratio : J1-J3 = tỉ số truyền đai/khâu sau motor (J1/J2: đai "3:1", J3: "1:1" nối thẳng);
#                Z     = mm/vòng motor ("8" -> 8 mm/vòng).
#   Vmax/Amax  : độ/s và độ/s² (J1-J3), mm/s và mm/s² (Z) — mặc định THẬN TRỌNG cho lần chạy đầu.
#                Z: động cơ 163 rpm x vít-me 2 mm/vòng ≈ 5.4 mm/s tối đa, nên Vmax Z phải ≤ ~5 mm/s
#                (cao hơn thì quỹ đạo chạy nhanh hơn động cơ -> sai số bám tăng -> FAULT trip).
#   PID        : duty PWM (0..4199) trên mỗi count sai số; deadband = vùng chết ±n counts (khớp main.c: J=5, Z=191).
DEFAULT_CONFIG = {
    "kinematics": {"h1": 0.0, "l1": 120.0, "l2": 100.0, "h2": 50.0},
    "joint_limits": {
        "J1": {"min": 0.0, "max": 120.0},
        "J2": {"min": 0.0, "max": 120.0},
        "J3": {"min": 0.0, "max": 120.0},
        "Z": {"min": 150.0, "max": 300.0},
    },
    # Vị trí gán cho từng trục khi HOMING chạm cảm biến home (độ / mm). Gửi xuống STM32 bằng lệnh HPOS (đã đổi ra
    # counts theo panel Encoder) khi Connect/Apply — firmware không còn tự tính vị trí này.
    "home_position": {"J1": 30.0, "J2": 30.0, "J3": 0.0, "Z": 300.0},
    "encoder": {
        "J1": {"ppr": 436800, "gear_ratio": "3:1", "direction": "Normal"},
        "J2": {"ppr": 436800, "gear_ratio": "3:1", "direction": "Normal"},
        "J3": {"ppr": 76500, "gear_ratio": "1:1", "direction": "Normal"},
        "Z": {"ppr": 436800, "gear_ratio": "8", "direction": "Normal"},
    },
    "motion_profile": {
        "J1": {"vmax": 30.0, "amax": 60.0},
        "J2": {"vmax": 30.0, "amax": 60.0},
        "J3": {"vmax": 30.0, "amax": 60.0},
        "Z": {"vmax": 5.0, "amax": 20.0},
    },
    "pid": {
        "J1": {"kp": 4.2, "ki": 0.0, "kd": 0.0, "deadband": 5},
        "J2": {"kp": 4.2, "ki": 0.0, "kd": 0.0, "deadband": 5},
        "J3": {"kp": 4.2, "ki": 0.0, "kd": 0.0, "deadband": 5},
        "Z": {"kp": 4.2, "ki": 0.0, "kd": 0.0, "deadband": 191},
    },
    # Ngưỡng sai số bám quỹ đạo (độ / mm) — gửi xuống STM32 bằng lệnh TRIP (đổi ra counts):
    #   trip      : khi chạy bình thường, vượt -> FAULT trip (phanh, tắt PID; kẹt cơ khí / sai chiều / mất encoder)
    #   home_trip : khi HOMING, vượt -> FAULT home (trục bị chặn khi tìm cảm biến). Nhỏ hơn trip vì HOMING chạy chậm.
    "fault_limits": {
        "J1": {"trip": 20.0, "home_trip": 1.6},
        "J2": {"trip": 20.0, "home_trip": 1.6},
        "J3": {"trip": 20.0, "home_trip": 5.0},
        "Z": {"trip": 1.4, "home_trip": 0.11},
    },
}


MAX_FIRMWARE_COUNTS = 20_000_000     # = CONTROL_POS_LIMIT trong control.h (giới hạn tham số LIMIT/HPOS/TRIP)


class ConfigError(Exception):
    """Lỗi nghiệp vụ config (file hỏng, thiếu quyền ghi...) — GUI bắt và
    hiển thị, không phải lỗi hệ thống."""


def parse_ratio(text):
    """'50:1' -> 50.0, '3:2' -> 1.5, '2' -> 2.0. Raise ValueError nếu không hợp lệ hoặc <= 0."""
    t = str(text).strip()
    if ":" in t:
        a, b = t.split(":", 1)
        value = float(a) / float(b)
    else:
        value = float(t)
    if not (value > 0) or value == float("inf"):
        raise ValueError(f"Gear Ratio không hợp lệ: {text!r}")
    return value


def counts_per_unit(axis, encoder_cfg):
    """Số count trên 1 đơn vị (độ với J1-J3, mm với Z) — gửi xuống STM32.
       J: PPR x tỉ số / 360      Z: PPR / bước vít (mm/vòng)."""
    ppr = float(encoder_cfg["ppr"])
    ratio = parse_ratio(encoder_cfg["gear_ratio"])
    return ppr / ratio if axis == "Z" else ppr * ratio / 360.0


# Gốc đổi đơn vị = vị trí ứng với 0 counts (lúc cấp nguồn, trước khi HOMING): J1=J2=J3=0°, Z=300 mm.
# KHÁC với vị trí cảm biến home (config["home_position"], gửi bằng HPOS): sau HOMING encoder = home_position.
HOME_POSITION = {"J1": 0.0, "J2": 0.0, "J3": 0.0, "Z": 300.0}


def axis_sign(encoder_cfg):
    """+1 (Normal) hoặc -1 (Reverse) — đảo chiều ở phía PC vì firmware cố định dấu encoder trong main.c."""
    return -1 if encoder_cfg["direction"] == "Reverse" else 1


def units_to_counts(axis, value, encoder_cfg):
    """Độ/mm -> counts so với vị trí cấp nguồn (Home). Z đi xuống (< 300 mm) cho counts ÂM."""
    cpu = counts_per_unit(axis, encoder_cfg)
    return int(round(axis_sign(encoder_cfg) * (float(value) - HOME_POSITION[axis]) * cpu))


def counts_to_units(axis, counts, encoder_cfg):
    cpu = counts_per_unit(axis, encoder_cfg)
    return HOME_POSITION[axis] + axis_sign(encoder_cfg) * counts / cpu


def get_default_config():
    """Trả về BẢN SAO độc lập của default — tránh sửa nhầm vào hằng số
    dùng chung khi caller mutate trực tiếp dict trả về."""
    return json.loads(json.dumps(DEFAULT_CONFIG))


def _deep_merge_defaults(config, defaults):
    """Điền mọi khóa còn thiếu trong `config` từ `defaults` (đệ quy) — để
    file cũ / thiếu trường (ví dụ bạn thêm khớp mới sau này) vẫn nạp
    được mà không cần validate gắt gao."""
    for key, default_value in defaults.items():
        if key not in config:
            config[key] = json.loads(json.dumps(default_value))
        elif isinstance(default_value, dict) and isinstance(config[key], dict):
            _deep_merge_defaults(config[key], default_value)
    return config


def load_config(file_path=DEFAULT_CONFIG_FILE):
    """Đọc config từ JSON. File chưa tồn tại (lần đầu chạy) -> trả về
    default, KHÔNG tự tạo file trên đĩa — chỉ ghi khi người dùng bấm Save,
    tránh việc GUI tự ý tạo file cấu hình ngoài ý muốn."""
    if not os.path.exists(file_path):
        return get_default_config()
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise ConfigError(f"Không đọc được file cấu hình '{file_path}': {e}")
    if not isinstance(config, dict):
        raise ConfigError(f"File cấu hình '{file_path}' không đúng định dạng.")
    config = _deep_merge_defaults(config, DEFAULT_CONFIG)
    # File cũ (thời S-Curve) còn khóa "jmax" — bỏ đi để lần Save kế tiếp
    # ghi ra file sạch, đúng profile hình thang (chỉ Vmax/Amax).
    for axis_cfg in config.get("motion_profile", {}).values():
        if isinstance(axis_cfg, dict):
            axis_cfg.pop("jmax", None)
    return config


def validate_config(config):
    """Kiểm tra dữ liệu trước khi Save/Apply — trả về (is_valid, [lỗi,...]).
    KHÔNG raise, để GUI gom hết lỗi rồi hiển thị 1 lần lên Log thay vì
    dừng ở lỗi đầu tiên."""
    errors = []

    kin = config.get("kinematics", {})
    for key in ("h1", "l1", "l2", "h2"):
        try:
            float(kin[key])
        except (KeyError, TypeError, ValueError):
            errors.append(f"Kinematics: giá trị '{key}' không hợp lệ.")

    limits = config.get("joint_limits", {})
    for axis in AXES:
        try:
            lo = float(limits[axis]["min"])
            hi = float(limits[axis]["max"])
            if lo >= hi:
                errors.append(f"Joint Limits {axis}: Min ({lo}) phải nhỏ hơn Max ({hi}).")
        except (KeyError, TypeError, ValueError):
            errors.append(f"Joint Limits {axis}: giá trị Min/Max không hợp lệ.")

    home = config.get("home_position", {})
    for axis in AXES:
        try:
            value = float(home[axis])
            lo, hi = float(limits[axis]["min"]), float(limits[axis]["max"])
            if not (lo <= value <= hi):
                errors.append(f"Home {axis}: {value:g} nằm ngoài giới hạn khớp [{lo:g}, {hi:g}].")
        except (KeyError, TypeError, ValueError):
            errors.append(f"Home {axis}: giá trị không hợp lệ.")

    encoder = config.get("encoder", {})
    for axis in AXES:
        try:
            ppr = int(float(encoder[axis]["ppr"]))
            if ppr <= 0:
                errors.append(f"Encoder {axis}: PPR phải > 0.")
            parse_ratio(encoder[axis]["gear_ratio"])
            if encoder[axis]["direction"] not in ("Normal", "Reverse"):
                errors.append(f"Encoder {axis}: Direction phải là Normal hoặc Reverse.")
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            errors.append(f"Encoder {axis}: dữ liệu không hợp lệ (PPR > 0, Gear Ratio dạng 'a:b' hoặc số > 0).")

    motion = config.get("motion_profile", {})
    for axis in AXES:
        try:
            vmax = float(motion[axis]["vmax"])
            amax = float(motion[axis]["amax"])
            if vmax <= 0 or amax <= 0:
                errors.append(f"Motion Profile {axis}: Vmax/Amax phải > 0.")
        except (KeyError, TypeError, ValueError):
            errors.append(f"Motion Profile {axis}: dữ liệu không hợp lệ.")

    pid = config.get("pid", {})
    for axis in AXES:
        try:
            kp = float(pid[axis]["kp"])
            ki = float(pid[axis]["ki"])
            kd = float(pid[axis]["kd"])
            if kp < 0 or ki < 0 or kd < 0:
                errors.append(f"PID {axis}: Kp/Ki/Kd không được âm.")
            db = int(float(pid[axis]["deadband"]))
            if not (0 <= db <= 100000):
                errors.append(f"PID {axis}: Deadband phải từ 0 đến 100000 counts.")
        except (KeyError, TypeError, ValueError):
            errors.append(f"PID {axis}: dữ liệu không hợp lệ.")

    faults = config.get("fault_limits", {})
    for axis in AXES:
        try:
            trip = float(faults[axis]["trip"])
            home_trip = float(faults[axis]["home_trip"])
            if not (trip > 0 and home_trip > 0):
                errors.append(f"Fault Thresholds {axis}: Trip / Home Trip phải > 0.")
                continue
            cpu = counts_per_unit(axis, encoder[axis])        # đổi ra counts phải >= 1 và nằm trong giới hạn firmware
            for name, value in (("Trip", trip), ("Home Trip", home_trip)):
                counts = round(value * cpu)
                if counts < 1:
                    errors.append(f"Fault Thresholds {axis}: {name} quá nhỏ (đổi ra < 1 count).")
                elif counts > MAX_FIRMWARE_COUNTS:
                    errors.append(f"Fault Thresholds {axis}: {name} quá lớn (vượt {MAX_FIRMWARE_COUNTS} counts).")
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            errors.append(f"Fault Thresholds {axis}: dữ liệu không hợp lệ.")

    return (len(errors) == 0), errors


def save_config(config, file_path=DEFAULT_CONFIG_FILE):
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except OSError as e:
        raise ConfigError(f"Không ghi được file cấu hình '{file_path}': {e}")