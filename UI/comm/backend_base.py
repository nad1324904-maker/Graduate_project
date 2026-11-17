"""
backend_base.py — Giao diện chung cho mọi backend điều khiển robot.
------------------------------------------------------------------------
Đây là phần "Phase 6" làm trước, vì mọi phase sau (2-5) đều cần code theo
đúng interface này ngay từ đầu để khỏi phải viết lại.

GUI / ProgramExecutor CHỈ được phép nói chuyện với robot qua các hàm định
nghĩa ở đây — không bao giờ đụng trực tiếp vào thuộc tính nội bộ của
SimulationBackend. Nhờ vậy, sau này viết thêm UartRobotBackend(RobotBackendBase)
để nói chuyện thật với STM32, GUI và ProgramExecutor không cần sửa gì cả.
"""

from abc import ABC, abstractmethod
from enum import Enum


class RobotStatus(str, Enum):
    """Trạng thái robot chung — mọi backend (mô phỏng hay UART thật) đều
    phải báo cáo qua các giá trị này, để GUI/ProgramExecutor không cần
    biết backend cụ thể là gì (mục 23)."""
    READY = "READY"
    BUSY = "BUSY"
    DONE = "DONE"     # dành cho lớp điều phối Program hiển thị khi vừa
                       # chạy xong — backend không tự set giá trị này.
    ERROR = "ERROR"


class RobotBackendBase(ABC):
    """Interface trừu tượng — SimulationBackend (mô phỏng) và sau này
    UartRobotBackend (thật) đều phải implement đầy đủ các hàm này."""

    # ---- Tạm dừng/tiếp tục chuyển động đang chạy (mục 18) ----
    @abstractmethod
    def pause_motion(self):
        """PAUSE (mục 18): yêu cầu robot controller giữ nguyên vị trí
        NGAY LẬP TỨC — không phải chỉ ngừng gửi Step mới. Với phần cứng
        thật, đây là việc STM32 (bộ điều khiển thời gian thực) xử lý;
        PC/GUI chỉ gửi yêu cầu và chờ phản hồi."""

    @abstractmethod
    def resume_motion(self):
        """Tiếp tục chuyển động đang dang dở sau pause_motion()."""

    @abstractmethod
    def is_motion_paused(self) -> bool: ...

    @abstractmethod
    def abort_motion(self):
        """Dùng cho STOP: HỦY HẲN target đang dang dở (không phải tạm
        giữ để resume như pause_motion), đưa robot về READY ngay tại vị
        trí hiện tại — sẵn sàng nhận lệnh mới (JOG/HOME/START) mà không
        cần chờ. Khác pause_motion() ở chỗ không thể resume() lại được."""

    # ---- Cấu hình runtime (mục Settings — Joint Limits / Motion Profile) ----
    @abstractmethod
    def set_joint_limits(self, limits: dict):
        """Cập nhật giới hạn hành trình từng khớp lúc runtime, từ màn
        hình Cài đặt (không phải hard-code nữa). `limits`: {axis: (min,
        max), ...}. Áp dụng ngay cho JOG/MOVE gửi SAU lệnh này — implement
        thật (UartRobotBackend) cần đẩy giá trị này xuống STM32."""

    @abstractmethod
    def set_max_velocity(self, velocities: dict):
        """Cập nhật Vmax từng khớp (mục Motion Profile trong Cài đặt).
        `velocities`: {axis: value, ...}. Áp dụng từ update(dt) / chu kỳ
        điều khiển kế tiếp."""

    # ---- Di chuyển khớp ----
    @abstractmethod
    def send_absolute_target(self, targets: dict):
        """Gửi TARGET tuyệt đối mới cho một hoặc nhiều khớp."""

    @abstractmethod
    def jog(self, axis: str, direction: int, step: float):
        """JOG theo khớp: target mới = target hiện tại + direction*step."""

    @abstractmethod
    def home(self):
        """Yêu cầu robot chạy về vị trí Home (thao tác độc lập, có
        HOME_DONE/HOME_ERROR riêng, không lẫn với STOP/RESET)."""

    def is_estop(self) -> bool:
        """True nếu STM32 đang ở trạng thái E-STOP (khóa chuyển động cho tới khi reset_estop()). Backend không có E-Stop: False."""
        return False

    @abstractmethod
    def is_homed(self) -> bool:
        """True nếu lần Home gần nhất đã hoàn tất và chưa có gì bất
        thường xảy ra kể từ đó (theo mô hình đơn giản hoá của backend)."""

    # ---- Kẹp ----
    @abstractmethod
    def grip(self, action: str):
        """action: 'ON' hoặc 'OFF'."""

    @abstractmethod
    def get_gripper_state(self) -> dict:
        """Trả về {'commanded': 'ON'/'OFF', 'actual': 'ON'/'OFF'/None}.
        actual=None nghĩa là KHÔNG có cảm biến thật để xác nhận — GUI
        không được hiển thị như thể đã chắc chắn kẹp đóng/mở."""

    # ---- Vòng lặp / trạng thái ----
    @abstractmethod
    def update(self, dt: float):
        """Được gọi đều đặn (mỗi tick) để tiến hoá trạng thái mô phỏng /
        polling trạng thái phần cứng thật."""

    @abstractmethod
    def get_actual_position(self) -> dict: ...

    @abstractmethod
    def get_target_position(self) -> dict: ...

    @abstractmethod
    def get_status(self): ...

    @abstractmethod
    def is_moving(self) -> bool: ...

    @abstractmethod
    def set_status_change_callback(self, callback):
        """callback(old_status, new_status)."""

    @abstractmethod
    def set_home_done_callback(self, callback):
        """callback(success: bool) — được gọi khi HOME hoàn tất
        (HOME_DONE) hoặc thất bại (HOME_ERROR)."""

    @abstractmethod
    def set_gripper_change_callback(self, callback):
        """callback(commanded, actual) — được gọi khi trạng thái kẹp
        (commanded hoặc actual) thay đổi."""
