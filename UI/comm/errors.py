"""errors.py — Lỗi giao tiếp UART dùng chung cho comm/ và ui/."""


class UartError(Exception):
    """Lỗi kết nối/giao tiếp UART — GUI bắt và hiển thị, không crash app."""


class LimitError(UartError):
    """Đích nằm ngoài giới hạn khớp (Settings → Joint Limits) — lệnh bị chặn ở PC, KHÔNG gửi xuống STM32.
    Kế thừa UartError để mọi chỗ GUI đang bắt UartError (JOG, Move, START...) tự hiển thị lý do."""
