"""visual.py — Tab GIÁM SÁT: hình robot 2D nhìn từ trên xuống + đồ thị bám quỹ đạo (PID) của 1 trục.

Hiệu năng (máy yếu):
  - Vẽ bằng tk.Canvas (không dùng matplotlib), chỉ khi tab đang mở, 10 lần/giây (theo DISPLAY_EVERY trong ui/perf.py).
  - Telemetry T 50 Hz chỉ được bật (SEL <trục>) khi tab mở; rời tab -> SEL 0, STM32 ngừng gửi.
  - Đồ thị chỉ vẽ cửa sổ thời gian đang xem, tối đa ~600 điểm mỗi đường.
"""

import csv
import math
import os
import tkinter as tk
from datetime import datetime
from tkinter import filedialog

import customtkinter as ctk

from comm.errors import UartError
from core import kinematics, robot_config
from core.kinematics import forward_kinematics
from core.paths import DATA_DIR
from ui.theme import (
    AXES, COL_ACCENT, COL_ACCENT_HOVER, COL_AMBER, COL_BG, COL_BTN_DARK, COL_BTN_DARK_HOVER, COL_GREEN, COL_INPUT,
    COL_PANEL_BORDER, COL_RED, COL_TEXT, COL_TEXT_DIM, COL_TEXT_DISABLED, UNITS
)
from ui.widgets import Card

FONT = ("Segoe UI", 9)
FONT_B = ("Segoe UI Semibold", 10)
PLOT_WINDOWS = {"5 s": 5.0, "10 s": 10.0, "30 s": 30.0}
MAX_PLOT_POINTS = 600


