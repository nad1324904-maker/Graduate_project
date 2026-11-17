# Checklist thử robot thật

Dùng khi lên xưởng thử firmware + GUI mới (có J3, kẹp, E-Stop). Làm **theo thứ tự**, bước sau dựa vào kết quả bước trước.
In ra giấy hoặc mở trên điện thoại, đánh dấu `[x]` và ghi kết quả vào cột trống.

> Mở app: `cd UI` rồi `python main.py`. Mọi chỗ ghi **Settings → …** bên dưới là tab con Settings **trong tab Robot** của app master.

> **Dừng ngay** (bấm ■ STOP trên GUI, hoặc cắt nguồn động lực) nếu: trục chạy sai chiều mà không tự FAULT, có tiếng kêu lạ / mùi khét,
> driver BTS7960 nóng bỏng tay, robot chạm cơ cấu cứng, hoặc dây encoder/cảm biến bị kéo căng.

---

## 0. Chuẩn bị (ở nhà, trước khi đi)

- [ ] Kéo code mới nhất: `git pull`. Ghi mã commit đang dùng: `__________` (lệnh `git log --oneline -1`)
- [ ] Build lại firmware trong Keil (0 error) rồi mới mang đi nạp. Firmware và GUI **phải cùng commit**
- [ ] Mang theo: thước đo góc, thước kẹp (hoặc thước lá), bút đánh dấu, băng dính, dây USB-UART dự phòng, đồng hồ VOM
- [ ] Trong tab Robot → Settings → **4. Trapezoidal Motion Profile**, **giảm Vmax** cho lần chạy đầu (khoảng 1/3 giá trị đang dùng) rồi Save. Nhớ trả lại sau khi test xong

## 1. Nạp firmware và kết nối

- [ ] Robot **chưa cấp nguồn động lực** (chỉ cấp nguồn cho STM32). Nạp firmware
- [ ] Mở app, tab Robot → Settings → Communication → chọn COM → Connect. Log có **CONFIG_OK**, không có dòng đỏ
- [ ] Badge kết nối báo đã kết nối; tab Giám sát thấy số vị trí cập nhật liên tục (dòng `S` 20 Hz đang về)
- [ ] Nếu Connect báo lỗi cấu hình → firmware và GUI lệch phiên bản → nạp lại firmware đúng commit

## 2. Cảm biến home (chưa cấp nguồn động lực)

Dùng tay che/chạm từng cảm biến, xem trạng thái trên GUI (hoặc `uart_tool.py`: bit **64** trong trường `st` của dòng `S` bật lên).

| Trục | Chân | Kích hoạt thì GUI thấy? | Ghi chú |
|---|---|---|---|
| Z | PD14 | [ ] | |
| J1 | PD15 | [ ] | |
| J2 | PD13 | [ ] | |
| J3 | PD11 | [ ] | **mới** — chưa từng thử |

## 3. Chiều encoder (chưa cấp nguồn động lực, xoay bằng tay)

Xoay từng khớp **bằng tay** theo chiều dương (theo quy ước động học của mình), số trên GUI phải **tăng**.

| Trục | Encoder | Xoay dương → số tăng? | Xoay ~10° / 10 mm, GUI hiện bao nhiêu? |
|---|---|---|---|
| Z | TIM8 | [ ] | |
| J1 | TIM2 | [ ] | |
| J2 | TIM3 | [ ] | |
| J3 | TIM4 | [ ] | **mới** |

- [ ] Trục nào **ngược chiều** → đổi `enc_sign` (cột thứ 7, `+1` ↔ `-1`) của trục đó trong bảng `cfg[]` ở `main.c` (dòng ~176–179), build và nạp lại
- [ ] Trục nào **sai tỉ lệ** (vd xoay 10° mà hiện 30°) → kiểm tra số counts/vòng và tỉ số truyền trong Settings → 3. Encoder / PPR / Gear Ratio

## 4. Cấp nguồn động lực, JOG từng trục

Một tay luôn đặt sẵn trên nút **■ STOP**. Chế độ JOG; tạm bật công tắc "Bỏ qua kiểm tra HOME (chỉ để debug)" để JOG được trước khi HOME.

- [ ] Bấm JOG **từng bước nhỏ** (1° / 1 mm) theo chiều + rồi chiều −, lần lượt Z → J1 → J2 → J3

| Trục | JOG + đi đúng chiều? | JOG − đi đúng chiều? | Bám êm, không rung? |
|---|---|---|---|
| Z | [ ] | [ ] | [ ] |
| J1 | [ ] | [ ] | [ ] |
| J2 | [ ] | [ ] | [ ] |
| J3 | [ ] | [ ] | [ ] |

- [ ] Nếu vừa JOG đã **FAULT trip ngay** hoặc trục chạy vọt đi → động cơ và encoder ngược nhau (encoder đã đúng ở bước 3) → đổi chỗ
  2 kênh PWM thuận/nghịch của trục đó trong `cfg[]` (cặp `t_fwd, ch_fwd` ↔ `t_rev, ch_rev`) hoặc đảo 2 dây động cơ
- [ ] J3: PWM = TIM14 CH1 / TIM12 CH2, encoder TIM4. Kiểm tra kỹ vì đây là lần đầu chạy

## 5. HOME lần đầu

