"""app.py — Cửa sổ chính ScaraRobotGUI: header (tab + STOP), các tab, thanh LOG chung, vòng lặp _tick.

Tab:  Vận hành (JOG · Monitor · Chạy chương trình) | Lập trình (Points · Program Editor) | Giám sát | Settings.
Chức năng từng khu vực nằm trong các mixin ở ui/robot_tab/, ui/visual_tab/, ui/settings_tab/."""

import time
from datetime import datetime

import customtkinter as ctk

from comm.offline_backend import OfflineBackend
from core import kinematics
from core import robot_config
from core.point_store import PointStore
from core.program_store import ProgramStore
from core.program_executor import ProgramExecutor
from ui.theme import (
    COL_ACCENT, COL_ACCENT_HOVER, COL_BG, COL_BTN_DARK, COL_BTN_DARK_HOVER, COL_GREEN, COL_HEADER, COL_INPUT,
    COL_ON_ACCENT, COL_PANEL, COL_PANEL_BORDER, COL_RED, COL_RED_HOVER, COL_TEXT, COL_TEXT_DIM, LOG_TAG_COLOR
)
from ui.widgets import HeaderBadge
from ui.perf import MAX_LOG_LINES, TICK_MS, DISPLAY_EVERY, install_configure_cache
from ui.robot_tab.control import ControlMixin
from ui.robot_tab.jog import JogMixin
from ui.robot_tab.monitor import MonitorMixin
from ui.robot_tab.points import PointsMixin
from ui.robot_tab.program import ProgramMixin
from ui.settings_tab.connection import ConnectionMixin
from ui.settings_tab.settings import SettingsMixin
from ui.visual_tab.visual import VisualMixin


