"""connection.py — Panel Communication: chọn cổng COM, Connect/Disconnect, nạp cấu hình, đổi backend lúc chạy."""

import customtkinter as ctk

from comm.uart_backend import UartRobotBackend, list_available_ports
from comm.offline_backend import OfflineBackend
from comm.errors import UartError
from core import kinematics
from core import robot_config
from core.program_executor import ProgramExecutor, ExecState
from ui.theme import (
    COL_AMBER, COL_BTN_DARK, COL_BTN_DARK_HOVER, COL_GREEN, COL_GREEN_HOVER, COL_INPUT,
    COL_RED, COL_RED_HOVER, COL_TEXT, COL_TEXT_DIM, COL_TEXT_DISABLED
)
from ui.widgets import Card


class ConnectionMixin:
    def _build_communication_panel(self, parent):
        card = Card(parent, "Communication (UART)", "🔗")
        body = card.body

        row1 = ctk.CTkFrame(body, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(row1, text="Cổng COM", font=("Segoe UI", 12), text_color=COL_TEXT,
                     width=90, anchor="w").pack(side="left")
        ports = list_available_ports() or ["(không có cổng)"]
        self.comm_port_menu = ctk.CTkOptionMenu(
            row1, values=ports, width=160, height=32, fg_color=COL_INPUT,
            button_color=COL_BTN_DARK, button_hover_color=COL_BTN_DARK_HOVER,
            font=("Segoe UI", 11))
        self.comm_port_menu.pack(side="left", padx=(8, 4))
        ctk.CTkButton(row1, text="🔄", width=32, height=32, corner_radius=8,
                      fg_color=COL_BTN_DARK, hover_color=COL_BTN_DARK_HOVER,
                      font=("Segoe UI", 13), command=self._refresh_com_ports).pack(side="left")

        row2 = ctk.CTkFrame(body, fg_color="transparent")
        row2.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(row2, text="Baud rate", font=("Segoe UI", 12), text_color=COL_TEXT,
                     width=90, anchor="w").pack(side="left")
        self.comm_baud_menu = ctk.CTkOptionMenu(
            row2, values=["9600", "19200", "38400", "57600", "115200", "230400"],
            width=160, height=32, fg_color=COL_INPUT, button_color=COL_BTN_DARK,
            button_hover_color=COL_BTN_DARK_HOVER, font=("Segoe UI", 11))
        self.comm_baud_menu.set("115200")
        self.comm_baud_menu.pack(side="left", padx=(8, 4))

        row3 = ctk.CTkFrame(body, fg_color="transparent")
        row3.pack(fill="x")
        self.comm_connect_btn = ctk.CTkButton(
            row3, text="🔌 Connect", width=140, height=36, corner_radius=8,
            fg_color=COL_GREEN, hover_color=COL_GREEN_HOVER,
            font=("Segoe UI Semibold", 12), command=self._on_connect_toggle)
        self.comm_connect_btn.pack(side="left")
        self.comm_status_label = ctk.CTkLabel(
            row3, text="● Chưa kết nối", font=("Segoe UI Semibold", 11), text_color=COL_TEXT_DIM)
        self.comm_status_label.pack(side="left", padx=12)

        ctk.CTkLabel(
            body, text="Khi Connect, GUI gửi cấu hình (PID, Vmax, Amax, Deadband, giới hạn khớp, vị trí Home) xuống STM32. "
                       "Sau khi cấp nguồn / reset / nạp code, vị trí robot chưa được biết: hãy bấm HOME để các trục tìm "
                       "cảm biến home trước khi JOG hoặc chạy chương trình. Giao thức: xem PROTOCOL.md.",
            font=("Segoe UI", 9), text_color=COL_TEXT_DISABLED,
            wraplength=560, justify="left").pack(anchor="w", pady=(8, 0))
        return card

    # ---------------- Connect / Disconnect UART ----------------
    def _refresh_com_ports(self):
        ports = list_available_ports() or ["(không có cổng)"]
        self.comm_port_menu.configure(values=ports)
        self.comm_port_menu.set(ports[0])
        self._log(f"Đã quét lại cổng COM: {ports}", "INFO")

    def _connected(self):
        return isinstance(self.backend, UartRobotBackend) and self.backend.is_connected()

    def _on_connect_toggle(self):
        if self._connected():
            self._disconnect_uart()
        else:
            self._connect_uart()

    def _connect_uart(self):
        port = self.comm_port_menu.get()
        if not port or port.startswith("("):
            self._log("Không có cổng COM nào để kết nối.", "ERROR")
            return
        try:
            baud = int(self.comm_baud_menu.get())
        except ValueError:
            baud = 115200

        self.comm_status_label.configure(text="● Đang kết nối...", text_color=COL_AMBER)
        self.update_idletasks()

        new_backend = UartRobotBackend(port, baudrate=baud)
        try:
            new_backend.connect()
        except UartError as e:
            self.comm_status_label.configure(text="● Kết nối lỗi", text_color=COL_RED)
            self._log(str(e), "ERROR")
            return

        new_backend.set_connection_lost_callback(self._on_uart_connection_lost)
        # Giới hạn/Vmax PC-side (kẹp target khi JOG) lấy từ robot_config.json; cấu hình đầy đủ
        # (encoder, PID, Amax, Deadband...) được gửi xuống STM32 bằng configure() ngay dưới.
        try:
            cfg = robot_config.load_config()
        except robot_config.ConfigError as e:
            new_backend.disconnect()
            self.comm_status_label.configure(text="● Cấu hình lỗi", text_color=COL_RED)
            self._log(str(e), "ERROR")
            return
        is_valid, errors = robot_config.validate_config(cfg)
        if not is_valid:
            new_backend.disconnect()
            self.comm_status_label.configure(text="● Cấu hình chưa hợp lệ", text_color=COL_RED)
            for err in errors:
                self._log(err, "ERROR")
            return
        kinematics.set_params(cfg["kinematics"])
        new_backend.set_joint_limits({axis: (v["min"], v["max"])
                                       for axis, v in cfg["joint_limits"].items()})
        new_backend.set_max_velocity({axis: v["vmax"]
                                       for axis, v in cfg["motion_profile"].items()})

        self._rebind_backend(new_backend)

        self.comm_connect_btn.configure(text="🔌 Disconnect", fg_color=COL_RED, hover_color=COL_RED_HOVER)
        self.comm_port_menu.configure(state="disabled")
        self.comm_baud_menu.configure(state="disabled")
        self.comm_status_label.configure(text="● Đang gửi cấu hình...", text_color=COL_AMBER)
        self.mode_badge.set_value(f"STM32F407 · {port}", COL_AMBER)
        self._log(f"Đã mở cổng {port} @ {baud} baud — đang gửi cấu hình xuống STM32...", "INFO")
        try:
            new_backend.configure(cfg, self._on_uart_config_result)
        except (UartError, ValueError) as e:
            self._log(f"Không gửi được cấu hình: {e}", "ERROR")
            self._disconnect_uart()

    def _on_uart_config_result(self, ok, message):
        """Kết quả nạp cấu hình (gọi từ backend.update() khi STM32 đã trả lời mọi lệnh)."""
        if not isinstance(self.backend, UartRobotBackend):
            return
        if ok:
            port = self.backend.port_name
            self.comm_status_label.configure(text=f"● Đã kết nối {port}", text_color=COL_GREEN)
            self.mode_badge.set_value(f"STM32F407 · {port}", COL_GREEN)
            self._log("STM32: CONFIG_OK — đã nạp PID / Vmax / Amax / Deadband / giới hạn khớp / vị trí Home. "
                      "Vị trí robot chưa được biết — hãy bấm HOME để tìm cảm biến home trước khi JOG / chạy chương trình.", "OK")
        else:
            self._log(f"STM32 từ chối cấu hình: {message}", "ERROR")
            self._disconnect_uart()

    def _on_backend_command_error(self, message):
        """STM32 từ chối lệnh (ERR) hoặc báo FAULT: ghi Log, và dừng chương trình nếu đang chạy."""
        self._log(message, "ERROR")
        if self.executor.state in (ExecState.RUNNING, ExecState.PAUSED):
            self.executor.fail(message)

    def _disconnect_uart(self):
        if isinstance(self.backend, UartRobotBackend):
            self.backend.disconnect()      # phanh cả 4 động cơ rồi đóng cổng
        self._revert_to_offline()
        self._log("Đã ngắt kết nối UART (đã gửi STOP tới 4 động cơ). GUI về trạng thái CHƯA KẾT NỐI.", "INFO")

    def _on_uart_connection_lost(self, reason):
        self._log(f"Mất kết nối UART ngoài ý muốn: {reason}", "ERROR")
        if self.executor.state in (ExecState.RUNNING, ExecState.PAUSED):
            self.executor.fail(f"Mất kết nối UART: {reason}")   # ghi nhận lỗi trước khi executor bị tạo lại
        self._revert_to_offline()

    def _revert_to_offline(self):
        self._rebind_backend(OfflineBackend())
        self.comm_connect_btn.configure(text="🔌 Connect", fg_color=COL_GREEN, hover_color=COL_GREEN_HOVER)
        self.comm_port_menu.configure(state="normal")
        self.comm_baud_menu.configure(state="normal")
        self.comm_status_label.configure(text="● Chưa kết nối", text_color=COL_TEXT_DIM)
        self.mode_badge.set_value("CHƯA KẾT NỐI", COL_TEXT_DIM)

    def _rebind_backend(self, new_backend):
        """Đổi backend đang hoạt động (Offline <-> UART) lúc runtime — tạo lại ProgramExecutor (vì nó
        đăng ký callback thẳng vào backend cũ lúc __init__) và đăng ký lại các callback GUI tự quản."""
        self.backend = new_backend
        self.backend.set_home_done_callback(self._on_home_done)
        self.backend.set_gripper_change_callback(self._on_gripper_change)
        if hasattr(self.backend, "set_command_error_callback"):     # chỉ backend UART có
            self.backend.set_command_error_callback(self._on_backend_command_error)
        if hasattr(self.backend, "set_info_callback"):              # thông tin thường (vd: trục chưa có cảm biến home)
            self.backend.set_info_callback(lambda message: self._log(message, "INFO"))
        self.executor = ProgramExecutor(self.backend, self.point_store, self.program_store)
        self.executor.set_callbacks(
            on_step_started=self._on_step_started,
            on_step_done=self._on_step_done,
            on_state_change=self._on_exec_state_change,
        )
