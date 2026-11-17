# Robot SCARA 4 bậc tự do — STM32F407 + giao diện điều khiển Python

Đồ án điều khiển robot SCARA 4 trục (**J1, J2, J3, Z**) gồm hai phần:

- **Firmware STM32F407** (`Code STM32/`): vòng điều khiển vị trí thời gian thực 1 kHz cho cả 4 động cơ DC có encoder,
  quỹ đạo hình thang, PID, tìm home bằng cảm biến, điều khiển kẹp và các cơ chế bảo vệ.
- **Giao diện PC** (`Giao dien dieu khien/`): ứng dụng Python (customtkinter) để kết nối, cấu hình, JOG, dạy điểm (Teach Point),
  soạn và chạy chương trình, hiển thị vị trí khớp và vị trí đầu công tác (TCP) theo động học thuận.

Hai phần giao tiếp qua **UART dạng văn bản, 115200 baud**, mỗi lệnh một dòng.

---

## 1. Kiến trúc hệ thống

```
┌──────────────────────── PC (Python) ────────────────────────┐
│  UI (customtkinter)                                          │
│   ├─ Tab Robot: JOG · Monitor · Points · Program · Control   │
│   └─ Tab Settings: cấu hình (JSON) · Connect                 │
│  core/: động học thuận, Point/Program store, ProgramExecutor │
│  comm/: UartRobotBackend  ── đổi độ/mm ↔ counts ──┐          │
└───────────────────────────────────────────────────┼──────────┘
                                   UART 115200 (text, mỗi lệnh 1 dòng)
┌──────────────────────── STM32F407 ────────────────┼──────────┐
│  comm.c   : USART3 + DMA (RX vòng, TX hàng đợi)  ◄┘          │
│  control.c: phân tích lệnh, trạng thái, FAULT, HOMING         │
│  Ngắt TIM9 1 kHz, cho mỗi trục:                              │
│    encoder → quỹ đạo hình thang → PID → PWM (BTS7960)        │
│  home_sen.c: cảm biến home   ·   gripper.c: kẹp (PD9)        │
└──────────────────────────────────────────────────────────────┘
```

**Phân chia trách nhiệm:**

- **STM32** làm mọi việc cần thời gian thực: bám quỹ đạo, PID, phanh, phát hiện lỗi, dừng ngay khi chạm cảm biến home.
- **PC** làm phần điều phối:
  - đổi đơn vị độ/mm ↔ counts (**chỉ PC đổi đơn vị**, firmware chỉ làm việc với counts);
  - động học thuận và hiển thị;
  - lưu Point/Program, chạy chương trình theo từng Step (gửi một Step, chờ xong rồi mới gửi Step kế tiếp).

---

## 2. Cấu trúc thư mục

```
scara_robot/
├── mo_phong_scara.html             Mô phỏng 3D robot (mở bằng Chrome / Edge, không cần robot) — mục 6.4
├── Code STM32/                     Firmware (Keil MDK-ARM + STM32CubeMX)
│   ├── Graduate_project.ioc        Cấu hình CubeMX (chân, timer, UART, DMA)
│   ├── MDK-ARM/                    Project Keil (Graduate_project.uvprojx)
│   └── Core/
│       ├── Inc/, Src/
│       │   ├── main.c              Nối phần cứng vào các module, cấu hình cảm biến home, kẹp
│       │   ├── control.c/.h        Vòng điều khiển + bộ phân tích lệnh + trạng thái (giao thức đầy đủ ở control.h)
│       │   ├── trap_profile.c/.h   Quỹ đạo vận tốc hình thang tính online
│       │   ├── pid.c/.h            PID vị trí (D theo tốc độ đo, chống bão hòa tích phân)
│       │   ├── encoder.c/.h        Encoder x4 (timer 16 bit → vị trí 32 bit, tốc độ)
│       │   ├── motor.c/.h          Driver BTS7960 (RPWM/LPWM, phanh)
│       │   ├── home_sen.c/.h       Cảm biến home (lọc nhiễu)
│       │   ├── gripper.c/.h        Kẹp (GPIO output)
│       │   └── comm.c/.h           UART + DMA, tách dòng
│       └── ...                     Mã HAL do CubeMX sinh
└── Giao dien dieu khien/           Giao diện PC (Python)
    ├── main.py                     Điểm khởi động
    ├── comm/                       Giao tiếp: uart_protocol.py, uart_backend.py, offline_backend.py
    ├── core/                       Logic: kinematics, robot_config, point_store, program_store, program_executor
    ├── ui/                         Giao diện: app.py, robot_tab/ (Vận hành + Lập trình), visual_tab/, settings_tab/,
    │                               theme (bảng màu sáng/tối), widgets, perf
    ├── data/                       robot_config.json, points.json, programs.json
    ├── firmware/PROTOCOL.md        Mô tả giao thức UART
    └── tools/uart_tool.py          Gửi lệnh tay tới STM32 không cần GUI (dùng khi thử phần cứng)
```

