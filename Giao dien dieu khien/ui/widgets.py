"""widgets.py — Widget dùng chung (Card, JogRow, các dòng bảng, nút lớn...)."""

import customtkinter as ctk

from ui.theme import (
    COL_ACCENT, COL_ACCENT_HOVER, COL_AMBER, COL_BTN_DARK, COL_BTN_DARK_HOVER, COL_GREEN,
    COL_INPUT, COL_ON_ACCENT, COL_ON_ACCENT_DIM, COL_PANEL, COL_PANEL_BORDER, COL_TEXT, COL_TEXT_DIM,
    COL_TEXT_DISABLED
)


# ============================================================
# Widget dùng chung
# ============================================================
class Card(ctk.CTkFrame):
    def __init__(self, master, title, icon="🔧", **kwargs):
        super().__init__(master, fg_color=COL_PANEL, border_color=COL_PANEL_BORDER,
                          border_width=1, corner_radius=14, **kwargs)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(header, text=icon, font=("Segoe UI", 15), text_color=COL_ACCENT).pack(side="left")
        ctk.CTkLabel(header, text=title, font=("Segoe UI Semibold", 13),
                     text_color=COL_TEXT).pack(side="left", padx=(8, 0))
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=14, pady=(0, 12))


class HeaderBadge(ctk.CTkFrame):
    """1 khối trạng thái trên header: icon/dot + nhãn + giá trị."""

    def __init__(self, master, icon, label):
        super().__init__(master, fg_color="transparent")
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(anchor="w")
        ctk.CTkLabel(top, text=icon, font=("Segoe UI", 13), text_color=COL_TEXT_DIM).pack(side="left")
        ctk.CTkLabel(top, text=label, font=("Segoe UI", 11), text_color=COL_TEXT_DIM).pack(side="left", padx=(5, 0))
        self.value_label = ctk.CTkLabel(self, text="—", font=("Segoe UI Semibold", 13), text_color=COL_TEXT)
        self.value_label.pack(anchor="w")

    def set_value(self, text, color=None):
        self.value_label.configure(text=text, text_color=color or COL_TEXT)


class JogRow(ctk.CTkFrame):
    """Nhãn trục + [-] [ô nhập step] [+] + 3 chip step nhanh."""

    def __init__(self, master, axis, default_step, unit, presets, on_jog=None):
        super().__init__(master, fg_color="transparent")
        self.unit = unit
        self.axis = axis
        self.on_jog = on_jog

        ctk.CTkLabel(self, text=axis, font=("Segoe UI Semibold", 14),
                     text_color=COL_TEXT, width=28, anchor="w").pack(side="left", padx=(0, 8))
        self.minus_btn = ctk.CTkButton(self, text="−", width=36, height=38, corner_radius=8,
                                        fg_color=COL_BTN_DARK, hover_color=COL_BTN_DARK_HOVER,
                                        font=("Segoe UI", 15), command=lambda: self._jog(-1))
        self.minus_btn.pack(side="left", padx=2)
        self.entry = ctk.CTkEntry(self, width=80, height=38, fg_color=COL_INPUT,
                                   border_width=0, justify="center",
                                   font=("Segoe UI", 13), text_color=COL_TEXT)
        self.entry.insert(0, f"{default_step:.2f}{unit}")
        self.entry.pack(side="left", padx=4)
        self.plus_btn = ctk.CTkButton(self, text="+", width=36, height=38, corner_radius=8,
                                       fg_color=COL_BTN_DARK, hover_color=COL_BTN_DARK_HOVER,
                                       font=("Segoe UI", 15), command=lambda: self._jog(1))
        self.plus_btn.pack(side="left", padx=(2, 10))

        self._preset_btns = []
        for val in presets:
            text = f"{val}{unit}" if unit == "°" else f"{val}{unit}"
            b = ctk.CTkButton(self, text=text, width=52, height=38, corner_radius=8,
                              fg_color=COL_ACCENT if val == presets[1] else COL_BTN_DARK,
                              hover_color=COL_BTN_DARK_HOVER, font=("Segoe UI Semibold", 12),
                              text_color=COL_ON_ACCENT if val == presets[1] else COL_TEXT_DIM,
                              command=lambda v=val: self._set_preset(v))
            b.pack(side="left", padx=2)
            self._preset_btns.append((b, val))
        if presets:
            self._set_preset(presets[1], _log=False)

    def _set_preset(self, value, _log=True):
        self.entry.delete(0, "end")
        self.entry.insert(0, f"{value:.2f}{self.unit}" if isinstance(value, float) else f"{value}{self.unit}")
        for b, val in self._preset_btns:
            b.configure(fg_color=COL_ACCENT if val == value else COL_BTN_DARK,
                        text_color=COL_ON_ACCENT if val == value else COL_TEXT_DIM)

    def get_step(self):
        raw = self.entry.get().replace(self.unit, "").strip()
        try:
            return float(raw)
        except ValueError:
            return 0.0

    def _jog(self, direction):
        step = self.get_step()
        btn = self.plus_btn if direction > 0 else self.minus_btn
        original = btn.cget("fg_color")
        btn.configure(fg_color=COL_ACCENT)
        self.after(150, lambda: btn.configure(fg_color=original))
        if self.on_jog:
            self.on_jog(self.axis, direction, step)

    def set_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        for w in (self.minus_btn, self.plus_btn, self.entry):
            w.configure(state=state)
        for b, _ in self._preset_btns:
            b.configure(state=state)


