# PLC — Mitsubishi FX0N

PLC điều khiển phần cơ khí của dây chuyền:
- băng tải;
- động cơ bước cấp PCB;
- xi lanh 1 (chặn PCB tại trạm kiểm tra);
- xi lanh 2 (2 đầu kim cấp nguồn cho PCB khi test chức năng);
- đèn tháp, E-Stop / Reset.

PC (app master trong `UI/`) là master: PC ra lệnh và đọc trạng thái. PLC thực thi lệnh và **tự xử lý** những tín hiệu cần
phản ứng nhanh (CB2 dừng băng tải, E-Stop). Xem `flow_chart.drawio`.

Thư mục này hiện có **`plc_test_ui.py`**: công cụ thử giao tiếp PC ↔ PLC **trước khi** đưa vào app master.

---

## 1. Kết nối phần cứng

| Mục | Giá trị |
|---|---|
| Cổng trên PLC | Cổng lập trình **RS422** (mini-DIN 8 chân) của FX0N |
| Phía PC | Cáp chuyển **USB ↔ RS422 cho Mitsubishi FX** (loại USB-SC09 / tương đương FX-USB-AW). Cài driver xong, máy hiện thêm 1 cổng COM (xem Device Manager → Ports) |
| Thông số | **9600 baud, 7 bit dữ liệu, parity chẵn (E), 1 stop** = `7E1` (mặc định của FX0N) |
| Giao thức | Giao thức FX của cổng lập trình (mục 3). PLC **không cần viết thêm code giao tiếp** |

> Cổng lập trình chỉ cho **một** chương trình dùng tại một thời điểm. Khi thử bằng tool này hoặc chạy app master, hãy đóng
> GX Developer / GX Works (và ngược lại).

---

## 2. Chạy công cụ thử

```bash
pip install customtkinter pyserial
cd PLC
python plc_test_ui.py
```

| Khung | Chức năng |
|---|---|
| **1. Kết nối** | Chọn cổng COM, baud, khung dữ liệu rồi bấm **Connect**. Có 3 nút kiểm tra nhanh: ENQ, M8000, D8000 (xem mục 4) |
| **2. Đọc / ghi thiết bị bất kỳ** | Gõ tên thiết bị (`X0`, `Y3`, `M100`, `D10`…) rồi bấm **Đọc** / **Ép ON** / **Ép OFF** / **Ghi D** |
| **3. Giám sát** | Đèn X0–X17, Y0–Y17 và bit trạng thái M200–M203, tự đọc mỗi 0.3 s |
| **4. Lệnh cho dây chuyền** | Các bit M mà PC dùng để ra lệnh (mục 5): bật/tắt hoặc gửi xung |
| **Log** | Mọi khung PC gửi (TX) và PLC trả lời (RX), ký tự điều khiển hiện dạng `<STX>`, `<ETX>`, `<ACK>`, `<NAK>` |

---

## 3. Giao thức FX (tóm tắt)

Mỗi khung có dạng `STX` + lệnh + dữ liệu (ký tự hex ASCII) + `ETX` + tổng kiểm. Trong đó:
- `STX` = 02h, `ETX` = 03h;
- **tổng kiểm** = byte thấp của tổng các byte **sau STX, tính cả ETX**, viết thành 2 ký tự hex.

| Lệnh | Khung PC gửi | PLC trả lời |
|---|---|---|
| Kiểm tra | `ENQ` (05h) | `ACK` (06h) |
| Đọc byte | `STX 0 AAAA NN ETX SS` (AAAA = địa chỉ, NN = số byte) | `STX <2·NN ký tự hex> ETX SS` |
| Ghi byte | `STX 1 AAAA NN <dữ liệu hex> ETX SS` | `ACK` / `NAK` |
| Ép bit ON / OFF | `STX 7 aaaa ETX SS` / `STX 8 aaaa ETX SS` (aaaa = địa chỉ bit **đảo byte**: byte thấp trước) | `ACK` / `NAK` |

**Bảng địa chỉ** (dùng chung cho FX0N / FX1S / FX1N / FX2N):

