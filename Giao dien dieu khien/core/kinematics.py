"""
kinematics.py — Forward Kinematics cho SCARA 4-DOF (J1, J2, J3, Z).
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
