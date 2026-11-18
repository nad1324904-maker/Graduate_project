# Raspberry Pi — kiểm tra ngoại quan và kiểm tra chức năng PCB

Raspberry Pi làm 2 việc theo lệnh của PC (app master trong `UI/`, xem `flow_chart.drawio`):

1. **Kiểm tra ngoại quan (Lỗi 1):**
   - Khi PCB dừng ở trạm (xi lanh 1 đã chặn), PC gửi lệnh chụp.
   - Pi chụp ảnh và xử lý ảnh (thiếu / lệch linh kiện…), rồi trả **ĐẠT** hoặc **LỖI**.
2. **Kiểm tra chức năng (Lỗi 2):**
   - PLC hạ xi lanh 2: 2 đầu kim chạm cổng domino và **cấp nguồn cho PCB**. Mạch đúng chức năng thì **LED 7 đoạn trên
     PCB đếm lần lượt 1 → 9**.
   - PC gửi lệnh kiểm tra, Pi dùng camera đọc LED và trả **ĐẠT** (thấy đủ 1 → 9 đúng thứ tự) hoặc **LỖI**.

PC là master: Pi **không tự chạy**, chỉ làm khi nhận lệnh và luôn trả lời.

Thư mục này hiện có **`pi_test_ui.py`**: công cụ chạy trên PC, đóng vai app master để thử chương trình trên Pi.

---

## 1. Chạy công cụ thử

```bash
pip install customtkinter pillow
cd "Raspberry Pi"
python pi_test_ui.py
```

- **Chưa có chương trình trên Pi:** bật **"Dùng Pi giả lập"** rồi bấm Connect. Tool tự mở một server giả trên máy
  (127.0.0.1), trả lời đúng giao thức ở mục 2. Kết quả lần lượt là ĐẠT / LỖI / không thấy PCB. Server giả này (lớp
  `MockPi` trong file) cũng là ví dụ mẫu cho phía Pi.
- **Đã có chương trình trên Pi:** tắt giả lập, nhập IP của Pi (gợi ý đặt IP tĩnh `192.168.0.20`) và cổng `5000`, rồi Connect.

| Khung | Chức năng |
|---|---|
| **1. Kết nối** | IP, cổng, Connect; nút **PING**, **STATUS**; **Mã PCB** gửi kèm lệnh; ô gõ lệnh tự do |
| **2. Ngoại quan** | Nút **CAPTURE**, kết quả ĐẠT / LỖI 1 / KHÔNG THẤY PCB, thời gian phản hồi so với timeout 5 s |
| **3. Chức năng** | Nút **FUNC**, 9 ô số sáng dần theo `FUNCSTEP` Pi gửi về, kết quả ĐẠT / LỖI 2, thời gian so với timeout 20 s |
| **4. Ảnh** | Nút **IMAGE**: lấy ảnh vừa chụp từ Pi và hiển thị |
| **Log** | Mọi dòng PC gửi (TX) và Pi trả lời (RX); báo đỏ khi quá thời gian chờ |

> Khi thử **FUNC**, PCB phải đang có nguồn: cho PLC hạ xi lanh 2 bằng `PLC/plc_test_ui.py`, hoặc cấp nguồn tay cho PCB.

---

## 2. Giao thức PC ↔ Pi (chương trình trên Pi phải làm đúng)

- **Kết nối:** TCP. **Pi là server**, nghe ở cổng **5000**. PC (một client) kết nối tới.
- **Định dạng:** mỗi lệnh / phản hồi là **1 dòng text UTF-8 kết thúc `\n`**, các trường cách nhau bởi dấu cách. Lý do lỗi
  viết liền bằng dấu `_` (vd `thieu_linh_kien_R12`).
- `<id>` là mã PCB do PC gửi. Pi **gửi trả đúng `<id>` đó** để PC biết kết quả của PCB nào.

