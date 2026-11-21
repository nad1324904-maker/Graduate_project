"""
program_executor.py — Điều phối chạy Program tuần tự (Phase 4).
------------------------------------------------------------------------
Đây là lớp "PC-side coordinator": nó KHÔNG phải GUI, cũng KHÔNG phải
backend — nó đứng giữa, đọc Step từ ProgramStore + Point từ PointStore,
rồi tuần tự gửi lệnh xuống RobotBackendBase và chờ hoàn thành mới gửi
Step kế tiếp (mục 16: "The PC sends only ONE Step at a time... Wait for
STEP_DONE... send next Step").

Tách riêng khỏi gui.py để:
  - Logic điều phối Program không phụ thuộc CustomTkinter, dễ test độc lập
    (xem test ở cuối phiên làm việc).
  - Đúng yêu cầu Phase 6 "Separate GUI logic from the simulation backend"
    — executor này chỉ phụ thuộc vào backend_base.RobotBackendBase, point_
    store, program_store, không phụ thuộc gui.py.

GUI chỉ cần: tạo ProgramExecutor, gọi start()/pause()/resume()/stop()/
reset(), và đăng ký callback để cập nhật hiển thị — không tự sequencing.
"""

from enum import Enum

from comm.backend_base import RobotStatus
from comm.errors import UartError
from core.program_store import describe_step
from core.stack_store import BIN_LABELS


