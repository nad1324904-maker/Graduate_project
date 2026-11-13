"""errors.py — Lỗi giao tiếp UART dùng chung cho comm/ và ui/."""


class UartError(Exception):
    """Lỗi kết nối/giao tiếp UART — GUI bắt và hiển thị, không crash app."""
