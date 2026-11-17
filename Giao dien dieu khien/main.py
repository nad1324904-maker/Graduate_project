"""main.py — Điểm khởi động SCARA Robot GUI.

  python main.py                 chạy bình thường (giao diện sáng)
  python main.py --dark          giao diện tối
  python main.py --scale 0.85    thu nhỏ giao diện (máy yếu / màn hình độ phân giải cao)
"""

import argparse
import os

from ui import perf


def main():
    parser = argparse.ArgumentParser(description="SCARA Robot GUI (STM32F407)")
    parser.add_argument("--scale", type=float, default=1.0, help="hệ số thu phóng giao diện, vd 0.85 (mặc định 1.0)")
    parser.add_argument("--dark", action="store_true", help="dùng giao diện tối (mặc định: sáng)")
    args = parser.parse_args()
    os.environ["SCARA_THEME"] = "dark" if args.dark else "light"   # ui/theme.py đọc biến này lúc import
    perf.apply_ui_scale(args.scale)            # phải trước khi tạo cửa sổ

    from ui.app import ScaraRobotGUI
    ScaraRobotGUI().mainloop()


if __name__ == "__main__":
    main()
