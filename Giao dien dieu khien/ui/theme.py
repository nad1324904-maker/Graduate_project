"""theme.py — Bảng màu, nhãn trạng thái, đơn vị và cấu hình giao diện chung."""

import customtkinter as ctk

from comm.backend_base import RobotStatus

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ---------- Bảng màu (theo mockup: navy đậm + cyan/blue) ----------
COL_BG = "#070d18"
COL_PANEL = "#0d1826"
COL_PANEL_BORDER = "#1c3252"
COL_HEADER = "#060b14"
COL_ACCENT = "#2f8fff"
COL_ACCENT_HOVER = "#1f6fe0"
COL_TEXT = "#eaf1fb"
COL_TEXT_DIM = "#7d90ad"
COL_TEXT_DISABLED = "#44526b"
COL_GREEN = "#22c55e"
COL_GREEN_HOVER = "#1ea34d"
COL_AMBER = "#f59e0b"
COL_AMBER_HOVER = "#d78a08"
COL_RED = "#ef4444"
COL_RED_HOVER = "#dc2f2f"
COL_GRAY_BTN = "#3a4a63"
COL_GRAY_BTN_HOVER = "#4a5c7a"
COL_BTN_DARK = "#132238"
COL_BTN_DARK_HOVER = "#1a2e4a"
COL_INPUT = "#0a1522"

STATUS_COLOR = {
    RobotStatus.READY: COL_GREEN,
    RobotStatus.BUSY: COL_ACCENT,
    RobotStatus.DONE: COL_GREEN,
    RobotStatus.ERROR: COL_RED,
}
STATUS_LABEL = {
    RobotStatus.READY: "READY",
    RobotStatus.BUSY: "BUSY",
    RobotStatus.DONE: "DONE",
    RobotStatus.ERROR: "ERROR",
}
AXES = ["J1", "J2", "J3", "Z"]
UNITS = {"J1": "°", "J2": "°", "J3": "°", "Z": "mm"}
LOG_TAG_COLOR = {"INFO": "#3ba7ff", "WARN": "#f59e0b", "ERROR": "#ef4444", "OK": "#22c55e"}
