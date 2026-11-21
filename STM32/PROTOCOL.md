# Giao thức PC ↔ STM32 (text, 115200 baud, mỗi lệnh 1 dòng kết thúc `\n`)

Đơn vị trên dây: **counts**, counts/s, counts/s². 0 counts = vị trí lúc cấp nguồn/reset. PC quy ước vị trí đó
bằng giá trị **Home** trong Settings (đổi tại Connect; trước đây cố định J1=J2=J3=0°, Z=300 mm). Sau `HOMING`, vị trí =
`HPOS` của trục đó.
**Chỉ PC đổi độ/mm ↔ counts** (Settings → Encoder); firmware không tự đổi đơn vị.

Động cơ: `1` = Z · `2` = J1 · `3` = J2 · `4` = J3. Theo cấu hình hiện tại: J1/J2 = 436 800 counts/vòng × đai 3:1
(3640 counts/°), J3 = 76 500 counts/vòng (212.5 counts/°), Z = 436 800 counts / 8 mm (54 600 counts/mm).

## PC → STM32  (`<LỆNH> <động cơ> [tham số]`, tối đa 63 ký tự)
| Lệnh | Tác dụng |
|---|---|
| `GOTO <id> <counts>` | đích tuyệt đối |
| `JOG <id> <counts>` | đích += counts |
| `HOME <id>` | đích = 0 |
| `STOP <id>` | phanh gấp, tắt PID tại vị trí hiện tại (goal = pos) |
| `PAUSE <id>` / `RESUME <id>` | giảm tốc theo Amax về điểm dừng rồi giữ / tiếp tục về đích cũ |
| `LIMIT <id> <min> <max>` | giới hạn hành trình (counts); JOG/GOTO/HOME ngoài khoảng → `ERR … range`. Riêng khi trục đang **ở ngoài** khoảng: chỉ nhận đích **đi vào phía trong** (cùng phía, gần khoảng hơn), không bao giờ cho đi xa thêm |
| `CLEAR <id>` | xóa FAULT đã chốt (trong lúc FAULT, JOG/GOTO/HOME bị từ chối `ERR … fault`) |
| `PID <id> <kp> <ki> <kd>` | hệ số PID (đầu ra = duty PWM 0..4199 trên mỗi count sai số) |
| `VMAX <id> <n>` / `AMAX <id> <n>` | counts/s, counts/s² |
| `DB <id> <n>` | vùng chết ±n counts quanh đích |
| `TRIP <id> <trip> <home>` | ngưỡng sai số bám (counts, > 0): `trip` khi chạy → `FAULT <id> trip`; `home` khi HOMING → `FAULT <id> home`. PC gửi khi Connect/Apply (Settings → Fault Thresholds, độ/mm). Mặc định trước khi nhận: 76 500 / 6 000 |
| `STALL <id> <pct> <ms> <counts>` | bảo vệ **kẹt / quá tải**: \|PWM\| trung bình (lọc 0,2 s) ≥ `pct` % mà trong `ms` ms trục đi chưa được `counts` → `FAULT <id> stall`. Bắt cả kẹt cơ khí lẫn PID "săn" qua lại (sai số vẫn dưới `TRIP`). `pct` = 0 tắt, hoặc 10..100; `ms` 50..10000. PC gửi khi Connect/Apply (Settings → Fault Thresholds). Mặc định: 70 %, 500 ms, Z 0,2 mm, J 0,5° |
| `HPOS <id> <counts>` | vị trí home: giá trị gán cho encoder khi `HOMING` chạm cảm biến. PC gửi khi Connect/Apply (đổi từ Settings → Home, độ/mm). Có hiệu lực từ lần `HOMING` kế tiếp |
| `HOMING <id>` | chạy chậm về cảm biến home; chạm thì dừng và đặt vị trí = `HPOS`. Lỗi → `FAULT <id> home`; trục chưa có cảm biến → `ERR HOMING <id> nosensor` |
| `SEL <id>` | chọn động cơ gửi telemetry `T` 50 Hz (mặc định: không gửi). `SEL 0` = tắt telemetry |
| `PING` | **không có số động cơ, không trả lời**: báo "PC còn hoạt động" cho watchdog. PC gửi mỗi 0.2 s |
| `WDT <ms>` | **không có số động cơ**: bật watchdog mất kết nối (100..60000 ms; `0` = tắt, mặc định). Trả `OK WDT <ms>`. PC gửi `WDT 600` khi Connect |
| `GRIP <0\|1>` | kẹp (PD9, HIGH = đóng) — **không có số động cơ**: `1` = ĐÓNG, `0` = MỞ. Trả `OK GRIP <0\|1>` hoặc `ERR GRIP ? arg\|nogrip`. Không tự đổi khi STOP/FAULT; reset → MỞ. Đang E-STOP → `ERR GRIP ? estop` |
| `ESTOP <1\|0>` | **không có số động cơ**. `1` = E-STOP: cả 4 động cơ phanh, tắt PID, **bỏ mốc vị trí** (homed = 0) và **khóa** `JOG/GOTO/HOME/HOMING/PAUSE/RESUME/GRIP` (trả `ERR … estop`); `STOP`, `CLEAR` và lệnh cấu hình vẫn dùng được. `0` = RESET: mở khóa + xóa mọi FAULT, robot **chưa có mốc** → PC phải `HOMING` lại. Trả `OK ESTOP <1\|0>`. PC gửi `ESTOP 1` khi PLC báo E-Stop, `ESTOP 0` khi người vận hành bấm Reset |

