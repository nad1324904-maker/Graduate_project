"""
integrated_ui_demo.py — BẢN DEMO giao diện app MASTER (PC) của hệ thống kiểm tra & phân loại PCB.

CHỈ có layout + style, CHƯA có chức năng: mọi số liệu là dữ liệu mẫu, các nút chỉ ghi một dòng vào Log.
Bảng màu lấy giống GUI robot (light mode) để hai app nhìn đồng bộ.

Chạy:  python integrated_ui_demo.py
"""

import time
import tkinter as tk
from datetime import datetime

import customtkinter as ctk

# ============================================================
# Bảng màu (giống "Giao dien dieu khien/ui/theme.py", bản LIGHT)
# ============================================================
BG, PANEL, BORDER, HEADER = "#eef2f7", "#ffffff", "#dbe3ee", "#ffffff"
TEXT, DIM, DISABLED = "#1e293b", "#64748b", "#8b98ab"
ACCENT, ACCENT_HOVER, ACCENT_SOFT, ACCENT_TEXT = "#2563eb", "#1d4ed8", "#dbeafe", "#1e40af"
GREEN, GREEN_HOVER, GREEN_SOFT, GREEN_TEXT = "#16a34a", "#15803d", "#dcfce7", "#166534"
AMBER, AMBER_HOVER, AMBER_SOFT, AMBER_TEXT = "#d97706", "#b45309", "#fef3c7", "#92400e"
RED, RED_HOVER, RED_SOFT, RED_TEXT = "#dc2626", "#b91c1c", "#fee2e2", "#991b1b"
GRAY_BTN, GRAY_BTN_HOVER = "#64748b", "#475569"
BTN_SOFT, BTN_SOFT_HOVER = "#e8eef6", "#d9e2ee"
INPUT, CANVAS = "#f1f5f9", "#fbfcfe"

PILL = {  # (nền, chữ) cho nhãn trạng thái dạng viên thuốc
    "green": (GREEN_SOFT, GREEN_TEXT), "amber": (AMBER_SOFT, AMBER_TEXT),
    "red": (RED_SOFT, RED_TEXT), "blue": (ACCENT_SOFT, ACCENT_TEXT), "gray": (INPUT, DIM),
}
LOG_COLOR = {"INFO": ACCENT, "OK": GREEN, "WARN": AMBER, "ERROR": RED}

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

F = "Segoe UI"
FB = "Segoe UI Semibold"


# ============================================================
# Widget dùng chung
# ============================================================
class Card(ctk.CTkFrame):
    """Thẻ trắng bo góc có tiêu đề (giống Card của GUI robot). Nội dung đặt vào self.body."""

    def __init__(self, master, title, icon, right_text=None, **kw):
        super().__init__(master, fg_color=PANEL, border_color=BORDER, border_width=1, corner_radius=14, **kw)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(10, 4))
        ctk.CTkLabel(head, text=icon, font=(F, 15), text_color=ACCENT).pack(side="left")
        ctk.CTkLabel(head, text=title, font=(FB, 13), text_color=TEXT).pack(side="left", padx=(8, 0))
        if right_text:
            ctk.CTkLabel(head, text=right_text, font=(F, 11), text_color=DIM).pack(side="right")
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=14, pady=(0, 12))


def pill(master, text, kind="gray", width=0, font_size=11):
    bg, fg = PILL[kind]
    return ctk.CTkLabel(master, text=text, fg_color=bg, text_color=fg, corner_radius=8,
                        font=(FB, font_size), width=width, height=24, padx=10)


class HeaderBadge(ctk.CTkFrame):
    """Khối nhỏ trên header: nhãn mờ ở trên, giá trị đậm ở dưới."""

    def __init__(self, master, icon, label, value, color=TEXT):
        super().__init__(master, fg_color="transparent")
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(anchor="w")
        ctk.CTkLabel(top, text=icon, font=(F, 12), text_color=color if icon == "●" else DIM).pack(side="left")
        ctk.CTkLabel(top, text=label, font=(F, 11), text_color=DIM).pack(side="left", padx=(5, 0))
        self.value = ctk.CTkLabel(self, text=value, font=(FB, 13), text_color=color)
        self.value.pack(anchor="w")


