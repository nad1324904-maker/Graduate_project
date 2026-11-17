"""perf.py — Tối ưu hiệu năng giao diện cho máy cấu hình yếu (KHÔNG đổi logic).

  1. install_configure_cache(): CTkLabel/CTkButton.configure() chỉ thực sự gọi khi giá trị ĐỔI. Trước đây mỗi tick
     GUI gọi ~48 configure() đặt lại đúng giá trị cũ, mỗi lần với CTkButton là vẽ lại hình chữ nhật bo góc.
  2. Hằng số nhịp: TICK_MS (xử lý UART + executor), DISPLAY_EVERY (cứ bao nhiêu tick thì cập nhật số liệu hiển thị),
     MAX_LOG_LINES (giới hạn số dòng SYSTEM LOG để Textbox không nặng dần).
  3. apply_ui_scale(): thu nhỏ giao diện (vd 0.85) — ít điểm ảnh cần vẽ hơn trên màn hình độ phân giải cao.
"""

import customtkinter as ctk

TICK_MS = 50          # chu kỳ xử lý dữ liệu UART + ProgramExecutor (giữ 50 ms để phản hồi giao thức kịp)
DISPLAY_EVERY = 2     # cập nhật số liệu hiển thị mỗi 2 tick = 100 ms (10 Hz, mắt thường không phân biệt được)
MAX_LOG_LINES = 500   # SYSTEM LOG chỉ giữ 500 dòng gần nhất

_installed = False


def _cached(orig):
    def configure(self, *args, **kwargs):
        if args or not kwargs:
            return orig(self, *args, **kwargs)
        last = self.__dict__.setdefault("_cfg_cache", {})
        changed = {}
        for key, value in kwargs.items():
            try:
                same = key in last and type(last[key]) is type(value) and last[key] == value
            except Exception:
                same = False
            if not same:
                changed[key] = value
        if not changed:
            return None            # không có gì đổi -> không vẽ lại
        last.update(changed)
        return orig(self, **changed)
    return configure


def install_configure_cache():
    """Gọi một lần (idempotent). Chỉ áp dụng cho CTkLabel và CTkButton — hai widget bị cập nhật mỗi tick."""
    global _installed
    if _installed:
        return
    for cls in (ctk.CTkLabel, ctk.CTkButton):
        cls.configure = _cached(cls.configure)
    _installed = True


def apply_ui_scale(scale):
    """Phải gọi TRƯỚC khi tạo cửa sổ. scale < 1 thu nhỏ giao diện."""
    if scale and abs(scale - 1.0) > 1e-6:
        ctk.set_widget_scaling(scale)
        ctk.set_window_scaling(scale)