---

## 3. Phần cứng

| Thành phần | Mô tả |
|---|---|
| Vi điều khiển | STM32F407VGT6, 168 MHz (HSI + PLL) |
| Động cơ | 4 động cơ DC có hộp số + encoder quadrature, driver **BTS7960** |
| Trục | Motor 1 = **Z** (tịnh tiến) · Motor 2 = **J1** · Motor 3 = **J2** · Motor 4 = **J3** (cổ tay) |
| Tỉ lệ encoder | J1/J2: 436 800 counts/vòng × đai 3:1 = **3640 counts/°** · J3: 76 500 counts/vòng = **212.5 counts/°** · Z: 436 800 counts / 8 mm = **54 600 counts/mm** |
| Cảm biến home | 4 cảm biến, mức tích cực LOW, có pull-up nội |
| Kẹp | 1 chân GPIO output, HIGH = đóng; không có cảm biến phản hồi |
| Giao tiếp | USART3 (PB10 TX, PB11 RX), 115200 8N1, qua bộ chuyển USB–UART |

### Sơ đồ chân

| Trục | RPWM (chạy thuận) | LPWM (chạy nghịch) | Encoder A/B | Cảm biến home |
|---|---|---|---|---|
| Z  (Motor 1) | PB14 · TIM12_CH1 | PA6 · TIM13_CH1 | PC6/PC7 · TIM8 | PD14 |
| J1 (Motor 2) | PA2 · TIM5_CH3 | PA0 · TIM5_CH1 | PA15/PB3 · TIM2 | PD15 |
| J2 (Motor 3) | PA1 · TIM5_CH2 | PA3 · TIM5_CH4 | PB4/PB5 · TIM3 | PD13 |
| J3 (Motor 4) | PA7 · TIM14_CH1 | PB15 · TIM12_CH2 | PB6/PB7 · TIM4 | PD11 |

- **R_EN/L_EN** của cả 4 driver nối chung vào **PB9**, được đặt mức HIGH ngay khi khởi động.
- **Kẹp:** **PD9**.
- **Timer:**
  - PWM 20 kHz (ARR = 4199) trên TIM5/12/13/14.
  - Vòng điều khiển chạy trên TIM9 ở 1 kHz, được ưu tiên ngắt cao nhất.
  - TIM1 (PA8/PA9) đã cấu hình chế độ encoder nhưng chưa dùng.

---

## 4. Firmware — thuật toán điều khiển

Mỗi 1 ms, ngắt TIM9 chạy lần lượt cho từng trục:

1. **Encoder** ([encoder.c](Code%20STM32/Core/Src/encoder.c)):
   - Lấy hiệu 16 bit của counter rồi cộng dồn vào vị trí 32 bit, nên không bị lỗi khi counter tràn.
   - Tính tốc độ hai cách: trung bình trượt 20 ms, và một bản lọc thông thấp (`vfilt`) dùng cho khâu D.
2. **Quỹ đạo hình thang online** ([trap_profile.c](Code%20STM32/Core/Src/trap_profile.c)):
   - Tốc độ đặt là `v = min(Vmax, √(2·Amax·quãng còn lại))`, bị giới hạn độ dốc bởi Amax.
   - Đổi đích giữa chừng vẫn mượt; quãng ngắn tự thành profile tam giác.
   - Vị trí đặt dùng kiểu `double` để không bị kẹt gần đích khi giá trị counts lớn.
3. **PID vị trí** ([pid.c](Code%20STM32/Core/Src/pid.c)):
   - Sai số = vị trí quỹ đạo − vị trí encoder.
   - Khâu D lấy theo **tốc độ đo được** (không lấy đạo hàm sai số), nên không bị giật khi đổi đích.
   - Tích phân có chống bão hòa (anti-windup). Đầu ra là duty PWM có dấu, trong khoảng ±4199.
4. **Vùng chết:** khi quỹ đạo đã tới đích và sai số nằm trong ±deadband thì nhả PWM (phanh) để động cơ không rung quanh đích.
5. **Động cơ** ([motor.c](Code%20STM32/Core/Src/motor.c)): duty > 0 xuất ra RPWM, duty < 0 xuất ra LPWM, duty = 0 thì phanh (cả hai kênh bằng 0).