| PC gửi | Pi trả lời | Thời gian tối đa |
|---|---|---|
| `PING` | `PONG` | 2 s |
| `STATUS` | `STATUS READY camera=ok` (hoặc `STATUS BUSY …`, `camera=error`) | 2 s |
| `CAPTURE <id>` | Chụp ảnh và kiểm tra ngoại quan, rồi trả **một** trong các dòng: `VIS <id> OK` · `VIS <id> NG <lý_do>` · `VIS <id> NOPCB` (không thấy PCB trong ảnh) | **5 s** |
| `FUNC <id>` | Đọc LED 7 đoạn. Mỗi khi thấy một số mới thì gửi `FUNCSTEP <id> <số>`. Kết thúc bằng **một** dòng: `FUNC <id> OK` (thấy đủ 1 → 9 đúng thứ tự) · `FUNC <id> NG <lý_do>` (vd `dung_o_so_4`, `khong_sang`, `sai_thu_tu`) | **20 s** |
| `IMAGE <id>` | `IMG <id> <số byte>` + `\n`, **ngay sau đó** là đúng `<số byte>` byte ảnh **JPEG** (ảnh của lần CAPTURE gần nhất, nên vẽ khung lỗi lên ảnh) | 5 s |
| lệnh không hiểu | `ERR <id> <lý_do>` | — |

- Khi PC vừa kết nối, Pi có thể gửi một dòng chào `HELLO <tên> <phiên bản>` (không bắt buộc).
- Các thời gian tối đa khớp tab **Cài đặt → Thời gian chờ** của app master. Quá thời gian, app master báo lỗi và dừng
  hệ thống (nhánh B của lưu đồ).
- Trong lúc đang xử lý `FUNC` (có thể mất vài giây), Pi **vẫn phải trả lời `PING`**. Nên xử lý mỗi lệnh ở một luồng riêng.

**Ví dụ một phiên** (`>` = PC gửi, `<` = Pi trả lời):

```
> CAPTURE 128
< VIS 128 OK
> FUNC 128
< FUNCSTEP 128 1
< FUNCSTEP 128 2
  ...
< FUNCSTEP 128 9
< FUNC 128 OK
> IMAGE 128
< IMG 128 48213
< (48213 byte JPEG)
```

---

## 3. Khung chương trình phía Pi (gợi ý)

```python
import socketserver, threading

class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        lock = threading.Lock()
        def send(line, raw=b""):
            with lock:
                self.wfile.write(line.encode() + b"\n" + raw)
        for raw in self.rfile:                                  # mỗi vòng = 1 dòng lệnh
            parts = raw.decode(errors="replace").split()
            if parts:
                threading.Thread(target=run_command, args=(parts, send), daemon=True).start()

def run_command(parts, send):
    cmd, pid = parts[0].upper(), (parts[1] if len(parts) > 1 else "0")
    if cmd == "PING":
        send("PONG")
    elif cmd == "CAPTURE":
        ok, why = kiem_tra_ngoai_quan()          # <- phần xử lý ảnh của bạn
        send(f"VIS {pid} OK" if ok else f"VIS {pid} NG {why}")
    elif cmd == "FUNC":
        ...                                       # mỗi số mới đọc được: send(f"FUNCSTEP {pid} {so}")
    else:
        send(f"ERR {pid} unknown_command")

socketserver.ThreadingTCPServer.allow_reuse_address = True
socketserver.ThreadingTCPServer(("0.0.0.0", 5000), Handler).serve_forever()
```

---

## 4. Thứ tự thử

1. Chạy tool với **Pi giả lập** để quen giao thức và giao diện.
2. Chạy chương trình trên Pi. **PING** phải có `PONG` (cùng mạng LAN, đúng IP, tường lửa cho cổng 5000).
3. **CAPTURE** với PCB tốt, PCB lỗi và khi không có PCB. Kết quả phải đúng, và thời gian phản hồi phải dưới 5 s.
4. **IMAGE:** ảnh rõ, đủ sáng, đúng vùng PCB.
5. **FUNC** với PCB tốt (LED đếm đủ 1 → 9) và PCB lỗi. Ô số sáng dần đúng theo LED, kết quả đúng, dưới 20 s.
6. Thử nhiều lần liên tiếp và ghi lại tỉ lệ đúng / sai để cân chỉnh.

---

## 5. Đưa vào app master

Lớp `PiLink` trong `pi_test_ui.py` không phụ thuộc giao diện. Khi giao thức đã chạy ổn với Pi thật, chuyển lớp này sang
`UI/comm/` để app master dùng lại. Các nút demo **Chụp ảnh** (tab Vận hành → MANUAL) và phần kiểm tra chức năng (sau
khi PLC hạ xi lanh 2) khi đó sẽ gửi `CAPTURE` / `FUNC` thật.
