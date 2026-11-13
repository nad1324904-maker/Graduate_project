"""app.py — Cửa sổ chính ScaraRobotGUI: khung, header, tab, vòng lặp _tick. Chức năng từng khu vực nằm trong
các mixin ở ui/robot_tab/ và ui/settings_tab/ (mọi self.xxx giữ nguyên như bản gui.py một file)."""

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
    COL_ACCENT, COL_ACCENT_HOVER, COL_BG, COL_BTN_DARK, COL_BTN_DARK_HOVER, COL_GREEN,
    COL_HEADER, COL_INPUT, COL_TEXT, COL_TEXT_DIM, LOG_TAG_COLOR
)
from ui.widgets import Card, HeaderBadge
from ui.perf import MAX_LOG_LINES, TICK_MS, DISPLAY_EVERY, install_configure_cache
from ui.robot_tab.control import ControlMixin
from ui.robot_tab.jog import JogMixin
from ui.robot_tab.monitor import MonitorMixin
from ui.robot_tab.points import PointsMixin
from ui.robot_tab.program import ProgramMixin
from ui.settings_tab.connection import ConnectionMixin
from ui.settings_tab.settings import SettingsMixin


class ScaraRobotGUI(ConnectionMixin, SettingsMixin, JogMixin, MonitorMixin, PointsMixin, ProgramMixin, ControlMixin, ctk.CTk):
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
        """LƯU Ý: không dùng winfo_reqheight() để auto-fit như các bản
        trước — vì nội dung chính nằm trong CTkScrollableFrame, kích
        thước "tự nhiên" nó báo về không phản ánh chiều cao thật sự bên
        trong (luôn nhỏ, vì mục đích scroll là tách rời 2 thứ đó). Dùng
        kích thước mặc định hợp lý, phần dư thừa (nếu có) tự cuộn được."""
        self.update_idletasks()
        width = max(self.winfo_reqwidth(), 1360)
        self.geometry(f"{width}x900")
        self.minsize(1200, 700)

    def _build_layout(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.settings_open = False
        self.active_tab = "robot"
        self._build_header()
        self._build_main()
        self._build_settings_view()
        self.settings_view.grid_remove()  # ẩn sẵn, chỉ hiện khi bấm ⚙

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

    def _build_header_tabbar(self, parent):
        """Thanh tab bar 2 nút (Robot / Settings) ở góc phải header — thay
        cho nút ⚙ đơn lẻ trước đây, để chuyển qua lại rõ ràng hơn."""
        bar = ctk.CTkFrame(parent, fg_color=COL_BTN_DARK, corner_radius=10)
        bar.pack(side="right", padx=(24, 0))
        self.tab_buttons = {}
        for key, icon, label in (("robot", "🤖", "Robot"), ("settings", "⚙", "Settings")):
            active = (key == self.active_tab)
            b = ctk.CTkButton(
                bar, text=f"{icon}  {label}", width=104, height=36, corner_radius=8,
                font=("Segoe UI Semibold", 12),
                fg_color=COL_ACCENT if active else "transparent",
                hover_color=COL_ACCENT_HOVER if active else COL_BTN_DARK_HOVER,
                text_color="#ffffff" if active else COL_TEXT_DIM,
                command=lambda k=key: self._set_active_tab(k))
            b.pack(side="left", padx=2, pady=2)
            self.tab_buttons[key] = b

    def _tick_clock(self):
        self.clock_badge.set_value(datetime.now().strftime("%H:%M:%S"))
        self.after(1000, self._tick_clock)

    # ---------------- Chuyển tab Robot <-> Settings ----------------
    def _set_active_tab(self, key):
        if key == self.active_tab:
            return
        self.active_tab = key
        for k, b in self.tab_buttons.items():
            active = (k == key)
            b.configure(fg_color=COL_ACCENT if active else "transparent",
                        hover_color=COL_ACCENT_HOVER if active else COL_BTN_DARK_HOVER,
                        text_color="#ffffff" if active else COL_TEXT_DIM)
        if key == "settings":
            self._open_settings()
        else:
            self._close_settings()

    def _open_settings(self):
        self.settings_open = True
        self.main_view.grid_remove()
        self.settings_view.grid()
        self._load_settings_into_fields(robot_config.load_config())
        self.settings_status_label.configure(text="", text_color=COL_TEXT_DIM)

    def _close_settings(self):
        self.settings_open = False
        self.settings_view.grid_remove()
        self.main_view.grid()

    # ---------------- MAIN (màn hình vận hành) ----------------
    def _build_main(self):
        outer = ctk.CTkScrollableFrame(self, fg_color=COL_BG,
                                        scrollbar_button_color=COL_BTN_DARK,
                                        scrollbar_button_hover_color=COL_BTN_DARK_HOVER)
        outer.grid(row=1, column=0, sticky="nsew")
        outer.grid_columnconfigure(0, weight=1)
        self.main_view = outer

        main_area = ctk.CTkFrame(outer, fg_color="transparent")
        main_area.grid(row=0, column=0, sticky="new", pady=4)

        row1 = ctk.CTkFrame(main_area, fg_color="transparent")
        row1.pack(fill="x")
        # MODE | JOG CONTROL | QUICK ACTION | OPERATION MONITOR
        row1.grid_columnconfigure(0, weight=2)
        row1.grid_columnconfigure(1, weight=5)
        row1.grid_columnconfigure(2, weight=2)
        row1.grid_columnconfigure(3, weight=7)
        row1.grid_rowconfigure(0, weight=1)
        self._build_mode_card(row1).grid(row=0, column=0, sticky="nsew", padx=(4, 4))
        self._build_jog_card(row1).grid(row=0, column=1, sticky="nsew", padx=4)
        self._build_quick_action_card(row1).grid(row=0, column=2, sticky="nsew", padx=4)
        self._build_monitor_card(row1).grid(row=0, column=3, sticky="nsew", padx=(4, 4))

        row2 = ctk.CTkFrame(main_area, fg_color="transparent")
        row2.pack(fill="x", pady=(8, 0))
        row2.grid_columnconfigure(0, weight=5)
        row2.grid_columnconfigure(1, weight=9)
        row2.grid_columnconfigure(2, weight=6)
        row2.grid_rowconfigure(0, weight=1)
        self._build_points_card(row2).grid(row=0, column=0, sticky="nsew", padx=(4, 4))
        self._build_program_card(row2).grid(row=0, column=1, sticky="nsew", padx=4)
        self._build_control_card(row2).grid(row=0, column=2, sticky="nsew", padx=(4, 4))

        self._build_log_card(outer).grid(row=1, column=0, sticky="ew", padx=4, pady=(8, 4))

        self._refresh_program_point_options()
        self._refresh_enabled_states()

    def _build_log_card(self, parent):
        card = Card(parent, "SYSTEM LOG", "📄")
        self.log_box = ctk.CTkTextbox(card.body, height=140, fg_color=COL_INPUT,
                                       text_color=COL_TEXT_DIM, font=("Consolas", 11), corner_radius=8)
        self.log_box.pack(fill="both", expand=True)
        for tag, color in LOG_TAG_COLOR.items():
            self.log_box.tag_config(tag, foreground=color)
        self.log_box.tag_config("TS", foreground=COL_GREEN)
        self.log_box.configure(state="disabled")
        return card

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
                self.backend.is_homed() if connected else None, self.skip_home_check.get())

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
        sig = self._ui_state_signature()
        if sig != self._ui_sig:
            self._ui_sig = sig
            self._refresh_enabled_states()
        self.after(TICK_MS, self._tick)
