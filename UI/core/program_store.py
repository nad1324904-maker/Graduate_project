"""
program_store.py — Quản lý Program (Phase 3).
------------------------------------------------------------------------
Một Program là một chuỗi Step có thứ tự (mục 11). Step có 3 loại
(mục 11-13, thêm DELAY):
  - MOVE : tham chiếu tới một Point đã lưu (theo TÊN, không nhập tay
           góc/tọa độ trực tiếp — đúng mục 12).
  - GRIP : "ON" hoặc "OFF" (mục 13).
  - DELAY: chờ N giây (vd để kẹp kịp đóng trước khi MOVE tiếp).

Program KHÔNG lưu chung với Point (mục 15: "Points and Programs are
stored separately"). Module này chỉ biết Point qua TÊN (string), không
import point_store — việc kiểm tra Point có tồn tại hay không (validate)
nhận PointStore từ bên ngoài truyền vào, giữ 2 module độc lập nhau.
"""

import json
import os

from core.paths import DATA_DIR

DEFAULT_PROGRAMS_FILE = os.path.join(DATA_DIR, "programs.json")


class ProgramError(Exception):
    """Lỗi nghiệp vụ Program — GUI bắt và hiển thị, không phải lỗi hệ thống."""


STACK_LABELS = {"DAT": "Khay Đạt", "LOI1": "Khay Lỗi 1", "LOI2": "Khay Lỗi 2"}


def move_step(point_name, stack=None):
    """MOVE tới Point. `stack` = "DAT"/"LOI1"/"LOI2" -> Step XẾP CHỒNG: lúc chạy
    Z được cộng thêm chiều cao 1 tầng × số khay đã có trong khay chứa đó
    (xem core/stack_store.py). Point chỉ cần Teach ở tầng 1."""
    step = {"type": "MOVE", "point": point_name}
    if stack:
        if stack not in STACK_LABELS:
            raise ProgramError(f"Khay xếp chồng '{stack}' không hợp lệ.")
        step["stack"] = stack
    return step


def stack_text(step):
    """' · xếp chồng Khay Đạt' nếu Step có đánh dấu, ngược lại ''."""
    s = step.get("stack")
    return f" · xếp chồng {STACK_LABELS.get(s, s)}" if s else ""


def grip_step(action):
    if action not in ("ON", "OFF"):
        raise ProgramError("GRIP step chỉ nhận 'ON' hoặc 'OFF'.")
    return {"type": "GRIP", "action": action}


MIN_DELAY_S = 0.1
MAX_DELAY_S = 60.0


def delay_step(seconds):
    """DELAY: chờ `seconds` giây (PC đếm giờ, robot giữ nguyên vị trí)."""
    if not (MIN_DELAY_S <= seconds <= MAX_DELAY_S):
        raise ProgramError(f"DELAY phải từ {MIN_DELAY_S} đến {MAX_DELAY_S:g} giây.")
    return {"type": "DELAY", "seconds": float(seconds)}


def describe_step(step):
    if step["type"] == "MOVE":
        return f"MOVE → {step['point']}{stack_text(step)}"
    if step["type"] == "DELAY":
        return f"DELAY {step['seconds']:g} s"
    return f"GRIP {step['action']}"