# ============================================================
# Ứng dụng
# ============================================================
class MasterDemo(ctk.CTk):
    TABS = (("operate", "🏭", "Vận hành"), ("robot", "🤖", "Robot"),
            ("history", "📋", "Lịch sử"), ("settings", "⚙", "Cài đặt"))

    def __init__(self):
        super().__init__(fg_color=BG)
        self.title("PCB Inspection & Sorting — Master (DEMO giao diện)")
        self.geometry("1480x800")
        self.minsize(1280, 720)
        try:
            self.state("zoomed")              # Windows: mở toàn màn hình (vẫn còn thanh tiêu đề)
        except tk.TclError:
            pass
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=1, column=0, sticky="nsew", padx=16, pady=(12, 0))
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        self.views = {
            "operate": self._build_operate_view(),
            "robot": self._build_robot_view(),
            "history": self._build_history_view(),
            "settings": self._build_settings_view(),
        }
        self._build_log()
        self._show_tab("operate")
        self._tick_clock()

        for lvl, msg in (("INFO", "Khởi động app master (DEMO — dữ liệu mẫu)."),
                         ("OK", "PLC: kết nối Modbus TCP 192.168.0.10:502."),
                         ("OK", "Raspberry Pi: kết nối TCP 192.168.0.20:5000."),
                         ("OK", "Robot SCARA: COM5 — CONFIG_OK, đã HOME."),
                         ("INFO", "PCB #0128: ngoại quan ĐẠT, đang kiểm tra chức năng...")):
            self.log(msg, lvl)

    # ---------------- HEADER ----------------
    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color=HEADER, height=76, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)

        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left", padx=20, pady=12)
        ctk.CTkLabel(left, text="🏭", font=(F, 26)).pack(side="left")
        box = ctk.CTkFrame(left, fg_color="transparent")
        box.pack(side="left", padx=(10, 0))
        ctk.CTkLabel(box, text="PCB INSPECTION & SORTING", font=(FB, 18), text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(box, text="Master PC — PLC · Raspberry Pi · SCARA robot",
                     font=(F, 11), text_color=DIM).pack(anchor="w")

        right = ctk.CTkFrame(header, fg_color="transparent")
        right.pack(side="right", padx=20, pady=12)
        self.clock = HeaderBadge(right, "🕐", "", "--:--:--")
        self.clock.pack(side="right", padx=(24, 0))
        HeaderBadge(right, "●", "Hệ thống", "ĐANG CHẠY", ACCENT).pack(side="right", padx=(24, 0))
        HeaderBadge(right, "⏱", "Chu kỳ gần nhất", "12.4 s").pack(side="right", padx=(24, 0))

        bar = ctk.CTkFrame(right, fg_color=BTN_SOFT, corner_radius=10)
        bar.pack(side="right", padx=(24, 0))
        self.tab_buttons = {}
        for key, icon, label in self.TABS:
            b = ctk.CTkButton(bar, text=f"{icon}  {label}", width=112, height=36, corner_radius=8,
                              font=(FB, 12), fg_color="transparent", hover_color=BTN_SOFT_HOVER,
                              text_color=TEXT, command=lambda k=key: self._show_tab(k))
            b.pack(side="left", padx=3, pady=3)
            self.tab_buttons[key] = b

    def _show_tab(self, key):
        for k, view in self.views.items():
            if k == key:
                view.grid(row=0, column=0, sticky="nsew")
            else:
                view.grid_remove()
        for k, b in self.tab_buttons.items():
            sel = k == key
            b.configure(fg_color=ACCENT_SOFT if sel else "transparent", text_color=ACCENT_TEXT if sel else TEXT)

    def _tick_clock(self):
        self.clock.value.configure(text=datetime.now().strftime("%H:%M:%S"))
        self.after(1000, self._tick_clock)

    # ============================================================
    # TAB VẬN HÀNH
    # ============================================================
    def _build_operate_view(self):
        v = ctk.CTkFrame(self.content, fg_color="transparent")
        v.grid_columnconfigure(0, weight=0, minsize=290)
        v.grid_columnconfigure(1, weight=1)
        v.grid_columnconfigure(2, weight=0, minsize=300)
        v.grid_rowconfigure(0, weight=1)

        # ---- cột trái: điều khiển + thiết bị ----
        left = ctk.CTkFrame(v, fg_color="transparent", width=290)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self._build_control_card(left).pack(fill="x")
        self._build_devices_card(left).pack(fill="x", pady=(12, 0))

        # ---- cột giữa: sơ đồ dây chuyền + PCB hiện tại ----
        mid = ctk.CTkFrame(v, fg_color="transparent")
        mid.grid(row=0, column=1, sticky="nsew")
        mid.grid_rowconfigure(0, weight=1)
        mid.grid_rowconfigure(1, weight=0)
        mid.grid_columnconfigure(0, weight=1)
        line = Card(mid, "Sơ đồ dây chuyền", "🛤", right_text="cập nhật theo cảm biến PLC")
        line.grid(row=0, column=0, sticky="nsew")
        self.line_canvas = tk.Canvas(line.body, bg=CANVAS, highlightthickness=0, height=200)
        self.line_canvas.pack(fill="both", expand=True)
        self.line_canvas.bind("<Configure>", lambda e: self._draw_line())
        self._build_current_pcb_card(mid).grid(row=1, column=0, sticky="ew", pady=(12, 0))

        # ---- cột phải: thống kê + tiến trình ----
        right = ctk.CTkFrame(v, fg_color="transparent", width=300)
        right.grid(row=0, column=2, sticky="nsew", padx=(12, 0))
        self._build_stats_card(right).pack(fill="x")
        self._build_steps_card(right).pack(fill="x", pady=(12, 0))
        return v

    def _build_control_card(self, parent):
        c = Card(parent, "Điều khiển hệ thống", "🎛")
        b = c.body
        estop = ctk.CTkFrame(b, fg_color=GREEN_SOFT, corner_radius=10)
        estop.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(estop, text="E-STOP", font=(FB, 11), text_color=GREEN_TEXT).pack(side="left", padx=12, pady=5)
        ctk.CTkLabel(estop, text="● Bình thường", font=(FB, 12), text_color=GREEN).pack(side="right", padx=12)

        seg = ctk.CTkSegmentedButton(b, values=["Tự động", "Từng bước"], height=30, font=(FB, 12),
                                     fg_color=BTN_SOFT, selected_color=ACCENT_SOFT, selected_hover_color="#bfdbfe",
                                     unselected_color=BTN_SOFT, unselected_hover_color=BTN_SOFT_HOVER,
                                     text_color=ACCENT_TEXT)
        seg.set("Tự động")
        seg.pack(fill="x", pady=(0, 8))

        ctk.CTkButton(b, text="▶  START", height=44, corner_radius=10, font=(FB, 15), fg_color=GREEN,
                      hover_color=GREEN_HOVER, command=lambda: self.log("START (demo)")).pack(fill="x")
        row = ctk.CTkFrame(b, fg_color="transparent")
        row.pack(fill="x", pady=(6, 0))
        row.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(row, text="■  STOP", height=38, corner_radius=10, font=(FB, 13), fg_color=RED,
                      hover_color=RED_HOVER, command=lambda: self.log("STOP (demo)", "WARN")
                      ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkButton(row, text="⟳  RESET", height=38, corner_radius=10, font=(FB, 13), fg_color=GRAY_BTN,
                      hover_color=GRAY_BTN_HOVER, command=lambda: self.log("RESET (demo)")
                      ).grid(row=0, column=1, sticky="ew", padx=(4, 0))
        ctk.CTkLabel(b, text="STOP: dừng sau khi xong PCB hiện tại. E-Stop là nút cứng trên tủ điện (PLC).",
                     font=(F, 10), text_color=DISABLED, wraplength=250, justify="left").pack(anchor="w", pady=(6, 0))
        return c

    def _build_devices_card(self, parent):
        c = Card(parent, "Thiết bị", "🔌")
        for name, detail, state, kind in (
                ("PLC", "192.168.0.10", "ONLINE", "green"),
                ("Raspberry Pi", "192.168.0.20", "ONLINE", "green"),
                ("Robot SCARA", "COM5", "BUSY", "blue"),
                ("Camera", "qua Raspberry", "ONLINE", "green")):
            r = ctk.CTkFrame(c.body, fg_color="transparent")
            r.pack(fill="x", pady=1)
            ctk.CTkLabel(r, text="●", font=(F, 12), text_color=PILL[kind][1]).pack(side="left")
            ctk.CTkLabel(r, text=name, font=(FB, 12), text_color=TEXT).pack(side="left", padx=(6, 0))
            pill(r, state, kind, width=70, font_size=10).pack(side="right")
            ctk.CTkLabel(r, text=detail, font=(F, 10), text_color=DIM).pack(side="right", padx=8)
        ctk.CTkButton(c.body, text="Kết nối lại tất cả", height=30, corner_radius=8, font=(FB, 12),
                      fg_color=BTN_SOFT, hover_color=BTN_SOFT_HOVER,
                      command=lambda: self.log("Kết nối lại (demo)")).pack(fill="x", pady=(8, 0))
        return c

    def _build_current_pcb_card(self, parent):
        c = Card(parent, "PCB hiện tại", "🔍", right_text="#0128 · vào lúc 14:32:05")
        b = c.body
        b.grid_columnconfigure(0, weight=0)
        b.grid_columnconfigure(1, weight=1)
        img = tk.Canvas(b, bg="#e2e8f0", highlightthickness=0, width=260, height=170)
        img.grid(row=0, column=0, sticky="nsw", padx=(0, 14))
        img.bind("<Configure>", lambda e: self._draw_camera_placeholder(img))

        info = ctk.CTkFrame(b, fg_color="transparent")
        info.grid(row=0, column=1, sticky="nsew")
        info.grid_columnconfigure(1, weight=1)
        rows = (("Ngoại quan (camera)", "ĐẠT", "green", "0 lỗi · độ tin cậy 0.97"),
                ("Chức năng (test jig)", "ĐANG TEST", "amber", "bước 3/5 · đo điện áp 3V3"),
                ("Robot phân loại", "CHỜ", "gray", "sẽ chạy chương trình theo kết quả"))
        for i, (name, val, kind, note) in enumerate(rows):
            ctk.CTkLabel(info, text=name, font=(F, 12), text_color=DIM, anchor="w"
                         ).grid(row=i * 2, column=0, sticky="w", pady=(4 if i else 0, 0))
            pill(info, val, kind, width=96).grid(row=i * 2, column=1, sticky="e", pady=(4 if i else 0, 0))
            ctk.CTkLabel(info, text=note, font=(F, 10), text_color=DISABLED, anchor="w"
                         ).grid(row=i * 2 + 1, column=0, columnspan=2, sticky="w")
        res = ctk.CTkFrame(info, fg_color=INPUT, corner_radius=10)
        res.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ctk.CTkLabel(res, text="Kết luận", font=(F, 12), text_color=DIM).pack(side="left", padx=12, pady=8)
        ctk.CTkLabel(res, text="— chờ test chức năng —", font=(FB, 14), text_color=DIM).pack(side="right", padx=12)
        return c

    def _build_stats_card(self, parent):
        c = Card(parent, "Thống kê ca làm việc", "📊", right_text="từ 13:00")
        b = c.body
        top = ctk.CTkFrame(b, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(top, text="127", font=(FB, 28), text_color=TEXT).pack(side="left")
        ctk.CTkLabel(top, text="  PCB đã xử lý", font=(F, 12), text_color=DIM).pack(side="left", pady=(12, 0))
        ctk.CTkLabel(top, text="92.1 %", font=(FB, 20), text_color=GREEN).pack(side="right", pady=(8, 0))

        # thanh tỉ lệ Đạt / Lỗi 1 / Lỗi 2
        counts = (("Đạt", 117, GREEN, "green"), ("Lỗi 1 — ngoại quan", 6, AMBER, "amber"),
                  ("Lỗi 2 — chức năng", 4, RED, "red"))
        bar = ctk.CTkFrame(b, fg_color=INPUT, corner_radius=6, height=12)
        bar.pack(fill="x", pady=(4, 8))
        bar.pack_propagate(False)
        total = sum(n for _, n, _, _ in counts)
        x = 0.0
        for _, n, col, _ in counts:
            seg = ctk.CTkFrame(bar, fg_color=col, corner_radius=0, height=12)
            seg.place(relx=x, rely=0, relwidth=n / total, relheight=1)
            x += n / total
        for name, n, col, kind in counts:
            r = ctk.CTkFrame(b, fg_color="transparent")
            r.pack(fill="x", pady=0)
            ctk.CTkLabel(r, text="■", font=(F, 12), text_color=col).pack(side="left")
            ctk.CTkLabel(r, text=name, font=(F, 12), text_color=TEXT).pack(side="left", padx=(6, 0))
            ctk.CTkLabel(r, text=str(n), font=(FB, 13), text_color=TEXT).pack(side="right")
        ctk.CTkLabel(b, text="Chu kỳ trung bình 12.8 s · ~281 PCB/giờ", font=(F, 10), text_color=DISABLED
                     ).pack(anchor="w", pady=(6, 0))
        return c

    def _build_steps_card(self, parent):
        c = Card(parent, "Tiến trình chu kỳ", "🧭", right_text="theo lưu đồ")
        steps = ("Cấp PCB (động cơ bước)", "Băng tải chạy, chờ CB1", "Xi lanh hạ S2, chụp ảnh",
                 "Kiểm tra chức năng", "Xi lanh về S1, chạy tới CB3", "Robot gắp & phân loại", "Hoàn tất, cộng thống kê")
        current = 3
        for i, s in enumerate(steps):
            done, now = i < current, i == current
            r = ctk.CTkFrame(c.body, fg_color=ACCENT_SOFT if now else "transparent", corner_radius=8)
            r.pack(fill="x", pady=0)
            mark, col = ("✓", GREEN) if done else (("▶", ACCENT) if now else (str(i + 1), DISABLED))
            ctk.CTkLabel(r, text=mark, font=(FB, 12), text_color=col, width=22, height=24).pack(side="left", padx=(6, 4), pady=1)
            ctk.CTkLabel(r, text=s, font=(FB if now else F, 12),
                         text_color=ACCENT_TEXT if now else (TEXT if done else DIM), anchor="w").pack(side="left")
            if now:
                ctk.CTkLabel(r, text="4.1 s", font=(F, 10), text_color=ACCENT_TEXT).pack(side="right", padx=8)
        return c

    # ---------------- vẽ ----------------
    def _draw_line(self):
        """Sơ đồ dây chuyền (dữ liệu mẫu): cấp PCB → băng tải (CB1, trạm kiểm tra CB2, CB3) → robot → 3 khay."""
        cv = self.line_canvas
        cv.delete("all")
        w, h = cv.winfo_width(), cv.winfo_height()
        if w < 200 or h < 120:
            return
        y = h * 0.52                              # tâm băng tải
        x0, x1 = w * 0.13, w * 0.72
        bt = 16                                   # nửa bề dày băng tải
        # băng tải
        cv.create_rectangle(x0, y - bt, x1, y + bt, fill="#cbd5e1", outline="#94a3b8", width=1)
        for k in range(int((x1 - x0) / 22)):
            xx = x0 + 11 + k * 22
            cv.create_line(xx, y - bt + 3, xx - 6, y + bt - 3, fill="#b6c2d2")
        for xx in (x0, x1):
            cv.create_oval(xx - bt, y - bt, xx + bt, y + bt, fill="#94a3b8", outline="#64748b")
        cv.create_text((x0 + x1) / 2, y + bt + 14, text="Băng tải · ĐANG CHẠY  ▶", fill=ACCENT, font=(FB, 10))

        # khay cấp PCB
        fx = w * 0.05
        for k in range(5):
            cv.create_rectangle(fx - 26, y - 36 - k * 7, fx + 26, y - 30 - k * 7, fill="#4ade80", outline="#15803d")
        cv.create_rectangle(fx - 32, y - 30, fx + 32, y + bt, fill="", outline="#94a3b8", width=2)
        cv.create_text(fx, y + bt + 14, text="Cấp PCB · 23 tấm", fill=DIM, font=(F, 10))

        # cảm biến CB1/CB2/CB3
        sensors = (("CB1", x0 + (x1 - x0) * 0.12, False), ("CB2", x0 + (x1 - x0) * 0.50, True),
                   ("CB3", x0 + (x1 - x0) * 0.93, False))
        for name, sx, on in sensors:
            cv.create_line(sx, y - bt - 2, sx, y - bt - 26, fill="#94a3b8", width=2)
            cv.create_oval(sx - 7, y - bt - 40, sx + 7, y - bt - 26, fill=GREEN if on else "#e2e8f0",
                           outline=GREEN_HOVER if on else "#94a3b8", width=1.5)
            cv.create_text(sx, y - bt - 50, text=name, fill=TEXT if on else DIM, font=(FB, 10))

        # trạm kiểm tra (camera + xi lanh) ở CB2
        cx = sensors[1][1]
        cv.create_rectangle(cx - 46, 8, cx + 46, 34, fill=ACCENT_SOFT, outline=ACCENT)
        cv.create_text(cx, 21, text="📷 Camera · S2", fill=ACCENT_TEXT, font=(FB, 10))
        # PCB trên băng tải
        for px, col, outl in ((x0 + (x1 - x0) * 0.27, "#4ade80", "#15803d"), (cx, "#fde68a", AMBER)):
            cv.create_rectangle(px - 20, y - 10, px + 20, y + 10, fill=col, outline=outl, width=2)
        cv.create_text(cx, y + bt + 30, text="#0128 đang kiểm tra", fill=AMBER_TEXT, font=(F, 9))

        # robot SCARA
        rx, ry = w * 0.80, y
        cv.create_oval(rx - 18, ry - 18, rx + 18, ry + 18, fill="#e2e8f0", outline="#64748b", width=2)
        ex, ey = rx - 38, ry - 38
        cv.create_line(rx, ry, ex, ey, fill=ACCENT, width=8, capstyle="round")
        cv.create_line(ex, ey, x1 - 6, y - 4, fill="#60a5fa", width=6, capstyle="round")
        cv.create_oval(rx - 5, ry - 5, rx + 5, ry + 5, fill=ACCENT, outline="")
        cv.create_text(rx, ry + 32, text="SCARA · chờ PCB", fill=DIM, font=(F, 10))

        # 3 khay phân loại
        bins = (("Đạt", "117", GREEN, GREEN_SOFT), ("Lỗi 1", "6", AMBER, AMBER_SOFT), ("Lỗi 2", "4", RED, RED_SOFT))
        bx = w * 0.92
        bh = min(44, (h - 20) / 3 - 6)
        top = (h - 3 * bh - 12) / 2
        for k, (name, n, col, soft) in enumerate(bins):
            by = top + k * (bh + 6)
            cv.create_rectangle(bx - 40, by, bx + 40, by + bh, fill=soft, outline=col, width=2)
            cv.create_text(bx, by + bh * 0.33, text=name, fill=col, font=(FB, 10))
            cv.create_text(bx, by + bh * 0.70, text=n, fill=TEXT, font=(FB, 11))

    @staticmethod
    def _draw_camera_placeholder(cv):
        cv.delete("all")
        w, h = cv.winfo_width(), cv.winfo_height()
        cv.create_rectangle(w * 0.15, h * 0.18, w * 0.85, h * 0.82, fill="#86efac", outline="#15803d", width=2)
        for k in range(6):
            yy = h * 0.28 + k * h * 0.09
            cv.create_line(w * 0.22, yy, w * 0.6, yy, fill="#15803d")
        cv.create_rectangle(w * 0.64, h * 0.3, w * 0.78, h * 0.5, fill="#1e293b", outline="")
        cv.create_text(w / 2, h - 10, text="Ảnh camera (Raspberry Pi gửi về)", fill=DIM, font=(F, 9))

    # ============================================================
    # TAB ROBOT
    # ============================================================
    def _build_robot_view(self):
        v = ctk.CTkFrame(self.content, fg_color="transparent")
        v.grid_columnconfigure((0, 1), weight=1, uniform="r")
        v.grid_rowconfigure(1, weight=1)

        st = Card(v, "Trạng thái robot", "🤖", right_text="COM5 · đã HOME")
        st.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        row = ctk.CTkFrame(st.body, fg_color="transparent")
        row.pack(fill="x")
        for i, (ax, val) in enumerate((("J1", "42.50°"), ("J2", "-18.20°"), ("J3", "90.00°"), ("Z", "312.0 mm"))):
            cell = ctk.CTkFrame(row, fg_color=INPUT, corner_radius=10)
            cell.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 4, 0))
            row.grid_columnconfigure(i, weight=1)
            ctk.CTkLabel(cell, text=ax, font=(F, 11), text_color=DIM).pack(pady=(8, 0))
            ctk.CTkLabel(cell, text=val, font=(FB, 18), text_color=TEXT).pack(pady=(0, 8))
        flags = ctk.CTkFrame(st.body, fg_color="transparent")
        flags.pack(fill="x", pady=(10, 0))
        for text, kind in (("BUSY", "blue"), ("HOMED", "green"), ("Kẹp: MỞ", "gray"), ("Không FAULT", "green")):
            pill(flags, text, kind).pack(side="left", padx=(0, 6))

        pg = Card(v, "Chương trình phân loại", "📝", right_text="lưu trên PC")
        pg.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        for res, prog, kind in (("PCB đạt", "Chương trình 1", "green"), ("Lỗi 2 — chức năng", "Chương trình 2", "red"),
                                ("Lỗi 1 — ngoại quan", "Chương trình 3", "amber")):
            r = ctk.CTkFrame(pg.body, fg_color=INPUT, corner_radius=10)
            r.pack(fill="x", pady=3)
            pill(r, res, kind, width=150).pack(side="left", padx=10, pady=8)
            ctk.CTkLabel(r, text="→  " + prog, font=(FB, 12), text_color=TEXT).pack(side="left")
            ctk.CTkButton(r, text="Chạy thử", width=80, height=28, corner_radius=8, font=(FB, 11),
                          fg_color=BTN_SOFT, hover_color=BTN_SOFT_HOVER,
                          command=lambda p=prog: self.log(f"Chạy thử {p} (demo)")).pack(side="right", padx=10)

        act = Card(v, "Thao tác robot (chỉ khi hệ thống dừng)", "🛠")
        act.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(12, 0))
        btns = ctk.CTkFrame(act.body, fg_color="transparent")
        btns.pack(anchor="w")
        for text, col, hov in (("⌂  HOME", ACCENT, ACCENT_HOVER), ("Mở / đóng kẹp", BTN_SOFT, BTN_SOFT_HOVER),
                               ("⟳  Reset lỗi robot", GRAY_BTN, GRAY_BTN_HOVER),
                               ("↗  Mở giao diện điều khiển robot", BTN_SOFT, BTN_SOFT_HOVER)):
            ctk.CTkButton(btns, text=text, height=40, corner_radius=10, font=(FB, 12), fg_color=col, hover_color=hov,
                          command=lambda t=text: self.log(f"{t.strip()} (demo)")).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(act.body, text="Teach điểm, soạn chương trình, chỉnh PID… làm trong giao diện điều khiển robot "
                                    "(module riêng). App master chỉ chạy chương trình và đọc trạng thái.",
                     font=(F, 11), text_color=DIM, justify="left", anchor="w").pack(anchor="w", pady=(12, 0))
        return v

    # ============================================================
    # TAB LỊCH SỬ
    # ============================================================
    def _build_history_view(self):
        v = ctk.CTkFrame(self.content, fg_color="transparent")
        v.grid_columnconfigure(0, weight=1)
        v.grid_rowconfigure(0, weight=1)
        c = Card(v, "Lịch sử PCB", "📋", right_text="127 bản ghi · ca từ 13:00")
        c.grid(row=0, column=0, sticky="nsew")

        tools = ctk.CTkFrame(c.body, fg_color="transparent")
        tools.pack(fill="x", pady=(0, 8))
        ctk.CTkSegmentedButton(tools, values=["Tất cả", "Đạt", "Lỗi 1", "Lỗi 2"], height=30, font=(FB, 11),
                               fg_color=BTN_SOFT, selected_color=ACCENT_SOFT, selected_hover_color="#bfdbfe",
                               unselected_color=BTN_SOFT, unselected_hover_color=BTN_SOFT_HOVER,
                               text_color=ACCENT_TEXT).pack(side="left")
        ctk.CTkButton(tools, text="💾 Xuất CSV", width=100, height=30, corner_radius=8, font=(FB, 11),
                      fg_color=BTN_SOFT, hover_color=BTN_SOFT_HOVER,
                      command=lambda: self.log("Xuất CSV (demo)")).pack(side="right")

        cols = (("Mã PCB", 90), ("Thời gian", 100), ("Ngoại quan", 120), ("Chức năng", 120),
                ("Kết luận", 120), ("Chu kỳ", 80), ("Ghi chú", 0))
        head = ctk.CTkFrame(c.body, fg_color=INPUT, corner_radius=8)
        head.pack(fill="x")
        for name, wdt in cols:
            ctk.CTkLabel(head, text=name, font=(FB, 11), text_color=DIM, width=wdt, anchor="w"
                         ).pack(side="left", padx=8, pady=6, fill="x", expand=wdt == 0)
        table = ctk.CTkScrollableFrame(c.body, fg_color="transparent")
        table.pack(fill="both", expand=True)
        sample = []
        for k in range(40):
            n = 127 - k
            kind = "red" if n % 23 == 0 else ("amber" if n % 17 == 0 else "green")
            vis = "LỖI" if kind == "amber" else "ĐẠT"
            fun = "LỖI" if kind == "red" else ("—" if kind == "amber" else "ĐẠT")
            res = {"green": "ĐẠT", "amber": "LỖI 1", "red": "LỖI 2"}[kind]
            note = {"green": "", "amber": "thiếu linh kiện R12", "red": "3V3 = 2.71 V"}[kind]
            t = time.strftime("%H:%M:%S", time.localtime(time.time() - k * 13))
            sample.append((f"#{n:04d}", t, vis, fun, res, f"{12 + (k % 5) * 0.3:.1f} s", note, kind))
        for i, (pid, t, vis, fun, res, cyc, note, kind) in enumerate(sample):
            r = ctk.CTkFrame(table, fg_color=PANEL if i % 2 == 0 else "#f8fafc", corner_radius=6)
            r.pack(fill="x")
            vals = (pid, t, vis, fun, None, cyc, note)
            for (name, wdt), val in zip(cols, vals):
                if val is None:
                    holder = ctk.CTkFrame(r, fg_color="transparent", width=wdt, height=26)
                    holder.pack(side="left", padx=8, pady=3)
                    holder.pack_propagate(False)
                    pill(holder, res, kind, font_size=10).pack(side="left")
                else:
                    color = RED if val == "LỖI" else (TEXT if wdt else DIM)
                    ctk.CTkLabel(r, text=val, font=(F, 11), text_color=color, width=wdt, anchor="w"
                                 ).pack(side="left", padx=8, pady=3, fill="x", expand=wdt == 0)
        return v

    # ============================================================
    # TAB CÀI ĐẶT
    # ============================================================
    def _build_settings_view(self):
        v = ctk.CTkFrame(self.content, fg_color="transparent")
        v.grid_columnconfigure((0, 1, 2), weight=1, uniform="s")
        v.grid_rowconfigure(0, weight=1)

        def field(parent, label, value, unit=""):
            r = ctk.CTkFrame(parent, fg_color="transparent")
            r.pack(fill="x", pady=4)
            ctk.CTkLabel(r, text=label, font=(F, 12), text_color=TEXT, anchor="w").pack(side="left")
            if unit:
                ctk.CTkLabel(r, text=unit, font=(F, 11), text_color=DIM, width=30, anchor="w").pack(side="right")
            e = ctk.CTkEntry(r, width=150, height=30, corner_radius=8, fg_color=INPUT, border_color=BORDER,
                             text_color=TEXT, font=(F, 12))
            e.insert(0, value)
            e.pack(side="right", padx=(0, 4))

        def section(parent, title):
            ctk.CTkLabel(parent, text=title, font=(FB, 11), text_color=DIM, anchor="w").pack(fill="x", pady=(10, 0))

        conn = Card(v, "Kết nối thiết bị", "🔌")
        conn.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        section(conn.body, "PLC (Modbus TCP)")
        field(conn.body, "Địa chỉ IP", "192.168.0.10")
        field(conn.body, "Cổng", "502")
        section(conn.body, "Raspberry Pi (TCP)")
        field(conn.body, "Địa chỉ IP", "192.168.0.20")
        field(conn.body, "Cổng", "5000")
        section(conn.body, "Robot SCARA (UART)")
        r = ctk.CTkFrame(conn.body, fg_color="transparent")
        r.pack(fill="x", pady=4)
        ctk.CTkLabel(r, text="Cổng COM", font=(F, 12), text_color=TEXT).pack(side="left")
        ctk.CTkOptionMenu(r, values=["COM5", "COM3", "COM7"], width=150, height=30, corner_radius=8,
                          fg_color=INPUT, button_color=BTN_SOFT, button_hover_color=BTN_SOFT_HOVER,
                          text_color=TEXT, font=(F, 12)).pack(side="right", padx=(0, 34))

        to = Card(v, "Thời gian chờ (timeout)", "⏱")
        to.grid(row=0, column=1, sticky="nsew", padx=6)
        for label, val in (("Chờ cảm biến CB1", "10"), ("Chờ xi lanh S1 / S2", "3"), ("Chờ kết quả camera", "5"),
                           ("Chờ test chức năng", "20"), ("Chờ cảm biến CB3", "10"), ("Chờ robot phân loại", "30")):
            field(to.body, label, val, "s")
        ctk.CTkLabel(to.body, text="Quá thời gian → hệ thống báo lỗi, dừng, chờ Reset (nhánh B của lưu đồ).",
                     font=(F, 10), text_color=DISABLED, wraplength=320, justify="left").pack(anchor="w", pady=(8, 0))

        oth = Card(v, "Khác", "🗂")
        oth.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        field(oth.body, "Thư mục lưu lịch sử", "data/history")
        field(oth.body, "Tên ca làm việc", "Ca chiều")
        for text in ("Tự lưu ảnh PCB lỗi", "Phát âm báo khi có lỗi", "Tự kết nối khi mở app"):
            sw = ctk.CTkSwitch(oth.body, text=text, font=(F, 12), text_color=TEXT, progress_color=ACCENT)
            sw.select()
            sw.pack(anchor="w", pady=5)
        ctk.CTkButton(oth.body, text="💾  Lưu cài đặt", height=38, corner_radius=10, font=(FB, 13), fg_color=ACCENT,
                      hover_color=ACCENT_HOVER, command=lambda: self.log("Lưu cài đặt (demo)", "OK")
                      ).pack(fill="x", side="bottom")
        return v

    # ============================================================
    # LOG
    # ============================================================
    def _build_log(self):
        frame = ctk.CTkFrame(self, fg_color=PANEL, border_color=BORDER, border_width=1, corner_radius=14, height=118)
        frame.grid(row=2, column=0, sticky="ew", padx=16, pady=12)
        frame.grid_propagate(False)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(frame, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=14, pady=(8, 0))
        ctk.CTkLabel(head, text="📜  Log", font=(FB, 12), text_color=TEXT).pack(side="left")
        ctk.CTkButton(head, text="Xóa", width=56, height=24, corner_radius=8, font=(F, 11), fg_color=BTN_SOFT,
                      hover_color=BTN_SOFT_HOVER, text_color=TEXT,
                      command=lambda: self.log_box.delete("1.0", "end")).pack(side="right")
        self.log_box = ctk.CTkTextbox(frame, fg_color=INPUT, text_color=TEXT, corner_radius=8,
                                      font=("Consolas", 11), wrap="none")
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=14, pady=(4, 10))
        for lvl, col in LOG_COLOR.items():
            self.log_box.tag_config(lvl, foreground=col)

    def log(self, msg, level="INFO"):
        self.log_box.insert("end", f"{datetime.now():%H:%M:%S}  ")
        self.log_box.insert("end", f"[{level:<5}] ", level)
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")


if __name__ == "__main__":
    MasterDemo().mainloop()