### Bảo vệ và trạng thái

- **FAULT trip:** khi chạy, nếu |sai số bám| vượt ngưỡng *Trip* thì phanh, tắt PID và chốt lỗi cho tới khi nhận lệnh `CLEAR`. Thường do kẹt cơ khí, sai chiều encoder hoặc mất tín hiệu encoder.
- **HOMING:**
  - Trục chạy chậm (một phần trăm của Vmax) về phía cảm biến.
  - Chạm cảm biến (đã lọc nhiễu 3 ms) thì **dừng ngay** và gán vị trí encoder bằng **vị trí home do PC gửi xuống**.
  - Quá thời gian chờ, hoặc sai số vượt ngưỡng *Home Trip* (trục bị chặn), thì báo `FAULT home`.
- **PAUSE / RESUME:** PAUSE giảm tốc theo Amax về điểm dừng và giữ nguyên đích cũ; RESUME đi tiếp tới đích đó.
- **Busy / settle:** sau khi quỹ đạo xong 1 s mà trục vẫn chưa vào vùng chết (do ma sát tĩnh) thì vẫn coi là đã ổn định, không báo lỗi.
- **Báo cáo về PC:**
  - Dòng trạng thái `S` 20 Hz chứa thông tin cả 4 trục (đang chạy, đang pause, busy, fault, đã home, đang homing, cảm biến đang kích hoạt) và trạng thái kẹp.
  - Telemetry `T` 50 Hz cho một trục được chọn bằng lệnh `SEL`.

---

## 5. Giao diện PC — chức năng

Giao diện có 4 tab, cùng **nút ■ STOP màu đỏ cố định trên thanh tiêu đề** và **thanh SYSTEM LOG ở đáy** (cả hai hiện ở mọi tab;
Log bấm "▲ Mở rộng" để xem nhiều dòng hơn). Mặc định là giao diện sáng, chạy `python main.py --dark` để dùng giao diện tối.

| Tab / khung | Chức năng |
|---|---|
| **Vận hành → JOG** | Hai kiểu, chọn bằng nút chuyển trên đầu khung: **Khớp** (J1, J2, J3, Z theo độ/mm) hoặc **Tọa độ** (X, Y, Z theo mm và θ theo độ của đầu công tác, dùng động học ngược). Bên dưới có nút **HOME** (cả 4 trục tìm cảm biến) và nút **Kẹp** (bấm để đóng/mở, chữ trên nút cho biết trạng thái). JOG chỉ hoạt động ở chế độ JOG và sau khi đã HOME |
| **Vận hành → Operation Monitor** | Vị trí đặt và vị trí thực của từng khớp; TCP (X, Y, Z, θ) theo động học thuận; hàng **Point ▾ / Move Here / Teach Point** để chọn điểm, đi tới điểm và dạy điểm mới mà không phải đổi tab; khung **Move to XYZθ**; trạng thái robot, home, pause, kẹp |
| **Vận hành → Move to XYZθ** | Nhập tọa độ đầu công tác, GUI tính động học ngược ra góc khớp rồi di chuyển. Nút "⤓ Hiện tại" điền sẵn vị trí đang đứng; ô nào không sửa thì dùng giá trị chính xác (không bị sai số làm tròn), và nếu đích trùng vị trí hiện tại thì không gửi lệnh |
| **Vận hành → Chạy chương trình** | Nút gạt **Chế độ JOG / CHƯƠNG TRÌNH**, chọn Program, thanh tiến độ, **START / PAUSE–RESUME / RESET** (RESET xóa FAULT bằng `CLEAR`). Bên dưới là danh sách Step, **Step đang chạy được tô sáng** |
| **Lập trình → Points** | Danh sách Point, Teach Point (lưu vị trí thực hiện tại), Save Position, đổi tên, xóa (bị chặn nếu Program đang dùng điểm đó) |
| **Lập trình → Program Editor** | Tạo chương trình gồm các Step: **MOVE** (tới một Point), **GRIP ON/OFF**, **DELAY** (0.1–60 s); sửa, xóa, chèn Step |
| **Giám sát** | Hình robot 2D nhìn từ trên xuống (tư thế thực, đích, Points, đường đi dự kiến của chương trình) và đồ thị bám quỹ đạo của một trục (mục 5.1) |
| **Settings** | 6 panel cấu hình (mục 7) và kết nối UART |

**Động học thuận** ([core/kinematics.py](Giao%20dien%20dieu%20khien/core/kinematics.py)):

