"""control.py — START/PAUSE/STOP/RESET, HOME/GRIP, callback của ProgramExecutor, trạng thái nút."""

import customtkinter as ctk

from comm.backend_base import RobotStatus
from comm.errors import UartError
from core.program_store import describe_step
from core.program_executor import ExecState, ExecutorError
from ui.theme import (
    COL_AMBER, COL_AMBER_HOVER, COL_GRAY_BTN, COL_GRAY_BTN_HOVER, COL_GREEN,
    COL_GREEN_HOVER, COL_RED, COL_RED_HOVER, COL_TEXT, COL_TEXT_DIM
)
from ui.widgets import Card, BigActionButton


class ControlMixin:
    # ============================================================
    # CONTROL (chạy chương trình)
    # ============================================================
    def _build_control_card(self, parent):
        card = Card(parent, "CONTROL", "▶")
        body = card.body

        ctk.CTkLabel(body, text="Progress", font=("Segoe UI", 11),
                     text_color=COL_TEXT_DIM, anchor="w").pack(fill="x")
        self.progress_bar = ctk.CTkProgressBar(body, height=10, progress_color=COL_GREEN)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", pady=(4, 2))
        self.progress_label = ctk.CTkLabel(body, text="0 / 0", font=("Segoe UI Semibold", 12),
                                            text_color=COL_TEXT, anchor="w")
        self.progress_label.pack(fill="x", pady=(0, 6))
        self.step_desc_label = ctk.CTkLabel(body, text="—", font=("Segoe UI", 10),
                                             text_color=COL_TEXT_DIM, anchor="w", wraplength=220)
        self.step_desc_label.pack(fill="x", pady=(0, 10))

        # Lưới nút chiếm phần còn lại → panel CONTROL cao bằng POINTS / PROGRAM
        grid = ctk.CTkFrame(body, fg_color="transparent")
        grid.pack(fill="both", expand=True)
        grid.grid_columnconfigure((0, 1), weight=1)
        grid.grid_rowconfigure((0, 1), weight=1)
        self.start_btn = BigActionButton(grid, "▶", "START", COL_GREEN, COL_GREEN_HOVER, self._on_start)
        self.start_btn.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        self.pause_btn = BigActionButton(grid, "⏸", "PAUSE", COL_AMBER, COL_AMBER_HOVER, self._on_pause)
        self.pause_btn.grid(row=0, column=1, sticky="nsew", padx=2, pady=2)
        self.stop_btn = BigActionButton(grid, "■", "STOP", COL_RED, COL_RED_HOVER, self._on_stop)
        self.stop_btn.grid(row=1, column=0, sticky="nsew", padx=2, pady=2)
        self.reset_btn = BigActionButton(grid, "⟳", "RESET", COL_GRAY_BTN, COL_GRAY_BTN_HOVER, self._on_reset)
        self.reset_btn.grid(row=1, column=1, sticky="nsew", padx=2, pady=2)
        return card

    def _on_start(self):
        if not self._connected():
            self._log("Bị chặn: chưa kết nối STM32 (Settings → Communication → Connect).", "WARN")
            return
        if self.backend.is_homing():
            self._log("Bị chặn: robot đang HOME (tìm cảm biến) — đợi xong hoặc bấm STOP.", "WARN")
            return
        if not self._home_ready():
            self._log("Bị chặn: chưa HOME — hãy bấm HOME (Quick Action) trước khi chạy chương trình.", "WARN")
            return
        if self.mode != "Chương trình":
            self._log("Bị chặn: START chỉ cho phép ở Chế độ PROGRAM.", "WARN")
            return
        if not self.selected_program:
            self._log("Chưa chọn chương trình nào để chạy.", "WARN")
            return
        try:
            if self.executor.state == ExecState.PAUSED and self.executor.program_name == self.selected_program:
                self.executor.resume()
                self._log(f"Tiếp tục chạy '{self.selected_program}'.")
                return
            self._program_just_completed = False
            self.executor.start(self.selected_program)
            self._log(f"START '{self.selected_program}'.", "OK")
        except (ExecutorError, UartError) as e:
            self._log(str(e), "ERROR")

    def _on_pause(self):
        try:
            if self.executor.state == ExecState.RUNNING:
                self.executor.pause()
                self._log("Đã tạm dừng: các động cơ giảm tốc về điểm dừng rồi giữ vị trí.", "WARN")
            elif self.executor.state == ExecState.PAUSED:
                self.executor.resume()
                self._log("Tiếp tục.")
        except UartError as e:
            self._log(str(e), "ERROR")

    def _on_stop(self):
        """STOP = phanh gấp cả 4 động cơ tại vị trí hiện tại (không tự về Home). Dùng được cả khi chỉ đang JOG/HOME."""
        if not self._connected():
            return
        try:
            if self.executor.state in (ExecState.RUNNING, ExecState.PAUSED):
                self.executor.stop()
                self._log("STOP — dừng tại vị trí hiện tại (không tự về Home).", "WARN")
            else:
                self.backend.abort_motion()
                self._log("STOP — phanh tất cả động cơ tại vị trí hiện tại.", "WARN")
        except UartError as e:
            self._log(str(e), "ERROR")

    def _on_reset(self):
        self.executor.reset()
        if self._connected() and self.backend.get_status() == RobotStatus.ERROR:
            try:
                self.backend.clear_fault()     # CLEAR cả 4 động cơ; không tự chạy lại
                self._log("Đã gửi CLEAR tới STM32 — FAULT được xóa. Kiểm tra cơ khí/encoder trước khi JOG.", "INFO")
            except UartError as e:
                self._log(str(e), "ERROR")
        self._program_just_completed = False
        self._log("RESET — không tự về Home.")
        self._refresh_progress_display()

    # ---------------- Callback từ ProgramExecutor ----------------
    def _on_step_started(self, index, step):
        self._log(f"Step {index + 1}: {describe_step(step)}")
        self._refresh_progress_display()

    def _on_step_done(self, index, step):
        self._log(f"STEP_DONE {index + 1}: {describe_step(step)}", "OK")
        self._refresh_progress_display()

    def _on_exec_state_change(self, old_state, new_state):
        self._log(f"Chương trình: {old_state.value} → {new_state.value}")
        if new_state == ExecState.COMPLETED:
            self._program_just_completed = True
        elif new_state == ExecState.RUNNING:
            self._program_just_completed = False
        self.pause_btn.configure(text="▶\nRESUME" if new_state == ExecState.PAUSED else "⏸\nPAUSE")
        self._refresh_progress_display()
        self._refresh_enabled_states()

    def _refresh_progress_display(self):
        current, total = self.executor.get_progress()
        self.progress_bar.set((current / total) if total else 0)
        self.progress_label.configure(text=f"{current} / {total}")
        self.step_desc_label.configure(text=self.executor.current_step_description())

    # ---------------- HOME / GRIP thủ công (sidebar QUICK ACTION) ----------------
    def _manual_action_allowed(self):
        return self.executor.state not in (ExecState.RUNNING, ExecState.PAUSED)

    def _on_home_click(self):
        if not self._connected():
            self._log("Bị chặn: chưa kết nối STM32.", "WARN")
            return
        if not self._manual_action_allowed():
            self._log("Không thể HOME khi chương trình đang chạy.", "WARN")
            return
        if self.backend.is_homing():
            self._log("Robot đang HOME rồi — đợi xong hoặc bấm STOP để hủy.", "WARN")
            return
        self._log("Yêu cầu HOME: 4 trục cùng chạy chậm tìm cảm biến home; chạm cảm biến thì dừng và đặt vị trí = vị trí home "
                  "(bấm STOP để hủy)...")
        try:
            self.backend.home()
        except UartError as e:
            self._log(str(e), "ERROR")
            return
        self._program_just_completed = False

    def _on_home_done(self, success):
        self._log("HOME_DONE — cả 4 trục đã chạm cảm biến home, vị trí đã được đặt theo cảm biến." if success else
                  "HOME_ERROR — HOME không hoàn tất (bị hủy, bị từ chối hoặc FAULT). Xem Log phía trên; nếu có FAULT hãy bấm RESET.",
                   "OK" if success else "ERROR")

    def _on_grip_click(self, action):
        if not self._connected():
            self._log("Bị chặn: chưa kết nối STM32.", "WARN")
            return
        if not self._manual_action_allowed():
            self._log("Không thể GRIP thủ công khi chương trình đang chạy.", "WARN")
            return
        try:
            self.backend.grip(action)
        except UartError as e:
            self._log(str(e), "ERROR")
            return
        self._log(f"GRIP {action} — {'đóng' if action == 'ON' else 'mở'} kẹp.")

    def _on_gripper_change(self, commanded, actual):
        self._log(f"Kẹp: {'ĐÓNG (ON)' if commanded == 'ON' else 'MỞ (OFF)'}", "OK")

    # ---------------- Bật/tắt điều khiển theo trạng thái ----------------
    def _refresh_enabled_states(self):
        connected = self._connected()
        jog_ok = self._jog_allowed()
        for row in list(self.jog_rows.values()) + list(self.cart_jog_rows.values()):
            row.set_enabled(jog_ok)
        if not connected:
            hint = "⚠ Chưa kết nối STM32 — vào Settings → Communication → Connect."
        elif self.backend.is_homing():
            hint = "⚠ Đang HOME (tìm cảm biến) — đợi xong hoặc bấm STOP."
        elif not self._home_ready():
            hint = "⚠ Chưa HOME — bấm HOME (Quick Action) để tìm vị trí gốc trước khi JOG / chạy chương trình."
        elif not jog_ok:
            hint = "⚠ JOG chỉ hoạt động ở Chế độ JOG và khi không có chương trình đang chạy."
        else:
            hint = ""
        self.jog_hint_label.configure(text=hint)
        self.move_xyz_btn.configure(state="normal" if jog_ok else "disabled")
        self.xyz_fill_btn.configure(state="normal" if connected else "disabled")

        manual_ok = connected and self._manual_action_allowed() and not self.backend.is_homing()
        self.home_btn.configure(state="normal" if manual_ok else "disabled")
        grip_ok = connected and self._manual_action_allowed()
        self.grip_on_btn.configure(state="normal" if grip_ok else "disabled")
        self.grip_off_btn.configure(state="normal" if grip_ok else "disabled")

        running = self.executor.state in (ExecState.RUNNING, ExecState.PAUSED)
        self.start_btn.configure(
            state="normal" if connected and self.executor.state != ExecState.RUNNING else "disabled")
        self.pause_btn.configure(state="normal" if running else "disabled")
        self.stop_btn.configure(state="normal" if connected else "disabled")
        self.header_stop_btn.configure(state="normal" if connected else "disabled")
