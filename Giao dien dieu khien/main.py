"""main.py — Điểm khởi động SCARA Robot GUI.

  python main.py                 chạy bình thường
  python main.py --scale 0.85    thu nhỏ giao diện (máy yếu / màn hình độ phân giải cao)
"""

import argparse

from ui import perf


def main():
    parser = argparse.ArgumentParser(description="SCARA Robot GUI (STM32F407)")
    parser.add_argument("--scale", type=float, default=1.0, help="hệ số thu phóng giao diện, vd 0.85 (mặc định 1.0)")
    args = parser.parse_args()
    perf.apply_ui_scale(args.scale)            # phải trước khi tạo cửa sổ

    from ui.app import ScaraRobotGUI
    ScaraRobotGUI().mainloop()


if __name__ == "__main__":
    main()
