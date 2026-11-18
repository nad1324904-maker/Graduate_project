# Hướng dẫn kết nối thiết bị với app master

App master (`UI/`, chạy `python main.py`) là phần mềm duy nhất trên PC, điều khiển 3 thiết bị:

| Thiết bị | Đường truyền | Trong app master | Trạng thái |
|---|---|---|---|
| **Raspberry Pi** (xử lý ảnh) | **TCP/IP** qua cáp mạng LAN (hoặc WiFi) | tab **Cài đặt → Kết nối thiết bị → Raspberry Pi · TCP/IP** | **chạy thật** |
| **Robot SCARA** (STM32F407) | UART 115200 qua cáp USB–UART (cổng COM) | tab **Cài đặt → Kết nối thiết bị → Robot SCARA · UART** | **chạy thật** |
| **PLC** Mitsubishi FX0N | RS422 qua cáp USB–RS422 (cổng COM) | tab **Cài đặt → Kết nối thiết bị → PLC · RS422** | dữ liệu mẫu (đang thử bằng `PLC/plc_test_ui.py`) |

Trên header của app, mục **🔌 Thiết bị** có chấm **xanh** khi Pi / Robot đang kết nối, **xám** khi chưa.

---

## 1. Raspberry Pi (TCP/IP)

### 1.1. Nối mạng

- **Cách nên dùng:** cáp LAN nối thẳng PC ↔ Pi, hoặc cả hai cắm vào cùng một switch / router. Ổn định hơn WiFi, nhất
  là khi gửi ảnh.
- **WiFi** vẫn dùng được nếu PC và Pi ở **cùng một mạng** (cùng dải địa chỉ, vd `192.168.1.x`).

### 1.2. Đặt địa chỉ IP tĩnh

Dùng cùng một dải, ví dụ:

| Máy | Địa chỉ IP | Subnet mask |
|---|---|---|
| Raspberry Pi | **192.168.1.100** (mặc định trong app) | 255.255.255.0 (/24) |
| PC | 192.168.1.10 (số nào cũng được, miễn khác Pi và cùng dải) | 255.255.255.0 |

**Trên PC (Windows 11):** Settings → Network & internet → Ethernet → IP assignment → **Edit** → Manual → bật IPv4 →
IP `192.168.1.10`, Subnet mask `255.255.255.0` (Gateway để trống nếu nối thẳng) → Save.

**Trên Raspberry Pi:**
- Raspberry Pi OS **Bookworm** (NetworkManager):
  ```bash
  sudo nmcli con mod "Wired connection 1" ipv4.method manual ipv4.addresses 192.168.1.100/24
  sudo nmcli con up "Wired connection 1"
  ```
- Bản cũ (**Bullseye**, dhcpcd): thêm vào cuối `/etc/dhcpcd.conf` rồi khởi động lại Pi:
  ```
  interface eth0
  static ip_address=192.168.1.100/24
  ```

### 1.3. Kiểm tra đường mạng

Trên PC mở **Command Prompt**:
```
ping 192.168.1.100
```
Phải có `Reply from 192.168.1.100`. Không có thì xem lại cáp, IP hai bên, cùng dải mạng chưa.

### 1.4. Chạy server trên Pi

- Chạy chương trình server của người làm xử lý ảnh. Server phải nghe ở **cổng 5000**, trên mọi địa chỉ (`0.0.0.0`).
- Nếu Pi bật tường lửa: `sudo ufw allow 5000/tcp`.
- Giao thức: xem [Raspberry Pi/README.md](Raspberry%20Pi/README.md), mục 2.

### 1.5. Thử riêng bằng `pi_tcp_test_ui.py` (nên làm trước)

```bash
cd "Raspberry Pi"
python pi_tcp_test_ui.py
```
Nhập IP / Port → **Connect** → **Test Connection** → **Capture Image** → **Start Inspection**. Chạy ổn ở đây thì mới
sang app master.

> Server trên Pi thường chỉ phục vụ **một** PC tại một thời điểm. **Đóng tool thử** (hoặc bấm Disconnect) trước khi
> kết nối từ app master.

### 1.6. Kết nối từ app master

