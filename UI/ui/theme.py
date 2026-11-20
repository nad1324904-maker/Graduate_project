"""theme.py — Bảng màu, nhãn trạng thái, đơn vị và cấu hình giao diện chung.

Hai bảng màu: LIGHT (mặc định, app master dùng bản này) và DARK (biến môi trường SCARA_THEME=dark, chưa dùng). Mọi màu trong giao diện đều lấy từ đây, kể cả
màu vẽ trên Canvas (tab Giám sát), nên đổi bảng màu chỉ cần sửa file này.

Ngoài ra file này đặt màu MẶC ĐỊNH cho widget customtkinter (_install_widget_defaults):
  - CTkButton: nền xám nhạt / trong suốt -> chữ tối; nền màu (xanh, đỏ, cam...) -> chữ trắng.
  - Nút đang bị khóa (state="disabled") tự đổi sang nền xám nhạt + chữ xám, để nhìn là biết không bấm được.
  - CTkOptionMenu / CTkEntry: chữ và menu xổ xuống theo bảng màu.
"""

import os

import customtkinter as ctk

from comm.backend_base import RobotStatus

THEME = "dark" if os.environ.get("SCARA_THEME", "light").lower() == "dark" else "light"

LIGHT = {
    "BG": "#eef2f7",              # nền cửa sổ
    "PANEL": "#ffffff",           # nền thẻ (Card)
    "PANEL_BORDER": "#dbe3ee",
    "HEADER": "#ffffff",
    "ACCENT": "#2563eb", "ACCENT_HOVER": "#1d4ed8",
    "ACCENT_SOFT": "#dbeafe", "ACCENT_SOFT_HOVER": "#bfdbfe", "ACCENT_TEXT": "#1e40af",   # nút chọn (segmented)
    "TEXT": "#1e293b", "TEXT_DIM": "#64748b", "TEXT_DISABLED": "#8b98ab",
    "ON_ACCENT": "#ffffff",       # chữ trên nền màu
    "ON_ACCENT_DIM": "#dbeafe",   # chữ phụ trên nền màu (dòng Point đang chọn)
    "GREEN": "#16a34a", "GREEN_HOVER": "#15803d",
    "AMBER": "#d97706", "AMBER_HOVER": "#b45309",
    "RED": "#dc2626", "RED_HOVER": "#b91c1c",
    "GRAY_BTN": "#64748b", "GRAY_BTN_HOVER": "#475569",
    "BTN_DARK": "#e8eef6", "BTN_DARK_HOVER": "#d9e2ee",     # nút phụ (secondary)
    "DISABLED_BG": "#eef1f5",
    "INPUT": "#f1f5f9",           # ô nhập, hộp con
    "CANVAS": "#fbfcfe", "GRID": "#edf1f6", "GRID_MAJOR": "#e2e8f0", "PLOT_BAND": "#e0ecff",
    "LINK2": "#60a5fa",           # khâu 2 của robot trên hình 2D
    "LOG_INFO": "#2563eb", "LOG_WARN": "#d97706", "LOG_ERROR": "#dc2626", "LOG_OK": "#16a34a",
}

DARK = {
    "BG": "#070d18",
    "PANEL": "#0d1826",
    "PANEL_BORDER": "#1c3252",
    "HEADER": "#060b14",
    "ACCENT": "#2f8fff", "ACCENT_HOVER": "#1f6fe0",
    "ACCENT_SOFT": "#2f8fff", "ACCENT_SOFT_HOVER": "#1f6fe0", "ACCENT_TEXT": "#eaf1fb",
    "TEXT": "#eaf1fb", "TEXT_DIM": "#7d90ad", "TEXT_DISABLED": "#44526b",
    "ON_ACCENT": "#ffffff",
    "ON_ACCENT_DIM": "#d7e6ff",
    "GREEN": "#22c55e", "GREEN_HOVER": "#1ea34d",
    "AMBER": "#f59e0b", "AMBER_HOVER": "#d78a08",
    "RED": "#ef4444", "RED_HOVER": "#dc2f2f",
    "GRAY_BTN": "#3a4a63", "GRAY_BTN_HOVER": "#4a5c7a",
    "BTN_DARK": "#132238", "BTN_DARK_HOVER": "#1a2e4a",
    "DISABLED_BG": "#111c2c",
    "INPUT": "#0a1522",
    "CANVAS": "#0a1522", "GRID": "#0f1e30", "GRID_MAJOR": "#13243a", "PLOT_BAND": "#12263d",
    "LINK2": "#5aa9ff",
    "LOG_INFO": "#3ba7ff", "LOG_WARN": "#f59e0b", "LOG_ERROR": "#ef4444", "LOG_OK": "#22c55e",
}

_P = DARK if THEME == "dark" else LIGHT

ctk.set_appearance_mode(THEME)
ctk.set_default_color_theme("blue")