class VisualMixin:
    # ============================================================
    # Dựng giao diện
    # ============================================================
    def _build_visual_view(self):
        view = ctk.CTkFrame(self, fg_color=COL_BG, corner_radius=0)
        view.grid(row=1, column=0, sticky="nsew")
        view.grid_columnconfigure(0, weight=5)
        view.grid_columnconfigure(1, weight=6)
        view.grid_rowconfigure(0, weight=1)
        self.visual_view = view

        self._trace_axis_choice = "J1"
        self._plot_frozen = None             # None = đang cập nhật; list = dữ liệu đã "dừng hình"
        self._visual_cfg = robot_config.get_default_config()

        self._build_view2d_card(view).grid(row=0, column=0, sticky="nsew", padx=(8, 4), pady=8)
        self._build_plot_card(view).grid(row=0, column=1, sticky="nsew", padx=(4, 8), pady=8)

    def _build_view2d_card(self, parent):
        card = Card(parent, "ROBOT 2D — NHÌN TỪ TRÊN XUỐNG", "🧭")
        body = card.body
        opts = ctk.CTkFrame(body, fg_color="transparent")
        opts.pack(fill="x", pady=(0, 6))
        self.v2d_show_points = ctk.BooleanVar(value=True)
        self.v2d_show_program = ctk.BooleanVar(value=True)
        for text, var in (("Points", self.v2d_show_points), ("Đường đi chương trình", self.v2d_show_program)):
            ctk.CTkCheckBox(opts, text=text, variable=var, font=("Segoe UI", 11), text_color=COL_TEXT_DIM,
                            checkbox_width=18, checkbox_height=18).pack(side="left", padx=(0, 14))
        self.v2d_canvas = tk.Canvas(body, bg=COL_INPUT, highlightthickness=0, width=420, height=300)
        self.v2d_canvas.pack(fill="both", expand=True)
        self.v2d_note = ctk.CTkLabel(body, text="", font=("Segoe UI", 10), text_color=COL_TEXT_DISABLED,
                                     anchor="w", justify="left", wraplength=520)
        self.v2d_note.pack(fill="x", pady=(6, 0))
        return card

    def _build_plot_card(self, parent):
        card = Card(parent, "ĐỒ THỊ BÁM QUỸ ĐẠO (PID)", "📈")
        body = card.body
        bar = ctk.CTkFrame(body, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 6))
        seg_kw = dict(height=28, font=("Segoe UI Semibold", 11), fg_color=COL_INPUT, selected_color=COL_ACCENT,
                      selected_hover_color=COL_ACCENT_HOVER, unselected_color=COL_BTN_DARK,
                      unselected_hover_color=COL_BTN_DARK_HOVER, text_color=COL_TEXT)
        self.plot_axis_seg = ctk.CTkSegmentedButton(bar, values=list(AXES), command=self._on_trace_axis_change,
                                                    **seg_kw)
        self.plot_axis_seg.set(self._trace_axis_choice)
        self.plot_axis_seg.pack(side="left")
        self.plot_window_seg = ctk.CTkSegmentedButton(bar, values=list(PLOT_WINDOWS), **seg_kw)
        self.plot_window_seg.set("10 s")
        self.plot_window_seg.pack(side="left", padx=10)
        self.plot_csv_btn = ctk.CTkButton(bar, text="💾 Lưu CSV", width=92, height=28, corner_radius=8,
                                          fg_color=COL_BTN_DARK, hover_color=COL_BTN_DARK_HOVER,
                                          font=("Segoe UI", 11), command=self._on_export_trace_csv)
        self.plot_csv_btn.pack(side="right")
        self.plot_freeze_btn = ctk.CTkButton(bar, text="⏸ Dừng hình", width=100, height=28, corner_radius=8,
                                             fg_color=COL_BTN_DARK, hover_color=COL_BTN_DARK_HOVER,
                                             font=("Segoe UI", 11), command=self._on_toggle_plot_freeze)
        self.plot_freeze_btn.pack(side="right", padx=6)

        self.plot_canvas = tk.Canvas(body, bg=COL_INPUT, highlightthickness=0, width=520, height=300)
        self.plot_canvas.pack(fill="both", expand=True)
        self.plot_stats = ctk.CTkLabel(body, text="", font=("Consolas", 11), text_color=COL_TEXT_DIM, anchor="w")
        self.plot_stats.pack(fill="x", pady=(6, 0))
        return card

    # ============================================================
    # Mở / rời tab
    # ============================================================
    def _on_visual_show(self):
        try:
            self._visual_cfg = robot_config.load_config()
        except robot_config.ConfigError:
            self._visual_cfg = robot_config.get_default_config()
        self._set_trace(self._trace_axis_choice)
        self._refresh_visual()

    def _on_visual_hide(self):
        self._set_trace(None)                # STM32 ngừng gửi telemetry khi không xem đồ thị

    def _set_trace(self, axis):
        if not self._connected():
            return
        try:
            self.backend.set_trace_axis(axis)
        except UartError as e:
            self._log(str(e), "ERROR")

    def _on_trace_axis_change(self, axis):
        self._trace_axis_choice = axis
        self._plot_frozen = None
        self.plot_freeze_btn.configure(text="⏸ Dừng hình")
        if self.active_tab == "visual":
            self._set_trace(axis)

    def _on_toggle_plot_freeze(self):
        if self._plot_frozen is None:
            self._plot_frozen = self._current_trace()[1]
            self.plot_freeze_btn.configure(text="▶ Tiếp tục")
        else:
            self._plot_frozen = None
            self.plot_freeze_btn.configure(text="⏸ Dừng hình")

    def _current_trace(self):
        if self._connected() and hasattr(self.backend, "get_trace"):
            return self.backend.get_trace()
        return None, []

    def _refresh_visual(self):
        """Gọi từ vòng _tick (10 lần/giây) khi tab Giám sát đang mở."""
        self._draw_view2d()
        self._draw_plot()

    # ============================================================
    # Hình robot 2D
    # ============================================================
    def _joint_limits(self):
        if hasattr(self.backend, "joint_limits"):
            return dict(self.backend.joint_limits)
        return {a: (v["min"], v["max"]) for a, v in self._visual_cfg["joint_limits"].items()}

    def _draw_view2d(self):
        c = self.v2d_canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 50 or h < 50:
            return
        p = kinematics.SCARA_PARAMS
        l1, l2, h1, h2 = p["l1"], p["l2"], p["h1"], p["h2"]
        reach = l1 + l2
        lim = self._joint_limits()
        zbar_w = 74
        plot_w = w - zbar_w
        s = min(plot_w, h) / (2.0 * reach * 1.12)                # mm -> pixel
        cx, cy = plot_w / 2.0, h / 2.0                            # pixel của khớp J1

        def px(x, y):
            return cx + (x - h1) * s, cy - y * s

        # ---- Lưới, vùng với tới, giới hạn J1 ----
        step = 50 if reach > 150 else 25
        n = int(reach * 1.12 // step) + 1
        for i in range(-n, n + 1):
            x0, _ = px(h1 + i * step, 0)
            _, y0 = px(0, i * step)
            c.create_line(x0, 0, x0, h, fill="#0f1e30")
            c.create_line(0, y0, plot_w, y0, fill="#0f1e30")
        ox, oy = px(h1, 0)
        for r, dash in ((reach, (6, 4)), (abs(l1 - l2), (3, 3))):
            if r > 0:
                c.create_oval(ox - r * s, oy - r * s, ox + r * s, oy + r * s, outline=COL_PANEL_BORDER, dash=dash)
        for a in lim["J1"]:
            ex, ey = px(h1 + reach * math.cos(math.radians(a)), reach * math.sin(math.radians(a)))
            c.create_line(ox, oy, ex, ey, fill=COL_TEXT_DISABLED, dash=(4, 4))
            c.create_text(ex, ey, text=f"J1 {a:g}°", fill=COL_TEXT_DISABLED, font=FONT,
                          anchor="w" if ex >= ox else "e")
        c.create_line(ox, oy, ox + 34, oy, fill=COL_RED, arrow="last")
        c.create_line(ox, oy, ox, oy - 34, fill=COL_GREEN, arrow="last")
        c.create_text(ox + 40, oy, text="X", fill=COL_RED, font=FONT_B)
        c.create_text(ox, oy - 42, text="Y", fill=COL_GREEN, font=FONT_B)

        # ---- Points + đường đi chương trình (xem trước, khớp đồng bộ = đường thẳng trong không gian khớp) ----
        note = []
        if self.v2d_show_program.get():
            note.append(self._draw_program_path(c, px))
        if self.v2d_show_points.get():
            for name in self.point_store.list_names():
                v = self.point_store.get(name)
                x, y, _, _ = forward_kinematics(v["J1"], v["J2"], v["J3"], v["Z"])
                X, Y = px(x, y)
                c.create_oval(X - 4, Y - 4, X + 4, Y + 4, fill=COL_TEXT_DIM, outline="")
                c.create_text(X + 7, Y - 7, text=name, fill=COL_TEXT_DIM, font=FONT, anchor="w")

        # ---- Robot: đích (mờ) và thực tế ----
        connected = self._connected()
        actual = self.backend.get_actual_position()
        target = self.backend.get_target_position()
        if connected and any(abs(target[a] - actual[a]) > 1e-3 for a in AXES):
            self._draw_arm(c, px, target, ghost=True)
        gripped = self.backend.get_gripper_state()["commanded"] == "ON"
        tcp = self._draw_arm(c, px, actual, ghost=False, gripped=gripped)
        x, y, z, th = tcp
        c.create_text(10, 10, anchor="nw", fill=COL_TEXT, font=("Consolas", 11),
                      text=f"X {x:8.2f} mm\nY {y:8.2f} mm\nZ {z:8.2f} mm\nθ {th:8.2f} °")
        if not connected:
            c.create_text(plot_w / 2, h - 16, text="CHƯA KẾT NỐI — hiển thị tư thế mặc định, vẫn xem trước được chương trình",
                          fill=COL_AMBER, font=FONT_B)

        # ---- Thanh Z (độ cao đầu công tác) ----
        zlo, zhi = (v - h2 for v in lim["Z"])
        bx0, bx1, by0, by1 = plot_w + 26, plot_w + 40, 40, h - 40
        c.create_text(plot_w + 33, 20, text="Z (mm)", fill=COL_TEXT_DIM, font=FONT_B)
        c.create_rectangle(bx0, by0, bx1, by1, outline=COL_PANEL_BORDER, fill=COL_BG)

        def zy(zv):
            f = 0.0 if zhi == zlo else (zv - zlo) / (zhi - zlo)
            return by1 - max(0.0, min(1.0, f)) * (by1 - by0)
        c.create_text(bx1 + 4, by0, text=f"{zhi:g}", fill=COL_TEXT_DISABLED, font=FONT, anchor="w")
        c.create_text(bx1 + 4, by1, text=f"{zlo:g}", fill=COL_TEXT_DISABLED, font=FONT, anchor="w")
        if connected:
            ty = zy(target["Z"] - h2)
            c.create_line(bx0 - 6, ty, bx1 + 6, ty, fill=COL_ACCENT, dash=(3, 2))
        ay = zy(z)
        c.create_rectangle(bx0, ay, bx1, by1, fill=COL_ACCENT, outline="")
        c.create_text(bx0 - 4, ay, text=f"{z:.1f}", fill=COL_TEXT, font=FONT, anchor="e")

        note = [n for n in note if n]
        note.append("— thực tế   ┄ đích đang chạy tới   ● Point   ┄ đường đi chương trình (các khớp đồng bộ)")
        self.v2d_note.configure(text="\n".join(note))

    def _draw_arm(self, c, px, j, ghost, gripped=False):
        """Vẽ cánh tay theo góc khớp j. Trả về (x, y, z, θ) của đầu công tác."""
        p = kinematics.SCARA_PARAMS
        t1, t12 = math.radians(j["J1"]), math.radians(j["J1"] + j["J2"])
        base = (p["h1"], 0.0)
        elbow = (p["h1"] + p["l1"] * math.cos(t1), p["l1"] * math.sin(t1))
        x, y, z, th = forward_kinematics(j["J1"], j["J2"], j["J3"], j["Z"])
        B, E, W = px(*base), px(*elbow), px(x, y)
        if ghost:
            c.create_line(*B, *E, *W, fill=COL_ACCENT, width=2, dash=(5, 4))
            return x, y, z, th
        c.create_line(*B, *E, fill=COL_ACCENT, width=9, capstyle="round")
        c.create_line(*E, *W, fill="#5aa9ff", width=7, capstyle="round")
        for (X, Y), r, col in ((B, 9, COL_TEXT), (E, 6, COL_TEXT), (W, 5, COL_GREEN if gripped else COL_AMBER)):
            c.create_oval(X - r, Y - r, X + r, Y + r, fill=col, outline=COL_BG, width=2)
        a = math.radians(th)                                       # hướng dụng cụ (θ)
        c.create_line(*W, W[0] + 22 * math.cos(a), W[1] - 22 * math.sin(a), fill=COL_GREEN if gripped else COL_AMBER,
                      width=3, arrow="last")
        return x, y, z, th

    def _draw_program_path(self, c, px):
        """Đường đi dự kiến của chương trình đang chọn ở tab Robot. Vì các khớp chạy đồng bộ (cùng xuất phát, cùng tới
        đích), đường đi giữa 2 Point = nội suy TUYẾN TÍNH trong không gian khớp -> FK. Trả về dòng chú thích."""
        name = getattr(self, "selected_program", None)
        if not name or not self.program_store.exists(name):
            return "Chọn một chương trình ở tab Robot để xem trước đường đi."
        steps = self.program_store.get(name)["steps"]
        moves = [(i + 1, st["point"]) for i, st in enumerate(steps)
                 if st["type"] == "MOVE" and self.point_store.exists(st["point"])]
        if not moves:
            return f"Chương trình '{name}' chưa có Step MOVE."
        pts = [self.point_store.get(pn) for _, pn in moves]
        for a, b in zip(pts, pts[1:]):
            line = []
            for k in range(25):
                f = k / 24.0
                j = {ax: a[ax] + f * (b[ax] - a[ax]) for ax in AXES}
                x, y, _, _ = forward_kinematics(j["J1"], j["J2"], j["J3"], j["Z"])
                line.extend(px(x, y))
            c.create_line(*line, fill=COL_AMBER, width=2, dash=(6, 3), arrow="last", arrowshape=(10, 12, 4))
        labels = {}
        for (idx, pn), v in zip(moves, pts):
            labels.setdefault(pn, (v, []))[1].append(str(idx))
        for pn, (v, nums) in labels.items():
            x, y, _, _ = forward_kinematics(v["J1"], v["J2"], v["J3"], v["Z"])
            X, Y = px(x, y)
            c.create_oval(X - 6, Y - 6, X + 6, Y + 6, outline=COL_AMBER, width=2)
            c.create_text(X + 8, Y + 9, text="#" + ",".join(nums), fill=COL_AMBER, font=FONT, anchor="w")
        return f"Xem trước '{name}': {len(moves)} bước MOVE (số # = thứ tự Step)."

    # ============================================================
    # Đồ thị bám quỹ đạo
    # ============================================================
    def _draw_plot(self):
        c = self.plot_canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 80 or h < 80:
            return
        axis = self._trace_axis_choice
        unit = UNITS[axis]
        if not self._connected():
            c.create_text(w / 2, h / 2, text="Chưa kết nối STM32 — Settings → Communication → Connect.",
                          fill=COL_TEXT_DIM, font=FONT_B)
            self.plot_stats.configure(text="")
            return
        live_axis, data = self._current_trace()
        if self._plot_frozen is not None:
            data = self._plot_frozen
        elif live_axis != axis:
            data = []
        if len(data) < 2:
            c.create_text(w / 2, h / 2, text=f"Đang chờ dữ liệu telemetry của {axis} (50 Hz)...",
                          fill=COL_TEXT_DIM, font=FONT_B)
            self.plot_stats.configure(text="")
            return
        span = PLOT_WINDOWS.get(self.plot_window_seg.get(), 10.0)
        t_end = data[-1][0]
        data = [r for r in data if r[0] >= t_end - span]
        stride = max(1, len(data) // MAX_PLOT_POINTS)
        pts = data[::stride]
        if pts[-1] is not data[-1]:
            pts.append(data[-1])

        db_counts = float(self._visual_cfg["pid"][axis]["deadband"])
        db = db_counts / robot_config.counts_per_unit(axis, self._visual_cfg["encoder"][axis])

        left, right, gap = 64, 14, 26
        top_h = (h - 3 * gap) * 0.62
        bot_h = (h - 3 * gap) - top_h
        top = (gap, gap + top_h)
        bot = (2 * gap + top_h, 2 * gap + top_h + bot_h)

        def xt(t):
            return left + (t - (t_end - span)) / span * (w - left - right)

        # ---- Khung trên: vị trí đặt / thực / đích ----
        vals = [v for r in pts for v in (r[2], r[3])]
        self._plot_panel(c, xt, left, w - right, top, min(vals), max(vals), f"Vị trí {axis} ({unit})",
                         [(1, COL_TEXT_DISABLED, (2, 3), 1, "đích"), (2, COL_ACCENT, None, 2, "đặt (quỹ đạo)"),
                          (3, COL_GREEN, None, 2, "thực (encoder)")], pts, t_end, span)
        # ---- Khung dưới: sai số bám = đặt − thực, kèm vùng chết ----
        err = [(r[0], r[2] - r[3]) for r in pts]
        emax = max(abs(e) for _, e in err)
        lim = max(emax, db * 1.5, 1e-6)
        self._plot_panel(c, xt, left, w - right, bot, -lim, lim, f"Sai số bám = đặt − thực ({unit})",
                         [(1, COL_AMBER, None, 2, "sai số")], err, t_end, span, band=db)

        all_err = [r[2] - r[3] for r in data]
        rms = math.sqrt(sum(e * e for e in all_err) / len(all_err))
        self.plot_stats.configure(text=(
            f"{axis}  sai số hiện tại {all_err[-1]:+.4f}{unit}   |sai số| lớn nhất {max(abs(e) for e in all_err):.4f}{unit}"
            f"   RMS {rms:.4f}{unit}   vùng chết ±{db:.4f}{unit} ({db_counts:g} counts)"
            + ("   ⏸ ĐANG DỪNG HÌNH" if self._plot_frozen is not None else "")))

    def _plot_panel(self, c, xt, x0, x1, ybounds, vmin, vmax, title, series, rows, t_end, span, band=None):
        """Vẽ 1 khung đồ thị: lưới, nhãn trục, các đường. series = [(chỉ số cột, màu, dash, độ dày, chú thích)]."""
        y0, y1 = ybounds
        if vmax - vmin < 1e-9:
            vmin, vmax = vmin - 0.5, vmax + 0.5
        pad = (vmax - vmin) * 0.08
        vmin, vmax = vmin - pad, vmax + pad

        def yv(v):
            return y1 - (v - vmin) / (vmax - vmin) * (y1 - y0)
        c.create_rectangle(x0, y0, x1, y1, outline=COL_PANEL_BORDER)
        if band:
            c.create_rectangle(x0, yv(band), x1, yv(-band), fill="#12263d", outline="")
            c.create_text(x1 - 4, yv(band) - 2, text="vùng chết", fill=COL_TEXT_DISABLED, font=FONT, anchor="se")
        for k in range(5):                                         # lưới ngang + nhãn giá trị
            v = vmin + (vmax - vmin) * k / 4
            y = yv(v)
            c.create_line(x0, y, x1, y, fill="#13243a")
            c.create_text(x0 - 6, y, text=f"{v:.3f}" if abs(vmax - vmin) < 10 else f"{v:.1f}",
                          fill=COL_TEXT_DISABLED, font=FONT, anchor="e")
        tick = 1.0 if span <= 10 else 5.0                          # lưới dọc theo thời gian
        k = 0
        while k * tick <= span + 1e-9:
            x = xt(t_end - k * tick)
            c.create_line(x, y0, x, y1, fill="#13243a")
            c.create_text(x, y1 + 10, text="0" if k == 0 else f"-{k * tick:g}s", fill=COL_TEXT_DISABLED, font=FONT)
            k += 1
        c.create_text(x0 + 6, y0 + 4, text=title, fill=COL_TEXT, font=FONT_B, anchor="nw")
        lx = x1 - 8
        for col, color, dash, width, label in reversed(series):   # chú thích góc phải
            c.create_text(lx, y0 + 6, text=label, fill=color, font=FONT, anchor="ne")
            lx -= 7 * len(label) + 18
        for col, color, dash, width, _ in series:
            line = []
            for r in rows:
                line.extend((xt(r[0]), yv(r[col])))
            if len(line) >= 4:
                c.create_line(*line, fill=color, width=width, dash=dash)

    # ============================================================
    # Xuất CSV
    # ============================================================
    def _on_export_trace_csv(self):
        axis, data = self._current_trace()
        if self._plot_frozen is not None:
            axis, data = self._trace_axis_choice, self._plot_frozen
        if not data:
            self._log("Chưa có dữ liệu đồ thị để lưu (cần kết nối và mở tab Giám sát).", "WARN")
            return
        unit = UNITS[axis]
        path = filedialog.asksaveasfilename(
            title="Lưu dữ liệu đồ thị", defaultextension=".csv", initialdir=DATA_DIR,
            initialfile=f"trace_{axis}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        t0 = data[0][0]
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:      # utf-8-sig: Excel đọc đúng tiếng Việt
                wr = csv.writer(f)
                wr.writerow(["t (s)", f"dich ({unit})", f"dat ({unit})", f"thuc ({unit})", f"sai so ({unit})",
                             f"v dat ({unit}/s)", f"v thuc ({unit}/s)"])
                for t, goal, sp, pos, sv, v in data:
                    wr.writerow([f"{t - t0:.3f}", f"{goal:.5f}", f"{sp:.5f}", f"{pos:.5f}", f"{sp - pos:.5f}",
                                 f"{sv:.4f}", f"{v:.4f}"])
        except OSError as e:
            self._log(f"Không ghi được file CSV: {e}", "ERROR")
            return
        self._log(f"Đã lưu {len(data)} mẫu ({data[-1][0] - t0:.1f} s) của {axis} vào {os.path.basename(path)}.", "OK")