class ScaraRobotGUI(ConnectionMixin, SettingsMixin, VisualMixin, JogMixin, MonitorMixin, PointsMixin, ProgramMixin,
                    ControlMixin, ctk.CTk):
    def __init__(self):
        install_configure_cache()    # chỉ configure() khi giá trị đổi (xem ui/perf.py)
        super().__init__()
        self.title("SCARA Robot — STM32F407")
        self.geometry("1560x1000")
        self.configure(fg_color=COL_BG)

        self._load_kinematics_from_config()
        self.backend = OfflineBackend()   # chưa kết nối: GUI chỉ vận hành sau khi Connect (Settings → Communication)
        self.backend.set_home_done_callback(self._on_home_done)
        self.backend.set_gripper_change_callback(self._on_gripper_change)

        self.point_store = PointStore()
        self.program_store = ProgramStore()
        self.executor = ProgramExecutor(self.backend, self.point_store, self.program_store)
        self.executor.set_callbacks(
            on_step_started=self._on_step_started,
            on_step_done=self._on_step_done,
            on_state_change=self._on_exec_state_change,
        )

        self.mode = "JOG"
        self.selected_point = None
        self.selected_program = None
        self.selected_step_index = None
        self.loaded_reference = None          # (tên, values) sau khi chọn dòng Point
        self._program_just_completed = False

        self._build_layout()
        self._tick_clock()
        self._last_tick = time.time()
        self._tick_count = 0
        self._ui_sig = None          # chữ ký trạng thái lần cuối đã cập nhật nút bấm
        self._tick()
        self._fit_window()

    def _load_kinematics_from_config(self):
        """Nạp h1/l1/l2/h2 từ robot_config.json ngay lúc khởi động (không đợi bấm Apply)."""
        try:
            kinematics.set_params(robot_config.load_config()["kinematics"])
        except (robot_config.ConfigError, KeyError, ValueError):
            pass

    # ---------------------------------------------------------------
    def _fit_window(self):
        """Cửa sổ rộng tối thiểu 1360, cao tối đa 900 nhưng không vượt màn hình (chừa thanh tiêu đề + taskbar)."""
        self.update_idletasks()
        width = min(max(self.winfo_reqwidth(), 1360), self.winfo_screenwidth())
        height = min(900, self.winfo_screenheight() - 90)      # chừa chỗ cho thanh tiêu đề + taskbar Windows
        self.geometry(f"{width}x{height}+0+0")
        self.minsize(1200, min(700, height))

    def _build_layout(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.settings_open = False
        self.active_tab = "operate"
        self._build_header()
        self._build_log_strip()           # thanh LOG ở đáy, hiện ở mọi tab (dựng trước để các tab gọi _log được)
        self._build_operate_view()
        self._build_program_view()
        self._build_settings_view()
        self._build_visual_view()         # tab Giám sát: chỉ vẽ + nhận telemetry khi đang mở
        self._views = {"operate": self.operate_view, "program": self.program_view,
                       "visual": self.visual_view, "settings": self.settings_view}
        for key, view in self._views.items():
            if key != self.active_tab:
                view.grid_remove()
        self._refresh_program_point_options()
        self._refresh_enabled_states()

    # ---------------- HEADER ----------------
    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color=COL_HEADER, height=76, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)

        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left", padx=20, pady=12)
        ctk.CTkLabel(left, text="🤖", font=("Segoe UI", 26)).pack(side="left")
        title_box = ctk.CTkFrame(left, fg_color="transparent")
        title_box.pack(side="left", padx=(10, 0))
        ctk.CTkLabel(title_box, text="SCARA ROBOT", font=("Segoe UI Semibold", 18),
                     text_color=COL_TEXT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(title_box, text="4-DOF (J1, J2, J3, Z) — STM32F407",
                     font=("Segoe UI", 11), text_color=COL_TEXT_DIM, anchor="w").pack(anchor="w")

        badges = ctk.CTkFrame(header, fg_color="transparent")
        badges.pack(side="right", padx=20, pady=12)

        self.clock_badge = HeaderBadge(badges, "🕐", "")
        self.clock_badge.pack(side="right", padx=(24, 0))

        self.status_badge = HeaderBadge(badges, "●", "Robot Status")
        self.status_badge.pack(side="right", padx=(24, 0))

        self.mode_badge = HeaderBadge(badges, "🔌", "Kết nối")
        self.mode_badge.set_value("CHƯA KẾT NỐI", COL_TEXT_DIM)
        self.mode_badge.pack(side="right", padx=(24, 0))

        self._build_header_tabbar(badges)

        # STOP luôn nhìn thấy ở mọi tab (trước đây nằm trong khung CONTROL, phải cuộn xuống mới thấy)
        self.header_stop_btn = ctk.CTkButton(
            badges, text="■  STOP", width=112, height=40, corner_radius=10,
            font=("Segoe UI Semibold", 14), fg_color=COL_RED, hover_color=COL_RED_HOVER,
            state="disabled", command=self._on_stop)
        self.header_stop_btn.pack(side="right", padx=(24, 0))
        # E-STOP (mềm): báo cho STM32 khóa chuyển động — giống lệnh master gửi khi PLC báo E-Stop. Gỡ bằng RESET rồi HOME.
        self.header_estop_btn = ctk.CTkButton(
            badges, text="⛔ E-STOP", width=104, height=40, corner_radius=10,
            font=("Segoe UI Semibold", 13), fg_color="transparent", hover_color=COL_RED_HOVER,
            text_color=COL_RED, border_width=2, border_color=COL_RED,
            state="disabled", command=self._on_estop)
        self.header_estop_btn.pack(side="right", padx=(8, 0))

    def _build_header_tabbar(self, parent):
        """Thanh tab ở header: Vận hành / Lập trình / Giám sát / Settings."""
        bar = ctk.CTkFrame(parent, fg_color=COL_BTN_DARK, corner_radius=10)
        bar.pack(side="right", padx=(24, 0))
        self.tab_buttons = {}
        for key, icon, label in (("operate", "🕹️", "Vận hành"), ("program", "📝", "Lập trình"),
                                 ("visual", "📊", "Giám sát"), ("settings", "⚙", "Settings")):
            active = (key == self.active_tab)
            b = ctk.CTkButton(
                bar, text=f"{icon} {label}", width=100, height=36, corner_radius=8,
                font=("Segoe UI Semibold", 12),
                fg_color=COL_ACCENT if active else "transparent",
                hover_color=COL_ACCENT_HOVER if active else COL_BTN_DARK_HOVER,
                text_color=COL_ON_ACCENT if active else COL_TEXT_DIM,
                command=lambda k=key: self._set_active_tab(k))
            b.pack(side="left", padx=2, pady=2)
            self.tab_buttons[key] = b

    def _tick_clock(self):
        self.clock_badge.set_value(datetime.now().strftime("%H:%M:%S"))
        self.after(1000, self._tick_clock)

    # ---------------- Chuyển tab ----------------
    def _set_active_tab(self, key):
        if key == self.active_tab:
            return
        prev, self.active_tab = self.active_tab, key
        for k, b in self.tab_buttons.items():
            active = (k == key)
            b.configure(fg_color=COL_ACCENT if active else "transparent",
                        hover_color=COL_ACCENT_HOVER if active else COL_BTN_DARK_HOVER,
                        text_color=COL_ON_ACCENT if active else COL_TEXT_DIM)
        for view in self._views.values():
            view.grid_remove()
        if prev == "visual":
            self._on_visual_hide()           # tắt telemetry T khi rời tab Giám sát
        self.settings_open = (key == "settings")
        self._views[key].grid()
        if key == "settings":
            self._load_settings_into_fields(robot_config.load_config())
            self.settings_status_label.configure(text="", text_color=COL_TEXT_DIM)
        elif key == "visual":
            self.update_idletasks()          # để canvas có kích thước thật trước lần vẽ đầu
            self._on_visual_show()

    # ---------------- Tab VẬN HÀNH: JOG | Monitor | Chạy chương trình (vừa 1 màn hình, không cuộn) ----------------
    def _build_operate_view(self):
        view = ctk.CTkFrame(self, fg_color=COL_BG, corner_radius=0)
        view.grid(row=1, column=0, sticky="nsew")
        view.grid_columnconfigure(0, weight=4, uniform="op")
        view.grid_columnconfigure(1, weight=5, uniform="op")
        view.grid_columnconfigure(2, weight=4, uniform="op")
        view.grid_rowconfigure(0, weight=1)
        self.operate_view = view
        self._build_jog_card(view).grid(row=0, column=0, sticky="nsew", padx=(8, 4), pady=8)
        self._build_monitor_card(view).grid(row=0, column=1, sticky="nsew", padx=4, pady=8)
        self._build_run_card(view).grid(row=0, column=2, sticky="nsew", padx=(4, 8), pady=8)

    # ---------------- Tab LẬP TRÌNH: Points | Program Editor ----------------
    def _build_program_view(self):
        view = ctk.CTkFrame(self, fg_color=COL_BG, corner_radius=0)
        view.grid(row=1, column=0, sticky="nsew")
        view.grid_columnconfigure(0, weight=2, uniform="pg")
        view.grid_columnconfigure(1, weight=3, uniform="pg")
        view.grid_rowconfigure(0, weight=1)
        self.program_view = view
        self._build_points_card(view).grid(row=0, column=0, sticky="nsew", padx=(8, 4), pady=8)
        self._build_program_card(view).grid(row=0, column=1, sticky="nsew", padx=(4, 8), pady=8)

    # ---------------- Thanh LOG ở đáy (mọi tab) ----------------
    LOG_HEIGHT_SMALL, LOG_HEIGHT_BIG = 74, 240

    def _build_log_strip(self):
        strip = ctk.CTkFrame(self, fg_color=COL_PANEL, corner_radius=0, border_width=1, border_color=COL_PANEL_BORDER)
        strip.grid(row=2, column=0, sticky="ew")
        top = ctk.CTkFrame(strip, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(6, 2))
        ctk.CTkLabel(top, text="📄 SYSTEM LOG", font=("Segoe UI Semibold", 11), text_color=COL_TEXT).pack(side="left")
        self.log_toggle_btn = ctk.CTkButton(top, text="▲ Mở rộng", width=90, height=24, corner_radius=6,
                                            fg_color=COL_BTN_DARK, hover_color=COL_BTN_DARK_HOVER,
                                            font=("Segoe UI", 11), command=self._toggle_log_size)
        self.log_toggle_btn.pack(side="right")
        self.log_box = ctk.CTkTextbox(strip, height=self.LOG_HEIGHT_SMALL, fg_color=COL_INPUT,
                                       text_color=COL_TEXT_DIM, font=("Consolas", 11), corner_radius=8)
        self.log_box.pack(fill="x", padx=12, pady=(0, 8))
        for tag, color in LOG_TAG_COLOR.items():
            self.log_box.tag_config(tag, foreground=color)
        self.log_box.tag_config("TS", foreground=COL_GREEN)
        self.log_box.configure(state="disabled")
        self._log_big = False

    def _toggle_log_size(self):
        self._log_big = not self._log_big
        self.log_box.configure(height=self.LOG_HEIGHT_BIG if self._log_big else self.LOG_HEIGHT_SMALL)
        self.log_toggle_btn.configure(text="▼ Thu gọn" if self._log_big else "▲ Mở rộng")
        self.log_box.see("end")

    def _log(self, message, level="INFO"):
        self.log_box.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_box.insert("end", f"{ts}", "TS")
        self.log_box.insert("end", "  |  ")
        self.log_box.insert("end", f"[{level}]", level)
        self.log_box.insert("end", f"  {message}\n")
        lines = int(self.log_box.index("end-1c").split(".")[0])
        if lines > MAX_LOG_LINES:                    # giữ Log gọn: xóa dòng cũ nhất
            self.log_box.delete("1.0", f"{lines - MAX_LOG_LINES + 1}.0")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    # ============================================================
    # Vòng lặp chính: xử lý UART + executor mỗi TICK_MS; số liệu hiển thị mỗi DISPLAY_EVERY tick;
    # trạng thái nút bấm chỉ cập nhật KHI thay đổi (dựa trên chữ ký trạng thái)
    # ============================================================
    def _ui_state_signature(self):
        connected = self._connected()
        return (connected, self.mode, self.executor.state,
                self.backend.get_status() if connected else None,
                self.backend.is_homed() if connected else None, self.skip_home_check.get(),
                self.backend.is_estop() if connected else None)

    def _tick(self):
        now = time.time()
        dt = now - self._last_tick
        self._last_tick = now
        self.backend.update(dt)
        self.executor.update(dt)
        self._tick_count += 1
        if self._tick_count % DISPLAY_EVERY == 0:
            self._refresh_position_display()
            self._refresh_status_display()
            if self.active_tab == "visual":
                self._refresh_visual()       # hình 2D + đồ thị: chỉ vẽ khi tab Giám sát đang mở
        sig = self._ui_state_signature()
        if sig != self._ui_sig:
            self._ui_sig = sig
            self._refresh_enabled_states()
        self.after(TICK_MS, self._tick)
