"""main.py — Điểm khởi động app MASTER của hệ thống PCB Inspection (app duy nhất của đồ án).

  python main.py                 chạy bình thường
  python main.py --scale 0.85    thu nhỏ giao diện (máy yếu / màn hình độ phân giải cao)

Điều khiển robot nằm trong tab Robot (ui/robot_panel.py).
"""

import argparse

from ui import perf


def main():
    parser = argparse.ArgumentParser(description="PCB Inspection & Sorting — Master")
    parser.add_argument("--scale", type=float, default=1.0, help="hệ số thu phóng giao diện, vd 0.85 (mặc định 1.0)")
    args = parser.parse_args()
    perf.apply_ui_scale(args.scale)            # phải trước khi tạo cửa sổ

    from ui.master_app import MasterApp
    MasterApp().mainloop()


if __name__ == "__main__":
    main()