- [ ] Tắt công tắc "Bỏ qua kiểm tra HOME". Đưa robot về giữa vùng làm việc. Bấm **HOME**, tay trên STOP
- [ ] Mỗi trục chạy **về phía cảm biến** (Z đi lên; J1, J2, J3 đi theo chiều giảm). Trục nào chạy ra xa cảm biến → bấm STOP, đổi
  tham số chiều (`+1`/`-1`) trong dòng `HomeSen_Init` của trục đó ở `main.c`
- [ ] Sau khi xong: log **HOME_DONE**, GUI hiện J1 = −30, J2 = −30, J3 = 0, Z = 350, Homed = YES
- [ ] Nếu **HOME_ERROR / FAULT home**: xem trục nào; thường là Home Trip (Settings → 6. Fault Thresholds) quá nhỏ hoặc timeout quá ngắn
- [ ] HOME lại 3 lần, đánh dấu vị trí đầu tay bằng bút: các lần có trùng nhau không? Lệch: `______ mm`

## 6. Đo độ chính xác

- [ ] Từ HOME, Move to J1 + 10° → đo bằng thước đo góc: `______ °`
- [ ] J2 + 10°: `______ °` · J3 + 90°: `______ °` · Z − 10 mm (thước kẹp): `______ mm`
- [ ] Sai nhiều hơn vài % → sai counts/vòng hoặc tỉ số truyền trong Settings → 3. Encoder / PPR / Gear Ratio

## 7. Kẹp (PD9) — **mới**

- [ ] Vừa cấp nguồn / sau Connect, kẹp đang **MỞ**
- [ ] Bấm nút kẹp → kẹp **ĐÓNG**, GUI báo ĐÓNG (ON); bấm lại → MỞ. Nếu ngược → sửa mức tích cực trong `Gripper_Init` ở `main.c`
- [ ] Bấm STOP trong lúc kẹp đang đóng → kẹp **giữ nguyên** (không tự mở làm rơi vật)
- [ ] Đo thời gian đóng/mở thật để đặt DELAY sau Step GRIP: `______ s`

## 8. Chuyển động đồng bộ

- [ ] Move to một điểm đổi cả 4 trục cùng lúc: các trục **bắt đầu và dừng cùng lúc**
- [ ] Tăng dần Vmax về giá trị thật (bước 0). Không FAULT, không rung mạnh

## 9. Kiểm tra PID (tab Giám sát)

- [ ] Chọn từng trục, cho chạy một đoạn dài, xem đồ thị: vọt lố nhỏ, không dao động kéo dài, sai số bám nhỏ
- [ ] Bấm "💾 Lưu CSV" một lần chạy đẹp của mỗi trục (dùng làm hình trong báo cáo): đã lưu [ ]
- [ ] Trục nào rung / bám kém → chỉnh Kp, Ki, Kd trong Settings → 5. PID + Deadband, Save, thử lại. Ghi bộ số cuối cùng:
  `J1: ________  J2: ________  J3: ________  Z: ________`

## 10. Bảo vệ

- [ ] **FAULT trip:** tạm đặt Trip của J1 (Settings → 6. Fault Thresholds) rất nhỏ (vd 0.2°), JOG nhanh → FAULT, robot dừng, log báo. Bấm RESET → hết FAULT. **Trả Trip về cũ**
- [ ] **Watchdog:** robot đang chạy một đoạn dài, **rút dây USB-UART** (không rút nguồn STM32) → robot giảm tốc dừng trong ~0.6 s.
  Cắm lại, Connect → chạy tiếp được, không cần HOME lại
- [ ] **E-STOP mềm — mới:** robot đang chạy, bấm **⛔ E-STOP** ở header →
  - [ ] cả 4 trục dừng ngay, badge hiện **E-STOP**, nút HOME / kẹp / JOG / START bị khóa
  - [ ] bấm RESET → hết E-STOP, Homed = NO → bấm HOME → chạy lại bình thường
- [ ] **E-Stop có cắt nguồn động lực:** robot đứng yên, **giữ Z bằng tay** rồi cắt nguồn driver (giả lập relay an toàn của PLC), bấm ⛔ E-STOP
  trên GUI → cấp lại nguồn → RESET → HOME. Ghi lại: Z có bị **tụt** khi mất nguồn không? `______`; kẹp mất nguồn thì đóng hay mở? `______`

## 11. Pick and place thật

- [ ] Teach 1 điểm gắp (tại vị trí dừng băng tải CB3) + 3 điểm thả (đạt / lỗi 1 / lỗi 2), mỗi điểm có điểm "trên" và điểm "dưới"
- [ ] Soạn chương trình 1, 2, 3 trong tab Lập trình (có DELAY sau GRIP), chạy từng chương trình bằng tay
- [ ] Chạy mỗi chương trình **10 lần liên tục**: lần nào gắp hụt / thả lệch? `______`
- [ ] Đo thời gian một chu kỳ gắp-thả: `______ s` (dùng cho báo cáo và để PC đặt timeout)

## 12. Sau buổi test

- [ ] Settings → Save. Gửi lại file `data/robot_config.json`, các Point / Program mới và các file CSV để commit lên GitHub
- [ ] Ghi lại những gì đã sửa trong `main.c` (enc_sign, chiều home, kênh PWM…) để commit
- [ ] Lỗi / hiện tượng lạ cần hỏi thêm:

```
....................................................................
....................................................................
```
