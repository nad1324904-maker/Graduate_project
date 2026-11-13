"""jog.py — Chế độ (JOG/Chương trình), JOG Control, Quick Action."""

import customtkinter as ctk

from comm.errors import UartError
from core.program_executor import ExecState
from ui.theme import AXES, COL_ACCENT, COL_TEXT, COL_TEXT_DIM, UNITS
from ui.widgets import Card, SidebarSection, JogRow


class JogMixin:
    # ============================================================
    # Chế độ hoạt động
    # ============================================================
    def _set_mode(self, mode):
        if self.executor.state in (ExecState.RUNNING, ExecState.PAUSED) and mode == "JOG":
            self._log("Không thể chuyển sang JOG khi chương trình đang chạy.", "WARN")
            return
        self.mode = mode
        for key, b in self._mode_section.buttons.items():
            if b.cget("state") == "disabled":
                continue
            active = (key == mode)
            b.configure(fg_color=COL_ACCENT if active else "transparent",
                        text_color="#ffffff" if active else COL_TEXT,
                        font=("Segoe UI Semibold" if active else "Segoe UI", 13))
        self._refresh_enabled_states()
        self._log(f"Chuyển chế độ → {mode}")

    # ============================================================
    # MODE / JOG CONTROL / QUICK ACTION — 3 panel riêng
    # ============================================================
    def _build_mode_card(self, parent):
        card = Card(parent, "MODE", "🔀")
        body = card.body
        mode_section = SidebarSection(body, "")
        mode_section.pack(fill="both", expand=True)
        mode_section.add_button("JOG", "👆", "JOG", lambda: self._set_mode("JOG"), active=True)
        mode_section.add_button("Chương trình", "</>", "PROGRAM", lambda: self._set_mode("Chương trình"))
        # "Tự động" chưa có yêu cầu chức năng cụ thể trong spec -> vô hiệu hóa.
        mode_section.add_button("Tự động", "▶", "AUTO", None, enabled=False)
        self._mode_section = mode_section
        return card

    def _build_jog_card(self, parent):
        card = Card(parent, "JOG CONTROL", "🕹️")
        body = card.body
        self.jog_rows = {}
        for axis in AXES:
            unit = UNITS[axis]
            presets = [0.1, 1, 5] if unit == "°" else [1, 5, 10]
            row = JogRow(body, axis, 1.00, unit, presets, on_jog=self._on_jog_request)
            row.pack(fill="x", pady=5)
            self.jog_rows[axis] = row
        self.jog_hint_label = ctk.CTkLabel(body, text="", font=("Segoe UI", 11),
                                            text_color=COL_TEXT_DIM, anchor="w")
        self.jog_hint_label.pack(fill="x", pady=(6, 0))
        # Công tắc debug: cho JOG/Move Here/START/Teach khi chưa HOME (vd chưa có cảm biến). Luôn TẮT mỗi lần mở app.
        self.skip_home_check = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(body, text="Bỏ qua kiểm tra HOME (chỉ để debug)", variable=self.skip_home_check,
                      command=self._on_toggle_skip_home, font=("Segoe UI", 11),
                      text_color=COL_TEXT_DIM).pack(anchor="w", pady=(8, 0))
        return card

    def _build_quick_action_card(self, parent):
        card = Card(parent, "QUICK ACTION", "⚡")
        body = card.body
        quick_section = SidebarSection(body, "")
        quick_section.pack(fill="both", expand=True)
        self.home_btn = quick_section.add_button("home", "🏠", "HOME", self._on_home_click)
        self.grip_on_btn = quick_section.add_button("grip_on", "🦾", "GRIP ON", lambda: self._on_grip_click("ON"))
        self.grip_off_btn = quick_section.add_button("grip_off", "🦾", "GRIP OFF", lambda: self._on_grip_click("OFF"))
        self.reset_btn_sidebar = quick_section.add_button("reset", "⟳", "RESET", self._on_reset)
        return card

    def _on_jog_request(self, axis, direction, step):
        if not self._jog_allowed():
            if not self._connected():
                self._log("Bị chặn: chưa kết nối STM32 (Settings → Communication → Connect).", "WARN")
            elif self.backend.is_homing():
                self._log("Bị chặn: robot đang HOME (tìm cảm biến) — đợi xong hoặc bấm STOP.", "WARN")
            elif not self._home_ready():
                self._log("Bị chặn: chưa HOME — hãy bấm HOME (Quick Action) để các trục tìm vị trí gốc trước khi JOG.", "WARN")
            else:
                self._log("Bị chặn: JOG chỉ cho phép ở Chế độ JOG và khi không có chương trình đang chạy.", "WARN")
            return
        before = self.backend.get_target_position()[axis]
        try:
            self.backend.jog(axis, direction, step)
        except UartError as e:
            self._log(str(e), "ERROR")
            return
        after = self.backend.get_target_position()[axis]
        sign = "+" if direction > 0 else "-"
        self._log(f"JOG {axis}{sign}{step:g}{UNITS[axis]} → target {before:.2f} → {after:.2f}{UNITS[axis]}")
        self._program_just_completed = False

    def _home_ready(self):
        """Đã biết vị trí gốc (các trục có cảm biến đã HOME) — hoặc đang bật 'Bỏ qua kiểm tra HOME' để debug."""
        return self.backend.is_homed() or self.skip_home_check.get()

    def _on_toggle_skip_home(self):
        if self.skip_home_check.get():
            self._log("Đã BẬT 'Bỏ qua kiểm tra HOME': vị trí hiển thị có thể KHÔNG đúng, JOG có thể đẩy trục vào chặn cơ khí "
                      "— chỉ dùng khi debug.", "WARN")
        else:
            self._log("Đã TẮT 'Bỏ qua kiểm tra HOME'.")
        self._refresh_enabled_states()

    def _jog_allowed(self):
        return (self._connected() and self.mode == "JOG"
                and self.executor.state not in (ExecState.RUNNING, ExecState.PAUSED)
                and not self.backend.is_homing()
                and self._home_ready())
