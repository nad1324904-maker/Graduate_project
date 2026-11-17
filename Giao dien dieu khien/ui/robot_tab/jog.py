"""jog.py — Chế độ (JOG/Chương trình), khung JOG (theo khớp hoặc X Y Z θ) + HOME + bật/tắt kẹp."""

import customtkinter as ctk

from comm.errors import UartError
from core.kinematics import IKError, forward_kinematics, inverse_kinematics
from core.program_executor import ExecState
from ui.theme import (
    AXES, COL_ACCENT, COL_ACCENT_HOVER, COL_AMBER, COL_BTN_DARK, COL_BTN_DARK_HOVER, COL_TEXT_DIM, SEGMENTED_STYLE,
    UNITS
)
from ui.widgets import Card, JogRow

# JOG theo tọa độ đầu công tác (TCP): tên, đơn vị, 3 bước nhanh (bước giữa là mặc định)
CART_AXES = (("X", "mm", [0.5, 1, 5]), ("Y", "mm", [0.5, 1, 5]), ("Z", "mm", [1, 5, 10]), ("θ", "°", [0.1, 1, 5]))
JOG_SPACE_JOINT, JOG_SPACE_CART = "Khớp  J1 J2 J3 Z", "Tọa độ  X Y Z θ"
# Chế độ: giá trị nội bộ (self.mode) <-> nhãn trên nút gạt
MODE_LABELS = {"JOG": "JOG", "Chương trình": "CHƯƠNG TRÌNH"}


