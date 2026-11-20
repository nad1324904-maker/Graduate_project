"""program.py — PROGRAM EDITOR: tạo/xóa chương trình, thêm/sửa/xóa/đổi thứ tự Step."""

import customtkinter as ctk

from core.program_store import ProgramError, move_step, grip_step, delay_step, describe_step
from core.program_executor import ExecState
from ui.theme import (
    COL_ACCENT, COL_ACCENT_HOVER, COL_AMBER, COL_AMBER_HOVER, COL_BTN_DARK,
    COL_BTN_DARK_HOVER, COL_GREEN, COL_GREEN_HOVER, COL_INPUT, COL_TEXT_DIM
)
from ui.widgets import Card, StepTableRow

# Ô chọn xếp chồng cho Step MOVE: nhãn hiển thị <-> giá trị "stack" lưu trong Step
STACK_CHOICES = {"Không xếp chồng": None, "Xếp chồng: Đạt": "DAT",
                 "Xếp chồng: Lỗi 1": "LOI1", "Xếp chồng: Lỗi 2": "LOI2"}
STACK_CHOICE_OF = {v: k for k, v in STACK_CHOICES.items()}


class ProgramMixin:
    # ============================================================
    # PROGRAM EDITOR
    # ============================================================
    def _build_program_card(self, parent):
        card = Card(parent, "PROGRAM EDITOR", "💻")
        body = card.body

        top_row = ctk.CTkFrame(body, fg_color="transparent")
        top_row.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(top_row, text="Program:", font=("Segoe UI", 11),
                     text_color=COL_TEXT_DIM).pack(side="left")
        self.program_option = ctk.CTkOptionMenu(
            top_row, values=["(chưa có)"], fg_color=COL_INPUT, button_color=COL_BTN_DARK,
            button_hover_color=COL_BTN_DARK_HOVER, height=28, width=150,
            command=self._on_select_program_from_menu)
        self.program_option.pack(side="left", padx=(6, 4))
        ctk.CTkButton(top_row, text="＋", width=28, height=28, corner_radius=6,
                      fg_color=COL_BTN_DARK, hover_color=COL_BTN_DARK_HOVER, font=("Segoe UI Semibold", 13),
                      command=self._on_create_program).pack(side="left", padx=2)
        ctk.CTkButton(top_row, text="🗑", width=28, height=28, corner_radius=6,
                      fg_color=COL_BTN_DARK, hover_color=COL_BTN_DARK_HOVER, font=("Segoe UI", 12),
                      command=self._on_delete_program).pack(side="left", padx=2)

        desc_row = ctk.CTkFrame(body, fg_color="transparent")
        desc_row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(desc_row, text="Description:", font=("Segoe UI", 11),
                     text_color=COL_TEXT_DIM).pack(side="left")
        self.desc_entry = ctk.CTkEntry(desc_row, fg_color=COL_INPUT, height=28, border_width=0)
        self.desc_entry.pack(side="left", fill="x", expand=True, padx=(6, 6))
        ctk.CTkButton(desc_row, text="Lưu", width=50, height=28, corner_radius=6,
                      fg_color=COL_BTN_DARK, hover_color=COL_BTN_DARK_HOVER, font=("Segoe UI", 11),
                      command=self._on_save_description).pack(side="left")

        content_row = ctk.CTkFrame(body, fg_color="transparent")
        content_row.pack(fill="both", expand=True)

        # ---- Bảng Step (trái) ----
        table_col = ctk.CTkFrame(content_row, fg_color="transparent")
        table_col.pack(side="left", fill="both", expand=True, padx=(0, 8))
        th_row = ctk.CTkFrame(table_col, fg_color="transparent")
        th_row.pack(fill="x", padx=4)
        ctk.CTkLabel(th_row, text="#", font=("Segoe UI Semibold", 10), text_color=COL_TEXT_DIM,
                     width=26).pack(side="left")
        ctk.CTkLabel(th_row, text="Type", font=("Segoe UI Semibold", 10), text_color=COL_TEXT_DIM,
                     width=56).pack(side="left", padx=4)
        ctk.CTkLabel(th_row, text="Detail", font=("Segoe UI Semibold", 10), text_color=COL_TEXT_DIM,
                     anchor="w").pack(side="left", fill="x", expand=True)
        self.step_list_frame = ctk.CTkScrollableFrame(
            table_col, fg_color="transparent", height=240, scrollbar_button_color=COL_BTN_DARK)
        self.step_list_frame.pack(fill="both", expand=True, pady=(2, 0))

        # ---- Cột nút thao tác (phải) ----
        action_col = ctk.CTkFrame(content_row, fg_color="transparent", width=118)
        action_col.pack(side="left", fill="y")
        self.move_point_option = ctk.CTkOptionMenu(
            action_col, values=["(chưa có Point)"], fg_color=COL_INPUT, button_color=COL_BTN_DARK,
            button_hover_color=COL_BTN_DARK_HOVER, height=26, width=110, font=("Segoe UI", 10))
        self.move_point_option.pack(pady=(0, 4))
        # Xếp chồng: lúc chạy Z += chiều cao 1 tầng × số khay đã có (cài ở tab Cài đặt của master)
        self.stack_option = ctk.CTkOptionMenu(
            action_col, values=list(STACK_CHOICES), fg_color=COL_INPUT, button_color=COL_BTN_DARK,
            button_hover_color=COL_BTN_DARK_HOVER, height=26, width=110, font=("Segoe UI", 10),
            dropdown_font=("Segoe UI", 11))
        self.stack_option.set("Không xếp chồng")
        self.stack_option.pack(pady=(0, 4))
        ctk.CTkButton(action_col, text="+ MOVE", height=28, corner_radius=8, width=110,
                      fg_color=COL_ACCENT, hover_color=COL_ACCENT_HOVER, font=("Segoe UI Semibold", 11),
                      command=self._on_add_move_step).pack(pady=2)
        ctk.CTkButton(action_col, text="+ GRIP ON", height=28, corner_radius=8, width=110,
                      fg_color=COL_GREEN, hover_color=COL_GREEN_HOVER, font=("Segoe UI Semibold", 11),
                      command=lambda: self._on_add_grip_step("ON")).pack(pady=2)
        ctk.CTkButton(action_col, text="+ GRIP OFF", height=28, corner_radius=8, width=110,
                      fg_color=COL_GREEN, hover_color=COL_GREEN_HOVER, font=("Segoe UI Semibold", 11),
                      command=lambda: self._on_add_grip_step("OFF")).pack(pady=2)
        self.delay_entry = ctk.CTkEntry(action_col, width=110, height=26, fg_color=COL_INPUT,
                                         border_width=0, justify="center",
                                         placeholder_text="giây (vd 0.5)")
        self.delay_entry.insert(0, "0.5")
        self.delay_entry.pack(pady=(8, 4))
        ctk.CTkButton(action_col, text="+ DELAY", height=28, corner_radius=8, width=110,
                      fg_color=COL_AMBER, hover_color=COL_AMBER_HOVER, font=("Segoe UI Semibold", 11),
                      command=self._on_add_delay_step).pack(pady=2)
        ctk.CTkButton(action_col, text="✎ Edit Step", height=28, corner_radius=8, width=110,
                      fg_color=COL_BTN_DARK, hover_color=COL_BTN_DARK_HOVER, font=("Segoe UI", 11),
                      command=self._on_edit_step).pack(pady=(10, 2))
        ctk.CTkButton(action_col, text="🗑 Delete Step", height=28, corner_radius=8, width=110,
                      fg_color=COL_BTN_DARK, hover_color=COL_BTN_DARK_HOVER, font=("Segoe UI", 11),
                      command=self._on_delete_step).pack(pady=2)

        self._refresh_program_list()
        return card

    # ---------------- Danh sách + chọn chương trình ----------------
    def _refresh_program_list(self):
        """Cập nhật 2 ô chọn chương trình: Program Editor (tab Lập trình) và Chạy chương trình (tab Vận hành)."""
        names = self.program_store.list_names()
        shown = self.selected_program if self.selected_program in names else (names[0] if names else "(chưa có)")
        for option in (self.program_option, self.run_program_option):
            option.configure(values=names or ["(chưa có)"])
            option.set(shown)

    def _on_select_program_from_menu(self, name):
        if name == "(chưa có)":
            return
        self._select_program(name)

    def _select_program(self, name):
        self.selected_program = name
        self.selected_step_index = None
        prog = self.program_store.get(name)
        self.desc_entry.delete(0, "end")
        self.desc_entry.insert(0, prog["description"])
        self._refresh_program_list()
        self._refresh_step_list()
        self._refresh_progress_display()     # gồm cả danh sách Step ở khung Chạy chương trình

    def _on_create_program(self):
        dialog = ctk.CTkInputDialog(text="Tên chương trình mới:", title="Tạo Program")
        name = dialog.get_input()
        if not name:
            return
        try:
            self.program_store.create(name)
            self._log(f"Đã tạo chương trình '{name}'.", "OK")
            self._select_program(name)
        except ProgramError as e:
            self._log(str(e), "ERROR")

    def _on_delete_program(self):
        if not self.selected_program:
            self._log("Chưa chọn chương trình nào để xóa.", "WARN")
            return
        name = self.selected_program
        if self.executor.state in (ExecState.RUNNING, ExecState.PAUSED) and self.executor.program_name == name:
            self._log("Không thể xóa chương trình đang chạy.", "WARN")
            return
        try:
            self.program_store.delete(name)
            self._log(f"Đã xóa chương trình '{name}'.", "OK")
            self.selected_program = None
            self.selected_step_index = None
            self.desc_entry.delete(0, "end")
            self._refresh_step_list()
            self._refresh_program_list()
        except ProgramError as e:
            self._log(str(e), "ERROR")

    def _on_save_description(self):
        if not self.selected_program:
            self._log("Chưa chọn chương trình nào.", "WARN")
            return
        self.program_store.set_description(self.selected_program, self.desc_entry.get())
        self._log(f"Đã lưu mô tả cho '{self.selected_program}'.", "OK")

    # ---------------- Step CRUD (không có reorder; Step mới chèn SAU Step đang chọn) ----------------
    def _refresh_program_point_options(self):
        """Cập nhật các ô chọn Point: '+ MOVE' (Program Editor) và 'Point' (tab Vận hành)."""
        names = self.point_store.list_names()
        self.move_point_option.configure(values=names or ["(chưa có Point)"])
        if names:
            self.move_point_option.set(names[0])
        self.ref_point_option.configure(values=names or ["(chưa có Point)"])
        ref = self.loaded_reference[0] if self.loaded_reference else None
        self.ref_point_option.set(ref if ref in names else "— chọn Point —")

    def _refresh_step_list(self):
        self._refresh_run_steps()
        for w in self.step_list_frame.winfo_children():
            w.destroy()
        if not self.selected_program:
            return
        prog = self.program_store.get(self.selected_program)
        for i, step in enumerate(prog["steps"]):
            row = StepTableRow(self.step_list_frame, i, step,
                                selected=(i == self.selected_step_index),
                                on_click=lambda i=i: self._select_step(i))
            row.pack(fill="x", pady=1)

    def _select_step(self, index):
        self.selected_step_index = index
        # Chọn Step MOVE -> 2 ô Point / Xếp chồng hiện đúng giá trị của Step (Edit chỉ đổi phần bạn chỉnh)
        steps = self.program_store.get(self.selected_program)["steps"] if self.selected_program else []
        step = steps[index] if 0 <= index < len(steps) else None
        if step and step["type"] == "MOVE":
            if self.point_store.exists(step["point"]):
                self.move_point_option.set(step["point"])
            self.stack_option.set(STACK_CHOICE_OF.get(step.get("stack"), "Không xếp chồng"))
        self._refresh_step_list()

    def _require_editable_program(self):
        if not self.selected_program:
            self._log("Chưa chọn chương trình nào để soạn thảo.", "WARN")
            return False
        if self.executor.state in (ExecState.RUNNING, ExecState.PAUSED) and \
                self.executor.program_name == self.selected_program:
            self._log("Không thể sửa chương trình đang chạy.", "WARN")
            return False
        return True

    def _insert_step(self, step, label):
        """Chèn Step sau Step đang chọn (không chọn gì -> thêm cuối). Step mới
        được chọn luôn để bấm thêm liên tiếp thì xếp đúng thứ tự."""
        after = self.selected_step_index
        pos = self.program_store.insert_step(self.selected_program, step, after)
        if after is not None:
            self.selected_step_index = pos
        self._log(f"Thêm Step {label} vào '{self.selected_program}' ở vị trí {pos + 1}.", "OK")
        self._refresh_step_list()
        self._refresh_program_list()

    def _build_delay_step(self):
        try:
            return delay_step(float(self.delay_entry.get().replace(",", ".")))
        except ValueError:
            self._log("Thời gian DELAY phải là số (giây).", "WARN")
        except ProgramError as e:
            self._log(str(e), "WARN")
        return None

    def _on_add_delay_step(self):
        if not self._require_editable_program():
            return
        step = self._build_delay_step()
        if step:
            self._insert_step(step, describe_step(step))

    def _on_add_move_step(self):
        if not self._require_editable_program():
            return
        point_name = self.move_point_option.get()
        if not self.point_store.exists(point_name):
            self._log("Chưa có Point nào để thêm MOVE — hãy Teach Point trước.", "WARN")
            return
        step = move_step(point_name, STACK_CHOICES.get(self.stack_option.get()))
        self._insert_step(step, describe_step(step))

    def _on_add_grip_step(self, action):
        if not self._require_editable_program():
            return
        self._insert_step(grip_step(action), f"GRIP {action}")

    def _on_edit_step(self):
        if not self._require_editable_program():
            return
        if self.selected_step_index is None:
            self._log("Chưa chọn Step nào để sửa — bấm vào 1 dòng trong bảng trước.", "WARN")
            return
        steps = self.program_store.get(self.selected_program)["steps"]
        step = steps[self.selected_step_index]
        if step["type"] == "MOVE":
            new_point = self.move_point_option.get()
            if not self.point_store.exists(new_point):
                self._log("Point trong dropdown không tồn tại.", "WARN")
                return
            new_step = move_step(new_point, STACK_CHOICES.get(self.stack_option.get()))
            self.program_store.edit_step(self.selected_program, self.selected_step_index, new_step)
            self._log(f"Sửa Step {self.selected_step_index + 1}: {describe_step(new_step)}.", "OK")
        elif step["type"] == "DELAY":
            new_step = self._build_delay_step()
            if not new_step:
                return
            self.program_store.edit_step(self.selected_program, self.selected_step_index, new_step)
            self._log(f"Sửa Step {self.selected_step_index + 1}: {describe_step(new_step)}.", "OK")
        else:
            new_action = "OFF" if step["action"] == "ON" else "ON"
            self.program_store.edit_step(self.selected_program, self.selected_step_index, grip_step(new_action))
            self._log(f"Sửa Step {self.selected_step_index + 1}: GRIP {step['action']} → {new_action}.", "OK")
        self._refresh_step_list()

    def _on_delete_step(self):
        if not self._require_editable_program():
            return
        if self.selected_step_index is None:
            self._log("Chưa chọn Step nào để xóa.", "WARN")
            return
        self.program_store.delete_step(self.selected_program, self.selected_step_index)
        self._log(f"Đã xóa Step {self.selected_step_index + 1}.", "OK")
        self.selected_step_index = None
        self._refresh_step_list()
        self._refresh_program_list()