## STM32 → PC
| Dòng | Ý nghĩa |
|---|---|
| `OK <lệnh> <id>` | lệnh được chấp nhận (theo đúng thứ tự gửi) |
| `ERR <lệnh> <id> <arg\|range\|fault\|unknown\|id\|homing\|nosensor\|estop>` | lệnh bị từ chối |
| `S <ms> (st goal sp pos)×4 <grip>` | **20 Hz**, trạng thái cả 4 động cơ theo thứ tự 1..4; `grip` = 1 kẹp đóng, 0 mở |
| `FAULT <id> trip` | sai số bám quỹ đạo > ngưỡng `TRIP`: phanh, tắt PID, chờ `CLEAR` |
| `FAULT <id> stall` | kẹt / quá tải theo ngưỡng `STALL`: phanh, tắt PID, chờ `CLEAR` |
| `BOOT` | STM32 vừa reset |
| `LINKLOST` | quá `WDT` ms không nhận được dòng nào từ PC: mọi trục đang chạy / PAUSE / HOMING **giảm tốc dừng rồi giữ vị trí** (không tắt PID, không mất mốc vị trí, không chốt FAULT). Gửi trước dòng `S` báo busy = 0, để PC không hiểu nhầm là Step đã xong |
| `T <id> <ms> <en> <goal> <sp> <pos> <sv> <v>` | telemetry 50 Hz của động cơ được `SEL` |

`st` là bitmask: **1** PID đang chạy · **2** đang PAUSE · **4** busy (chưa ổn định tại đích; cũng là 1 khi PAUSE; tự về 0 sau 1 s kể từ khi quỹ đạo xong dù chưa vào vùng chết) ·
**8** FAULT đang chốt · **16** đã HOME thật · **32** đang HOMING · **64** cảm biến home đang kích hoạt · **128** đang E-STOP. `sp` = vị trí quỹ đạo đặt, `pos` = vị trí encoder.

## Quy tắc chống nhận nhầm "Step xong"
`OK` luôn xếp **sau** các dòng `S` đã chụp trước khi lệnh được xử lý. PC chỉ chấp nhận BUSY→READY khi mọi
lệnh chuyển động đã có `OK` **và** đã nhận thêm một dòng `S` sau `OK` cuối cùng. Không có `OK` sau 0.5 s hoặc
không có `S` sau 1 s ⇒ PC coi là mất kết nối.
