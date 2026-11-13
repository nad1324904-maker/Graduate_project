"""
uart_tool.py — Công cụ dòng lệnh để thử STM32 mà KHÔNG cần GUI (bring-up phần cứng).
  python uart_tool.py COM5            (Windows)        python uart_tool.py /dev/ttyUSB0
  python uart_tool.py COM5 230400     (baud khác)      python uart_tool.py COM5 raw   (in cả dòng S/T mỗi lần nhận)

Gõ lệnh theo giao thức (xem PROTOCOL.md), đơn vị là COUNTS, ví dụ:
  GOTO 2 12750      JOG 1 -3825      HOME 2      HOMING 2     STOP 1      PAUSE 2      RESUME 2      CLEAR 2
  LIMIT 2 0 25500   PID 2 4.2 0 0    VMAX 2 12750   AMAX 2 21250   DB 2 5      SEL 2
  GRIP 1 (đóng kẹp)  GRIP 0 (mở kẹp)  HPOS 2 109200 (home J1 = 30° nếu 3640 counts/°)
  TRIP 2 72800 5824  (ngưỡng FAULT J1: 20° khi chạy, 1.6° khi HOMING)
Công cụ in mọi dòng nhận về (dòng S chỉ in mỗi giây một lần trừ khi có 'raw'). Thoát: Ctrl+C hoặc gõ quit.
"""
import sys
import threading
import time

import serial


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    port, raw = sys.argv[1], "raw" in sys.argv[2:]
    baud = next((int(a) for a in sys.argv[2:] if a.isdigit()), 115200)
    ser = serial.serial_for_url(port, baudrate=baud, timeout=0.05)
    stop = threading.Event()

    def reader():
        buf, last_s = b"", 0.0
        while not stop.is_set():
            buf += ser.read(256)
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                text = line.decode("ascii", "replace").strip()
                if not text:
                    continue
                if text[0] in "ST" and text[1:2] == " " and not raw:
                    if time.time() - last_s < 1.0:
                        continue
                    last_s = time.time()
                print(f"  << {text}")

    threading.Thread(target=reader, daemon=True).start()
    print(f"Đã mở {port} @ {baud}. Gõ lệnh (vd GOTO 2 12750), quit để thoát.")
    try:
        while True:
            line = input("> ").strip()
            if line.lower() in ("quit", "exit"):
                break
            if line:
                ser.write((line + "\n").encode("ascii"))
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        stop.set()
        for m in (1, 2, 3, 4):          # phanh cả 4 động cơ trước khi đóng cổng
            try:
                ser.write(f"STOP {m}\n".encode("ascii"))
            except Exception:
                break
        time.sleep(0.1)
        ser.close()


if __name__ == "__main__":
    main()