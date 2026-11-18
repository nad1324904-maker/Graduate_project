# Raspberry Pi — kiểm tra PCB bằng xử lý ảnh

Raspberry Pi kiểm tra PCB theo lệnh của PC (app master trong `UI/`, xem `flow_chart.drawio`) và trả kết quả:

| Kết quả | Ý nghĩa |
|---|---|
| `PASS` | PCB đạt |
| `FAIL1` | **Lỗi 1 — ngoại quan / linh kiện** (thiếu, lệch linh kiện… thấy qua ảnh chụp) |
| `FAIL2` | **Lỗi 2 — chức năng**: khi PLC hạ xi lanh 2 cấp nguồn cho PCB, LED 7 đoạn trên PCB phải đếm lần lượt 1 → 9; không đếm đủ / sai thứ tự / không sáng là lỗi chức năng |

PC là master: Pi **không tự chạy**, chỉ làm khi nhận lệnh và luôn trả lời.

Thư mục này hiện có **`pi_test_ui.py`**: công cụ chạy trên PC, đóng vai app master để thử chương trình server trên Pi.

---

## 1. Chạy công cụ thử

```bash
pip install customtkinter pillow
cd "Raspberry Pi"
python pi_test_ui.py
```

- **Chưa có chương trình trên Pi:** bật **"Dùng Pi giả lập"** rồi bấm Connect. Tool tự mở một server giả trên máy
  (127.0.0.1) trả lời đúng giao thức ở mục 2. Kết quả `inspect` lần lượt là PASS / FAIL1 / FAIL2. Server giả này (lớp
  `MockPi` trong file) cũng là ví dụ mẫu cho phía Pi.
- **Đã có chương trình trên Pi:** tắt giả lập, nhập IP của Pi (mặc định `192.168.1.100`) và cổng `5000`, rồi Connect.

| Khung | Chức năng |
|---|---|
| **1. Kết nối** | IP, cổng, Connect. **Test Connection**: chưa Connect thì chỉ kiểm tra cổng TCP có mở; đã Connect thì gửi `ping` và đo thời gian khứ hồi |
| **2. Camera** | **Capture**: Pi chụp và gửi ảnh JPEG về, hiển thị ảnh + kích thước |
| **3. Kiểm tra PCB** | **Start Inspection**: kết quả PASS / FAIL1 / FAIL2, thời gian xử lý ảnh do Pi báo (`process_time_ms`), tổng thời gian PC đo được, JSON phản hồi đầy đủ |
| **4. Thống kê** | Tổng số lần kiểm tra, số PASS / FAIL1 / FAIL2, tỉ lệ đạt |
| **Log** | Mọi gói PC gửi (TX) và Pi trả lời (RX), lỗi mất kết nối / quá thời gian chờ |

---

## 2. Giao thức PC ↔ Pi (chương trình trên Pi phải làm đúng)

- **Kết nối:** TCP/IP. **Pi là server**, nghe ở cổng **5000**. PC là client (một kết nối, giữ suốt phiên làm việc).
- **Khung gói** (cả hai chiều): `[4 byte big-endian: độ dài JSON][JSON UTF-8]`.
  Nếu JSON có `"image_size": N` thì **N byte JPEG thô** nối ngay sau JSON.
- Mỗi lệnh PC gửi có `"id"` tăng dần. Pi **gửi lại đúng `"id"` đó**; PC bỏ qua phản hồi có `id` cũ.
- Hỏi–đáp tuần tự: PC chỉ gửi lệnh mới sau khi đã nhận phản hồi (hoặc hết thời gian chờ) của lệnh trước.

| PC gửi | Pi trả lời | Thời gian chờ tối đa |
|---|---|---|
| `{"id":1,"cmd":"ping"}` | `{"id":1,"cmd":"ping","status":"ok"}` | 3 s |
| `{"id":2,"cmd":"capture"}` | `{"id":2,"cmd":"capture","status":"ok","image_size":N}` + N byte JPEG | 10 s |
| `{"id":3,"cmd":"inspect"}` | `{"id":3,"cmd":"inspect","status":"ok","result":"PASS"\|"FAIL1"\|"FAIL2","process_time_ms":123.4, …}` | 20 s |
| lỗi bất kỳ | `{"id":N,"status":"error","message":"…"}` | — |

- Phản hồi `inspect` được thêm **trường tùy ý** (vd `"defect":"thieu linh kien R12"`, `"led_last_digit":4`).
  Tool hiển thị nguyên JSON để kiểm tra.
- Độ dài JSON tối đa 1 MB, ảnh tối đa 20 MB. Sai khung (độ dài vô lý, không phải JSON) thì PC coi là mất kết nối.
- Quá thời gian chờ, app master sẽ báo lỗi và dừng hệ thống (nhánh B của lưu đồ).

---

## 3. Khung chương trình phía Pi (gợi ý)

```python
import json, socket, struct

def recv_exact(conn, n):
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise ConnectionError
        buf += chunk
    return buf

def send_packet(conn, obj, image=b""):
    data = json.dumps(obj, ensure_ascii=False).encode()
    conn.sendall(struct.pack(">I", len(data)) + data + image)

srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("0.0.0.0", 5000)); srv.listen(1)
while True:
    conn, _ = srv.accept()
    try:
        while True:
            (n,) = struct.unpack(">I", recv_exact(conn, 4))
            req = json.loads(recv_exact(conn, n))
            rid, cmd = req.get("id"), req.get("cmd")
            if cmd == "ping":
                send_packet(conn, {"id": rid, "cmd": "ping", "status": "ok"})
            elif cmd == "capture":
                jpg = chup_anh_jpeg()                         # <- phần camera của bạn
                send_packet(conn, {"id": rid, "cmd": "capture", "status": "ok", "image_size": len(jpg)}, jpg)
            elif cmd == "inspect":
                result, ms = kiem_tra_pcb()                   # <- "PASS" / "FAIL1" / "FAIL2", thời gian xử lý (ms)
                send_packet(conn, {"id": rid, "cmd": "inspect", "status": "ok", "result": result,
                                   "process_time_ms": ms})
            else:
                send_packet(conn, {"id": rid, "status": "error", "message": f"unknown cmd {cmd}"})
    except (ConnectionError, OSError):
        conn.close()
```

---

## 4. Thứ tự thử

1. Chạy tool với **Pi giả lập** để quen giao thức và giao diện.
2. Chạy server trên Pi. **Test Connection** khi chưa Connect phải báo cổng TCP mở (cùng mạng LAN, đúng IP, tường lửa cho
   cổng 5000). Connect rồi Test lại: `ping` phải có phản hồi.
3. **Capture**: ảnh rõ, đủ sáng, đúng vùng PCB.
4. **Start Inspection** với PCB tốt, PCB lỗi linh kiện, PCB lỗi chức năng (đang được cấp nguồn). Kết quả phải đúng và
   nằm trong thời gian chờ.
5. Kiểm tra nhiều lần liên tiếp, xem tỉ lệ ở khung Thống kê để cân chỉnh.

---

## 5. Đưa vào app master

Lớp `PiLink` trong `pi_test_ui.py` không phụ thuộc giao diện. Khi giao thức đã chạy ổn với Pi thật, chuyển lớp này sang
`UI/comm/` để app master dùng lại. Nút demo **Chụp ảnh** và **Test chức năng** (tab Vận hành → MANUAL) khi đó sẽ gửi
`capture` / `inspect` thật.