| Thiết bị | Địa chỉ byte (lệnh 0 / 1) | Địa chỉ bit (lệnh 7 / 8) |
|---|---|---|
| S | 0000h | 0000h |
| X (bát phân) | 0080h | 0400h |
| Y (bát phân) | 00A0h | 0500h |
| T (tiếp điểm) | 00C0h | 0600h |
| M0… | 0100h | 0800h |
| C (tiếp điểm) | 01C0h | 0E00h |
| M8000… | 01E0h | 0F00h |
| D0… (2 byte / thanh ghi, byte thấp trước) | 1000h + 2·n | — |
| D8000… | 0E00h + 2·(n − 8000) | — |

Ví dụ:
- Đọc 4 byte từ D123 (D123, D124): `<STX>010F604<ETX>74`.
- Ép ON M100: địa chỉ bit 0800h + 100 = 0864h, gửi đảo byte thành `<STX>76408<ETX>..`.

---

## 4. Thứ tự thử (làm lần lượt)

1. **ENQ → ACK:** PLC có trả lời, nghĩa là cáp, cổng COM và thông số 7E1 đúng. Không trả lời thì kiểm tra cáp, driver,
   đúng cổng COM, PLC đã cấp nguồn.
2. **Đọc M8000:** PLC đang RUN thì = 1. Nếu đọc ra 0 khi PLC đang RUN thì bảng địa chỉ bit không khớp, cần báo lại.
3. **Đọc D8000:** mặc định = 200 (thời gian watchdog), dùng để xác nhận bảng địa chỉ thanh ghi D đúng.
4. **Ngõ vào:** kích từng cảm biến / nút bằng tay (CB1–CB3, START / STOP / RESET, E-Stop). Đèn X tương ứng phải sáng.
   Ghi lại nếu đấu dây khác bảng ở mục 5.
5. **Lệnh M:** thử từng lệnh ở khung 4 (khi ladder đã có phần đọc M, xem mục 5). Quan sát Y và cơ cấu thật:
   - băng tải chạy / dừng;
   - xi lanh 1, 2 hạ / thu: xi lanh chạy **hết hành trình**, sau đúng thời gian timer thì bit M204–M207 đổi theo
     (bấm giờ thật một lần hạ / thu để đặt timer, mục 5);
   - cấp 1 PCB.
6. **Liên động:**
   - Hạ xi lanh 1 (M102 = ON) rồi cho băng tải chạy với một khay: khay tì sát thanh chặn, CB2 tác động → khoảng 0.5 s
     sau PLC phải tự dừng băng tải (M100 tự về OFF). Khay phải nằm sát thanh chặn, không bị dừng sớm.
   - Nhấn E-Stop → mọi Y tắt, M200 = 1, lệnh M từ PC không còn tác dụng cho tới khi Reset.

---

## 5. Bảng gán tín hiệu (ĐỀ XUẤT — sửa theo đấu dây / ladder thật)

Bảng này cũng nằm ở đầu `plc_test_ui.py` (`INPUTS`, `OUTPUTS`, `PC_CMDS`, `PLC_STATUS`). Sửa ở đó để tool hiển thị đúng tên.

**Ngõ vào X** (đánh số bát phân):

| X | Tín hiệu | X | Tín hiệu |
|---|---|---|---|
| X0 | CB1 · PCB ở đầu băng tải | X4 | Nút START trên tủ |
| X1 | CB2 · PCB tì sát thanh chặn (trạm kiểm tra) | X5 | Nút STOP trên tủ |
| X2 | CB3 · PCB tới vị trí gắp | X6 | Nút RESET trên tủ |
| X3 | E-Stop (tiếp điểm NC: 1 = bình thường) | | |

> 2 xi lanh **không có cảm biến hành trình**: van luôn cho chạy tối đa, xi lanh luôn đi hết hành trình. Vị trí
> "đã hạ / đã thu" do PLC tính bằng timer (bảng trạng thái bên dưới).

**Ngõ ra Y:**

