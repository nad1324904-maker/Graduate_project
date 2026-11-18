# Raspberry Pi — kiểm tra PCB bằng xử lý ảnh

Raspberry Pi kiểm tra PCB theo lệnh của PC (app master trong `UI/`) và trả kết quả:

| Kết quả | Ý nghĩa |
|---|---|
| `PASS` | PCB đạt |
| `FAIL1` | **Lỗi 1 — linh kiện / ngoại quan** (thiếu, lệch linh kiện… thấy qua ảnh chụp) |
| `FAIL2` | **Lỗi 2 — chức năng**: khi PLC hạ xi lanh 2 cấp nguồn cho PCB, LED 7 đoạn trên PCB phải đếm 1 → 9 |

PC là master: Pi **không tự chạy**, chỉ làm khi nhận lệnh và luôn trả lời.

**Hướng dẫn nối dây mạng, đặt IP và kết nối từ app master:** xem [HUONG_DAN_KET_NOI.md](../HUONG_DAN_KET_NOI.md).

---

## 1. Công cụ thử: `pi_tcp_test_ui.py`

Do người phụ trách xử lý ảnh viết và đã thử với Pi thật. Chạy trên PC, đóng vai PC master để thử riêng server trên Pi.

```bash
pip install customtkinter pillow
cd "Raspberry Pi"
python pi_tcp_test_ui.py
```

| Khung | Chức năng |
|---|---|
| **Connection Settings** | IP (mặc định `192.168.1.100`), Port `5000`, Connect. **Test Connection**: chưa Connect thì chỉ kiểm tra cổng TCP có mở; đã Connect thì gửi `ping`, đo thời gian khứ hồi |
| **Camera Test** | **Capture Image**: Pi chụp, gửi ảnh JPEG về |
| **Inspection Result** | **Start Inspection**: PASS / FAIL1 / FAIL2, thời gian xử lý ảnh trên Pi, tổng thời gian PC đo, JSON phản hồi |
| **Statistics** | Tổng số, PASS / FAIL1 / FAIL2, tỉ lệ đạt |
| **Communication Monitor** | Mọi gói gửi (TX) / nhận (RX) |

---

## 2. Giao thức PC ↔ Pi

- **TCP/IP**, **Pi là server** (cổng **5000**), PC là client và giữ một kết nối suốt phiên làm việc.
- **Khung gói** (cả hai chiều): `[4 byte big-endian: độ dài JSON][JSON UTF-8]`.
  Nếu JSON có `"image_size": N` thì **N byte JPEG thô** nối ngay sau JSON.
- Mỗi lệnh có `"id"` tăng dần. Pi **gửi lại đúng `"id"`** đó; PC bỏ qua phản hồi có `id` cũ (đến muộn sau khi đã quá
  thời gian chờ).
- **Hỏi – đáp tuần tự:** PC chỉ gửi lệnh mới sau khi đã nhận phản hồi (hoặc quá thời gian chờ) của lệnh trước.

| PC gửi | Pi trả lời | Chờ tối đa |
|---|---|---|
| `{"id":1,"cmd":"ping"}` | `{"id":1,"cmd":"ping","status":"ok"}` | 3 s |
| `{"id":2,"cmd":"capture"}` | `{"id":2,"cmd":"capture","status":"ok","image_size":N}` + N byte JPEG | 10 s |
| `{"id":3,"cmd":"inspect"}` | `{"id":3,"cmd":"inspect","status":"ok","result":"PASS"\|"FAIL1"\|"FAIL2","process_time_ms":123.4, …}` | 20 s |
| lỗi bất kỳ | `{"id":N,"status":"error","message":"…"}` | — |

- Phản hồi `inspect` được thêm **trường tùy ý** (vd `"defect": "thieu linh kien R12"`, `"led_last_digit": 4`). App
  master in các trường này ra Log và thẻ "PCB hiện tại".
- **Nên** cho `inspect` gửi kèm ảnh đã dùng để kết luận (`"image_size": N` + JPEG). App master sẽ hiện ảnh đó cạnh kết
  quả. Không gửi kèm cũng được, khi đó master chỉ hiện ảnh của lần `capture` gần nhất.
- Giới hạn: JSON ≤ 1 MB, ảnh ≤ 20 MB. Sai khung (độ dài vô lý, không phải JSON) thì PC coi là mất kết nối.
- Khi rảnh, app master tự gửi `ping` khoảng 5 s một lần để phát hiện Pi treo / rớt mạng. Server trên Pi phải luôn trả
  lời `ping`.

---

## 3. Lưu ý về trình tự kiểm tra

Lưu đồ hiện tại tách 2 bước: kiểm tra ngoại quan **trước**, rồi chỉ khi đạt mới hạ xi lanh 2 cấp nguồn để kiểm tra
chức năng. Giao thức hiện có **một lệnh `inspect`** trả luôn FAIL1 hoặc FAIL2, nên app master đang làm như sau:
**Test chức năng** = PLC hạ xi lanh 2 (cấp nguồn) → gửi `inspect`.

Nếu muốn đúng lưu đồ (không cấp nguồn cho PCB lỗi linh kiện), phía Pi thêm 1 trường vào lệnh, ví dụ
`{"cmd":"inspect","stage":"visual"}` và `{"cmd":"inspect","stage":"function"}`. Phía PC chỉ phải sửa ở
`UI/comm/pi_link.py` và hàm `_inspect` / `_func_test` trong `UI/ui/master_app.py`.