class PointTableRow(ctk.CTkFrame):
    """1 dòng trong bảng POINTS: Name | Description(tóm tắt tọa độ) — bấm
    để chọn + Load Position (nạp tham chiếu, KHÔNG tự di chuyển)."""

    def __init__(self, master, name, subtitle, selected, on_click):
        super().__init__(master, fg_color=COL_ACCENT if selected else "transparent", corner_radius=6)
        self.bind("<Button-1>", lambda e: on_click())
        name_lbl = ctk.CTkLabel(self, text=name, font=("Segoe UI Semibold", 12), width=90,
                                 anchor="w", text_color=COL_ON_ACCENT if selected else COL_TEXT)
        name_lbl.pack(side="left", padx=(8, 4), pady=6)
        name_lbl.bind("<Button-1>", lambda e: on_click())
        sub_lbl = ctk.CTkLabel(self, text=subtitle, font=("Segoe UI", 10), anchor="w",
                                text_color=COL_ON_ACCENT_DIM if selected else COL_TEXT_DIM)
        sub_lbl.pack(side="left", fill="x", expand=True, padx=4)
        sub_lbl.bind("<Button-1>", lambda e: on_click())


class StepTableRow(ctk.CTkFrame):
    """1 dòng trong bảng PROGRAM EDITOR: # | Type(pill) | Detail — bấm để
    chọn cho Edit Step / Delete Step."""

    TYPE_COLOR = {"MOVE": COL_ACCENT, "GRIP": COL_GREEN, "DELAY": COL_AMBER}

    def __init__(self, master, index, step, selected, on_click):
        super().__init__(master, fg_color=COL_BTN_DARK if selected else "transparent", corner_radius=6)
        self.bind("<Button-1>", lambda e: on_click())
        num_lbl = ctk.CTkLabel(self, text=f"{index + 1:02d}", font=("Segoe UI", 11),
                                text_color=COL_TEXT_DIM, width=26)
        num_lbl.pack(side="left", padx=(6, 4), pady=5)
        num_lbl.bind("<Button-1>", lambda e: on_click())
        pill = ctk.CTkLabel(self, text=step["type"], font=("Segoe UI Semibold", 10),
                             fg_color=self.TYPE_COLOR[step["type"]], text_color=COL_ON_ACCENT,
                             corner_radius=6, width=52, height=20)
        pill.pack(side="left", padx=4)
        pill.bind("<Button-1>", lambda e: on_click())
        detail = {"MOVE": f"→ {step.get('point')}", "GRIP": step.get("action"),
                  "DELAY": f"{step.get('seconds', 0):g} s"}[step["type"]]
        detail_lbl = ctk.CTkLabel(self, text=detail, font=("Segoe UI", 11), anchor="w",
                                   text_color=COL_TEXT)
        detail_lbl.pack(side="left", fill="x", expand=True, padx=6)
        detail_lbl.bind("<Button-1>", lambda e: on_click())


# ============================================================
# Ứng dụng chính
# ============================================================
