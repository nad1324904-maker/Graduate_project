"""control.py — Khung CHẠY CHƯƠNG TRÌNH (chế độ, START/PAUSE/RESET, Step đang chạy), STOP, HOME/GRIP,
callback của ProgramExecutor, bật/tắt nút theo trạng thái."""

import customtkinter as ctk

from comm.backend_base import RobotStatus
from comm.errors import UartError
from core.program_store import describe_step
from core.program_executor import ExecState, ExecutorError
from ui.robot_tab.jog import MODE_LABELS
from ui.theme import (
    COL_AMBER, COL_AMBER_HOVER, COL_BTN_DARK, COL_BTN_DARK_HOVER, COL_GRAY_BTN, COL_GRAY_BTN_HOVER, COL_GREEN,
    COL_GREEN_HOVER, COL_INPUT, COL_TEXT, COL_TEXT_DIM, SEGMENTED_STYLE
)
from ui.widgets import Card, StepTableRow


class ControlMixin:
    # ============================================================
    # CHẠY CHƯƠNG TRÌNH (tab Vận hành)
    # ============================================================
    def _build_run_card(self, parent):
        card = Card(parent, "CHẠY CHƯƠNG TRÌNH", "▶")
        body = card.body

        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(row, text="Chế độ", font=("Segoe UI", 11), text_color=COL_TEXT_DIM, width=70,
                     anchor="w").pack(side="left")
        self.mode_seg = ctk.CTkSegmentedButton(row, values=list(MODE_LABELS.values()), command=self._on_mode_seg,
                                               height=30, font=("Segoe UI Semibold", 11), **SEGMENTED_STYLE)
        self.mode_seg.set(MODE_LABELS[self.mode])
        self.mode_seg.pack(side="left", fill="x", expand=True)

        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(row, text="Program", font=("Segoe UI", 11), text_color=COL_TEXT_DIM, width=70,
                     anchor="w").pack(side="left")
        self.run_program_option = ctk.CTkOptionMenu(
            row, values=["(chưa có)"], fg_color=COL_INPUT, button_color=COL_BTN_DARK,
            button_hover_color=COL_BTN_DARK_HOVER, height=30, font=("Segoe UI Semibold", 12),
            command=self._on_select_program_from_menu)
        self.run_program_option.pack(side="left", fill="x", expand=True)

        self.progress_bar = ctk.CTkProgressBar(body, height=10, progress_color=COL_GREEN)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", pady=(2, 4))
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x")
        self.progress_label = ctk.CTkLabel(row, text="0 / 0", font=("Segoe UI Semibold", 12), text_color=COL_TEXT)
        self.progress_label.pack(side="left")
        self.step_desc_label = ctk.CTkLabel(row, text="—", font=("Segoe UI", 11), text_color=COL_TEXT_DIM,
                                            anchor="e")
        self.step_desc_label.pack(side="right")

        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.pack(fill="x", pady=(8, 8))
        buttons.grid_columnconfigure((0, 1, 2), weight=1, uniform="run")
        self.start_btn = ctk.CTkButton(buttons, text="▶  START", height=42, corner_radius=10, fg_color=COL_GREEN,
                                       hover_color=COL_GREEN_HOVER, font=("Segoe UI Semibold", 13),
                                       command=self._on_start)
        self.start_btn.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        self.pause_btn = ctk.CTkButton(buttons, text="⏸  PAUSE", height=42, corner_radius=10, fg_color=COL_AMBER,
                                       hover_color=COL_AMBER_HOVER, font=("Segoe UI Semibold", 13),
                                       command=self._on_pause)
        self.pause_btn.grid(row=0, column=1, sticky="ew", padx=3)
        self.reset_btn = ctk.CTkButton(buttons, text="⟳  RESET", height=42, corner_radius=10, fg_color=COL_GRAY_BTN,
                                       hover_color=COL_GRAY_BTN_HOVER, font=("Segoe UI Semibold", 13),
                                       command=self._on_reset)
        self.reset_btn.grid(row=0, column=2, sticky="ew", padx=(3, 0))

        # Danh sách Step (chỉ xem): tô sáng Step đang chạy. Sửa chương trình ở tab Lập trình.
        ctk.CTkLabel(body, text="Các Step (sửa ở tab Lập trình)", font=("Segoe UI Semibold", 10),
                     text_color=COL_TEXT_DIM, anchor="w").pack(fill="x")
        self.run_step_frame = ctk.CTkScrollableFrame(body, fg_color=COL_INPUT, corner_radius=8, height=60,
                                                     scrollbar_button_color=COL_BTN_DARK)
        self.run_step_frame.pack(fill="both", expand=True, pady=(2, 0))
        return card

    def _refresh_run_steps(self):
        """Vẽ lại danh sách Step của chương trình đang chọn, tô sáng Step đang chạy (gọi khi đổi chương trình / Step)."""
        for w in self.run_step_frame.winfo_children():
            w.destroy()
        if not self.selected_program or not self.program_store.exists(self.selected_program):
            ctk.CTkLabel(self.run_step_frame, text="Chưa chọn chương trình.", font=("Segoe UI", 11),
                         text_color=COL_TEXT_DIM).pack(pady=8)
            return
        running = (self.executor.program_name == self.selected_program
                   and self.executor.state in (ExecState.RUNNING, ExecState.PAUSED))
        current = self.executor.current_index if running else None
        for i, step in enumerate(self.program_store.get(self.selected_program)["steps"]):
            StepTableRow(self.run_step_frame, i, step, selected=(i == current), on_click=lambda: None).pack(
                fill="x", pady=1)

    def _on_start(self):
        if not self._connected():
            self._log("Bị chặn: chưa kết nối STM32 (Settings → Communication → Connect).", "WARN")
            return
        if self.backend.is_homing():
            self._log("Bị chặn: robot đang HOME (tìm cảm biến) — đợi xong hoặc bấm STOP.", "WARN")
            return
        if self.backend.is_estop():
            self._log("Bị chặn: đang E-STOP — bấm RESET rồi HOME trước khi chạy chương trình.", "WARN")
            return
        if not self._home_ready():
            self._log("Bị chặn: chưa HOME — hãy bấm HOME trước khi chạy chương trình.", "WARN")
            return
        if self.mode != "Chương trình":
            self._log("Bị chặn: START chỉ cho phép ở chế độ CHƯƠNG TRÌNH (nút gạt Chế độ ngay phía trên).", "WARN")
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

    def _on_estop(self):
        """E-STOP mềm: dừng chương trình + báo STM32 (ESTOP 1) khóa mọi chuyển động và bỏ mốc vị trí.
        Master sẽ gọi backend.emergency_stop() y như vậy khi PLC báo E-Stop. Gỡ: RESET rồi HOME."""
        if not self._connected():
            return
        try:
            if self.executor.state in (ExecState.RUNNING, ExecState.PAUSED):
                self.executor.stop()
            self.backend.emergency_stop()
            self._log("E-STOP — STM32 phanh cả 4 động cơ và khóa chuyển động. Bấm RESET rồi HOME để chạy lại.", "ERROR")
        except UartError as e:
            self._log(str(e), "ERROR")

    def _on_reset(self):
        self.executor.reset()
        if self._connected() and self.backend.is_estop():
            try:
                self.backend.reset_estop()     # ESTOP 0: mở khóa + xóa FAULT; robot đã mất mốc vị trí
                self._log("Đã gửi RESET E-Stop (ESTOP 0) tới STM32. Robot đã mất mốc vị trí — bấm HOME trước khi chạy.", "INFO")
            except UartError as e:
                self._log(str(e), "ERROR")
        elif self._connected() and self.backend.get_status() == RobotStatus.ERROR:
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
        self.pause_btn.configure(text="▶  RESUME" if new_state == ExecState.PAUSED else "⏸  PAUSE")
        self._refresh_progress_display()
        self._refresh_enabled_states()

    def _refresh_progress_display(self):
        current, total = self.executor.get_progress()
        self.progress_bar.set((current / total) if total else 0)
        self.progress_label.configure(text=f"{current} / {total}")
        self.step_desc_label.configure(text=self.executor.current_step_description())
        self._refresh_run_steps()

    # ---------------- HOME / GRIP thủ công (khung JOG) ----------------
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
        if self.backend.is_estop():
            self._log("Đang E-STOP — bấm RESET trước rồi mới HOME.", "WARN")
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
        self._update_grip_button()

    # ---------------- Bật/tắt điều khiển theo trạng thái ----------------
    def _refresh_enabled_states(self):
        connected = self._connected()
        jog_ok = self._jog_allowed()
        for row in list(self.jog_rows.values()) + list(self.cart_jog_rows.values()):
            row.set_enabled(jog_ok)
        estop = connected and self.backend.is_estop()
        if not connected:
            hint = "⚠ Chưa kết nối STM32 — vào Settings → Communication → Connect."
        elif estop:
            hint = "⛔ E-STOP — mọi chuyển động bị khóa. Bấm RESET (khung Chạy chương trình) rồi HOME lại."
        elif self.backend.is_homing():
            hint = "⚠ Đang HOME (tìm cảm biến) — đợi xong hoặc bấm STOP."
        elif not self._home_ready():
            hint = "⚠ Chưa HOME — bấm HOME (bên dưới) để tìm vị trí gốc trước khi JOG / chạy chương trình."
        elif not jog_ok:
            hint = "⚠ JOG chỉ hoạt động ở chế độ JOG (nút gạt trong khung Chạy chương trình) và khi không chạy chương trình."
        else:
            hint = ""
        self.jog_hint_label.configure(text=hint)
        self.move_xyz_btn.configure(state="normal" if jog_ok else "disabled")
        self.xyz_fill_btn.configure(state="normal" if connected else "disabled")
        self.move_here_btn.configure(state="normal" if jog_ok and self.loaded_reference else "disabled")
        self.teach_quick_btn.configure(state="normal" if connected and self._home_ready() else "disabled")

        manual_ok = connected and self._manual_action_allowed() and not self.backend.is_homing() and not estop
        self.home_btn.configure(state="normal" if manual_ok else "disabled")
        grip_ok = connected and self._manual_action_allowed() and not estop
        self.grip_toggle_btn.configure(state="normal" if grip_ok else "disabled")
        self._update_grip_button()

        running = self.executor.state in (ExecState.RUNNING, ExecState.PAUSED)
        self.start_btn.configure(
            state="normal" if connected and self.executor.state != ExecState.RUNNING else "disabled")
        self.pause_btn.configure(state="normal" if running else "disabled")
        self.header_stop_btn.configure(state="normal" if connected else "disabled")
        self.header_estop_btn.configure(state="normal" if connected and not estop else "disabled")