```
x = h1 + l1·cos θ1 + l2·cos(θ1 + θ2)
y =      l1·sin θ1 + l2·sin(θ1 + θ2)
z = d_Z − h2
θ = θ1 + θ2 + θ3   (bọc về [−180°, 180°))
```

**Động học ngược** (cùng file, hàm `inverse_kinematics`), có lời giải đóng:

```
x' = x − h1
cos θ2 = (x'² + y² − l1² − l2²) / (2·l1·l2)      → |cos θ2| > 1: điểm ngoài vùng với tới
θ2 = ± arccos(cos θ2)                            → 2 nghiệm: khuỷu θ2 > 0 và θ2 < 0
θ1 = atan2(y, x') − atan2(l2·sin θ2, l1 + l2·cos θ2)
θ3 = θ − θ1 − θ2
d_Z = z + h2
```

- **Vùng với tới:** điểm phải cách trục J1 một khoảng nằm trong [|l1 − l2|, l1 + l2]. Đúng tại trục J1 là điểm kỳ dị (J1 có vô số nghiệm) nên bị từ chối.
- **Dung sai làm tròn:** điểm vượt biên tầm với hoặc trục Z dưới 0.01 mm, hoặc góc vượt giới hạn khớp dưới 0.01°, vẫn được nhận nhưng **kẹp đúng về biên**, nên không bao giờ ra lệnh vượt giới hạn.
- **Gần tư thế duỗi thẳng (J2 ≈ 0°):** động học ngược rất nhạy, sai lệch tọa độ rất nhỏ cũng làm góc khớp đổi đáng kể. Đây là đặc tính của SCARA ở gần điểm kỳ dị.
- **Chọn nghiệm:**
  - Mỗi góc được xét cả các giá trị tương đương ±360° để tìm giá trị nằm trong giới hạn khớp.
  - Trong 2 nghiệm khuỷu tay, nghiệm vượt giới hạn bị loại.
  - Nếu cả 2 đều hợp lệ thì chọn nghiệm **gần tư thế hiện tại nhất**, tức tổng **bình phương** Δθ của J1, J2, J3 nhỏ nhất.
    Không dùng tổng |Δθ|: khi 3 khớp cùng quay một chiều, tổng |Δθ| của hai nghiệm luôn bằng nhau (vì J1 + J2 + J3 = θ),
    nên việc chọn khuỷu tay sẽ chỉ do sai số làm tròn quyết định.
- **Báo lỗi** rõ lý do: quá xa, quá gần, Z ngoài giới hạn, hoặc cả 2 nghiệm đều vượt giới hạn khớp nào.
- **Kiểm chứng:** 20 000 tư thế ngẫu nhiên trong giới hạn khớp đều cho kết quả FK(IK(p)) = p.

**Đồng bộ khớp** ([uart_backend.py](Giao%20dien%20dieu%20khien/comm/uart_backend.py), hàm `_sync_profiles`).
Áp dụng cho mọi lệnh di chuyển: JOG, Move to XYZθ, Move Here và Step MOVE.

- **Vấn đề:** nếu mỗi khớp chạy với Vmax/Amax riêng, các khớp tới đích vào thời điểm khác nhau và đầu công tác đi vòng. Ví dụ JOG Y +5 mm có thể lệch khỏi đường thẳng khoảng 1.9 mm.
- **Cách làm:** PC tính một quỹ đạo hình thang **chung theo tỉ lệ quãng đường**, nhanh nhất mà không khớp nào vượt giới hạn của nó:
  ```
  V = min_i (Vmax_i / d_i),   A = min_i (Amax_i / d_i)      (d_i = quãng đường của khớp i, counts)
  VMAX_i = d_i · V,           AMAX_i = d_i · A
  ```
  rồi gửi `VMAX`/`AMAX` cho từng khớp trước lệnh `GOTO`. Chỉ gửi giá trị nào khác với giá trị STM32 đang dùng.
- **Kết quả:** mọi khớp có cùng hình dạng quỹ đạo, nên **cùng xuất phát và cùng tới đích** (lệch dưới 1 ms khi mô phỏng đúng thuật toán của firmware). Đầu công tác đi thẳng trong không gian khớp, rất gần đường thẳng khi bước ngắn. Ví dụ JOG Y +5 mm chỉ lệch 0.03 mm, Y +10 mm lệch 0.13 mm. Tổng thời gian bằng thời gian của khớp chậm nhất, nên không chậm hơn so với khi chạy độc lập.
- **Trước HOMING**, Vmax/Amax của mọi trục được trả về giá trị đầy đủ, vì tốc độ tìm home tính theo phần trăm Vmax.
- **Không cần sửa firmware:** chỉ dùng các lệnh `VMAX`/`AMAX` đã có sẵn.