class ProgramStore:
    def __init__(self, file_path=DEFAULT_PROGRAMS_FILE):
        self.file_path = file_path
        # name -> {"description": str, "steps": [step, ...]}
        self.programs = {}
        self._load()

    # ---------------- Persistence ----------------
    def _load(self):
        if os.path.exists(self.file_path):
            with open(self.file_path, "r", encoding="utf-8") as f:
                self.programs = json.load(f)
        else:
            self.programs = {}

    def _save(self):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(self.programs, f, ensure_ascii=False, indent=2)

    # ---------------- Program CRUD ----------------
    def list_names(self):
        return sorted(self.programs.keys())

    def exists(self, name):
        return name in self.programs

    def get(self, name):
        if name not in self.programs:
            raise ProgramError(f"Chương trình '{name}' không tồn tại.")
        return {"description": self.programs[name]["description"],
                "steps": list(self.programs[name]["steps"])}

    def create(self, name, description=""):
        name = name.strip()
        if not name:
            raise ProgramError("Tên chương trình không được để trống.")
        if name in self.programs:
            raise ProgramError(f"Chương trình '{name}' đã tồn tại.")
        self.programs[name] = {"description": description, "steps": []}
        self._save()

    def delete(self, name):
        if name not in self.programs:
            raise ProgramError(f"Chương trình '{name}' không tồn tại.")
        del self.programs[name]
        self._save()

    def set_description(self, name, description):
        self._require(name)
        self.programs[name]["description"] = description
        self._save()

    # ---------------- Step CRUD ----------------
    def add_step(self, program_name, step):
        self._require(program_name)
        self.programs[program_name]["steps"].append(step)
        self._save()

    def insert_step(self, program_name, step, after_index=None):
        """Chèn Step ngay SAU `after_index` (None = thêm vào cuối). Trả về
        vị trí của Step vừa chèn."""
        steps = self._require(program_name)["steps"]
        if after_index is None:
            pos = len(steps)
        elif 0 <= after_index < len(steps):
            pos = after_index + 1
        else:
            raise ProgramError("Vị trí Step không hợp lệ.")
        steps.insert(pos, step)
        self._save()
        return pos

    def edit_step(self, program_name, index, new_step):
        steps = self._require(program_name)["steps"]
        if not (0 <= index < len(steps)):
            raise ProgramError("Vị trí Step không hợp lệ.")
        steps[index] = new_step
        self._save()

    def delete_step(self, program_name, index):
        steps = self._require(program_name)["steps"]
        if not (0 <= index < len(steps)):
            raise ProgramError("Vị trí Step không hợp lệ.")
        del steps[index]
        self._save()

    def move_step(self, program_name, index, new_index):
        """Đổi thứ tự Step (reorder)."""
        steps = self._require(program_name)["steps"]
        if not (0 <= index < len(steps)) or not (0 <= new_index < len(steps)):
            raise ProgramError("Vị trí Step không hợp lệ.")
        steps.insert(new_index, steps.pop(index))
        self._save()

    def _require(self, name):
        if name not in self.programs:
            raise ProgramError(f"Chương trình '{name}' không tồn tại.")
        return self.programs[name]

    # ---------------- Validate / tham chiếu Point ----------------
    def validate(self, program_name, point_store):
        """Kiểm tra mọi Step MOVE có tham chiếu tới Point còn tồn tại
        không (mục 15-17: 'must not silently create invalid program
        references', 'All referenced Points must exist' trước khi START).
        Trả về (is_valid, [tên_point_thiếu, ...])."""
        steps = self._require(program_name)["steps"]
        missing = []
        for step in steps:
            if step["type"] == "MOVE" and not point_store.exists(step["point"]):
                missing.append(step["point"])
        return (len(missing) == 0), missing

    def stack_bins(self, program_name):
        """Các khay chứa mà Program này xếp chồng vào (theo thứ tự xuất hiện)."""
        bins = []
        for step in self._require(program_name)["steps"]:
            b = step.get("stack") if step["type"] == "MOVE" else None
            if b and b not in bins:
                bins.append(b)
        return bins

    def point_is_referenced(self, point_name):
        """Point này có đang được Program nào tham chiếu không — dùng để
        chặn xóa Point một cách an toàn (mục 15)."""
        for prog in self.programs.values():
            for step in prog["steps"]:
                if step["type"] == "MOVE" and step["point"] == point_name:
                    return True
        return False

    def rename_point_reference(self, old_name, new_name):
        """Khi Point được đổi tên, cập nhật lại mọi Step MOVE đang tham
        chiếu tên cũ — tránh Program bị tham chiếu treo (mục 15)."""
        changed = False
        for prog in self.programs.values():
            for step in prog["steps"]:
                if step["type"] == "MOVE" and step["point"] == old_name:
                    step["point"] = new_name
                    changed = True
        if changed:
            self._save()