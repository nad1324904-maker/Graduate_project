"""offline_backend.py — Backend "chưa kết nối" (thay cho SimulationBackend cũ)."""

from comm.backend_base import RobotBackendBase, RobotStatus
from comm.errors import UartError
from core.robot_config import HOME_POSITION


class OfflineBackend(RobotBackendBase):
    """Backend 'chưa kết nối' — thay cho SimulationBackend cũ. KHÔNG mô phỏng gì: vị trí chỉ là Home mặc định,
    mọi lệnh chuyển động/kẹp đều raise UartError. GUI dùng nó để các hàm đọc (get_*) không phải kiểm tra None."""

    def __init__(self):
        self._pos = dict(HOME_POSITION)

    @staticmethod
    def _no(*_a, **_k):
        raise UartError("Chưa kết nối STM32 — hãy Connect ở tab Settings.")

    pause_motion = resume_motion = abort_motion = home = grip = _no
    send_absolute_target = jog = emergency_stop = reset_estop = _no

    def set_joint_limits(self, limits): pass       # chỉ là cấu hình — không cần kết nối
    def set_max_velocity(self, velocities): pass
    def is_motion_paused(self): return False
    def is_homed(self): return False
    def get_gripper_state(self): return {"commanded": "OFF", "actual": None}
    def update(self, dt): pass
    def get_actual_position(self): return dict(self._pos)
    def get_target_position(self): return dict(self._pos)
    def get_status(self): return RobotStatus.READY
    def is_moving(self): return False
    def get_telemetry(self): return {}
    def is_connected(self): return False
    def set_status_change_callback(self, callback): pass
    def set_home_done_callback(self, callback): pass
    def set_gripper_change_callback(self, callback): pass
