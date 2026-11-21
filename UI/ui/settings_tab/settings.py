"""settings.py — Màn hình Settings: 5 panel cấu hình + đọc/ghi/Save/Apply robot_config.json."""

import os

import customtkinter as ctk

from comm.errors import UartError
from core import kinematics
from core import robot_config
from ui.theme import (
    AXES, COL_ACCENT, COL_ACCENT_HOVER, COL_BG, COL_BTN_DARK, COL_BTN_DARK_HOVER, COL_GREEN,
    COL_GREEN_HOVER, COL_INPUT, COL_RED, COL_TEXT, COL_TEXT_DIM, COL_TEXT_DISABLED, UNITS
)
from ui.widgets import Card


class SettingsMixin:
    # ============================================================
    # MÀN HÌNH CÀI ĐẶT (Robot Configuration) — 5 panel, không chia tab
    # ============================================================
    def _build_settings_view(self):
        outer = ctk.CTkScrollableFrame(self, fg_color=COL_BG,
                                        scrollbar_button_color=COL_BTN_DARK,
                                        scrollbar_button_hover_color=COL_BTN_DARK_HOVER)
        outer.grid(row=1, column=0, sticky="nsew")
        outer.grid_columnconfigure(0, weight=1)
        self.settings_view = outer

        self.set_entries = {"kinematics": {}, "joint_limits": {}, "home_position": {}, "encoder": {},
                             "motion_profile": {}, "pid": {}, "fault_limits": {}}

        area = ctk.CTkFrame(outer, fg_color="transparent")
        area.pack(fill="x", padx=4, pady=4)

        # ---- Thanh trên: back + tiêu đề + Load/Save/Apply ----
        top = ctk.CTkFrame(area, fg_color="transparent")
        top.pack(fill="x", pady=(0, 4))
        left = ctk.CTkFrame(top, fg_color="transparent")
        left.pack(side="left")
        ctk.CTkButton(left, text="←", width=36, height=36, corner_radius=8,
                      fg_color=COL_BTN_DARK, hover_color=COL_BTN_DARK_HOVER,
                      font=("Segoe UI", 15), command=lambda: self._set_active_tab("operate")).pack(side="left", padx=(0, 12))
        title_box = ctk.CTkFrame(left, fg_color="transparent")
        title_box.pack(side="left")
        ctk.CTkLabel(title_box, text="⚙ Robot Configuration", font=("Segoe UI Semibold", 18),
                     text_color=COL_TEXT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(title_box, text="Cấu hình tham số robot và lưu ra file",
                     font=("Segoe UI", 11), text_color=COL_TEXT_DIM, anchor="w").pack(anchor="w")

        right = ctk.CTkFrame(top, fg_color="transparent")
        right.pack(side="right")
        ctk.CTkButton(right, text="📄 Load from File", height=36, corner_radius=8,
                      fg_color=COL_BTN_DARK, hover_color=COL_BTN_DARK_HOVER,
                      font=("Segoe UI Semibold", 12), command=self._on_settings_load).pack(side="left", padx=4)
        ctk.CTkButton(right, text="💾 Save", height=36, corner_radius=8,
                      fg_color=COL_ACCENT, hover_color=COL_ACCENT_HOVER,
                      font=("Segoe UI Semibold", 12), command=self._on_settings_save).pack(side="left", padx=4)
        ctk.CTkButton(right, text="✓ Apply", height=36, corner_radius=8,
                      fg_color=COL_GREEN, hover_color=COL_GREEN_HOVER,
                      font=("Segoe UI Semibold", 12), command=self._on_settings_apply).pack(side="left", padx=4)

        status_row = ctk.CTkFrame(area, fg_color="transparent")
        status_row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(status_row, text=f"📁 {os.path.basename(robot_config.DEFAULT_CONFIG_FILE)}",
                     font=("Segoe UI", 11), text_color=COL_TEXT_DIM).pack(side="left")
        self.settings_status_label = ctk.CTkLabel(status_row, text="", font=("Segoe UI Semibold", 11),
                                                    text_color=COL_TEXT_DIM)
        self.settings_status_label.pack(side="right")

        # (Kết nối UART tới STM32 nằm ở tab Cài đặt của app master — thẻ "Kết nối thiết bị".)

        # ---- Row 1: Kinematics + Joint Limits/Home + Fault Thresholds ----
        row1 = ctk.CTkFrame(area, fg_color="transparent")
        row1.pack(fill="x")
        row1.grid_columnconfigure((0, 1, 2), weight=1)
        self._build_kinematics_panel(row1).grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        self._build_joint_limits_panel(row1).grid(row=0, column=1, sticky="nsew", padx=4)
        self._build_fault_limits_panel(row1).grid(row=0, column=2, sticky="nsew", padx=(4, 0))

        # ---- Row 2: Encoder + Motion Profile + PID ----
        row2 = ctk.CTkFrame(area, fg_color="transparent")
        row2.pack(fill="x", pady=(8, 0))
        row2.grid_columnconfigure((0, 1, 2), weight=1)
        self._build_encoder_panel(row2).grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        self._build_motion_profile_panel(row2).grid(row=0, column=1, sticky="nsew", padx=4)
        self._build_pid_panel(row2).grid(row=0, column=2, sticky="nsew", padx=(4, 0))

        self._load_settings_into_fields(robot_config.load_config())

    def _entry_row_widget(self, parent, width, height=30, justify="center", font_size=11):
        return ctk.CTkEntry(parent, width=width, height=height, fg_color=COL_INPUT,
                             border_width=0, justify=justify,
                             font=("Segoe UI", font_size), text_color=COL_TEXT)

    def _build_kinematics_panel(self, parent):
        card = Card(parent, "1. Robot Kinematics", "🔗")
        body = card.body
        ctk.CTkLabel(body, text="Kinematic Parameters", font=("Segoe UI Semibold", 11),
                     text_color=COL_TEXT_DIM, anchor="w").pack(fill="x", pady=(0, 6))
        fields = [("h1", "h1 (Base X Offset)"), ("l1", "l1 (Link 1 Length)"),
                  ("l2", "l2 (Link 2 Length)"), ("h2", "h2 (Tool Z Offset)")]
        for key, label in fields:
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", pady=5)
            ctk.CTkLabel(row, text=label, font=("Segoe UI", 12), text_color=COL_TEXT,
                         anchor="w").pack(side="left", fill="x", expand=True)
            entry = self._entry_row_widget(row, 90, height=32, justify="right", font_size=12)
            entry.pack(side="left", padx=(8, 6))
            ctk.CTkLabel(row, text="mm", font=("Segoe UI", 11), text_color=COL_TEXT_DIM,
                         width=24, anchor="w").pack(side="left")
            self.set_entries["kinematics"][key] = entry
        return card

    def _build_joint_limits_panel(self, parent):
        card = Card(parent, "2. Joint Limits + Home", "📐")
        body = card.body
        header = ctk.CTkFrame(body, fg_color="transparent")
        header.pack(fill="x", pady=(0, 4))
        for text, w in (("Joint", 46), ("Min", 80), ("Max", 80), ("Home", 80), ("Unit", 40)):
            ctk.CTkLabel(header, text=text, font=("Segoe UI Semibold", 10),
                         text_color=COL_TEXT_DIM, width=w, anchor="w").pack(side="left", padx=2)
        for axis in AXES:
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", pady=4)
            ctk.CTkLabel(row, text=axis, font=("Segoe UI Semibold", 12),
                         text_color=COL_TEXT, width=46, anchor="w").pack(side="left", padx=2)
            min_e = self._entry_row_widget(row, 76)
            min_e.pack(side="left", padx=2)
            max_e = self._entry_row_widget(row, 76)
            max_e.pack(side="left", padx=2)
            home_e = self._entry_row_widget(row, 76)
            home_e.pack(side="left", padx=2)
            ctk.CTkLabel(row, text=UNITS[axis], font=("Segoe UI", 11), text_color=COL_TEXT_DIM,
                         width=40, anchor="w").pack(side="left", padx=2)
            self.set_entries["joint_limits"][axis] = {"min": min_e, "max": max_e}
            self.set_entries["home_position"][axis] = home_e
        ctk.CTkLabel(body, text="Home = vị trí gán cho trục khi HOMING chạm cảm biến home (gửi xuống STM32 bằng HPOS). "
                                 "Đổi Home thì phải bấm HOME lại mới có hiệu lực.",
                     font=("Segoe UI", 9), text_color=COL_TEXT_DISABLED,
                     wraplength=300, justify="left").pack(anchor="w", pady=(6, 0))
        return card

    def _build_fault_limits_panel(self, parent):
        card = Card(parent, "6. Fault Thresholds", "🛡️")
        body = card.body
        header = ctk.CTkFrame(body, fg_color="transparent")
        header.pack(fill="x", pady=(0, 4))
        for text, w in (("Joint", 40), ("Trip", 64), ("Home Trip", 64), ("Kẹt: đi ≥", 64), ("Unit", 30)):
            ctk.CTkLabel(header, text=text, font=("Segoe UI Semibold", 10),
                         text_color=COL_TEXT_DIM, width=w, anchor="w").pack(side="left", padx=2)
        for axis in AXES:
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", pady=4)
            ctk.CTkLabel(row, text=axis, font=("Segoe UI Semibold", 12),
                         text_color=COL_TEXT, width=40, anchor="w").pack(side="left", padx=2)
            trip_e = self._entry_row_widget(row, 62)
            trip_e.pack(side="left", padx=2)
            home_e = self._entry_row_widget(row, 62)
            home_e.pack(side="left", padx=2)
            stall_e = self._entry_row_widget(row, 62)
            stall_e.pack(side="left", padx=2)
            ctk.CTkLabel(row, text=UNITS[axis], font=("Segoe UI", 11), text_color=COL_TEXT_DIM,
                         width=30, anchor="w").pack(side="left", padx=2)
            self.set_entries["fault_limits"][axis] = {"trip": trip_e, "home_trip": home_e, "stall_dist": stall_e}
        # bảo vệ kẹt: PWM và thời gian dùng chung cho 4 trục (quãng tối thiểu riêng từng trục ở cột "Kẹt: đi ≥")
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", pady=(6, 0))
        ctk.CTkLabel(row, text="Kẹt khi PWM ≥", font=("Segoe UI", 11), text_color=COL_TEXT).pack(side="left", padx=2)
        self.stall_pct_entry = self._entry_row_widget(row, 46)
        self.stall_pct_entry.pack(side="left", padx=2)
        ctk.CTkLabel(row, text="% trong", font=("Segoe UI", 11), text_color=COL_TEXT).pack(side="left", padx=2)
        self.stall_ms_entry = self._entry_row_widget(row, 56)
        self.stall_ms_entry.pack(side="left", padx=2)
        ctk.CTkLabel(row, text="ms", font=("Segoe UI", 11), text_color=COL_TEXT).pack(side="left", padx=2)
        ctk.CTkLabel(body, text="Sai số bám quỹ đạo (đặt − thực) vượt ngưỡng thì STM32 phanh, tắt PID và báo FAULT. "
                                 "Trip: khi chạy (kẹt cơ khí, sai chiều/mất encoder). Home Trip: khi HOMING (trục bị chặn "
                                 "khi tìm cảm biến) — tăng lên nếu bị FAULT home giả. Kẹt: PWM trung bình cao mà trục đi "
                                 "chưa được quãng 'Kẹt: đi ≥' trong thời gian trên (chạm đầu hành trình / PID săn) → FAULT "
                                 "stall, chống cháy dây. PWM = 0: tắt.",
                     font=("Segoe UI", 9), text_color=COL_TEXT_DISABLED,
                     wraplength=300, justify="left").pack(anchor="w", pady=(6, 0))
        return card

    def _build_encoder_panel(self, parent):
        card = Card(parent, "3. Encoder / PPR / Gear Ratio", "🧮")
        body = card.body
        header = ctk.CTkFrame(body, fg_color="transparent")
        header.pack(fill="x", pady=(0, 4))
        for text, w in (("Joint", 32), ("PPR", 58), ("Gear", 58), ("Direction", 92)):
            ctk.CTkLabel(header, text=text, font=("Segoe UI Semibold", 10),
                         text_color=COL_TEXT_DIM, width=w, anchor="w").pack(side="left", padx=2)
        for axis in AXES:
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", pady=4)
            ctk.CTkLabel(row, text=axis, font=("Segoe UI Semibold", 12),
                         text_color=COL_TEXT, width=32, anchor="w").pack(side="left", padx=2)
            ppr_e = self._entry_row_widget(row, 54)
            ppr_e.pack(side="left", padx=2)
            gear_e = self._entry_row_widget(row, 54)
            gear_e.pack(side="left", padx=2)
            dir_opt = ctk.CTkOptionMenu(row, values=["Normal", "Reverse"], width=92, height=30,
                                         fg_color=COL_INPUT, button_color=COL_BTN_DARK,
                                         button_hover_color=COL_BTN_DARK_HOVER, font=("Segoe UI", 10))
            dir_opt.pack(side="left", padx=2)
            self.set_entries["encoder"][axis] = {"ppr": ppr_e, "gear_ratio": gear_e, "direction": dir_opt}
        ctk.CTkLabel(body, text="PPR = counts/vòng sau hộp số motor (đã ×4). Gear: J = tỉ số truyền (vd 1:1), "
                                 "Z = bước vít (mm/vòng). Direction đảo chiều ở phía PC. "
                                 "Dùng để đổi độ/mm ↔ counts khi gửi xuống STM32.",
                     font=("Segoe UI", 9), text_color=COL_TEXT_DISABLED,
                     wraplength=230, justify="left").pack(anchor="w", pady=(6, 0))
        return card

    def _build_motion_profile_panel(self, parent):
        card = Card(parent, "4. Trapezoidal Motion Profile", "📈")
        body = card.body
        header = ctk.CTkFrame(body, fg_color="transparent")
        header.pack(fill="x", pady=(0, 4))
        for text, w in (("Joint", 32), ("Vmax (°/s · mm/s)", 96), ("Amax (°/s² · mm/s²)", 110)):
            ctk.CTkLabel(header, text=text, font=("Segoe UI Semibold", 10),
                         text_color=COL_TEXT_DIM, width=w, anchor="w").pack(side="left", padx=2)
        for axis in AXES:
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", pady=4)
            ctk.CTkLabel(row, text=axis, font=("Segoe UI Semibold", 12),
                         text_color=COL_TEXT, width=32, anchor="w").pack(side="left", padx=2)
            v_e = self._entry_row_widget(row, 80, font_size=10)
            v_e.pack(side="left", padx=2)
            a_e = self._entry_row_widget(row, 80, font_size=10)
            a_e.pack(side="left", padx=2)
            self.set_entries["motion_profile"][axis] = {"vmax": v_e, "amax": a_e}
        ctk.CTkLabel(body, text="Gửi xuống STM32 (VMAX/AMAX, đổi ra counts/s). Z: động cơ chỉ đạt ≈ 5.4 mm/s — "
                                 "đặt Vmax Z cao hơn sẽ làm sai số bám tăng và gây FAULT.",
                     font=("Segoe UI", 9), text_color=COL_TEXT_DISABLED,
                     wraplength=230, justify="left").pack(anchor="w", pady=(6, 0))
        return card

    def _build_pid_panel(self, parent):
        card = Card(parent, "5. PID + Deadband", "🎚️")
        body = card.body
        header = ctk.CTkFrame(body, fg_color="transparent")
        header.pack(fill="x", pady=(0, 4))
        for text, w in (("Joint", 32), ("Kp", 42), ("Ki", 42), ("Kd", 42), ("DB", 46)):
            ctk.CTkLabel(header, text=text, font=("Segoe UI Semibold", 10),
                         text_color=COL_TEXT_DIM, width=w, anchor="w").pack(side="left", padx=2)
        for axis in AXES:
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", pady=4)
            ctk.CTkLabel(row, text=axis, font=("Segoe UI Semibold", 12),
                         text_color=COL_TEXT, width=32, anchor="w").pack(side="left", padx=2)
            kp_e = self._entry_row_widget(row, 42, font_size=10)
            kp_e.pack(side="left", padx=2)
            ki_e = self._entry_row_widget(row, 42, font_size=10)
            ki_e.pack(side="left", padx=2)
            kd_e = self._entry_row_widget(row, 42, font_size=10)
            kd_e.pack(side="left", padx=2)
            db_e = self._entry_row_widget(row, 46, font_size=10)
            db_e.pack(side="left", padx=2)
            self.set_entries["pid"][axis] = {"kp": kp_e, "ki": ki_e, "kd": kd_e, "deadband": db_e}
        ctk.CTkLabel(body, text="PID chạy trên STM32: đầu ra = duty PWM (0..4199) trên mỗi count sai số. "
                                 "DB = vùng chết ±n counts quanh đích (mặc định J: 5, Z: 191). "
                                 "Gửi xuống khi Connect/Apply.",
                     font=("Segoe UI", 9), text_color=COL_TEXT_DISABLED,
                     wraplength=230, justify="left").pack(anchor="w", pady=(6, 0))
        return card

    # ---------------- Đọc/ghi dữ liệu giữa form <-> dict config ----------------
    def _load_settings_into_fields(self, cfg):
        def set_entry(entry, value):
            entry.delete(0, "end")
            entry.insert(0, str(value))

        for key, entry in self.set_entries["kinematics"].items():
            set_entry(entry, cfg["kinematics"][key])
        for axis, w in self.set_entries["joint_limits"].items():
            set_entry(w["min"], cfg["joint_limits"][axis]["min"])
            set_entry(w["max"], cfg["joint_limits"][axis]["max"])
        for axis, entry in self.set_entries["home_position"].items():
            set_entry(entry, cfg["home_position"][axis])
        for axis, w in self.set_entries["fault_limits"].items():
            set_entry(w["trip"], cfg["fault_limits"][axis]["trip"])
            set_entry(w["home_trip"], cfg["fault_limits"][axis]["home_trip"])
            set_entry(w["stall_dist"], cfg["fault_limits"][axis]["stall_dist"])
        set_entry(self.stall_pct_entry, cfg["fault_limits"]["J1"]["stall_pct"])
        set_entry(self.stall_ms_entry, cfg["fault_limits"]["J1"]["stall_ms"])
        for axis, w in self.set_entries["encoder"].items():
            set_entry(w["ppr"], cfg["encoder"][axis]["ppr"])
            set_entry(w["gear_ratio"], cfg["encoder"][axis]["gear_ratio"])
            w["direction"].set(cfg["encoder"][axis]["direction"])
        for axis, w in self.set_entries["motion_profile"].items():
            set_entry(w["vmax"], cfg["motion_profile"][axis]["vmax"])
            set_entry(w["amax"], cfg["motion_profile"][axis]["amax"])
        for axis, w in self.set_entries["pid"].items():
            set_entry(w["kp"], cfg["pid"][axis]["kp"])
            set_entry(w["ki"], cfg["pid"][axis]["ki"])
            set_entry(w["kd"], cfg["pid"][axis]["kd"])
            set_entry(w["deadband"], cfg["pid"][axis]["deadband"])

    def _collect_settings_from_fields(self):
        """Đọc toàn bộ ô nhập thành 1 dict config. Trả về None (và log lỗi)
        nếu có ô không parse được số — KHÔNG raise để form không bị đóng
        giữa chừng, người dùng còn cơ hội sửa lại."""
        try:
            return {
                "kinematics": {k: float(e.get()) for k, e in self.set_entries["kinematics"].items()},
                "joint_limits": {
                    axis: {"min": float(w["min"].get()), "max": float(w["max"].get())}
                    for axis, w in self.set_entries["joint_limits"].items()
                },
                "home_position": {axis: float(e.get()) for axis, e in self.set_entries["home_position"].items()},
                "fault_limits": {
                    axis: {"trip": float(w["trip"].get()), "home_trip": float(w["home_trip"].get()),
                           "stall_pct": int(float(self.stall_pct_entry.get())),
                           "stall_ms": int(float(self.stall_ms_entry.get())),
                           "stall_dist": float(w["stall_dist"].get())}
                    for axis, w in self.set_entries["fault_limits"].items()
                },
                "encoder": {
                    axis: {"ppr": int(float(w["ppr"].get())),
                           "gear_ratio": w["gear_ratio"].get().strip(),
                           "direction": w["direction"].get()}
                    for axis, w in self.set_entries["encoder"].items()
                },
                "motion_profile": {
                    axis: {"vmax": float(w["vmax"].get()), "amax": float(w["amax"].get())}
                    for axis, w in self.set_entries["motion_profile"].items()
                },
                "pid": {
                    axis: {"kp": float(w["kp"].get()), "ki": float(w["ki"].get()),
                           "kd": float(w["kd"].get()),
                           "deadband": int(float(w["deadband"].get()))}
                    for axis, w in self.set_entries["pid"].items()
                },
            }
        except ValueError:
            self._log("Có ô nhập không phải số hợp lệ — kiểm tra lại các trường màu đỏ trong Cài đặt.", "ERROR")
            return None

    # ---------------- Load / Save / Apply ----------------
    def _on_settings_load(self):
        try:
            cfg = robot_config.load_config()
            self._load_settings_into_fields(cfg)
            self.settings_status_label.configure(text="✓ File loaded", text_color=COL_GREEN)
            self._log(f"Đã nạp cấu hình từ '{robot_config.DEFAULT_CONFIG_FILE}'.", "OK")
        except robot_config.ConfigError as e:
            self.settings_status_label.configure(text="✗ Lỗi đọc file", text_color=COL_RED)
            self._log(str(e), "ERROR")

    def _on_settings_save(self):
        cfg = self._collect_settings_from_fields()
        if cfg is None:
            return
        is_valid, errors = robot_config.validate_config(cfg)
        if not is_valid:
            for err in errors:
                self._log(err, "ERROR")
            self.settings_status_label.configure(text="✗ Dữ liệu chưa hợp lệ", text_color=COL_RED)
            return
        try:
            robot_config.save_config(cfg)
            self.settings_status_label.configure(text="✓ Saved", text_color=COL_GREEN)
            self._log(f"Đã lưu cấu hình vào '{robot_config.DEFAULT_CONFIG_FILE}'.", "OK")
        except robot_config.ConfigError as e:
            self.settings_status_label.configure(text="✗ Lỗi ghi file", text_color=COL_RED)
            self._log(str(e), "ERROR")

    def _on_uart_reconfig_result(self, ok, message):
        if ok:
            self._log("STM32: CONFIG_OK — cấu hình mới đã có hiệu lực.", "OK")
        else:
            self._log(f"STM32 từ chối cấu hình mới: {message}", "ERROR")

    def _on_settings_apply(self):
        cfg = self._collect_settings_from_fields()
        if cfg is None:
            return
        is_valid, errors = robot_config.validate_config(cfg)
        if not is_valid:
            for err in errors:
                self._log(err, "ERROR")
            self.settings_status_label.configure(text="✗ Dữ liệu chưa hợp lệ", text_color=COL_RED)
            return
        try:
            robot_config.save_config(cfg)  # Apply cũng lưu luôn để lần chạy sau tự nạp lại đúng
        except robot_config.ConfigError as e:
            self._log(str(e), "ERROR")
            return

        kinematics.set_params(cfg["kinematics"])
        self.backend.set_joint_limits({axis: (v["min"], v["max"]) for axis, v in cfg["joint_limits"].items()})
        self.backend.set_max_velocity({axis: v["vmax"] for axis, v in cfg["motion_profile"].items()})

        self.settings_status_label.configure(text="✓ Applied", text_color=COL_GREEN)
        self._log("Apply: Kinematics (h1/l1/l2/h2) + giới hạn khớp (phía PC) đã cập nhật.", "OK")
        if self._connected():
            try:
                self.backend.configure(cfg, self._on_uart_reconfig_result)
                self._log("Đang gửi toàn bộ cấu hình (PID, Vmax, Amax, Deadband, giới hạn khớp, vị trí Home, ngưỡng FAULT) xuống STM32... "
                          "Nếu vừa đổi Home hoặc Encoder, hãy bấm HOME lại để vị trí được đặt theo giá trị mới.", "INFO")
            except (UartError, ValueError) as e:
                self._log(f"Không gửi được cấu hình xuống STM32: {e}", "ERROR")
        else:
            self._log("Chưa kết nối STM32: cấu hình đã lưu vào file và sẽ được gửi xuống khi Connect.", "WARN")
        self._refresh_position_display()
