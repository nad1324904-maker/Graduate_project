"""
kinematics.py — Động học thuận (FK) và động học ngược (IK) cho SCARA 4-DOF (J1, J2, J3, Z).
------------------------------------------------------------------------
Module thuần túy (pure function), không phụ thuộc GUI hay backend — đúng
mục 26 trong spec: "The PC performs Forward Kinematics... FK uses the
actual joint positions."

Cấu trúc động học kế thừa từ project trước của bạn:
  - d1  : khớp tịnh tiến Z, nâng toàn bộ cụm tay lên/xuống (= trục Z)
  - h1  : offset X cố định từ gốc tới khớp O1 (KHÔNG do người dùng chỉnh)
  - theta1, theta2 : 2 khớp quay chính quyết định vị trí X, Y (= J1, J2)
  - theta3 : khớp quay cổ tay, chỉ ảnh hưởng góc θ của TCP, KHÔNG ảnh
             hưởng vị trí X, Y (= J3)
  - l1, l2 : chiều dài 2 khâu, mặc định l1 = l2 = 100mm (đã chốt)
  - h2  : offset cố định từ O3 xuống đầu công tác (KHÔNG do người dùng
          chỉnh)

h1, l1, l2, h2 giờ chỉnh được ngay trong GUI (màn hình CÀI ĐẶT → Robot
Kinematics), không cần sửa code nữa — xem set_params() bên dưới. Giá trị
ở SCARA_PARAMS chỉ còn là DEFAULT dùng lúc app chưa nạp robot_config.json.
"""

import math

SCARA_PARAMS = {
    "l1": 100.0,  # mm — mặc định, chỉnh trong Settings
    "l2": 100.0,  # mm — mặc định, chỉnh trong Settings
    "h1": 0.0,    # mm — mặc định, chỉnh trong Settings
    "h2": 0.0,    # mm — mặc định, chỉnh trong Settings
}


def set_params(new_params: dict, params=None):
    """Cập nhật SCARA_PARAMS tại runtime — gọi từ GUI khi bấm Apply ở màn
    hình Settings. Mặc định sửa NGAY TRÊN dict SCARA_PARAMS (không tạo
    dict mới) để mọi lệnh gọi forward_kinematics() sau đó (dùng
    `params or SCARA_PARAMS` mặc định) thấy giá trị mới ngay lập tức mà
    GUI không cần truyền lại params thủ công ở mọi nơi.

    Truyền `params` khác nếu muốn cập nhật một bộ tham số riêng (ví dụ
    test) thay vì SCARA_PARAMS toàn cục.
    """
    target = params if params is not None else SCARA_PARAMS
    required = ("h1", "l1", "l2", "h2")
    missing = [k for k in required if k not in new_params]
    if missing:
        raise ValueError(f"Thiếu tham số kinematics: {missing}")
    for k in required:
        target[k] = float(new_params[k])
    return target


def forward_kinematics(j1, j2, j3, z, params=None):
    """Tính vị trí Descartes (X, Y, Z, theta) của TCP từ vị trí khớp thực
    tế (ACTUAL) — theo đúng mục 26: KHÔNG được dùng target thay cho actual.

    j1, j2, j3: độ (degree)
    z: mm (= d1)
    Trả về (x, y, z_tcp, theta) — x/y/z_tcp tính bằng mm, theta bằng độ.
    """
    p = params or SCARA_PARAMS
    l1, l2, h1, h2 = p["l1"], p["l2"], p["h1"], p["h2"]

    t1 = math.radians(j1)
    t2 = math.radians(j2)

    x = h1 + l1 * math.cos(t1) + l2 * math.cos(t1 + t2)
    y = l1 * math.sin(t1) + l2 * math.sin(t1 + t2)
    z_tcp = z - h2
    theta = (j1 + j2 + j3 + 180) % 360 - 180  # bọc về [-180, 180)

    return x, y, z_tcp, theta


# ======================================================================
# Inverse Kinematics
# ======================================================================
class IKError(ValueError):
    """Không tìm được tư thế khớp cho tọa độ yêu cầu (ngoài vùng với tới, vượt giới hạn khớp, điểm kỳ dị)."""


_EPS = 1e-6


def _wrap180(angle):
    return (angle + 180.0) % 360.0 - 180.0


def _fit_angle(angle, lo, hi, ref):
    """Trong các góc tương đương angle + k·360°, chọn góc nằm trong [lo, hi] và gần `ref` nhất. None nếu không có."""
    best = None
    base = _wrap180(angle)
    for k in range(-2, 3):
        a = base + 360.0 * k
        if lo - _EPS <= a <= hi + _EPS and (best is None or abs(a - ref) < abs(best - ref)):
            best = min(max(a, lo), hi)          # kẹp phần sai số làm tròn (≤ _EPS) về đúng biên
    return best