**Chống nhận nhầm "Step đã xong":** trạng thái chỉ chuyển BUSY → READY khi mọi lệnh đã nhận `OK` **và** đã nhận thêm ít nhất một dòng `S` sau `OK` cuối cùng.

**Phát hiện mất kết nối:**

- Lệnh không có `OK`/`ERR` sau 0.5 s, hoặc không nhận được dòng `S` trong 1 s, thì PC coi là mất kết nối.
- Nhận `BOOT` sau khi đã cấu hình (STM32 vừa reset) cũng bị coi là mất kết nối.
- **Phía STM32 (watchdog):** khi Connect, PC gửi `WDT 600`, rồi một luồng riêng gửi `PING` mỗi 0.2 s. Luồng này độc lập với giao diện, nên kéo cửa sổ hay giao diện đơ một lúc không làm robot dừng oan. Nếu dây USB tuột hoặc chương trình trên PC chết, quá 0.6 s không nhận được gì thì STM32 cho mọi trục đang chạy **giảm tốc dừng rồi giữ vị trí** và gửi `LINKLOST`. Mốc vị trí vẫn đúng, nên Connect lại là chạy tiếp được, không cần HOME lại.

### 5.1. Tab Giám sát

- **Robot 2D nhìn từ trên xuống:**
  - Hiện vùng với tới, các tia giới hạn J1, tư thế **thực** (nét liền) và tư thế **đích** đang chạy tới (nét đứt).
  - Hiện các Point, cùng một thanh độ cao Z.
  - Chọn một chương trình (ở tab Vận hành hoặc Lập trình) thì tab này vẽ **đường đi dự kiến**, với số thứ tự Step tại mỗi điểm. Vì các khớp chạy đồng bộ, đường đi giữa hai Point chính là nội suy tuyến tính trong không gian khớp, nên hình vẽ đúng với đường robot sẽ đi.
  - Xem trước được cả khi chưa kết nối.
- **Đồ thị bám quỹ đạo:**
  - Chọn trục J1, J2, J3 hoặc Z, và cửa sổ thời gian 5, 10 hoặc 30 s.
  - Khung trên vẽ vị trí **đặt** (quỹ đạo), **thực** (encoder) và **đích**.
  - Khung dưới vẽ **sai số bám** cùng dải vùng chết. Bên dưới ghi sai số hiện tại, sai số lớn nhất và RMS. Dùng để chỉnh PID và lấy hình cho báo cáo.
  - Nút **Dừng hình** giữ nguyên đồ thị để chụp. Nút **Lưu CSV** xuất 60 s dữ liệu gần nhất để vẽ lại bằng Excel hoặc MATLAB.
- **Hiệu năng:**
  - Vẽ bằng `tk.Canvas` (không dùng matplotlib), 10 lần/giây, và **chỉ khi tab đang mở**.
  - Telemetry `T` 50 Hz chỉ được bật (`SEL <trục>`) khi tab mở. Rời tab thì GUI gửi `SEL 0`, STM32 ngừng gửi.

---

## 6. Hướng dẫn sử dụng

### 6.1. Build và nạp firmware

1. Mở `Code STM32/MDK-ARM/Graduate_project.uvprojx` bằng **Keil µVision 5** (đã cài pack STM32F4xx_DFP).
2. Build (F7), rồi nạp qua ST-Link (F8).
3. Nếu sửa cấu hình chân bằng CubeMX (`Graduate_project.ioc`) và sinh lại code, phần code người dùng nằm trong các khối `USER CODE BEGIN/END` nên không bị mất. Nhớ kiểm tra lại các file `.c` tự thêm (`gripper.c`, `home_sen.c`, …) vẫn còn trong project Keil.

Các thông số **cảm biến home** đặt trực tiếp trong `main.c`, gồm chân cảm biến, tốc độ tìm (% Vmax), chiều tìm (+1/−1) và thời gian chờ:

```c
HomeSen_Init(&home_sen[1], GPIOD, GPIO_PIN_15, 60, -1, 10000);   /* Motor 2: J1 */
```

- **Vị trí home** (độ/mm) **không** đặt ở đây mà đặt trong Settings của GUI (mục 7).
- Trục nào chưa lắp cảm biến thì comment dòng `HomeSen_Init` của trục đó. PC sẽ bỏ qua trục ấy khi HOME.