| Y | Tín hiệu | Y | Tín hiệu |
|---|---|---|---|
| Y0 | Động cơ bước cấp PCB (xung) | Y4 | Đèn xanh |
| Y1 | Động cơ băng tải | Y5 | Đèn vàng |
| Y2 | Van xi lanh 1 | Y6 | Đèn đỏ |
| Y3 | Van xi lanh 2 | Y7 | Còi |

> Nếu phát xung cho động cơ bước bằng lệnh PLSY thì cần ngõ ra **transistor** (FX0N-xxMT). Kiểm tra lại ngõ ra nào
> của model đang dùng hỗ trợ phát xung.

**Lệnh PC → PLC (PC ép bit M, ladder đọc):**

| Bit | Lệnh | Kiểu |
|---|---|---|
| M100 | Băng tải chạy | giữ: ON = chạy, OFF = dừng |
| M101 | Cấp 1 PCB | xung ~0.3 s: ladder bắt **cạnh lên** (LDP / PLS) |
| M102 | Xi lanh 1 hạ (thanh chặn: chặn + giữ đúng vị trí PCB) | giữ: ON = hạ, OFF = thu. PC hạ **trước** khi cấp PCB, thu sau khi kiểm tra xong |
| M103 | Xi lanh 2 hạ (cấp nguồn PCB, dùng khi **test chức năng**) | giữ: ON = hạ, OFF = thu (ngắt nguồn) |
| M110 / M111 / M112 | START / STOP / RESET từ phần mềm | xung, tác dụng giống nút trên tủ |

**Trạng thái PLC → PC (ladder ghi, PC chỉ đọc):**

| Bit | Ý nghĩa |
|---|---|
| M200 / M201 / M202 / M203 | E-Stop đang chốt / có lỗi / đang cấp PCB / sẵn sàng |
| M204 / M205 | Xi lanh 1 **đã hạ** / **đã thu** (hết timer hành trình) |
| M206 / M207 | Xi lanh 2 **đã hạ** / **đã thu** (hết timer hành trình) |

**Timer hành trình xi lanh** (thay cho cảm biến S1 / S2):
- Mỗi lần van xi lanh đổi trạng thái (Y2 / Y3 bật hoặc tắt): xóa ngay cả 2 bit "đã hạ" và "đã thu" của xi lanh đó, rồi
  chạy timer.
- Hết timer: bật bit "đã hạ" (nếu van đang bật) hoặc "đã thu" (nếu van đang tắt).
- Giá trị timer = thời gian xi lanh chạy hết hành trình **đo thực tế** + dự phòng (vd đo 0.6 s thì đặt 1.0 s). Dùng
  timer 100 ms: K10 = 1.0 s.
- Lúc PLC khởi động: coi như đang ở trạng thái của van (chạy timer một lần).

**Yêu cầu với ladder:**
- **Không** để PC điều khiển thẳng Y. Ladder đọc M100–M112 rồi mới quyết định Y, để liên động luôn nằm ở PLC:
  - E-Stop chặn mọi lệnh;
  - **CB2 → trễ 0.5 s rồi dừng băng tải** (reset M100). Thanh chặn đã được PC hạ sẵn từ đầu chu kỳ; trong 0.5 s băng tải
    trượt dưới đáy khay, ép khay tì sát thanh chặn để định vị đúng chỗ cho camera và 2 đầu kim. Dùng timer 100 ms: K5.
    Bước này **không** hạ xi lanh 1 nữa;
  - không hạ xi lanh 2 khi xi lanh 1 chưa hạ xong (M204).
- E-Stop có tự giữ (M200). Chỉ RESET (nút tủ hoặc M112) khi E-Stop đã nhả mới được xóa.
- Lỗi cần PC biết thì ladder ghi vào M201. PC đọc trạng thái mỗi chu kỳ.

---

## 6. Đưa vào app master

Lớp `FxLink` trong `plc_test_ui.py` không phụ thuộc giao diện. Khi đã thử xong trên PLC thật, chuyển lớp này sang
`UI/comm/` để app master dùng lại đúng đoạn code đã thử. Các nút demo của PLC trong app master (tab Vận hành → MANUAL,
tab Cài đặt → Kết nối thiết bị → PLC · RS422) khi đó sẽ gọi vào `FxLink` thay vì chỉ ghi Log.