def inverse_kinematics(x, y, z, theta, params=None, limits=None, current=None):
    """Động học ngược: tọa độ TCP (x, y, z_tcp mm; theta độ) -> vị trí khớp {"J1", "J2", "J3" (độ), "Z" (mm)}.

    Là nghịch đảo đúng của forward_kinematics():
        x' = x − h1,   cos θ2 = (x'² + y² − l1² − l2²) / (2·l1·l2),   θ2 = ± arccos(...)
        θ1 = atan2(y, x') − atan2(l2·sin θ2, l1 + l2·cos θ2)
        θ3 = θ − θ1 − θ2,   Z = z_tcp + h2
    Có 2 nghiệm (khuỷu θ2 > 0 và θ2 < 0). Mỗi góc được chọn trong các giá trị tương đương ±360° sao cho nằm trong
    giới hạn khớp. Nghiệm hợp lệ nào gần tư thế hiện tại nhất (tổng |Δ góc| của J1, J2, J3) thì được chọn.

    limits : {axis: (min, max)} — giới hạn khớp; None = không giới hạn.
    current: {axis: value} — tư thế hiện tại để chọn nghiệm; None = chọn gần 0°.
    Raise IKError (thông báo tiếng Việt) nếu không có nghiệm hợp lệ.
    """
    p = params or SCARA_PARAMS
    l1, l2, h1, h2 = float(p["l1"]), float(p["l2"]), float(p["h1"]), float(p["h2"])
    if l1 <= 0 or l2 <= 0:
        raise IKError("Chiều dài khâu l1, l2 phải > 0 (Settings → Robot Kinematics).")

    inf = float("inf")
    lim = {a: (-inf, inf) for a in ("J1", "J2", "J3", "Z")}
    if limits:
        lim.update({a: (float(v[0]), float(v[1])) for a, v in limits.items() if a in lim})
    ref = {"J1": 0.0, "J2": 0.0, "J3": 0.0}
    if current:
        ref.update({a: float(current[a]) for a in ref if a in current})

    # ---- Z (độc lập với X, Y) ----
    zj = float(z) + h2
    if not (lim["Z"][0] - _EPS <= zj <= lim["Z"][1] + _EPS):
        raise IKError(f"Z = {z:g} mm cần trục Z = {zj:g} mm, ngoài giới hạn [{lim['Z'][0]:g}, {lim['Z'][1]:g}] mm.")

    # ---- Vùng với tới trên mặt phẳng XY ----
    xp, yp = float(x) - h1, float(y)
    r = math.hypot(xp, yp)
    r_min, r_max = abs(l1 - l2), l1 + l2
    if r > r_max + _EPS:
        raise IKError(f"Điểm ({x:g}, {y:g}) quá xa: cách khớp J1 {r:.2f} mm > tầm với tối đa l1 + l2 = {r_max:g} mm.")
    if r < r_min - _EPS:
        raise IKError(f"Điểm ({x:g}, {y:g}) quá gần: cách khớp J1 {r:.2f} mm < tầm với tối thiểu |l1 − l2| = {r_min:g} mm.")
    if r < _EPS:
        raise IKError("Điểm trùng trục khớp J1 (điểm kỳ dị): J1 có vô số nghiệm — hãy chọn điểm lệch khỏi tâm.")

    c2 = (r * r - l1 * l1 - l2 * l2) / (2.0 * l1 * l2)
    c2 = max(-1.0, min(1.0, c2))

    candidates, rejected = [], []
    for sign in (1.0, -1.0):
        t2 = sign * math.acos(c2)
        t1 = math.atan2(yp, xp) - math.atan2(l2 * math.sin(t2), l1 + l2 * math.cos(t2))
        raw = {"J1": math.degrees(t1), "J2": math.degrees(t2)}
        sol = {a: _fit_angle(raw[a], *lim[a], ref[a]) for a in ("J1", "J2")}
        bad = [a for a in ("J1", "J2") if sol[a] is None]
        if not bad:
            sol["J3"] = _fit_angle(float(theta) - sol["J1"] - sol["J2"], *lim["J3"], ref["J3"])
            if sol["J3"] is None:
                bad = ["J3"]
                raw["J3"] = _wrap180(float(theta) - raw["J1"] - raw["J2"])
        if bad:
            rejected.append(", ".join(f"{a}={_wrap180(raw[a]):.1f}° ngoài [{lim[a][0]:g}, {lim[a][1]:g}]" for a in bad))
            continue
        sol["Z"] = min(max(zj, lim["Z"][0]), lim["Z"][1])
        candidates.append(sol)

    if not candidates:
        raise IKError("Cả 2 nghiệm động học ngược đều vượt giới hạn khớp: " + " | ".join(rejected) + ".")
    return min(candidates, key=lambda s: sum(abs(s[a] - ref[a]) for a in ("J1", "J2", "J3")))