class ExecState(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


class ExecutorError(Exception):
    pass


class ProgramExecutor:
    def __init__(self, backend, point_store, program_store, stack_store=None):
        self.backend = backend
        self.point_store = point_store
        self.program_store = program_store
        self.stack_store = stack_store   # None = bỏ qua đánh dấu xếp chồng (Z giữ nguyên Point)
        self._pending_stack = None       # khay chứa đang xếp dở: tăng đếm ở GRIP OFF kế tiếp
        self._on_stack_placed = None     # callback(bin, count) sau khi thả xong 1 khay

        self.program_name = None
        self.steps = []
        self.current_index = -1          # -1 = chưa bắt đầu
        self.state = ExecState.IDLE

        self._waiting_step_done = False  # đã gửi Step, đang chờ robot BUSY->READY
        self._delay_left = 0.0           # giây còn lại của Step DELAY đang chạy
        self.error_message = ""          # lý do của ExecState.ERROR gần nhất
        self._on_step_started = None     # callback(index, step)
        self._on_step_done = None        # callback(index, step)
        self._on_state_change = None     # callback(old_state, new_state)

        # Backend báo BUSY->READY nghĩa là Step vừa gửi đã xong (STEP_DONE)
        self.backend.set_status_change_callback(self._on_backend_status_change)

    # ---------------- Callback đăng ký từ GUI ----------------
    def set_callbacks(self, on_step_started=None, on_step_done=None, on_state_change=None,
                      on_stack_placed=None):
        self._on_step_started = on_step_started
        self._on_step_done = on_step_done
        self._on_state_change = on_state_change
        self._on_stack_placed = on_stack_placed

    # ---------------- Xếp chồng ----------------
    def _z_max(self):
        limits = getattr(self.backend, "joint_limits", None)
        try:
            return float(limits["Z"][1])
        except (TypeError, KeyError, IndexError, ValueError):
            return None

    def _limit_error(self, step, point):
        """Lỗi nếu đích của Step MOVE nằm ngoài giới hạn khớp của backend (Settings → Joint Limits), ngược lại None.
        Kiểm tra trước ở START để không chạy dở chừng rồi mới bị chặn."""
        limits = getattr(self.backend, "joint_limits", None) or {}
        for axis, value in point.items():
            if axis not in limits:
                continue
            lo, hi = limits[axis]
            if not (lo - 0.01 <= float(value) <= hi + 0.01):
                unit = "mm" if axis == "Z" else "°"
                return (f"Point '{step['point']}': {axis} = {float(value):.2f} {unit} nằm ngoài giới hạn "
                        f"[{lo:g}, {hi:g}] — Teach lại Point hoặc sửa Settings → Joint Limits.")
        return None

    def _stack_target(self, step):
        """(point đã cộng Z, lỗi) cho Step MOVE: Z cộng thêm nếu xếp chồng, rồi kiểm tra giới hạn khớp."""
        point = self.point_store.get(step["point"])
        b = step.get("stack")
        if not b or self.stack_store is None:
            err = self._limit_error(step, point)
            return (None, err) if err else (point, None)
        d = self.stack_store.get(b)
        label = BIN_LABELS.get(b, b)
        if d["count"] >= d["max"]:
            return None, (f"{label} đã đầy ({d['count']}/{d['max']} tầng) — thay khay chứa rỗng "
                          f"rồi bấm 'Đã thay khay'.")
        point["Z"] = float(point["Z"]) + d["layer_mm"] * d["count"]
        zmax = self._z_max()
        if zmax is not None and point["Z"] > zmax + 1e-6:
            return None, (f"{label} tầng {d['count'] + 1}: Z = {point['Z']:.1f} mm vượt giới hạn "
                          f"Z max {zmax:g} mm — giảm số tầng tối đa hoặc chiều cao 1 tầng.")
        err = self._limit_error(step, point)
        return (None, err) if err else (point, None)

    # ---------------- Điều khiển vòng đời (mục 17-20) ----------------
    def start(self, program_name):
        """START (mục 17): validate trước, rồi bắt đầu gửi Step đầu tiên."""
        is_valid, missing = self.program_store.validate(program_name, self.point_store)
        if not is_valid:
            raise ExecutorError(
                f"Không thể START: chương trình tham chiếu Point không tồn tại: {missing}")

        prog = self.program_store.get(program_name)
        if not prog["steps"]:
            raise ExecutorError("Không thể START: chương trình chưa có Step nào.")

        # Point ngoài giới hạn khớp / khay chứa đầy / xếp chồng vượt Z max: báo NGAY, không chạy dở chừng
        for step in prog["steps"]:
            if step["type"] == "MOVE":
                _, err = self._stack_target(step)
                if err:
                    raise ExecutorError(f"Không thể START: {err}")

        self.program_name = program_name
        self.steps = prog["steps"]
        self.current_index = -1
        self._pending_stack = None
        self._set_state(ExecState.RUNNING)
        self._send_next_step()

    def pause(self):
        """PAUSE (mục 18): yêu cầu robot controller giữ nguyên vị trí
        NGAY LẬP TỨC (không chỉ ngừng gửi Step mới), đồng thời ngừng gửi
        Step kế tiếp và giữ nguyên Step/trạng thái hiện tại."""
        if self.state != ExecState.RUNNING:
            return
        self.backend.pause_motion()
        self._set_state(ExecState.PAUSED)

    def resume(self):
        if self.state != ExecState.PAUSED:
            return
        self.backend.resume_motion()
        self._set_state(ExecState.RUNNING)
        if not self._waiting_step_done:
            self._send_next_step()

    def stop(self):
        """STOP (mục 19): hủy NGAY chuyển động hiện tại (không giữ để
        resume như PAUSE), dừng hẳn tiến trình Program, KHÔNG tự động
        HOME. Muốn chạy lại phải RESET rồi START lại từ đầu."""
        if self.state not in (ExecState.RUNNING, ExecState.PAUSED):
            return
        # QUAN TRỌNG: đặt cờ/trạng thái TRƯỚC khi gọi abort_motion(), vì
        # abort_motion() có thể bắn callback status-change ĐỒNG BỘ ngay
        # trong lệnh gọi này (BUSY->READY) — nếu chưa đặt cờ trước, executor
        # sẽ tưởng đó là STEP_DONE của Step đang dang dở và tự gửi Step kế
        # tiếp, dù người dùng vừa bấm STOP.
        self._waiting_step_done = False
        self._set_state(ExecState.STOPPED)
        self.backend.abort_motion()

    def fail(self, reason=""):
        """Dừng chương trình vì LỖI từ robot (STM32 từ chối lệnh / báo fault) — khác stop() ở chỗ
        state = ERROR để GUI phân biệt được. Không tự HOME."""
        if self.state not in (ExecState.RUNNING, ExecState.PAUSED):
            return
        self.error_message = reason
        self._waiting_step_done = False
        self._set_state(ExecState.ERROR)
        try:
            self.backend.abort_motion()
        except Exception:
            pass   # best-effort: có thể đang mất kết nối; STM32 cũng tự dừng bằng watchdog

    def reset(self):
        """RESET (mục 20): reset trạng thái điều phối, KHÔNG tự động
        HOME — RESET không phải lệnh homing."""
        self.program_name = None
        self.steps = []
        self.current_index = -1
        self._waiting_step_done = False
        self._pending_stack = None
        self.error_message = ""
        self._set_state(ExecState.IDLE)

    # ---------------- Nội bộ: gửi Step / nhận STEP_DONE ----------------
    def _send_next_step(self):
        if self.state != ExecState.RUNNING:
            return
        self.current_index += 1
        if self.current_index >= len(self.steps):
            self._set_state(ExecState.COMPLETED)
            return

        step = self.steps[self.current_index]
        self._waiting_step_done = True
        if self._on_step_started:
            self._on_step_started(self.current_index, step)

        if step["type"] == "MOVE":
            point, err = self._stack_target(step)
            if err:
                self.fail(err)
                return
            if step.get("stack") and self.stack_store is not None:
                self._pending_stack = step["stack"]
            try:
                self.backend.send_absolute_target(point)
            except UartError as e:                 # bị chặn (ngoài giới hạn) / mất kết nối: dừng chương trình, báo ERROR
                self._pending_stack = None
                self.fail(str(e))
                return
        elif step["type"] == "GRIP":
            try:
                self.backend.grip(step["action"])
            except UartError as e:
                self.fail(str(e))
                return
        elif step["type"] == "DELAY":
            self._delay_left = float(step["seconds"])
            return  # hết giờ do update(dt) quyết định, không chờ backend
        else:
            raise ExecutorError(f"Loại Step không hợp lệ: {step['type']}")

        # Trường hợp Step không cần di chuyển gì (target trùng actual sẵn)
        # thì backend có thể vẫn ở READY ngay lập tức — không đợi callback.
        if not self.backend.is_moving():
            self._handle_step_done()

    def _on_backend_status_change(self, old_status, new_status):
        # BUSY -> READY khi đang chờ Step hiện tại = STEP_DONE (mục 16).
        if new_status == RobotStatus.ERROR and self.state in (ExecState.RUNNING, ExecState.PAUSED):
            self.fail("Robot báo lỗi")
            return
        # Step DELAY không chờ backend — bỏ qua READY lạc tới trong lúc chờ.
        if (self._waiting_step_done and new_status == RobotStatus.READY
                and self.steps[self.current_index]["type"] != "DELAY"):
            self._handle_step_done()

    def _handle_step_done(self):
        if not self._waiting_step_done:
            return
        self._waiting_step_done = False
        step = self.steps[self.current_index]
        if (step["type"] == "GRIP" and step["action"] == "OFF"
                and self._pending_stack and self.stack_store is not None):
            b, self._pending_stack = self._pending_stack, None
            self.stack_store.increment(b)          # khay vừa được thả vào khay chứa
            if self._on_stack_placed:
                self._on_stack_placed(b, self.stack_store.get(b)["count"])
        if self._on_step_done:
            self._on_step_done(self.current_index, step)
        if self.state == ExecState.RUNNING:
            self._send_next_step()
        # Nếu đang PAUSED/STOPPED thì dừng lại đúng tại đây, không gửi tiếp.

    def update(self, dt):
        """Gọi mỗi tick từ GUI — chỉ đếm giờ cho Step DELAY. PAUSED thì
        không đếm nên thời gian còn lại được giữ nguyên."""
        if self.state != ExecState.RUNNING or not self._waiting_step_done:
            return
        if self.steps[self.current_index]["type"] != "DELAY":
            return
        self._delay_left -= dt
        if self._delay_left <= 0:
            self._delay_left = 0.0
            self._handle_step_done()

    # ---------------- Trạng thái đọc ra ----------------
    def get_progress(self):
        """Trả về (current_step_1_based, total_steps) — 0/total nếu
        chưa bắt đầu."""
        total = len(self.steps)
        current = max(0, self.current_index + (0 if self._waiting_step_done else 1))
        if self.state == ExecState.COMPLETED:
            current = total
        return current, total

    def current_step_description(self):
        if 0 <= self.current_index < len(self.steps):
            return describe_step(self.steps[self.current_index])
        return "—"

    def _set_state(self, new_state):
        old = self.state
        if old == new_state:
            return
        self.state = new_state
        if self._on_state_change:
            self._on_state_change(old, new_state)