### 6.2. Chạy giao diện

Yêu cầu Python 3.10 trở lên:

```bash
pip install customtkinter pyserial
cd "Giao dien dieu khien"
python main.py                 # chạy bình thường
python main.py --scale 0.85    # thu nhỏ giao diện (máy yếu / màn hình độ phân giải cao)
python main.py --dark          # giao diện tối (mặc định: sáng)
```

### 6.3. Quy trình vận hành

1. **Kết nối:**
   - Vào **Settings → Communication**, chọn cổng COM, baud 115200, bấm **Connect**.
   - GUI gửi toàn bộ cấu hình xuống STM32. Chờ Log báo `CONFIG_OK`.
2. **HOME:**
   - Bấm **HOME** (tab Vận hành, dưới khung JOG). Các trục chạy chậm về cảm biến và dừng; vị trí được đặt bằng giá trị Home trong Settings.
   - Chờ Log báo `HOME_DONE`.
   - Chưa HOME thì GUI chặn JOG và START. Có công tắc *"Bỏ qua kiểm tra HOME"* nhưng chỉ dùng khi debug.
3. **Dạy điểm** (tab **Vận hành**, chế độ **JOG**): đưa robot tới vị trí cần lưu. Có ba cách: JOG từng khớp, JOG theo
   **Tọa độ X Y Z θ**, hoặc nhập tọa độ ở **Move to XYZθ**. Sau đó bấm **📌 Teach Point** và đặt tên. Muốn sửa lại
   một điểm đã có thì sang tab **Lập trình**, chọn điểm rồi bấm **Save Position**.
4. **Soạn chương trình** (tab **Lập trình**): tạo Program, thêm các Step MOVE / GRIP / DELAY. Nên thêm DELAY sau GRIP để kẹp kịp đóng hoặc mở.
   Với pick and place, mỗi vị trí gắp hoặc đặt nên có **hai Point**: một điểm phía trên (Z cao) và một điểm phía dưới.
   Robot đi ngang ở độ cao an toàn rồi mới hạ thẳng xuống, để tránh va vào vật:
   ```
   MOVE P1_tren → MOVE P1_duoi → GRIP ON → DELAY → MOVE P1_tren → MOVE P2_tren → MOVE P2_duoi → GRIP OFF → DELAY → MOVE P2_tren
   ```
5. **Chạy** (tab **Vận hành**, khung Chạy chương trình): gạt **Chế độ** sang **CHƯƠNG TRÌNH**, chọn Program và bấm
   **START**. Có thể PAUSE/RESUME bất kỳ lúc nào; nút **■ STOP** trên thanh tiêu đề dừng ngay ở mọi tab.
6. **Khi có FAULT:**
   - Kiểm tra cơ khí và encoder trước.
   - Bấm **RESET** (gửi `CLEAR`), rồi **HOME** lại vì trục đã mất mốc vị trí.

### 6.4. Mô phỏng 3D (không cần robot)

Nhấp đúp file **`mo_phong_scara.html`** ở thư mục gốc để mở bằng Chrome hoặc Edge. Lần đầu cần Internet để tải thư viện
3D (three.js); sau đó trình duyệt tự lưu lại.

- **Mô hình tính toán giống hệt GUI:** cùng FK/IK, cùng giới hạn khớp, cùng cách chọn nghiệm và cùng cách **đồng bộ khớp**.
  Đã kiểm tra trên 20 000 trường hợp ngẫu nhiên: kết quả IK của trang web trùng với `core/kinematics.py`.
- **Điều khiển:**
  - Kéo thanh trượt J1, J2, J3, Z.
  - Nhập tọa độ đầu công tác X, Y, Z, θ rồi bấm **Đi tới**, hoặc bấm − / + để dịch từng bước.
  - Bấm một **Point** để đi tới điểm đó; có nút Home và nút Kẹp.
- **Teach Point:** JOG robot tới vị trí cần lưu rồi bấm **📌 Teach Point** và đặt tên. Bấm một Point để chọn, sau đó có thể
  **Đi tới** (hoặc nhấp đúp), **Cập nhật** theo tư thế hiện tại, **Đổi tên** (tự sửa mọi Step MOVE dùng tên cũ) hoặc
  **Xóa** (bị chặn nếu chương trình đang dùng Point đó).
- **Soạn chương trình** giống tab Lập trình của GUI: tạo/xóa chương trình; thêm **MOVE / GRIP ON / GRIP OFF / DELAY**
  (Step mới chèn ngay sau Step đang chọn); **Sửa**, **▲ ▼** đổi thứ tự, **Xóa** Step.
