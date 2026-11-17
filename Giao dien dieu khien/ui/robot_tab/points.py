"""points.py — Bảng POINTS (tab Lập trình): Teach / Save Position / Rename / Delete; chọn Point tham chiếu cho
Move Here (ô chọn Point ở tab Vận hành dùng chung lựa chọn này)."""

import customtkinter as ctk

from comm.errors import UartError
from core.point_store import PointError
from ui.theme import (
    AXES, COL_ACCENT, COL_ACCENT_HOVER, COL_BTN_DARK, COL_BTN_DARK_HOVER, COL_TEXT_DIM,
    UNITS
)
from ui.widgets import Card, PointTableRow


class PointsMixin:
    # ============================================================
    # POINTS
    # ============================================================
    def _build_points_card(self, parent):
        card = Card(parent, "POINTS", "📍")
        body = card.body

        header_row = ctk.CTkFrame(body, fg_color="transparent")
        header_row.pack(fill="x", padx=4)
        ctk.CTkLabel(header_row, text="Name", font=("Segoe UI Semibold", 10),
                     text_color=COL_TEXT_DIM, width=90, anchor="w").pack(side="left")
        ctk.CTkLabel(header_row, text="Description", font=("Segoe UI Semibold", 10),
                     text_color=COL_TEXT_DIM, anchor="w").pack(side="left", fill="x", expand=True)

        self.point_list_frame = ctk.CTkScrollableFrame(
            body, fg_color="transparent", height=150, scrollbar_button_color=COL_BTN_DARK)
        self.point_list_frame.pack(fill="both", expand=True, pady=(2, 8))

        row1 = ctk.CTkFrame(body, fg_color="transparent")
        row1.pack(fill="x")
        ctk.CTkButton(row1, text="+ Teach Point", height=32, corner_radius=8,
                      fg_color=COL_ACCENT, hover_color=COL_ACCENT_HOVER, font=("Segoe UI Semibold", 11),
                      command=self._on_teach_point).pack(side="left", expand=True, fill="x", padx=2)
        ctk.CTkButton(row1, text="💾 Save Position", height=32, corner_radius=8,
                      fg_color=COL_BTN_DARK, hover_color=COL_BTN_DARK_HOVER, font=("Segoe UI Semibold", 11),
                      command=self._on_save_position).pack(side="left", expand=True, fill="x", padx=2)
        row2 = ctk.CTkFrame(body, fg_color="transparent")
        row2.pack(fill="x", pady=(4, 0))
        ctk.CTkButton(row2, text="✎ Rename", height=30, corner_radius=8,
                      fg_color=COL_BTN_DARK, hover_color=COL_BTN_DARK_HOVER, font=("Segoe UI", 11),
                      command=self._on_rename_point).pack(side="left", expand=True, fill="x", padx=2)
        ctk.CTkButton(row2, text="🗑 Delete", height=30, corner_radius=8,
                      fg_color=COL_BTN_DARK, hover_color=COL_BTN_DARK_HOVER, font=("Segoe UI", 11),
                      command=self._on_delete_point).pack(side="left", expand=True, fill="x", padx=2)

        self._refresh_point_list()
        return card

    def _refresh_point_list(self):
        for w in self.point_list_frame.winfo_children():
            w.destroy()
        names = self.point_store.list_names()
        if not names:
            ctk.CTkLabel(self.point_list_frame, text="Chưa có Point nào — Jog robot rồi 'Teach Point'.",
                         font=("Segoe UI", 11), text_color=COL_TEXT_DIM).pack(pady=8)
            return
        for name in names:
            vals = self.point_store.get(name)
            subtitle = f"J1={vals['J1']:.1f}° J2={vals['J2']:.1f}° J3={vals['J3']:.1f}° Z={vals['Z']:.1f}mm"
            row = PointTableRow(self.point_list_frame, name, subtitle,
                                 selected=(name == self.selected_point),
                                 on_click=lambda n=name: self._select_and_load_point(n))
            row.pack(fill="x", pady=1)

    def _select_and_load_point(self, name):
        """Bấm dòng Point = chọn (cho Save/Rename/Delete) VÀ Load Position
        (nạp tham chiếu). KHÔNG tự di chuyển robot — muốn di chuyển phải
        bấm 'Move Here' riêng (mục 9 trong spec)."""
        self.selected_point = name
        values = self.point_store.get(name)
        self.loaded_reference = (name, values)
        self.ref_point_option.set(name)
        self._refresh_point_list()
        self._refresh_enabled_states()
        text = ", ".join(f"{a}={values[a]:.2f}{UNITS[a]}" for a in AXES)
        self._log(f"Chọn Point '{name}' làm tham chiếu ({text}) — chưa di chuyển, bấm Move Here để đi tới.")

    def _on_ref_point_option(self, name):
        if self.point_store.exists(name):
            self._select_and_load_point(name)

    def _on_move_to_reference(self):
        if not self.loaded_reference:
            return
        if not self._jog_allowed():
            self._log("Bị chặn: chỉ di chuyển tới tham chiếu khi đã kết nối, đã HOME, ở Chế độ JOG và không chạy chương trình.", "WARN")
            return
        name, values = self.loaded_reference
        try:
            self.backend.send_absolute_target(values)
        except UartError as e:
            self._log(str(e), "ERROR")
            return
        self._log(f"Di chuyển tới tham chiếu '{name}'.")
        self._program_just_completed = False

    def _on_teach_point(self):
        if not self._connected():
            self._log("Teach Point cần vị trí actual thật — hãy kết nối STM32 trước.", "WARN")
            return
        if not self._home_ready():
            self._log("Bị chặn: chưa HOME nên vị trí actual chưa đáng tin — hãy bấm HOME trước khi Teach Point.", "WARN")
            return
        dialog = ctk.CTkInputDialog(text="Tên Point mới (VD: PICK):", title="Teach Point")
        name = dialog.get_input()
        if not name:
            return
        try:
            self.point_store.create(name, self.backend.get_actual_position())
            self._log(f"Teach Point: tạo '{name}' từ vị trí actual hiện tại.", "OK")
            self._refresh_program_point_options()
            self._select_and_load_point(name)
        except PointError as e:
            self._log(str(e), "ERROR")

    def _on_save_position(self):
        if not self._connected():
            self._log("Save Position cần vị trí actual thật — hãy kết nối STM32 trước.", "WARN")
            return
        if not self._home_ready():
            self._log("Bị chặn: chưa HOME nên vị trí actual chưa đáng tin — hãy bấm HOME trước khi Save Position.", "WARN")
            return
        if not self.selected_point:
            self._log("Chưa chọn Point nào — hãy chọn 1 dòng trong bảng, hoặc dùng Teach Point.", "WARN")
            return
        try:
            self.point_store.update(self.selected_point, self.backend.get_actual_position())
            self._log(f"Save Position: cập nhật '{self.selected_point}' theo vị trí actual hiện tại.", "OK")
            self._refresh_point_list()
        except PointError as e:
            self._log(str(e), "ERROR")

    def _on_rename_point(self):
        if not self.selected_point:
            self._log("Chưa chọn Point nào để đổi tên.", "WARN")
            return
        dialog = ctk.CTkInputDialog(text=f"Tên mới cho '{self.selected_point}':", title="Rename Point")
        new_name = dialog.get_input()
        if not new_name:
            return
        try:
            old_name = self.selected_point
            self.point_store.rename(old_name, new_name)
            self.program_store.rename_point_reference(old_name, new_name)
            self.selected_point = new_name
            if self.loaded_reference and self.loaded_reference[0] == old_name:
                self.loaded_reference = (new_name, self.point_store.get(new_name))
            self._log(f"Đổi tên Point '{old_name}' → '{new_name}' (đã cập nhật mọi Step MOVE tham chiếu).", "OK")
            self._refresh_point_list()
            self._refresh_program_point_options()
            self._refresh_step_list()
        except PointError as e:
            self._log(str(e), "ERROR")

    def _on_delete_point(self):
        if not self.selected_point:
            self._log("Chưa chọn Point nào để xóa.", "WARN")
            return
        name = self.selected_point
        if self.program_store.point_is_referenced(name):
            self._log(f"Không thể xóa '{name}': đang được tham chiếu trong ít nhất 1 Program.", "ERROR")
            return
        try:
            self.point_store.delete(name)
            self._log(f"Đã xóa Point '{name}'.", "OK")
            self.selected_point = None
            self.loaded_reference = None
            self._refresh_point_list()
            self._refresh_program_point_options()
            self._refresh_enabled_states()
        except PointError as e:
            self._log(str(e), "ERROR")