class JogMixin:
    # ============================================================
    # Chế độ hoạt động
    # ============================================================
    def _on_mode_seg(self, label):
        self._set_mode(next(k for k, v in MODE_LABELS.items() if v == label))

    def _set_mode(self, mode):
        """Chế độ JOG: cho JOG / Move. Chế độ CHƯƠNG TRÌNH: cho START, khóa JOG. Nút gạt nằm trong khung Chạy chương trình."""
        if self.executor.state in (ExecState.RUNNING, ExecState.PAUSED) and mode == "JOG":
            self._log("Không thể chuyển sang JOG khi chương trình đang chạy.", "WARN")
            self.mode_seg.set(MODE_LABELS[self.mode])          # trả nút gạt về chế độ cũ
            return
        self.mode = mode
        self.mode_seg.set(MODE_LABELS[mode])
        self._refresh_enabled_states()
        self._log(f"Chuyển chế độ → {MODE_LABELS[mode]}")

    # ============================================================
    # JOG (khớp / tọa độ) + HOME + kẹp
    # ============================================================
    def _build_jog_card(self, parent):
        card = Card(parent, "JOG CONTROL", "🕹️")
        body = card.body
        # Chọn JOG theo từng khớp hay theo tọa độ đầu công tác (động học ngược + đồng bộ khớp)
        self.jog_space_seg = ctk.CTkSegmentedButton(
            body, values=[JOG_SPACE_JOINT, JOG_SPACE_CART], command=self._on_jog_space_change, height=30,
            font=("Segoe UI Semibold", 11), **SEGMENTED_STYLE)
        self.jog_space_seg.set(JOG_SPACE_JOINT)
        self.jog_space_seg.pack(fill="x", pady=(0, 6))

        rows_box = ctk.CTkFrame(body, fg_color="transparent")
        rows_box.pack(fill="x")
        self._jog_joint_frame = ctk.CTkFrame(rows_box, fg_color="transparent")
        self._jog_cart_frame = ctk.CTkFrame(rows_box, fg_color="transparent")
        self.jog_rows = {}
        for axis in AXES:
            unit = UNITS[axis]
            presets = [0.1, 1, 5] if unit == "°" else [1, 5, 10]
            row = JogRow(self._jog_joint_frame, axis, 1.00, unit, presets, on_jog=self._on_jog_request)
            row.pack(fill="x", pady=5)
            self.jog_rows[axis] = row
        self.cart_jog_rows = {}
        for name, unit, presets in CART_AXES:
            row = JogRow(self._jog_cart_frame, name, 1.00, unit, presets, on_jog=self._on_cart_jog_request)
            row.pack(fill="x", pady=5)
            self.cart_jog_rows[name] = row
        self._jog_joint_frame.pack(fill="x")
        self.jog_hint_label = ctk.CTkLabel(body, text="", font=("Segoe UI", 11),
                                            text_color=COL_AMBER, anchor="w", justify="left")
        self.jog_hint_label.pack(fill="x", pady=(6, 0))
        # tự xuống dòng theo độ rộng khung (trước đây dòng nhắc dài bị cắt chữ ở màn hình hẹp)
        body.bind("<Configure>", lambda e: self.jog_hint_label.configure(
            wraplength=max(200, int(e.width / self.jog_hint_label._get_widget_scaling()) - 10)), add="+")
        # HOME + kẹp (trước đây là khung QUICK ACTION riêng)
        actions = ctk.CTkFrame(body, fg_color="transparent")
        actions.pack(fill="x", pady=(10, 0))
        self.home_btn = ctk.CTkButton(actions, text="🏠  HOME", height=40, corner_radius=10,
                                      fg_color=COL_ACCENT, hover_color=COL_ACCENT_HOVER,
                                      font=("Segoe UI Semibold", 13), command=self._on_home_click)
        self.home_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.grip_toggle_btn = ctk.CTkButton(actions, text="🦾  Kẹp: MỞ", height=40, corner_radius=10,
                                             fg_color=COL_BTN_DARK, hover_color=COL_BTN_DARK_HOVER,
                                             font=("Segoe UI Semibold", 13), command=self._on_grip_toggle)
        self.grip_toggle_btn.pack(side="left", fill="x", expand=True, padx=(4, 0))
        # Công tắc debug: cho JOG/Move Here/START/Teach khi chưa HOME (vd chưa có cảm biến). Luôn TẮT mỗi lần mở app.
        self.skip_home_check = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(body, text="Bỏ qua kiểm tra HOME (chỉ để debug)", variable=self.skip_home_check,
                      command=self._on_toggle_skip_home, font=("Segoe UI", 11),
                      text_color=COL_TEXT_DIM).pack(anchor="w", pady=(10, 0))
        return card

    def _on_grip_toggle(self):
        """1 nút cho kẹp: đang MỞ thì đóng, đang ĐÓNG thì mở (trạng thái theo firmware báo về)."""
        closed = self.backend.get_gripper_state()["commanded"] == "ON"
        self._on_grip_click("OFF" if closed else "ON")

    def _update_grip_button(self):
        closed = self._connected() and self.backend.get_gripper_state()["commanded"] == "ON"
        self.grip_toggle_btn.configure(text="🦾  Kẹp: ĐÓNG  → mở" if closed else "🦾  Kẹp: MỞ  → đóng")

    def _on_jog_space_change(self, value):
        """Đổi bảng JOG: theo khớp (J1 J2 J3 Z) hoặc theo tọa độ đầu công tác (X Y Z θ)."""
        cart = (value == JOG_SPACE_CART)
        (self._jog_joint_frame if cart else self._jog_cart_frame).pack_forget()
        (self._jog_cart_frame if cart else self._jog_joint_frame).pack(fill="x")
        self._log("JOG theo tọa độ X Y Z θ (động học ngược, các khớp chạy đồng bộ)." if cart else "JOG theo từng khớp.")

    def _log_jog_blocked(self):
        if not self._connected():
            self._log("Bị chặn: chưa kết nối STM32 (Settings → Communication → Connect).", "WARN")
        elif self.backend.is_homing():
            self._log("Bị chặn: robot đang HOME (tìm cảm biến) — đợi xong hoặc bấm STOP.", "WARN")
        elif not self._home_ready():
            self._log("Bị chặn: chưa HOME — hãy bấm HOME để các trục tìm vị trí gốc trước khi JOG.", "WARN")
        else:
            self._log("Bị chặn: JOG chỉ cho phép ở Chế độ JOG và khi không có chương trình đang chạy.", "WARN")

    def _on_cart_jog_request(self, name, direction, step):
        """JOG theo tọa độ: lấy tư thế ĐÍCH hiện tại (không lấy vị trí thực, để sai số vùng chết không cộng dồn qua
        nhiều lần bấm), cộng bước vào X/Y/Z/θ, giải động học ngược rồi GOTO. Các khớp được đồng bộ trong backend nên
        đầu công tác đi gần đường thẳng. JOG Z chỉ chạy trục Z; JOG θ chỉ xoay J3 (đầu công tác đứng yên)."""
        if not self._jog_allowed():
            self._log_jog_blocked()
            return
        if step <= 0:
            self._log(f"JOG {name}: bước phải > 0.", "WARN")
            return
        joints_now = self.backend.get_target_position()
        x, y, z, th = forward_kinematics(joints_now["J1"], joints_now["J2"], joints_now["J3"], joints_now["Z"])
        pose = {"X": x, "Y": y, "Z": z, "θ": th}
        pose[name] += direction * step
        try:
            joints = inverse_kinematics(pose["X"], pose["Y"], pose["Z"], pose["θ"],
                                        limits=getattr(self.backend, "joint_limits", None), current=joints_now)
        except IKError as e:
            self._log(f"JOG {name}: {e}", "ERROR")
            return
        try:
            self.backend.send_absolute_target(joints)
        except UartError as e:
            self._log(str(e), "ERROR")
            return
        unit = "°" if name == "θ" else "mm"
        sign = "+" if direction > 0 else "-"
        self._log(f"JOG {name}{sign}{step:g}{unit} → X={pose['X']:.2f} Y={pose['Y']:.2f} Z={pose['Z']:.2f} "
                  f"θ={(pose['θ'] + 180) % 360 - 180:.2f}°  ⇒  "
                  + "  ".join(f"{a}={joints[a]:.2f}{UNITS[a]}" for a in AXES))
        self._program_just_completed = False

    def _on_jog_request(self, axis, direction, step):
        if not self._jog_allowed():
            self._log_jog_blocked()
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
