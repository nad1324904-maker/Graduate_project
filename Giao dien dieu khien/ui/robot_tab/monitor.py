"""monitor.py — Header status badge + OPERATION MONITOR (actual/target/TCP/Move to XYZθ/mini badge)."""

import customtkinter as ctk

from comm.backend_base import RobotStatus
from comm.errors import UartError
from core.kinematics import IKError, forward_kinematics, inverse_kinematics
from ui.theme import (
    AXES, COL_ACCENT, COL_ACCENT_HOVER, COL_AMBER, COL_BG as COL_BG_ENTRY, COL_BTN_DARK, COL_BTN_DARK_HOVER,
    COL_GREEN, COL_INPUT, COL_TEXT, COL_TEXT_DIM, COL_TEXT_DISABLED, STATUS_COLOR, STATUS_LABEL, UNITS
)
from ui.widgets import Card


class MonitorMixin:
    # ============================================================
    # Robot Status (header badge)
    # ============================================================
    def _refresh_status_display(self):
        if not self._connected():
            self.status_badge.set_value("OFFLINE", COL_TEXT_DIM)
            return
        backend_status = self.backend.get_status()
        if self._program_just_completed and backend_status == RobotStatus.READY:
            display_status = RobotStatus.DONE
        else:
            display_status = backend_status
        self.status_badge.set_value(STATUS_LABEL[display_status], STATUS_COLOR[display_status])

    # ============================================================
    # OPERATION MONITOR
    # ============================================================
    def _build_monitor_card(self, parent):
        card = Card(parent, "OPERATION MONITOR", "🖥️")
        body = card.body
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)

        # ---- Robot Position (Actual) ----
        pos_box = ctk.CTkFrame(body, fg_color=COL_INPUT, corner_radius=10)
        pos_box.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        ctk.CTkLabel(pos_box, text="📍 Robot Position (Actual)", font=("Segoe UI Semibold", 11),
                     text_color=COL_TEXT).pack(anchor="w", padx=10, pady=(8, 4))
        self.pos_actual_labels = {}
        self.pos_target_labels = {}
        self.pos_dots = {}
        for axis in AXES:
            row = ctk.CTkFrame(pos_box, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=3)
            dot = ctk.CTkLabel(row, text="●", font=("Segoe UI", 10), text_color=COL_GREEN, width=14)
            dot.pack(side="left")
            ctk.CTkLabel(row, text=axis, font=("Segoe UI Semibold", 12),
                         text_color=COL_TEXT, width=26, anchor="w").pack(side="left")
            actual_lbl = ctk.CTkLabel(row, text="0.00°", font=("Segoe UI Semibold", 12), text_color=COL_TEXT)
            actual_lbl.pack(side="left", padx=(4, 10))
            ctk.CTkLabel(row, text="Target", font=("Segoe UI", 9), text_color=COL_TEXT_DIM).pack(side="left")
            target_lbl = ctk.CTkLabel(row, text="0.00°", font=("Segoe UI", 10), text_color=COL_ACCENT)
            target_lbl.pack(side="left", padx=(4, 0))
            self.pos_actual_labels[axis] = actual_lbl
            self.pos_target_labels[axis] = target_lbl
            self.pos_dots[axis] = dot
        ctk.CTkFrame(pos_box, fg_color="transparent", height=4).pack()

        # ---- TCP Position (Actual) ----
        tcp_box = ctk.CTkFrame(body, fg_color=COL_INPUT, corner_radius=10)
        tcp_box.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        ctk.CTkLabel(tcp_box, text="🎯 TCP Position (Actual)", font=("Segoe UI Semibold", 11),
                     text_color=COL_TEXT).pack(anchor="w", padx=10, pady=(8, 4))
        self.tcp_labels = {}
        for name in ["X", "Y", "Z", "θ"]:
            row = ctk.CTkFrame(tcp_box, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=3)
            ctk.CTkLabel(row, text="●", font=("Segoe UI", 10), text_color=COL_ACCENT, width=14).pack(side="left")
            ctk.CTkLabel(row, text=name, font=("Segoe UI Semibold", 12),
                         text_color=COL_TEXT, width=18, anchor="w").pack(side="left")
            lbl = ctk.CTkLabel(row, text="0.00 mm", font=("Segoe UI Semibold", 12), text_color=COL_TEXT)
            lbl.pack(side="right")
            self.tcp_labels[name] = lbl
        ctk.CTkLabel(tcp_box, text="FK dùng h1/l1/l2/h2 trong Settings (mm).",
                     font=("Segoe UI", 9), text_color=COL_TEXT_DISABLED,
                     wraplength=230, justify="left").pack(anchor="w", padx=10, pady=(2, 8))

        # ---- Tham chiếu đã Load + Move Here ----
        ref_row = ctk.CTkFrame(body, fg_color="transparent")
        ref_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.ref_label = ctk.CTkLabel(ref_row, text="Chưa chọn Point tham chiếu nào.",
                                       font=("Segoe UI", 11), text_color=COL_TEXT_DIM, anchor="w")
        self.ref_label.pack(side="left", fill="x", expand=True)
        self.move_here_btn = ctk.CTkButton(ref_row, text="▶ Move Here", width=110, height=28, corner_radius=8,
                                            fg_color=COL_ACCENT, hover_color=COL_ACCENT_HOVER,
                                            font=("Segoe UI Semibold", 11), state="disabled",
                                            command=self._on_move_to_reference)
        self.move_here_btn.pack(side="right")

        # ---- Move to XYZθ (động học ngược) ----
        xyz_row = ctk.CTkFrame(body, fg_color=COL_INPUT, corner_radius=10)
        xyz_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ctk.CTkLabel(xyz_row, text="🧭 Move to", font=("Segoe UI Semibold", 11),
                     text_color=COL_TEXT).pack(side="left", padx=(10, 6), pady=8)
        self.xyz_entries = {}
        for name, unit in (("X", "mm"), ("Y", "mm"), ("Z", "mm"), ("θ", "°")):
            ctk.CTkLabel(xyz_row, text=name, font=("Segoe UI Semibold", 11),
                         text_color=COL_TEXT_DIM).pack(side="left", padx=(4, 2))
            entry = ctk.CTkEntry(xyz_row, width=62, height=28, fg_color=COL_BG_ENTRY, border_width=0,
                                  justify="center", font=("Segoe UI", 11), text_color=COL_TEXT,
                                  placeholder_text=unit)
            entry.pack(side="left", padx=(0, 2))
            entry.bind("<Return>", lambda _e: self._on_move_xyz())
            self.xyz_entries[name] = entry
        self.move_xyz_btn = ctk.CTkButton(xyz_row, text="▶ Move", width=70, height=28, corner_radius=8,
                                           fg_color=COL_ACCENT, hover_color=COL_ACCENT_HOVER,
                                           font=("Segoe UI Semibold", 11), state="disabled",
                                           command=self._on_move_xyz)
        self.move_xyz_btn.pack(side="right", padx=(4, 10))
        self.xyz_fill_btn = ctk.CTkButton(xyz_row, text="⤓ Hiện tại", width=78, height=28, corner_radius=8,
                                           fg_color=COL_BTN_DARK, hover_color=COL_BTN_DARK_HOVER,
                                           font=("Segoe UI", 11), state="disabled",
                                           command=self._on_fill_xyz_from_actual)
        self.xyz_fill_btn.pack(side="right", padx=4)

        # ---- Mini status badges ----
        mini_row = ctk.CTkFrame(body, fg_color="transparent")
        mini_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        for i in range(4):
            mini_row.grid_columnconfigure(i, weight=1)
        self.mini_status = self._mini_badge(mini_row, "📶", "Robot Status", 0)
        self.mini_homed = self._mini_badge(mini_row, "🏠", "Homed", 1)
        self.mini_paused = self._mini_badge(mini_row, "⏸", "Motion Paused", 2)
        self.mini_gripper = self._mini_badge(mini_row, "🦾", "Gripper", 3)
        return card

    # ---------------- Move to XYZθ ----------------
    def _on_fill_xyz_from_actual(self):
        """Điền ô X/Y/Z/θ bằng vị trí TCP thực hiện tại (FK) — tiện để sửa 1 trục rồi Move."""
        if not self._connected():
            return
        a = self.backend.get_actual_position()
        values = dict(zip(("X", "Y", "Z", "θ"), forward_kinematics(a["J1"], a["J2"], a["J3"], a["Z"])))
        for name, entry in self.xyz_entries.items():
            entry.delete(0, "end")
            entry.insert(0, f"{values[name]:.2f}")

    def _on_move_xyz(self):
        """Động học ngược: tọa độ TCP -> góc khớp (trong giới hạn, nghiệm gần tư thế hiện tại nhất) -> GOTO.
        Các trục chạy độc lập nên robot tới ĐÚNG điểm đích nhưng đường đi ở giữa KHÔNG phải đường thẳng."""
        if not self._jog_allowed():
            self._log("Bị chặn: Move XYZθ chỉ hoạt động khi đã kết nối, đã HOME, ở Chế độ JOG và không chạy chương trình.", "WARN")
            return
        try:
            target = {name: float(entry.get().replace(",", ".")) for name, entry in self.xyz_entries.items()}
        except ValueError:
            self._log("Move XYZθ: nhập đủ X, Y, Z (mm) và θ (°) dạng số — bấm '⤓ Hiện tại' để điền sẵn vị trí đang đứng.", "WARN")
            return
        try:
            joints = inverse_kinematics(target["X"], target["Y"], target["Z"], target["θ"],
                                        limits=getattr(self.backend, "joint_limits", None),
                                        current=self.backend.get_actual_position())
        except IKError as e:
            self._log(f"Move XYZθ: {e}", "ERROR")
            return
        try:
            self.backend.send_absolute_target(joints)
        except UartError as e:
            self._log(str(e), "ERROR")
            return
        self._log(f"Move XYZθ → X={target['X']:g} Y={target['Y']:g} Z={target['Z']:g} θ={target['θ']:g}°  ⇒  "
                  + "  ".join(f"{a}={joints[a]:.2f}{UNITS[a]}" for a in AXES))
        self._program_just_completed = False

    def _mini_badge(self, parent, icon, label, col):
        box = ctk.CTkFrame(parent, fg_color=COL_INPUT, corner_radius=8)
        box.grid(row=0, column=col, sticky="ew", padx=3)
        ctk.CTkLabel(box, text=f"{icon} {label}", font=("Segoe UI", 10),
                     text_color=COL_TEXT_DIM).pack(anchor="w", padx=8, pady=(6, 0))
        val = ctk.CTkLabel(box, text="—", font=("Segoe UI Semibold", 12), text_color=COL_TEXT)
        val.pack(anchor="w", padx=8, pady=(0, 6))
        return val

    def _refresh_position_display(self):
        if not self._connected():          # chưa kết nối thì không có số liệu thật để hiển thị
            for axis in AXES:
                self.pos_actual_labels[axis].configure(text="—")
                self.pos_target_labels[axis].configure(text="—")
                self.pos_dots[axis].configure(text_color=COL_TEXT_DISABLED)
            for lbl in self.tcp_labels.values():
                lbl.configure(text="—")
            self.mini_status.configure(text="OFFLINE", text_color=COL_TEXT_DIM)
            for lbl in (self.mini_homed, self.mini_paused, self.mini_gripper):
                lbl.configure(text="—", text_color=COL_TEXT_DIM)
            return
        actual = self.backend.get_actual_position()
        target = self.backend.get_target_position()
        moving = self.backend.is_moving()
        for axis in AXES:
            self.pos_actual_labels[axis].configure(text=f"{actual[axis]:.2f}{UNITS[axis]}")
            self.pos_target_labels[axis].configure(text=f"{target[axis]:.2f}{UNITS[axis]}")
            self.pos_dots[axis].configure(text_color=COL_ACCENT if moving else COL_GREEN)

        x, y, z, th = forward_kinematics(actual["J1"], actual["J2"], actual["J3"], actual["Z"])
        self.tcp_labels["X"].configure(text=f"{x:.2f} mm")
        self.tcp_labels["Y"].configure(text=f"{y:.2f} mm")
        self.tcp_labels["Z"].configure(text=f"{z:.2f} mm")
        self.tcp_labels["θ"].configure(text=f"{th:.2f}°")

        self.mini_status.configure(text=STATUS_LABEL[self.backend.get_status()],
                                    text_color=STATUS_COLOR[self.backend.get_status()])
        self.mini_homed.configure(text="YES" if self.backend.is_homed() else "NO",
                                   text_color=COL_GREEN if self.backend.is_homed() else COL_TEXT_DIM)
        self.mini_paused.configure(text="YES" if self.backend.is_motion_paused() else "NO",
                                    text_color=COL_AMBER if self.backend.is_motion_paused() else COL_TEXT_DIM)
        grip = self.backend.get_gripper_state()
        state = grip["actual"] or grip["commanded"]                     # không có cảm biến kẹp: hiển thị trạng thái đã ra lệnh
        self.mini_gripper.configure(text=state, text_color=COL_GREEN if state == "ON" else COL_TEXT_DIM)
