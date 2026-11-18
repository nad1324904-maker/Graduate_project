"""
master_app.py — App MASTER (PC) của hệ thống kiểm tra & phân loại PCB: app DUY NHẤT của đồ án (chạy: python main.py).

Tab:  Vận hành (AUTO / MANUAL, sơ đồ dây chuyền, PCB hiện tại, thống kê) | Robot (nguyên giao diện điều khiển robot,
      ui/robot_panel.py) | Lịch sử | Cài đặt.
Hiện trạng:
  - Robot: THẬT (kết nối STM32 ở tab Cài đặt → Kết nối thiết bị → Robot SCARA).
  - Raspberry Pi: THẬT (TCP, comm/pi_link.py; kết nối ở tab Cài đặt; MANUAL: Chụp ảnh / Kiểm tra PCB / Test chức năng).
  - PLC, chế độ AUTO, thống kê, lịch sử: dữ liệu mẫu, các nút chỉ ghi Log (hoặc giả lập phản hồi).

Một app duy nhất mở cổng COM của STM32 → phần tự động của master gọi thẳng self.robot.backend / self.robot.executor.
"""

import io
import os
import time
import tkinter as tk
from datetime import datetime

import customtkinter as ctk
from PIL import Image, ImageTk

from comm.pi_link import DEFAULT_HOST as PI_HOST, DEFAULT_PORT as PI_PORT, RESULTS as PI_RESULTS, PiClient
from comm.uart_backend import list_available_ports
from core.paths import ROOT_DIR
from ui.robot_panel import ScaraRobotPanel   # import cả ui/theme.py: màu mặc định widget dùng chung với tab Robot

# ============================================================
# Bảng màu (giống ui/theme.py, bản LIGHT)
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
LOG_COLOR = {"INFO": ACCENT, "OK": GREEN, "WARN": AMBER, "ERROR": RED, "TX": DIM, "RX": "#7c3aed"}
PI_RESULT = {"PASS": ("ĐẠT", "green"), "FAIL1": ("LỖI 1", "amber"), "FAIL2": ("LỖI 2", "red")}   # kết quả Pi -> loại PCB

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