# ---------- Bảng màu (tên giữ nguyên như trước để các file khác không phải sửa) ----------
COL_BG = _P["BG"]
COL_PANEL = _P["PANEL"]
COL_PANEL_BORDER = _P["PANEL_BORDER"]
COL_HEADER = _P["HEADER"]
COL_ACCENT = _P["ACCENT"]
COL_ACCENT_HOVER = _P["ACCENT_HOVER"]
COL_ACCENT_SOFT = _P["ACCENT_SOFT"]
COL_ACCENT_SOFT_HOVER = _P["ACCENT_SOFT_HOVER"]
COL_ACCENT_TEXT = _P["ACCENT_TEXT"]
COL_TEXT = _P["TEXT"]
COL_TEXT_DIM = _P["TEXT_DIM"]
COL_TEXT_DISABLED = _P["TEXT_DISABLED"]
COL_ON_ACCENT = _P["ON_ACCENT"]
COL_ON_ACCENT_DIM = _P["ON_ACCENT_DIM"]
COL_GREEN = _P["GREEN"]
COL_GREEN_HOVER = _P["GREEN_HOVER"]
COL_AMBER = _P["AMBER"]
COL_AMBER_HOVER = _P["AMBER_HOVER"]
COL_RED = _P["RED"]
COL_RED_HOVER = _P["RED_HOVER"]
COL_GRAY_BTN = _P["GRAY_BTN"]
COL_GRAY_BTN_HOVER = _P["GRAY_BTN_HOVER"]
COL_BTN_DARK = _P["BTN_DARK"]
COL_BTN_DARK_HOVER = _P["BTN_DARK_HOVER"]
COL_DISABLED_BG = _P["DISABLED_BG"]
COL_INPUT = _P["INPUT"]
COL_CANVAS = _P["CANVAS"]
COL_GRID = _P["GRID"]
COL_GRID_MAJOR = _P["GRID_MAJOR"]
COL_PLOT_BAND = _P["PLOT_BAND"]
COL_LINK2 = _P["LINK2"]

# Kiểu dùng chung cho CTkSegmentedButton (JOG Khớp/Tọa độ, chọn trục đồ thị...)
SEGMENTED_STYLE = dict(fg_color=COL_BTN_DARK, selected_color=COL_ACCENT_SOFT,
                       selected_hover_color=COL_ACCENT_SOFT_HOVER, unselected_color=COL_BTN_DARK,
                       unselected_hover_color=COL_BTN_DARK_HOVER, text_color=COL_ACCENT_TEXT)

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
LOG_TAG_COLOR = {"INFO": _P["LOG_INFO"], "WARN": _P["LOG_WARN"], "ERROR": _P["LOG_ERROR"], "OK": _P["LOG_OK"]}


# ============================================================
# Màu mặc định cho widget customtkinter
# ============================================================
_SOFT_BG = {COL_BTN_DARK, COL_INPUT, COL_PANEL, COL_BG, COL_ACCENT_SOFT, "transparent"}


def _install_widget_defaults():
    btn_init, btn_cfg = ctk.CTkButton.__init__, ctk.CTkButton.configure

    def button_init(self, *args, **kw):
        fg = kw.get("fg_color")
        kw.setdefault("text_color", COL_TEXT if isinstance(fg, str) and fg in _SOFT_BG else COL_ON_ACCENT)
        kw.setdefault("text_color_disabled", COL_TEXT_DISABLED)
        btn_init(self, *args, **kw)
        self._fg_enabled = self.cget("fg_color")
        if kw.get("state") == "disabled" and self._fg_enabled != "transparent":
            btn_cfg(self, fg_color=COL_DISABLED_BG)

    def button_configure(self, require_redraw=False, **kw):
        if "_fg_enabled" in self.__dict__:
            if "fg_color" in kw:
                self._fg_enabled = kw["fg_color"]
            if self._fg_enabled != "transparent" and ("state" in kw or "fg_color" in kw):
                disabled = kw.get("state", self.cget("state")) == "disabled"
                kw["fg_color"] = COL_DISABLED_BG if disabled else self._fg_enabled
        return btn_cfg(self, require_redraw=require_redraw, **kw)

    ctk.CTkButton.__init__ = button_init
    ctk.CTkButton.configure = button_configure

    menu_init = ctk.CTkOptionMenu.__init__

    def optionmenu_init(self, *args, **kw):
        kw.setdefault("text_color", COL_TEXT)
        kw.setdefault("text_color_disabled", COL_TEXT_DISABLED)
        kw.setdefault("dropdown_fg_color", COL_PANEL)
        kw.setdefault("dropdown_hover_color", COL_BTN_DARK_HOVER)
        kw.setdefault("dropdown_text_color", COL_TEXT)
        menu_init(self, *args, **kw)

    ctk.CTkOptionMenu.__init__ = optionmenu_init

    entry_init = ctk.CTkEntry.__init__

    def entry_init_(self, *args, **kw):
        kw.setdefault("text_color", COL_TEXT)
        kw.setdefault("placeholder_text_color", COL_TEXT_DISABLED)
        kw.setdefault("border_color", COL_PANEL_BORDER)
        entry_init(self, *args, **kw)

    ctk.CTkEntry.__init__ = entry_init_


_install_widget_defaults()
