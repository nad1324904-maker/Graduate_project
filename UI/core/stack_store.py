"""
stack_store.py — Bộ đếm XẾP CHỒNG cho 3 khay chứa (Đạt / Lỗi 1 / Lỗi 2).
------------------------------------------------------------------------
Robot xếp các khay PCB chồng lên nhau trong khay chứa. Chỉ cần Teach
Point cho TẦNG 1 (khay chứa đang trống); Step MOVE nào được đánh dấu
"stack": "<khay>" thì lúc chạy Z được cộng thêm:

    Z_thực = Z_point + chiều cao 1 tầng × số khay đã có trong khay chứa

Số đếm tăng 1 sau Step GRIP OFF đầu tiên theo sau Step xếp chồng (lúc
đó khay mới thật sự được thả xuống). Khay chứa đầy (đếm = tối đa) thì
không cho chạy chương trình xếp vào khay đó nữa — người vận hành thay
khay chứa rỗng rồi bấm "Đã thay khay" (đếm về 0).

Lưu JSON ở data/stack_state.json để tắt app mở lại vẫn nhớ số đếm.
Module không phụ thuộc GUI/backend.
"""

import json
import os

from core.paths import DATA_DIR

DEFAULT_STACK_FILE = os.path.join(DATA_DIR, "stack_state.json")

BINS = ("DAT", "LOI1", "LOI2")
BIN_LABELS = {"DAT": "Khay Đạt", "LOI1": "Khay Lỗi 1", "LOI2": "Khay Lỗi 2"}

DEFAULT_MAX = 7
DEFAULT_LAYER_MM = 25.0
LAYER_RANGE = (1.0, 200.0)     # mm
MAX_RANGE = (1, 50)            # tầng


class StackError(Exception):
    """Lỗi nghiệp vụ xếp chồng — GUI bắt và hiển thị."""


class StackStore:
    def __init__(self, file_path=DEFAULT_STACK_FILE):
        self.file_path = file_path
        self.bins = {b: {"count": 0, "max": DEFAULT_MAX, "layer_mm": DEFAULT_LAYER_MM} for b in BINS}
        self._listeners = []
        self._load()

    # ---------------- Persistence ----------------
    def _load(self):
        if not os.path.exists(self.file_path):
            return
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return          # file hỏng -> dùng mặc định, lần lưu sau ghi đè
        for b in BINS:
            d = data.get(b, {})
            try:
                mx = int(d.get("max", DEFAULT_MAX))
                layer = float(d.get("layer_mm", DEFAULT_LAYER_MM))
                count = int(d.get("count", 0))
            except (TypeError, ValueError):
                continue
            mx = min(max(mx, MAX_RANGE[0]), MAX_RANGE[1])
            layer = min(max(layer, LAYER_RANGE[0]), LAYER_RANGE[1])
            self.bins[b] = {"count": min(max(count, 0), mx), "max": mx, "layer_mm": layer}

    def _save(self):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(self.bins, f, ensure_ascii=False, indent=2)
        for cb in list(self._listeners):
            cb()

    def add_listener(self, callback):
        """callback() được gọi mỗi khi số đếm/cài đặt thay đổi (để GUI vẽ lại)."""
        self._listeners.append(callback)

    # ---------------- Đọc ----------------
    @staticmethod
    def _check_bin(b):
        if b not in BINS:
            raise StackError(f"Khay chứa '{b}' không hợp lệ.")

    def get(self, b):
        self._check_bin(b)
        return dict(self.bins[b])

    def is_full(self, b):
        d = self.get(b)
        return d["count"] >= d["max"]

    def offset_mm(self, b):
        """Z cộng thêm cho khay KẾ TIẾP xếp vào khay chứa `b`."""
        d = self.get(b)
        return d["layer_mm"] * d["count"]

    # ---------------- Ghi ----------------
    def set_count(self, b, count):
        self._check_bin(b)
        d = self.bins[b]
        count = int(count)
        if not (0 <= count <= d["max"]):
            raise StackError(f"Số khay phải từ 0 đến {d['max']}.")
        d["count"] = count
        self._save()

    def set_max(self, b, mx):
        self._check_bin(b)
        mx = int(mx)
        if not (MAX_RANGE[0] <= mx <= MAX_RANGE[1]):
            raise StackError(f"Số tầng tối đa phải từ {MAX_RANGE[0]} đến {MAX_RANGE[1]}.")
        d = self.bins[b]
        d["max"] = mx
        d["count"] = min(d["count"], mx)
        self._save()

    def set_layer(self, b, layer_mm):
        self._check_bin(b)
        layer_mm = float(layer_mm)
        if not (LAYER_RANGE[0] <= layer_mm <= LAYER_RANGE[1]):
            raise StackError(f"Chiều cao 1 tầng phải từ {LAYER_RANGE[0]:g} đến {LAYER_RANGE[1]:g} mm.")
        self.bins[b]["layer_mm"] = layer_mm
        self._save()

    def replace(self, b):
        """'Đã thay khay': khay chứa rỗng mới -> đếm về 0."""
        self.set_count(b, 0)

    def increment(self, b):
        d = self.get(b)
        self.bins[b]["count"] = min(d["count"] + 1, d["max"])
        self._save()