F = "Segoe UI"
FB = "Segoe UI Semibold"
LOGO_FILE = os.path.join(ROOT_DIR, "assets", "logo_iuh.png")


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
class MasterApp(ctk.CTk):
    TABS = (("operate", "🏭", "Vận hành"), ("robot", "🤖", "Robot"),
            ("history", "📋", "Lịch sử"), ("settings", "⚙", "Cài đặt"))

    def __init__(self):
        super().__init__(fg_color=BG)
        self.title("PCB Inspection & Sorting — Master")
        self.geometry("1480x800")
        self.minsize(1280, 720)
        try:
            self.state("zoomed")              # Windows: mở toàn màn hình (vẫn còn thanh tiêu đề)
        except tk.TclError:
            pass
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        # Xi lanh KHÔNG có cảm biến hành trình, luôn chạy hết hành trình: "đã hạ / đã thu" do PLC tính bằng timer
        # (thời gian hành trình) và báo qua bit trạng thái. True = đã hạ, False = đã thu.
        self.cyl_down = {"Xi lanh 1": True, "Xi lanh 2": True}
        # Raspberry Pi: kết nối THẬT (TCP, giao thức JSON có độ dài — comm/pi_link.py)
        self.pi = PiClient(log=lambda lvl, msg: self.log(f"Pi: {msg}", lvl))
        self.pi.set_state_callback(self._on_pi_state)

        self._build_header()
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=1, column=0, sticky="nsew", padx=16, pady=(12, 0))
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        self._build_log()
        self.views = {
            "operate": self._build_operate_view(),
            "robot": self._build_robot_view(),
            "history": self._build_history_view(),
            "settings": self._build_settings_view(),
        }
        self._show_tab("operate")
        self._tick_clock()
        self._poll_devices()

        self.log("Khởi động app master. Robot và Raspberry Pi: kết nối thật ở tab Cài đặt; PLC: dữ liệu mẫu.")

    # ---------------- HEADER ----------------
    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color=HEADER, height=76, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)

        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left", padx=(16, 0), pady=12)
        try:                                      # logo trường (UI/assets/logo_iuh.png); thiếu file thì dùng icon cũ
            img = Image.open(LOGO_FILE)
            h = 46
            self._logo = ctk.CTkImage(light_image=img, size=(round(img.width * h / img.height), h))
            ctk.CTkLabel(left, text="", image=self._logo).pack(side="left")
        except OSError:
            ctk.CTkLabel(left, text="🏭", font=(F, 26)).pack(side="left")
        box = ctk.CTkFrame(left, fg_color="transparent")
        box.pack(side="left", padx=(14, 0))
        ctk.CTkLabel(box, text="CDT09-KHÓA LUẬN TỐT NGHIỆP IUH K18", font=(FB, 16), text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(box, text="Master PC — PLC · Raspberry Pi · SCARA robot",
                     font=(F, 11), text_color=DIM).pack(anchor="w")

        right = ctk.CTkFrame(header, fg_color="transparent")
        right.pack(side="right", padx=(0, 16), pady=12)
        self.clock = HeaderBadge(right, "🕐", "", "--:--:--")
        self.clock.pack(side="right", padx=(16, 0))
        self.sys_badge = HeaderBadge(right, "●", "Hệ thống", "AUTO · ĐANG CHẠY", ACCENT)
        self.sys_badge.pack(side="right", padx=(16, 0))
        HeaderBadge(right, "⏱", "Chu kỳ gần nhất", "12.4 s").pack(side="right", padx=(16, 0))

        # trạng thái các slave: luôn thấy ở mọi tab (Connect / Disconnect nằm ở tab Cài đặt)
        dev = ctk.CTkFrame(right, fg_color="transparent")
        dev.pack(side="right", padx=(16, 0))
        ctk.CTkLabel(dev, text="🔌 Thiết bị", font=(F, 11), text_color=DIM).pack(anchor="w")
        row = ctk.CTkFrame(dev, fg_color="transparent")
        row.pack(anchor="w")
        self.dev_dots = {}                        # Pi, Robot: theo kết nối thật (_poll_devices); PLC: mẫu
        for name, kind in (("PLC", "green"), ("Pi", "gray"), ("Robot", "gray")):
            dot = ctk.CTkLabel(row, text="●", font=(F, 12), text_color=PILL[kind][1] if kind != "gray" else DISABLED)
            dot.pack(side="left")
            ctk.CTkLabel(row, text=name, font=(FB, 12), text_color=TEXT).pack(side="left", padx=(3, 10))
            self.dev_dots[name] = dot

        bar = ctk.CTkFrame(right, fg_color=BTN_SOFT, corner_radius=10)
        bar.pack(side="right", padx=(16, 0))
        self.tab_buttons = {}
        for key, icon, label in self.TABS:
            b = ctk.CTkButton(bar, text=f"{icon}  {label}", width=100, height=36, corner_radius=8,
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

    def _poll_devices(self):
        """Mỗi 50 ms: nhận kết quả từ Raspberry Pi (luồng nền) + cập nhật đèn Pi / Robot trên header."""
        self.pi.poll()
        self.dev_dots["Pi"].configure(text_color=GREEN if self.pi.connected else DISABLED)
        self.dev_dots["Robot"].configure(text_color=GREEN if self.robot._connected() else DISABLED)
        self.after(50, self._poll_devices)

    # ============================================================
    # TAB VẬN HÀNH
    # ============================================================
    def _build_operate_view(self):
        v = ctk.CTkFrame(self.content, fg_color="transparent")
        v.grid_columnconfigure(0, weight=0, minsize=290)
        v.grid_columnconfigure(1, weight=1)
        v.grid_columnconfigure(2, weight=0, minsize=300)
        v.grid_rowconfigure(0, weight=1)

        # ---- cột trái: điều khiển (AUTO / MANUAL) ----
        left = ctk.CTkFrame(v, fg_color="transparent", width=290)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self._build_control_card(left).pack(fill="both", expand=True)

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

        self.mode_seg = ctk.CTkSegmentedButton(
            b, values=["AUTO", "MANUAL"], height=32, font=(FB, 12), command=self._on_mode,
            fg_color=BTN_SOFT, selected_color=ACCENT_SOFT, selected_hover_color="#bfdbfe",
            unselected_color=BTN_SOFT, unselected_hover_color=BTN_SOFT_HOVER, text_color=ACCENT_TEXT)
        self.mode_seg.set("AUTO")
        self.mode_seg.pack(fill="x", pady=(0, 6))

        # kết quả kiểm tra trong chế độ MANUAL (để biết robot phải chạy chương trình nào)
        self._m_result = None                     # "ĐẠT" / "LỖI 1" / "LỖI 2" theo kết quả inspect của Pi
        self._cam_demo = 0
        self._fun_demo = 0
        self.auto_panel = self._build_auto_panel(b)
        self.manual_panel = self._build_manual_panel(b)
        self.auto_panel.pack(fill="x")
        return c

    @staticmethod
    def _section(parent, text):
        ctk.CTkLabel(parent, text=text, font=(FB, 11), text_color=DIM, anchor="w", height=22
                     ).pack(fill="x", pady=(5, 0))

    @staticmethod
    def _pair(parent):
        """Hàng 2 nút rộng bằng nhau."""
        r = ctk.CTkFrame(parent, fg_color="transparent")
        r.pack(fill="x", pady=2)
        r.grid_columnconfigure((0, 1), weight=1, uniform="p")
        return r

    @staticmethod
    def _btn(parent, text, cmd, color=BTN_SOFT, hover=BTN_SOFT_HOVER, h=34, size=12):
        return ctk.CTkButton(parent, text=text, height=h, corner_radius=10, font=(FB, size),
                             fg_color=color, hover_color=hover, command=cmd)

    # ---------------- AUTO ----------------
    def _build_auto_panel(self, parent):
        p = ctk.CTkFrame(parent, fg_color="transparent")
        self._btn(p, "▶  START", lambda: self.log("START (demo)"), GREEN, GREEN_HOVER, h=44, size=15
                  ).pack(fill="x", pady=(2, 0))
        r = self._pair(p)
        self._btn(r, "■  STOP", lambda: self.log("STOP (demo)", "WARN"), RED, RED_HOVER, h=38, size=13
                  ).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        self._btn(r, "⟳  RESET", lambda: self.log("RESET (demo)"), GRAY_BTN, GRAY_BTN_HOVER, h=38, size=13
                  ).grid(row=0, column=1, sticky="ew", padx=(3, 0))

        self._section(p, "Nút trên tủ điện (PLC đọc)")
        r = ctk.CTkFrame(p, fg_color="transparent")
        r.pack(fill="x")
        for name in ("START", "STOP", "RESET"):
            pill(r, "○ " + name, "gray", font_size=10).pack(side="left", padx=(0, 6))
        r = ctk.CTkFrame(p, fg_color="transparent")
        r.pack(fill="x", pady=(6, 0))
        ctk.CTkLabel(r, text="Đèn tháp", font=(F, 12), text_color=TEXT).pack(side="left")
        ctk.CTkLabel(r, text="● XANH — đang chạy", font=(FB, 12), text_color=GREEN).pack(side="right")

        ctk.CTkLabel(p, text="Nút trên tủ điện và nút trên app có cùng tác dụng. STOP: dừng sau khi xong PCB "
                              "hiện tại. E-Stop chỉ dùng nút cứng. Chỉ đổi sang MANUAL khi hệ thống đã dừng.",
                     font=(F, 10), text_color=DISABLED, wraplength=255, justify="left").pack(anchor="w", pady=(10, 0))
        return p

    # ---------------- MANUAL ----------------
    def _build_manual_panel(self, parent):
        p = ctk.CTkFrame(parent, fg_color="transparent")

        # ---- PLC: băng tải, động cơ bước cấp PCB, 2 xi lanh (test chức năng = PLC hạ xi lanh 2 cấp nguồn cho PCB) ----
        self._section(p, "PLC — băng tải & xi lanh")
        self.belt_btn = self._btn(p, "⏵  Giữ để chạy băng tải", None, ACCENT, ACCENT_HOVER, h=36)
        self.belt_btn.pack(fill="x", pady=2)
        self.belt_btn.bind("<ButtonPress-1>", lambda e: self._belt(True), add="+")
        self.belt_btn.bind("<ButtonRelease-1>", lambda e: self._belt(False), add="+")
        r = self._pair(p)
        self._btn(r, "⇥  Cấp 1 PCB", lambda: self.log("Động cơ bước: cấp 1 PCB lên băng tải (demo)")
                  ).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        self._btn(r, "⏹  Dừng tất cả", lambda: self.log("MANUAL: dừng băng tải, động cơ bước, robot (demo)", "WARN"),
                  RED, RED_HOVER).grid(row=0, column=1, sticky="ew", padx=(3, 0))

        self.cyl_state, self.cyl_seg = {}, {}
        for name, role in (("Xi lanh 1", "chặn PCB"), ("Xi lanh 2", "cấp nguồn PCB")):
            r = ctk.CTkFrame(p, fg_color="transparent")
            r.pack(fill="x", pady=2)
            box = ctk.CTkFrame(r, fg_color="transparent")
            box.pack(side="left")
            ctk.CTkLabel(box, text=f"{name} · {role}", font=(FB, 12), text_color=TEXT, height=16).pack(anchor="w")
            low = self.cyl_down[name]
            st = ctk.CTkLabel(box, text="● đã hạ" if low else "● đã thu", font=(F, 10),
                              text_color=ACCENT if low else DIM, height=14)
            st.pack(anchor="w")
            self.cyl_state[name] = st
            seg = ctk.CTkSegmentedButton(
                r, values=["▲ Thu", "▼ Hạ"], width=140, height=30, font=(FB, 11),
                command=lambda v, n=name: self._cylinder(n, v),
                fg_color=BTN_SOFT, selected_color=ACCENT_SOFT, selected_hover_color="#bfdbfe",
                unselected_color=BTN_SOFT, unselected_hover_color=BTN_SOFT_HOVER, text_color=ACCENT_TEXT)
            seg.set("▼ Hạ" if low else "▲ Thu")
            seg.pack(side="right")
            self.cyl_seg[name] = seg
        self._btn(p, "🔌  Test chức năng (hạ xi lanh 2 cấp nguồn)", self._func_test).pack(fill="x", pady=2)

        self._section(p, "Raspberry Pi (xử lý ảnh)")
        r = self._pair(p)
        self._btn(r, "📷  Chụp ảnh", self._capture).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        self._btn(r, "🔍  Kiểm tra PCB", self._inspect).grid(row=0, column=1, sticky="ew", padx=(3, 0))

        self._section(p, "Robot")
        r = ctk.CTkFrame(p, fg_color="transparent")
        r.pack(fill="x", pady=2)
        ctk.CTkLabel(r, text="Loại PCB", font=(F, 12), text_color=TEXT).pack(side="left")
        ctk.CTkButton(r, text="✕", width=26, height=24, corner_radius=8, font=(F, 11), fg_color=BTN_SOFT,
                      hover_color=BTN_SOFT_HOVER, command=self._clear_manual_result).pack(side="right")
        self.type_pill = pill(r, "CHƯA XÁC ĐỊNH", "gray", font_size=10)
        self.type_pill.pack(side="right", padx=(0, 6))
        r = self._pair(p)
        self._btn(r, "🤖  Robot phân loại", self._robot_sort, ACCENT, ACCENT_HOVER
                  ).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        self._btn(r, "⌂  Robot về Home", lambda: self.log("Robot: về vị trí Home (demo)")
                  ).grid(row=0, column=1, sticky="ew", padx=(3, 0))
        return p

    def _on_mode(self, mode):
        if mode == "AUTO":
            self.manual_panel.pack_forget()
            self.auto_panel.pack(fill="x")
            self.sys_badge.value.configure(text="AUTO · ĐANG CHẠY", text_color=ACCENT)
        else:
            self.auto_panel.pack_forget()
            self.manual_panel.pack(fill="x")
            self.sys_badge.value.configure(text="MANUAL", text_color=AMBER)
        self.log(f"Chuyển sang chế độ {mode}.")

    # ---------------- hành vi mô phỏng (DEMO) của chế độ MANUAL ----------------
    def _belt(self, on):
        """Giữ nút = băng tải chạy, thả nút = dừng (an toàn hơn nút bật/tắt)."""
        self.belt_btn.configure(fg_color=GREEN if on else ACCENT,
                                text="⏵  Băng tải đang chạy..." if on else "⏵  Giữ để chạy băng tải")
        self.log("Băng tải: CHẠY (đang giữ nút)" if on else "Băng tải: DỪNG (đã thả nút)", "INFO" if on else "OK")

    def _cylinder(self, name, value, on_done=None):
        """Xi lanh không có cảm biến hành trình: PLC đổi van rồi đếm timer thời gian hành trình; hết timer thì bật bit
        'đã hạ' / 'đã thu' cho PC đọc (giả lập: 0.5 s)."""
        down = value.startswith("▼")
        self.cyl_seg[name].set("▼ Hạ" if down else "▲ Thu")
        self.log(f"{name}: gửi lệnh {'HẠ' if down else 'THU'} cho PLC...")
        self.cyl_state[name].configure(text="● đang chạy hết hành trình...", text_color=AMBER)

        def done():
            self.cyl_state[name].configure(text="● đã hạ" if down else "● đã thu",
                                           text_color=ACCENT if down else DIM)
            self.cyl_down[name] = down
            self._draw_line()
            self.log(f"{name}: PLC báo đã {'hạ' if down else 'thu'} xong (hết timer hành trình).", "OK")
            if on_done:
                on_done()
        self.after(500, done)

    # ---------------- Raspberry Pi (THẬT, qua comm/pi_link.py) ----------------
    def _pi_ready(self, action):
        if not self.pi.connected:
            self.log(f"{action}: chưa kết nối Raspberry Pi (tab Cài đặt → Kết nối thiết bị → Raspberry Pi).", "WARN")
            return False
        if self.pi.busy():
            self.log(f"{action}: Raspberry Pi đang xử lý lệnh trước — đợi xong rồi bấm lại.", "WARN")
            return False
        return True

    def _capture(self):
        """Lệnh capture: Pi chụp và gửi ảnh JPEG về, hiện ở thẻ PCB hiện tại."""
        if not self._pi_ready("Chụp ảnh"):
            return
        self._set_pcb_row("img", "ĐANG CHỤP", "blue")

        def done(reply, img, rtt, err):
            if err or not reply or reply.get("status") != "ok" or not img:
                why = err or (reply or {}).get("message", "không có ảnh")
                self._set_pcb_row("img", "LỖI", "red", f"capture thất bại: {why}")
                self.log(f"Pi: chụp ảnh thất bại — {why}", "ERROR")
                return
            pil = self._show_camera_image(img)
            if pil:
                self._set_pcb_row("img", "OK", "green", f"{pil.width}×{pil.height} · {len(img) / 1024:.0f} KB · "
                                                        f"{rtt:.0f} ms")
                self.log(f"Pi: nhận ảnh {pil.width}×{pil.height} ({len(img) / 1024:.0f} KB) sau {rtt:.0f} ms.", "OK")
        self.pi.request("capture", done)

    def _inspect(self, on_done=None):
        """Lệnh inspect: Pi kiểm tra PCB và trả PASS / FAIL1 / FAIL2 (+ process_time_ms, có thể kèm ảnh)."""
        if not self._pi_ready("Kiểm tra PCB"):
            return
        self._set_pcb_row("pi", "ĐANG KIỂM TRA", "blue", "Pi đang xử lý ảnh...")
        self.conclusion.configure(text="— đang kiểm tra —", text_color=DIM)

        def done(reply, img, rtt, err):
            code = (reply or {}).get("result")
            if err or reply.get("status") != "ok" or code not in PI_RESULTS:
                why = err or reply.get("message") or f"phản hồi không hợp lệ (result={code!r})"
                self._set_pcb_row("pi", "LỖI", "red", str(why))
                self.conclusion.configure(text="— lỗi kiểm tra —", text_color=RED)
                self.log(f"Pi: kiểm tra PCB thất bại — {why}", "ERROR")
                return
            text, kind = PI_RESULT[code]
            pt = reply.get("process_time_ms")
            extra = {k: v for k, v in reply.items()
                     if k not in ("id", "cmd", "status", "result", "process_time_ms", "image_size")}
            note = (f"{code} · Pi xử lý {pt:.0f} ms" if isinstance(pt, (int, float)) else code) + f" · tổng {rtt:.0f} ms"
            if extra:
                note += " · " + ", ".join(f"{k}={v}" for k, v in extra.items())
            self._set_pcb_row("pi", text, kind, note)
            if img:
                pil = self._show_camera_image(img)
                if pil:
                    self._set_pcb_row("img", "OK", "green", f"ảnh Pi dùng để kết luận · {pil.width}×{pil.height}")
            self._m_result = text
            self._refresh_type()
            self.log(f"Pi: kết quả kiểm tra {code} → PCB {text} ({note}).", "OK" if code == "PASS" else "WARN")
            if on_done:
                on_done(code)
        self.pi.request("inspect", done)

    def _func_test(self):
        """Test chức năng (theo lưu đồ): PC ghi lệnh → PLC hạ xi lanh 2, 2 đầu kim cấp nguồn cho PCB qua domino →
        PLC báo xi lanh 2 đã hạ (hết timer hành trình) → PC gửi inspect cho Raspberry Pi (camera xem LED 7 đoạn
        đếm 1 → 9 + kiểm tra linh kiện) → PASS / FAIL1 / FAIL2. Phần PLC vẫn là giả lập; phần Pi là THẬT."""
        if not self._pi_ready("Test chức năng"):
            return
        self.log("Test chức năng: PLC hạ xi lanh 2 để cấp nguồn cho PCB.")
        self._cylinder("Xi lanh 2", "▼ Hạ", on_done=self._inspect)

    def _on_pi_state(self, connected, message):
        """PiClient báo đổi trạng thái kết nối (Connect / Disconnect / mất kết nối)."""
        self.log(f"Pi: {message}", "OK" if connected else ("INFO" if "Đã ngắt" in message else "ERROR"))
        self._refresh_pi_ui()

    def _pcb_type(self):
        return self._m_result

    def _refresh_type(self):
        t = self._pcb_type()
        text, kind = ("CHƯA XÁC ĐỊNH", "gray") if t is None else (t, {"ĐẠT": "green", "LỖI 1": "amber", "LỖI 2": "red"}[t])
        bg, fg = PILL[kind]
        self.type_pill.configure(text=text, fg_color=bg, text_color=fg)
        if t is None:
            self.conclusion.configure(text="— chưa kiểm tra —", text_color=DIM)
            self._set_pcb_row("robot", "CHỜ", "gray", "sẽ chạy chương trình theo kết quả")
        else:
            self.conclusion.configure(text=f"PCB {t}", text_color={"green": GREEN, "amber": AMBER, "red": RED}[kind])
            prog = {"ĐẠT": "Chương trình 1", "LỖI 2": "Chương trình 2", "LỖI 1": "Chương trình 3"}[t]
            self._set_pcb_row("robot", "SẴN SÀNG", "blue", f"sẽ chạy {prog}")

    def _clear_manual_result(self):
        self._m_result = None
        self._set_pcb_row("pi", "CHƯA CÓ", "gray", "chưa có kết quả inspect")
        self._refresh_type()
        self.log("Đã xóa kết quả kiểm tra của PCB hiện tại.")

    def _robot_sort(self):
        t = self._pcb_type()
        if t is None:
            self.log("Chưa xác định được loại PCB (chưa Kiểm tra PCB / Test chức năng) — robot KHÔNG chạy.", "WARN")
            return
        prog = {"ĐẠT": "Chương trình 1", "LỖI 2": "Chương trình 2", "LỖI 1": "Chương trình 3"}[t]
        self.log(f"Gửi robot chạy {prog} (PCB {t})...")

        def done():
            self.log(f"Robot: {prog} xong (demo).", "OK")
            self._m_result = None
            self._refresh_type()
        self.after(1500, done)

    def _build_current_pcb_card(self, parent):
        c = Card(parent, "PCB hiện tại", "🔍")
        b = c.body
        b.grid_columnconfigure(0, weight=0)
        b.grid_columnconfigure(1, weight=1)
        self.cam_canvas = tk.Canvas(b, bg="#e2e8f0", highlightthickness=0, width=260, height=170)
        self.cam_canvas.grid(row=0, column=0, sticky="nsw", padx=(0, 14))
        self.cam_canvas.bind("<Configure>", lambda e: self._draw_camera())
        self._cam_jpeg = None                     # ảnh JPEG gần nhất Pi gửi về
        self._cam_photo = None                    # giữ tham chiếu để Tk không xóa ảnh

        info = ctk.CTkFrame(b, fg_color="transparent")
        info.grid(row=0, column=1, sticky="nsew")
        info.grid_columnconfigure(1, weight=1)
        self.pcb_rows = {}
        rows = (("pi", "Kiểm tra (Raspberry Pi)", "CHƯA CÓ", "gray", "chưa có kết quả inspect"),
                ("img", "Ảnh camera", "CHƯA CÓ", "gray", "bấm Chụp ảnh hoặc kiểm tra PCB"),
                ("robot", "Robot phân loại", "CHỜ", "gray", "sẽ chạy chương trình theo kết quả"))
        for i, (key, name, val, kind, note) in enumerate(rows):
            ctk.CTkLabel(info, text=name, font=(F, 12), text_color=DIM, anchor="w"
                         ).grid(row=i * 2, column=0, sticky="w", pady=(4 if i else 0, 0))
            p = pill(info, val, kind, width=96)
            p.grid(row=i * 2, column=1, sticky="e", pady=(4 if i else 0, 0))
            n = ctk.CTkLabel(info, text=note, font=(F, 10), text_color=DISABLED, anchor="w")
            n.grid(row=i * 2 + 1, column=0, columnspan=2, sticky="w")
            self.pcb_rows[key] = (p, n)
        res = ctk.CTkFrame(info, fg_color=INPUT, corner_radius=10)
        res.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ctk.CTkLabel(res, text="Kết luận", font=(F, 12), text_color=DIM).pack(side="left", padx=12, pady=8)
        self.conclusion = ctk.CTkLabel(res, text="— chưa kiểm tra —", font=(FB, 14), text_color=DIM)
        self.conclusion.pack(side="right", padx=12)
        return c

    def _set_pcb_row(self, key, text, kind, note=None):
        p, n = self.pcb_rows[key]
        bg, fg = PILL[kind]
        p.configure(text=text, fg_color=bg, text_color=fg)
        if note is not None:
            n.configure(text=note)

    def _show_camera_image(self, jpeg):
        try:
            img = Image.open(io.BytesIO(jpeg))
            img.load()
        except Exception as e:  # noqa: BLE001 - ảnh hỏng: chỉ báo Log
            self.log(f"Pi: không giải mã được ảnh ({len(jpeg)} byte): {e}", "ERROR")
            return None
        self._cam_jpeg = img
        self._draw_camera()
        return img

    def _draw_camera(self):
        cv = self.cam_canvas
        if self._cam_jpeg is None:
            self._draw_camera_placeholder(cv)
            return
        cv.delete("all")
        w, h = max(cv.winfo_width(), 50), max(cv.winfo_height(), 50)
        img = self._cam_jpeg
        s = min(w / img.width, h / img.height)
        self._cam_photo = ImageTk.PhotoImage(img.resize((max(1, int(img.width * s)), max(1, int(img.height * s)))))
        cv.create_image(w / 2, h / 2, image=self._cam_photo)

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
        steps = ("Cấp PCB (động cơ bước)", "Băng tải chạy, chờ CB1", "Xi lanh 1 chặn PCB, chụp ảnh",
                 "Xi lanh 2 cấp nguồn, đếm LED 1 → 9", "Thu 2 xi lanh, chạy tới CB3", "Robot gắp & phân loại", "Hoàn tất, cộng thống kê")
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
    def _draw_cylinder(self, cv, xc, body_top, tip_y, lowered, label, label_anchor, label_x, probes):
        """1 xi lanh nhìn từ bên cạnh: thân + ty. lowered = đã hạ / đã thu (hết hành trình, không có cảm biến).
        probes=True: đầu ty mang 2 đầu kim cấp nguồn; False: đầu ty là thanh chặn PCB."""
        body_bot = body_top + 28
        active = ACCENT if lowered else "#94a3b8"
        cv.create_text(label_x, body_top - 8, anchor=label_anchor, font=(FB, 9),
                       text=f"{label}  {'HẠ ▼' if lowered else 'THU ▲'}", fill=ACCENT_TEXT if lowered else DIM)
        # ty (đầu ty hạ xuống tip_y khi lowered, thu ngắn khi đã thu)
        rod_end = (tip_y - (8 if probes else 0)) if lowered else body_bot + 12
        cv.create_rectangle(xc - 3, body_bot, xc + 3, rod_end, fill="#94a3b8", outline="#64748b")
        if probes:
            pin_len = 8
            cv.create_rectangle(xc - 9, rod_end, xc + 9, rod_end + 4, fill="#475569", outline="")
            for dx in (-5, 5):
                cv.create_line(xc + dx, rod_end + 4, xc + dx, rod_end + 4 + pin_len, fill=AMBER, width=2)
            if lowered:
                cv.create_text(xc, rod_end - 12, text="⚡", font=(F, 10), fill=AMBER)
        else:
            cv.create_rectangle(xc - 4, rod_end - 14 if lowered else rod_end - 2, xc + 4, rod_end + 2,
                                fill="#475569", outline="")
        # thân xi lanh (vẽ sau để che đoạn ty bên trong)
        cv.create_rectangle(xc - 11, body_top, xc + 11, body_bot, fill=ACCENT_SOFT if lowered else BTN_SOFT,
                            outline=active, width=2)
        cv.create_line(xc - 11, body_top + 7, xc + 11, body_top + 7, fill=active)

    def _draw_line(self):
        """Sơ đồ dây chuyền (dữ liệu mẫu): cấp PCB → băng tải → trạm kiểm tra (CB2, camera, xi lanh 1 + 2)
        → CB3 → robot → 3 khay. Xi lanh lấy trạng thái từ self.cyl_down (đổi được ở chế độ MANUAL)."""
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
        cv.create_text(x0 + 6, y - bt - 12, anchor="w", text="Băng tải · DỪNG", fill=AMBER_TEXT, font=(FB, 10))

        # khay cấp PCB
        fx = max(w * 0.05, 56)
        for k in range(5):
            cv.create_rectangle(fx - 26, y - 36 - k * 7, fx + 26, y - 30 - k * 7, fill="#4ade80", outline="#15803d")
        cv.create_rectangle(fx - 32, y - 30, fx + 32, y + bt, fill="", outline="#94a3b8", width=2)
        cv.create_text(fx, y + bt + 14, text="Cấp PCB · 23 tấm", fill=DIM, font=(F, 10))

        # cảm biến CB1/CB2/CB3 — đặt DƯỚI băng tải để phía trên dành cho xi lanh + camera
        cx = x0 + (x1 - x0) * 0.50                # trạm kiểm tra (CB2)
        sensors = (("CB1", x0 + (x1 - x0) * 0.12, False), ("CB2", cx, True), ("CB3", x0 + (x1 - x0) * 0.93, False))
        for name, sx, on in sensors:
            cv.create_line(sx, y + bt + 2, sx, y + bt + 14, fill="#94a3b8", width=2)
            cv.create_oval(sx - 7, y + bt + 14, sx + 7, y + bt + 28, fill=GREEN if on else "#e2e8f0",
                           outline=GREEN_HOVER if on else "#94a3b8", width=1.5)
            cv.create_text(sx, y + bt + 38, text=name, fill=TEXT if on else DIM, font=(FB, 10))
        cv.create_text(cx, y + bt + 56, text="#0128 đang test chức năng", fill=AMBER_TEXT, font=(F, 9))

        # PCB đang chờ ở CB1→CB2 (nhỏ) và PCB đang kiểm tra ở trạm (to hơn: có domino + LED 7 đoạn)
        px = x0 + (x1 - x0) * 0.27
        cv.create_rectangle(px - 20, y - 10, px + 20, y + 10, fill="#4ade80", outline="#15803d", width=2)
        cv.create_rectangle(cx - 28, y - 10, cx + 28, y + 10, fill="#fde68a", outline=AMBER, width=2)
        cv.create_rectangle(cx - 27, y - 7, cx - 17, y + 7, fill="#1e293b", outline="")          # domino (cấp nguồn)
        for dy in (-3, 3):
            cv.create_oval(cx - 24, y + dy - 1.5, cx - 20, y + dy + 2.5, fill="#94a3b8", outline="")
        cv.create_rectangle(cx + 4, y - 6, cx + 20, y + 6, fill="#1e293b", outline="")           # LED 7 đoạn
        cv.create_text(cx + 12, y, text="7", fill="#f87171", font=("Consolas", 9, "bold"))

        # trạm kiểm tra: camera ở trên, xi lanh 2 (2 đầu kim) phía domino, xi lanh 1 (chặn) phía trước PCB
        cv.create_rectangle(cx - 36, 4, cx + 36, 24, fill=ACCENT_SOFT, outline=ACCENT)
        cv.create_text(cx, 14, text="📷 Camera", fill=ACCENT_TEXT, font=(FB, 10))
        cv.create_line(cx + 4, 24, cx + 4, y - 12, fill=ACCENT, dash=(3, 3))                      # trục quang camera
        tip_y = y - 10                                                                            # mặt trên PCB
        self._draw_cylinder(cv, cx - 22, 44, tip_y, self.cyl_down["Xi lanh 2"], "XL2 · cấp nguồn", "e", cx - 4, True)
        self._draw_cylinder(cv, cx + 34, 44, y + 10, self.cyl_down["Xi lanh 1"], "XL1 · chặn PCB", "w", cx + 14, False)

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
            cv.create_text(bx, by + bh * 0.27, text=name, fill=col, font=(FB, 10))
            cv.create_text(bx, by + bh * 0.75, text=n, fill=TEXT, font=(FB, 11))

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
        """Tab Robot = NGUYÊN GUI điều khiển robot (Vận hành / Lập trình / Giám sát / Settings), nhúng vào đây.
        Log của robot ghi chung vào Log của master (có tiền tố "Robot:")."""
        v = ctk.CTkFrame(self.content, fg_color="transparent")
        self.robot = ScaraRobotPanel(v, embedded=True, log_sink=lambda msg, lvl: self.log(f"Robot: {msg}", lvl))
        self.robot.pack(fill="both", expand=True)
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
            note = {"green": "", "amber": "thiếu linh kiện R12", "red": "LED 7 đoạn dừng ở số 4"}[kind]
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

        def slave_header(parent, title, state, kind, connected):
            """Tiêu đề 1 slave: tên + trạng thái + nút Connect / Disconnect riêng."""
            r = ctk.CTkFrame(parent, fg_color="transparent")
            r.pack(fill="x", pady=(12, 2))
            ctk.CTkLabel(r, text=title, font=(FB, 12), text_color=TEXT, anchor="w").pack(side="left")
            pill(r, state, kind, font_size=10).pack(side="left", padx=(8, 0))
            if connected:
                btn = dict(text="Disconnect", fg_color=BTN_SOFT, hover_color=BTN_SOFT_HOVER)
            else:
                btn = dict(text="Connect", fg_color=ACCENT, hover_color=ACCENT_HOVER)
            ctk.CTkButton(r, width=96, height=28, corner_radius=8, font=(FB, 11),
                          command=lambda: self.log(f"{btn['text']} {title} (demo)"), **btn).pack(side="right")

        def choice(parent, label, values, value, refresh=None):
            """Ô chọn (cổng COM, baud...) thẳng cột với khối Robot SCARA; refresh: nút ⟳ quét lại cổng COM."""
            r = ctk.CTkFrame(parent, fg_color="transparent")
            r.pack(fill="x", pady=4)
            ctk.CTkLabel(r, text=label, font=(F, 12), text_color=TEXT).pack(side="left")
            if refresh:
                ctk.CTkButton(r, text="⟳", width=30, height=30, corner_radius=8, font=(F, 13), fg_color=BTN_SOFT,
                              hover_color=BTN_SOFT_HOVER, command=lambda: refresh(m)).pack(side="right")
            else:
                ctk.CTkFrame(r, fg_color="transparent", width=30, height=30).pack(side="right")
            m = ctk.CTkOptionMenu(r, values=values, width=150, height=30, corner_radius=8, fg_color=INPUT,
                                  button_color=BTN_SOFT, button_hover_color=BTN_SOFT_HOVER, text_color=TEXT,
                                  font=(F, 12))
            m.set(value)
            m.pack(side="right", padx=(0, 4))
            return m

        def refresh_plc_ports(menu):
            ports = list_available_ports() or ["(không có cổng)"]
            menu.configure(values=ports)
            menu.set(ports[0])
            self.log(f"PLC: đã quét lại cổng COM: {ports}")

        conn = Card(v, "Kết nối thiết bị", "🔌")
        conn.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        # PLC nối với PC qua RS422 (bộ chuyển USB–RS422 → 1 cổng COM, KHÁC cổng COM của robot)
        slave_header(conn.body, "PLC · RS422", "ONLINE", "green", True)
        ports = list_available_ports() or ["(không có cổng)"]
        self.plc_port_menu = choice(conn.body, "Cổng COM", ports, ports[0], refresh=refresh_plc_ports)
        self.plc_baud_menu = choice(conn.body, "Baud rate", ["9600", "19200", "38400", "57600", "115200"], "9600")
        self.plc_frame_menu = choice(conn.body, "Khung dữ liệu", ["8N1", "8E1", "8O1", "7E1", "7O1"], "8N1")
        self._build_pi_connection(conn.body)              # THẬT: TCP tới Raspberry Pi (comm/pi_link.py)
        self.robot.build_connection_section(conn.body)     # THẬT: cổng COM + Connect STM32 (ui/settings_tab/connection.py)
        ctk.CTkButton(conn.body, text="Connect tất cả", height=32, corner_radius=8, font=(FB, 12),
                      fg_color=BTN_SOFT, hover_color=BTN_SOFT_HOVER,
                      command=self._connect_all).pack(fill="x", pady=(14, 0))

        to = Card(v, "Thời gian chờ (timeout)", "⏱")
        to.grid(row=0, column=1, sticky="nsew", padx=6)
        for label, val in (("Chờ cảm biến CB1", "10"), ("Chờ xi lanh xong hành trình", "3"), ("Chờ ảnh camera (Pi)", "10"),
                           ("Chờ test chức năng", "20"), ("Chờ cảm biến CB3", "10"), ("Chờ robot phân loại", "30")):
            field(to.body, label, val, "s")
        ctk.CTkLabel(to.body, text="Quá thời gian → hệ thống báo lỗi, dừng, chờ Reset (nhánh B của lưu đồ).",
                     font=(F, 10), text_color=DISABLED, wraplength=320, justify="left").pack(anchor="w", pady=(8, 0))

        ctk.CTkButton(to.body, text="💾  Lưu cài đặt", height=38, corner_radius=10, font=(FB, 13), fg_color=ACCENT,
                      hover_color=ACCENT_HOVER, command=lambda: self.log("Lưu cài đặt (demo)", "OK")
                      ).pack(fill="x", side="bottom")

        pg = Card(v, "Quản lý chương trình robot", "📝")
        pg.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        # thư mục chứa chương trình (dùng chung với GUI robot)
        r = ctk.CTkFrame(pg.body, fg_color="transparent")
        r.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(r, text="Thư mục", font=(F, 12), text_color=TEXT).pack(side="left")
        ctk.CTkButton(r, text="📁", width=30, height=30, corner_radius=8, font=(F, 12), fg_color=BTN_SOFT,
                      hover_color=BTN_SOFT_HOVER, command=lambda: self.log("Chọn thư mục (demo)")).pack(side="right")
        e = ctk.CTkEntry(r, height=30, corner_radius=8, fg_color=INPUT, border_color=BORDER, text_color=TEXT, font=(F, 11))
        e.insert(0, "UI/data")
        e.pack(side="right", fill="x", expand=True, padx=(8, 4))

        # chương trình gán cho từng kết quả phân loại
        section(pg.body, "Gán chương trình theo kết quả")
        names = ["Chương trình 1", "Chương trình 2", "Chương trình 3", "TEST"]
        for res, kind, prog in (("PCB đạt", "green", "Chương trình 1"), ("Lỗi 1 — ngoại quan", "amber", "Chương trình 3"),
                                ("Lỗi 2 — chức năng", "red", "Chương trình 2")):
            r = ctk.CTkFrame(pg.body, fg_color="transparent")
            r.pack(fill="x", pady=3)
            pill(r, res, kind, width=140).pack(side="left")
            m = ctk.CTkOptionMenu(r, values=names, width=150, height=30, corner_radius=8, fg_color=INPUT,
                                  button_color=BTN_SOFT, button_hover_color=BTN_SOFT_HOVER, text_color=TEXT, font=(F, 12))
            m.set(prog)
            m.pack(side="right")

        # danh sách chương trình đang có
        section(pg.body, "Chương trình có trong thư mục")
        lst = ctk.CTkFrame(pg.body, fg_color=INPUT, corner_radius=10)
        lst.pack(fill="x", pady=(4, 0))
        for i, (name, steps, used) in enumerate((("Chương trình 1", 10, "đạt"), ("Chương trình 2", 10, "lỗi 2"),
                                                 ("Chương trình 3", 10, "lỗi 1"), ("TEST", 4, ""))):
            r = ctk.CTkFrame(lst, fg_color=ACCENT_SOFT if i == 0 else "transparent", corner_radius=8)
            r.pack(fill="x", padx=4, pady=(4 if i == 0 else 0, 4 if i == 3 else 0))
            ctk.CTkLabel(r, text=name, font=(FB, 12), text_color=ACCENT_TEXT if i == 0 else TEXT
                         ).pack(side="left", padx=8, pady=4)
            ctk.CTkLabel(r, text=f"{steps} step" + (f" · {used}" if used else " · chưa gán"), font=(F, 10),
                         text_color=DIM).pack(side="right", padx=8)
        btns = ctk.CTkFrame(pg.body, fg_color="transparent")
        btns.pack(fill="x", pady=(8, 0))
        btns.grid_columnconfigure((0, 1, 2), weight=1)
        for k, (text, col, hov) in enumerate((("⟳ Tải lại", BTN_SOFT, BTN_SOFT_HOVER),
                                               ("▶ Chạy thử", ACCENT, ACCENT_HOVER),
                                               ("👁 Xem step", BTN_SOFT, BTN_SOFT_HOVER))):
            ctk.CTkButton(btns, text=text, height=32, corner_radius=8, font=(FB, 11), fg_color=col, hover_color=hov,
                          command=lambda t=text: self.log(f"{t} (demo)")
                          ).grid(row=0, column=k, sticky="ew", padx=(0 if k == 0 else 3, 0))
        ctk.CTkLabel(pg.body, text="Soạn / sửa chương trình và Teach điểm làm trong giao diện điều khiển robot; "
                                   "master chỉ đọc và chạy.", font=(F, 10), text_color=DISABLED, wraplength=320,
                     justify="left").pack(anchor="w", pady=(8, 0))
        return v

    def _connect_all(self):
        self.log("Connect PLC (demo)")
        if not self.pi.connected and not self.pi.busy():
            self._pi_toggle_connect()
        if not self.robot._connected():
            self.robot._connect_uart()

    # ---------------- Raspberry Pi: khối kết nối trong tab Cài đặt ----------------
    def _build_pi_connection(self, parent):
        r = ctk.CTkFrame(parent, fg_color="transparent")
        r.pack(fill="x", pady=(12, 2))
        ctk.CTkLabel(r, text="Raspberry Pi · TCP/IP", font=(FB, 12), text_color=TEXT, anchor="w").pack(side="left")
        self.pi_pill = pill(r, "OFFLINE", "gray", font_size=10)
        self.pi_pill.pack(side="left", padx=(8, 0))
        self.pi_btn = ctk.CTkButton(r, text="Connect", width=96, height=28, corner_radius=8, font=(FB, 11),
                                    fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self._pi_toggle_connect)
        self.pi_btn.pack(side="right")
        self.pi_ping_btn = ctk.CTkButton(r, text="Ping", width=52, height=28, corner_radius=8, font=(FB, 11),
                                         fg_color=BTN_SOFT, hover_color=BTN_SOFT_HOVER, text_color=TEXT,
                                         command=self._pi_ping)
        self.pi_ping_btn.pack(side="right", padx=(0, 4))
        self.pi_entries = {}
        for key, label, value in (("host", "Địa chỉ IP", PI_HOST), ("port", "Cổng", str(PI_PORT))):
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", pady=4)
            ctk.CTkLabel(row, text=label, font=(F, 12), text_color=TEXT, anchor="w").pack(side="left")
            ctk.CTkFrame(row, fg_color="transparent", width=30, height=30).pack(side="right")   # thẳng cột ô COM
            e = ctk.CTkEntry(row, width=150, height=30, corner_radius=8, fg_color=INPUT, border_color=BORDER,
                             text_color=TEXT, font=(F, 12))
            e.insert(0, value)
            e.pack(side="right", padx=(0, 4))
            self.pi_entries[key] = e
        self._refresh_pi_ui()

    def _refresh_pi_ui(self):
        if not hasattr(self, "pi_btn"):
            return
        on, busy = self.pi.connected, self.pi.busy()
        if on:
            host, port = self.pi.peer
            self.pi_pill.configure(text=f"ONLINE · {host}", fg_color=PILL["green"][0], text_color=PILL["green"][1])
            self.pi_btn.configure(text="Disconnect", fg_color=BTN_SOFT, hover_color=BTN_SOFT_HOVER, text_color=TEXT)
        else:
            text = "ĐANG KẾT NỐI" if busy else "OFFLINE"
            kind = "amber" if busy else "gray"
            self.pi_pill.configure(text=text, fg_color=PILL[kind][0], text_color=PILL[kind][1])
            self.pi_btn.configure(text="Connect", fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#ffffff")
        self.pi_ping_btn.configure(state="normal" if on else "disabled")
        for e in self.pi_entries.values():
            e.configure(state="disabled" if on or busy else "normal")

    def _pi_toggle_connect(self):
        if self.pi.connected:
            self.pi.disconnect()
            return
        if self.pi.busy():
            self.log("Pi: đang kết nối, đợi một chút.", "WARN")
            return
        host = self.pi_entries["host"].get().strip()
        try:
            port = int(self.pi_entries["port"].get())
            if not host or not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            self.log("Pi: địa chỉ IP hoặc cổng không hợp lệ.", "ERROR")
            return
        self.log(f"Pi: đang kết nối {host}:{port}...")

        def done(ok, message):
            if not ok:
                self.log(f"Pi: {message}. Kiểm tra Pi đã chạy server, cùng mạng LAN, đúng IP / cổng, tường lửa.", "ERROR")
            self._refresh_pi_ui()
        self.pi.connect(host, port, done)
        self._refresh_pi_ui()

    def _pi_ping(self):
        def done(reply, img, rtt, err):
            ok = not err and reply and reply.get("status") == "ok"
            self.log(f"Pi: ping {'OK' if ok else 'LỖI'} — " + (f"khứ hồi {rtt:.0f} ms" if ok else str(err or reply)),
                     "OK" if ok else "ERROR")
        if self._pi_ready("Ping"):
            self.pi.request("ping", done)

    # ============================================================
    # LOG
    # ============================================================
    def _build_log(self):
        frame = ctk.CTkFrame(self, fg_color=PANEL, border_color=BORDER, border_width=1, corner_radius=14, height=104)
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
