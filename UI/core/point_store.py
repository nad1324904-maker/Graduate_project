"""
point_store.py — Quản lý Point (Phase 2).
------------------------------------------------------------------------
Một Point là một vị trí robot đã lưu, gồm J1, J2, J3, Z và một tên duy
nhất (mục 6 trong spec). Module này KHÔNG phụ thuộc GUI hay backend —
GUI gọi vào đây, và tự lấy vị trí ACTUAL từ backend khi cần (Teach Point /
Save Position) rồi truyền giá trị xuống, để point_store không cần biết
gì về backend cả.

Lưu trữ bền vững dạng JSON (mục 10), tự tạo file nếu chưa có.
"""

import json
import os

from core.paths import DATA_DIR

DEFAULT_POINTS_FILE = os.path.join(DATA_DIR, "points.json")
AXES = ["J1", "J2", "J3", "Z"]


class PointError(Exception):
    """Lỗi nghiệp vụ Point (trùng tên, không tồn tại...) — GUI bắt và
    hiển thị thông báo, không phải lỗi hệ thống."""


class PointStore:
    def __init__(self, file_path=DEFAULT_POINTS_FILE):
        self.file_path = file_path
        self.points = {}  # name -> {"J1":.., "J2":.., "J3":.., "Z":..}
        self._load()

    # ---------------- Persistence ----------------
    def _load(self):
        if os.path.exists(self.file_path):
            with open(self.file_path, "r", encoding="utf-8") as f:
                self.points = json.load(f)
        else:
            self.points = {}

    def _save(self):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(self.points, f, ensure_ascii=False, indent=2)

    # ---------------- CRUD ----------------
    def list_names(self):
        return sorted(self.points.keys())

    def exists(self, name):
        return name in self.points

    def get(self, name):
        if name not in self.points:
            raise PointError(f"Point '{name}' không tồn tại.")
        return dict(self.points[name])

    def create(self, name, values: dict):
        """Tạo Point mới — dùng bởi Teach Point (mục 7)."""
        name = name.strip()
        if not name:
            raise PointError("Tên Point không được để trống.")
        if name in self.points:
            raise PointError(f"Point '{name}' đã tồn tại — dùng Save Position để cập nhật.")
        self.points[name] = {axis: float(values[axis]) for axis in AXES}
        self._save()

    def update(self, name, values: dict):
        """Cập nhật Point ĐÃ TỒN TẠI — dùng bởi Save Position (mục 8).
        KHÔNG được tự tạo mới nếu chưa chọn Point (đúng mục 8)."""
        if name not in self.points:
            raise PointError(f"Point '{name}' không tồn tại — hãy Teach Point để tạo mới.")
        self.points[name] = {axis: float(values[axis]) for axis in AXES}
        self._save()

    def rename(self, old_name, new_name):
        new_name = new_name.strip()
        if old_name not in self.points:
            raise PointError(f"Point '{old_name}' không tồn tại.")
        if not new_name:
            raise PointError("Tên mới không được để trống.")
        if new_name != old_name and new_name in self.points:
            raise PointError(f"Point '{new_name}' đã tồn tại.")
        self.points[new_name] = self.points.pop(old_name)
        self._save()

    def delete(self, name):
        if name not in self.points:
            raise PointError(f"Point '{name}' không tồn tại.")
        del self.points[name]
        self._save()
