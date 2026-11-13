"""paths.py — Thư mục dữ liệu chung (points.json, programs.json, robot_config.json) nằm ở gốc dự án."""
import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")
