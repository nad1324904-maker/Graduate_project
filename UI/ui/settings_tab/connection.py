"""connection.py — Kết nối robot (UART): chọn cổng COM, Connect/Disconnect, nạp cấu hình, đổi backend lúc chạy.
Giao diện nằm ở tab Cài đặt của app master (thẻ "Kết nối thiết bị"), xem build_connection_section()."""

import customtkinter as ctk

from comm.uart_backend import UartRobotBackend, list_available_ports
from comm.offline_backend import OfflineBackend
from comm.errors import UartError
from core import kinematics
from core import robot_config
from core.program_executor import ProgramExecutor, ExecState
from ui.theme import (
    COL_ACCENT, COL_ACCENT_HOVER, COL_AMBER, COL_BTN_DARK, COL_BTN_DARK_HOVER, COL_GREEN, COL_INPUT,
    COL_ON_ACCENT, COL_RED, COL_TEXT, COL_TEXT_DIM, COL_TEXT_DISABLED
)


class ConnectionMixin:
    # Kết nối robot nằm ở tab Cài đặt của app MASTER (thẻ "Kết nối thiết bị"), cùng chỗ với PLC / Raspberry Pi:
    # master gọi panel.build_connection_section(<khung trong thẻ>). Widget thuộc khung của master, còn
    # logic Connect / Disconnect vẫn ở đây (self = ScaraRobotPanel).
    def build_connection_section(self, parent):
        """Dựng khối "Robot SCARA · UART" (tiêu đề + trạng thái + Connect, cổng COM, baud) vào `parent`."""
        head = ctk.CTkFrame(parent, fg_color="transparent")
        head.pack(fill="x", pady=(12, 2))
        ctk.CTkLabel(head, text="Robot SCARA · UART", font=("Segoe UI Semibold", 12), text_color=COL_TEXT,
                     anchor="w").pack(side="left")
        self.comm_status_label = ctk.CTkLabel(head, text="", fg_color=COL_INPUT, corner_radius=8, height=24,
                                              padx=10, font=("Segoe UI Semibold", 10))
        self.comm_status_label.pack(side="left", padx=(8, 0))
        self.comm_connect_btn = ctk.CTkButton(head, width=96, height=28, corner_radius=8,
                                              font=("Segoe UI Semibold", 11), command=self._on_connect_toggle)
        self.comm_connect_btn.pack(side="right")

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=4)
        ctk.CTkLabel(row, text="Cổng COM", font=("Segoe UI", 12), text_color=COL_TEXT).pack(side="left")
        ctk.CTkButton(row, text="⟳", width=30, height=30, corner_radius=8, font=("Segoe UI", 13),
                      fg_color=COL_BTN_DARK, hover_color=COL_BTN_DARK_HOVER,
                      command=self._refresh_com_ports).pack(side="right")
        ports = list_available_ports() or ["(không có cổng)"]
        self.comm_port_menu = ctk.CTkOptionMenu(
            row, values=ports, width=150, height=30, corner_radius=8, fg_color=COL_INPUT,
            button_color=COL_BTN_DARK, button_hover_color=COL_BTN_DARK_HOVER, font=("Segoe UI", 12))
        self.comm_port_menu.pack(side="right", padx=(0, 4))

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=4)
        ctk.CTkLabel(row, text="Baud rate", font=("Segoe UI", 12), text_color=COL_TEXT).pack(side="left")
        ctk.CTkFrame(row, fg_color="transparent", width=30, height=30).pack(side="right")   # thẳng cột với ô COM
        self.comm_baud_menu = ctk.CTkOptionMenu(
            row, values=["9600", "19200", "38400", "57600", "115200", "230400"], width=150, height=30,
            corner_radius=8, fg_color=COL_INPUT, button_color=COL_BTN_DARK,
            button_hover_color=COL_BTN_DARK_HOVER, font=("Segoe UI", 12))
        self.comm_baud_menu.set("115200")
        self.comm_baud_menu.pack(side="right", padx=(0, 4))

        ctk.CTkLabel(
            parent, text="Connect: gửi cấu hình robot (PID, Vmax, Amax, Deadband, giới hạn khớp, Home) xuống STM32. "
                         "Sau khi cấp nguồn / reset, bấm HOME (tab Robot) trước khi JOG hoặc chạy chương trình.",
            font=("Segoe UI", 10), text_color=COL_TEXT_DISABLED, wraplength=320, justify="left"
        ).pack(anchor="w", pady=(2, 0))
        self._set_comm_ui(False, "OFFLINE", COL_TEXT_DIM)

    def _set_comm_ui(self, connected, status, color):
        """Nút Connect/Disconnect + khóa chọn cổng + nhãn trạng thái (status: chữ IN HOA ngắn)."""
        if connected:
            self.comm_connect_btn.configure(text="Disconnect", fg_color=COL_BTN_DARK,
                                            hover_color=COL_BTN_DARK_HOVER, text_color=COL_TEXT)
        else:
            self.comm_connect_btn.configure(text="Connect", fg_color=COL_ACCENT,
                                            hover_color=COL_ACCENT_HOVER, text_color=COL_ON_ACCENT)
        self.comm_port_menu.configure(state="disabled" if connected else "normal")
        self.comm_baud_menu.configure(state="disabled" if connected else "normal")
        self._set_comm_status(status, color)

    def _set_comm_status(self, status, color):
        self.comm_status_label.configure(text=status, text_color=color)

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

        self._set_comm_status("ĐANG KẾT NỐI", COL_AMBER)
        self.update_idletasks()

        new_backend = UartRobotBackend(port, baudrate=baud)
        try:
            new_backend.connect()
        except UartError as e:
            self._set_comm_status("LỖI KẾT NỐI", COL_RED)
            self._log(str(e), "ERROR")
            return

        new_backend.set_connection_lost_callback(self._on_uart_connection_lost)
        # Giới hạn/Vmax PC-side (kẹp target khi JOG) lấy từ robot_config.json; cấu hình đầy đủ
        # (encoder, PID, Amax, Deadband...) được gửi xuống STM32 bằng configure() ngay dưới.
        try:
            cfg = robot_config.load_config()
        except robot_config.ConfigError as e:
            new_backend.disconnect()
            self._set_comm_status("CẤU HÌNH LỖI", COL_RED)
            self._log(str(e), "ERROR")
            return
        is_valid, errors = robot_config.validate_config(cfg)
        if not is_valid:
            new_backend.disconnect()
            self._set_comm_status("CẤU HÌNH LỖI", COL_RED)
            for err in errors:
                self._log(err, "ERROR")
            return
        kinematics.set_params(cfg["kinematics"])
        new_backend.set_joint_limits({axis: (v["min"], v["max"])
                                       for axis, v in cfg["joint_limits"].items()})
        new_backend.set_max_velocity({axis: v["vmax"]
                                       for axis, v in cfg["motion_profile"].items()})

        self._rebind_backend(new_backend)

        self._set_comm_ui(True, "ĐANG GỬI CẤU HÌNH", COL_AMBER)
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
            self._set_comm_status(f"ONLINE · {port}", COL_GREEN)
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
        self._set_comm_ui(False, "OFFLINE", COL_TEXT_DIM)
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