- **💾 Lưu** ghi `points.json` + `programs.json` vào thư mục data, **cùng định dạng với GUI** nên dùng được ngay trên robot
  thật. Chưa mở thư mục data thì Lưu sẽ tải 2 file xuống để bạn chép vào. Có dấu "● Có thay đổi chưa lưu", và trang hỏi
  lại nếu đóng khi chưa lưu.
  > ⚠ Giao diện điều khiển chỉ đọc các file này **lúc khởi động**. Lưu từ mô phỏng xong thì **tắt và mở lại** giao diện
  > điều khiển. Đừng soạn Point / chương trình ở cả hai nơi cùng lúc, vì bên nào lưu sau sẽ ghi đè bên kia.
- **Chạy thử chương trình:** chọn Program rồi bấm **Chạy**, có thể Tạm dừng / Dừng và chọn tốc độ ×0.25 tới ×10.
  Step đang chạy được tô sáng. Thời gian mỗi chuyển động tính theo Vmax/Amax trong Settings nên gần với robot thật.
- **Hiển thị:**
  - Vùng làm việc, vết đầu công tác, các Point.
  - Đường đi dự kiến của chương trình, có số thứ tự Step.
  - Bốn góc nhìn: 3D, Trên xuống, Mặt trước, Mặt bên. Chuột trái xoay, chuột phải dời, lăn chuột phóng to.
- **Dữ liệu (nên dùng Chrome / Edge):**
  - Bấm **🔗 Mở thư mục data** và chọn thư mục `Giao dien dieu khien\data`. Trang đọc cấu hình, Point và chương trình
    **mới nhất**, robot đứng tại Home trong Settings. Trang nhớ thư mục này: lần sau mở lại, trang tự đọc (hoặc chỉ cần
    bấm "Mở lại thư mục data" một lần để cho phép).
  - Chưa mở thư mục thì trang dùng bản chụp nhúng sẵn lúc tạo file. Vẫn có thể **Nạp file JSON…** hoặc kéo-thả file vào trang.
- **Khác với robot thật:** Tạm dừng trong mô phỏng là dừng hình ngay, còn robot thật giảm tốc rồi mới dừng. Mô phỏng
  không mô phỏng PID, ma sát hay sai số bám.

---

## 7. Cấu hình (`Giao dien dieu khien/data/robot_config.json`)

Mọi thông số dưới đây chỉnh trong **Settings** và lưu bằng **Save** hoặc **Apply**. Apply gửi ngay xuống STM32 nếu đang kết nối; nếu chưa thì gửi khi Connect. File JSON là **nguồn cấu hình duy nhất** cho việc đổi đơn vị.

| Panel | Nội dung | Lệnh gửi xuống STM32 |
|---|---|---|
| 1. Robot Kinematics | h1, l1, l2, h2 (mm), chỉ dùng trên PC cho động học thuận | — |
| 2. Joint Limits + Home | Min/Max từng khớp; **Home** = vị trí gán khi chạm cảm biến | `LIMIT`, `HPOS` |
| 3. Encoder | PPR (counts/vòng, đã ×4), Gear (J: tỉ số truyền, Z: mm/vòng), Direction | dùng để đổi đơn vị |
| 4. Motion Profile | Vmax, Amax (°/s, °/s² hoặc mm/s, mm/s²) | `VMAX`, `AMAX` |
| 5. PID + Deadband | Kp, Ki, Kd, vùng chết (counts) | `PID`, `DB` |
| 6. Fault Thresholds | **Trip** (khi chạy) và **Home Trip** (khi HOMING), đơn vị độ/mm | `TRIP` |

> Đổi **Home** hoặc **Encoder** thì phải bấm **HOME** lại để vị trí được đặt theo giá trị mới.
> Quy ước gốc đổi đơn vị: 0 counts (lúc cấp nguồn) ứng với J1 = J2 = J3 = 0°, Z = 300 mm.

---

## 8. Giao thức UART (tóm tắt)

PC → STM32: `<LỆNH> <động cơ 1..4> [tham số]`, đơn vị counts. Các lệnh:

- **Chuyển động:** `GOTO`, `JOG`, `HOME`, `HOMING`, `STOP`, `PAUSE`, `RESUME`
- **Cấu hình:** `PID`, `VMAX`, `AMAX`, `DB`, `LIMIT`, `HPOS`, `TRIP`
- **Khác:** `CLEAR` (xóa FAULT), `SEL` (chọn trục gửi telemetry, `SEL 0` = tắt)
- **Không kèm số động cơ:** `GRIP <0|1>`, `WDT <ms>`, `PING` (không trả lời)