1. `cd UI` → `python main.py`.
2. Tab **Cài đặt** → thẻ **Kết nối thiết bị** → khối **Raspberry Pi · TCP/IP**: nhập **Địa chỉ IP** và **Cổng** →
   bấm **Connect**. Nhãn đổi `OFFLINE` → `ĐANG KẾT NỐI` → `ONLINE · 192.168.1.100`, chấm **Pi** trên header chuyển xanh.
3. Bấm **Ping**: Log báo `Pi: ping OK — khứ hồi … ms`.
4. Tab **Vận hành** → chế độ **MANUAL** → nhóm **Raspberry Pi (xử lý ảnh)**:
   - **📷 Chụp ảnh** (`capture`): ảnh hiện ở thẻ **PCB hiện tại**.
   - **🔍 Kiểm tra PCB** (`inspect`): kết quả PASS / FAIL1 / FAIL2 hiện ở thẻ PCB hiện tại và ô **Loại PCB**
     (ĐẠT / LỖI 1 / LỖI 2); robot sẽ chạy Chương trình 1 / 3 / 2 tương ứng.
   - **🔌 Test chức năng** (nhóm PLC): PLC hạ xi lanh 2 cấp nguồn cho PCB, rồi tự gửi `inspect`. Phần PLC hiện
     vẫn là giả lập, phần Pi là thật.
5. Mọi gói gửi / nhận hiện trong **Log** ở đáy app (dòng `TX` / `RX`, có tiền tố `Pi:`).

**Hành vi tự động:**
- **Thời gian chờ:** ping 3 s, capture 10 s, inspect 20 s. Quá hạn thì Log báo lỗi; kết nối vẫn giữ.
- **Ping tự động:** khi rảnh, app tự `ping` khoảng 5 s một lần (không ghi Log). Pi không trả lời hoặc rớt mạng thì app
  báo **"Mất kết nối Raspberry Pi"**, chấm Pi chuyển xám và các nút Pi bị chặn cho tới khi Connect lại.
- **Một lệnh một lúc:** Pi đang xử lý mà bấm tiếp thì app báo "đang xử lý lệnh trước" và không gửi chồng.

### 1.7. Sự cố thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| `Không kết nối được … actively refused` (WinError 10061) | Mạng thông nhưng **chưa chạy server** trên Pi, hoặc sai cổng |
| `Không kết nối được … timed out` | Sai IP, khác dải mạng, cáp lỏng, hoặc tường lửa Pi chặn cổng 5000 |
| Kết nối được nhưng mọi lệnh đều "không phản hồi" | Server nhận kết nối nhưng không trả lời đúng khung `[4 byte độ dài][JSON]`, hoặc không gửi lại đúng `id` |
| `Mất kết nối … Phản hồi không phải JSON hợp lệ` / `Độ dài JSON không hợp lệ` | Server gửi sai khung (thiếu 4 byte độ dài, độ dài sai, JSON hỏng) |
| Kết nối từ app master bị từ chối dù tool thử chạy được | Tool thử vẫn đang giữ kết nối: đóng tool rồi Connect lại |
| `inspect` hay quá 20 s | Xử lý ảnh trên Pi quá chậm: tối ưu phía Pi hoặc tăng `TIMEOUT` trong `UI/comm/pi_link.py` |

---

## 2. Robot SCARA (UART)

1. Cắm cáp USB–UART (STM32 USART3: PB10 TX, PB11 RX), nạp firmware cùng phiên bản với app.
2. Tab **Cài đặt** → **Robot SCARA · UART**: chọn **Cổng COM** (bấm ⟳ để quét lại), baud **115200** → **Connect**.
3. Log báo `CONFIG_OK`, rồi sang tab **Robot** bấm **HOME** trước khi JOG / chạy chương trình.

Chi tiết: [README.md](README.md) mục 6.3 và [CHECKLIST_THU_ROBOT.md](CHECKLIST_THU_ROBOT.md).

---

## 3. PLC FX0N (RS422)

- Cổng lập trình RS422 của FX0N → cáp **USB ↔ RS422 cho Mitsubishi FX** → một cổng COM (**khác** cổng của robot).
  Thông số **9600 baud, 7E1**.
- App master **chưa** điều khiển PLC thật (nút chỉ ghi Log). Thử giao tiếp bằng `PLC/plc_test_ui.py`.

Chi tiết: [PLC/README.md](PLC/README.md).