STM32 → PC:

- `OK <lệnh> <id>` hoặc `ERR <lệnh> <id> <lý do>`
- `S <ms> (st goal sp pos)×4 <grip>` (20 Hz)
- `FAULT <id> trip|home`
- `BOOT`
- `LINKLOST` (STM32 tự dừng vì mất tín hiệu từ PC)
- `T …` (telemetry)

Chi tiết đầy đủ xem [firmware/PROTOCOL.md](Giao%20dien%20dieu%20khien/firmware/PROTOCOL.md) và phần chú thích trong [control.h](Code%20STM32/Core/Inc/control.h).

Muốn thử phần cứng không cần GUI:

```bash
python "Giao dien dieu khien/tools/uart_tool.py" COM5        # gõ lệnh trực tiếp, vd: GOTO 2 109200
```

> **Firmware và GUI phải cùng phiên bản.** GUI mới gửi các lệnh `HPOS`/`TRIP`/`GRIP`/`WDT`/`PING`/`SEL 0` và đọc trạng thái kẹp ở cuối dòng `S`. Dùng lệch phiên bản sẽ bị lỗi cấu hình khi Connect.

---

## 9. Xử lý sự cố

| Hiện tượng | Nguyên nhân thường gặp / cách xử lý |
|---|---|
| Connect xong bị ngắt, Log báo "không nhận được dòng trạng thái (S)" | Sai cổng COM hoặc baud, STM32 chưa chạy firmware, dây TX/RX đảo |
| `STM32 từ chối cấu hình … firmware không biết lệnh này` | Firmware trên chip là bản cũ, cần build và nạp lại |
| `FAULT … trip` ngay khi chạy | Encoder ngược chiều (sửa `enc_sign` trong `main.c` hoặc Direction trong Settings), Vmax/Amax quá cao so với động cơ, kẹt cơ khí, ngưỡng Trip quá nhỏ |
| `FAULT … home` | Không thấy cảm biến trong thời gian chờ (sai chiều tìm, sai chân, cảm biến hỏng) hoặc trục bị chặn; nếu bị báo giả khi tìm nhanh thì tăng *Home Trip* |
| Sau HOME vị trí hiển thị sai | Kiểm tra panel Encoder (PPR, Gear) đúng với cơ khí; JOG 10° rồi đo bằng thước đo góc để xác nhận |
| JOG / START bị chặn | Chưa Connect, chưa HOME, sai chế độ (nút gạt JOG / CHƯƠNG TRÌNH trong khung Chạy chương trình), hoặc chương trình đang chạy |
| Log báo "STM32 tự dừng vì quá 0.6 s không nhận được tín hiệu từ PC" | Dây USB lỏng hoặc bộ chuyển USB–UART chập chờn, cũng có thể máy tính bị treo. Robot đã tự dừng và giữ vị trí: kiểm tra dây, bấm RESET rồi chạy lại, không cần HOME lại |
| Giao diện chậm trên máy yếu | Chạy với `--scale 0.85`; có thể chỉnh `TICK_MS`, `DISPLAY_EVERY`, `MAX_LOG_LINES` trong `ui/perf.py` |

---

## 10. Giới hạn hiện tại và hướng phát triển

- **Chưa có nội suy đường thẳng trong không gian Descartes.** Các khớp đã được đồng bộ nên đầu công tác đi thẳng
  trong không gian khớp. Với bước ngắn, đường đi rất gần đường thẳng (dưới 1% bước ở tư thế thường). Với quãng dài
  (vài chục mm trở lên) đường đi vẫn hơi cong. Robot dùng cho **pick and place trong không gian thoáng**, chỉ cần tới
  đúng điểm đích và di chuyển ngang ở độ cao an toàn, nên không cần nội suy đường thẳng. Nếu sau này cần đi thẳng
  thật (trượt theo thanh dẫn, đưa vào khe hẹp, vẽ, dán keo…), PC phải chia nhỏ quãng đường và gửi liên tục, đồng thời
  firmware cần thêm hàng đợi điểm.
- **JOG theo tọa độ là JOG từng bước,** chưa có kiểu giữ nút để chạy liên tục.
- Kẹp không có cảm biến phản hồi; Step GRIP báo xong ngay khi STM32 xác nhận lệnh, nên cần DELAY để chờ kẹp đóng/mở.
- Giao thức UART không có checksum; dòng hỏng chỉ bị bỏ qua.
