#ifndef CONTROL_H
#define CONTROL_H

#include "main.h"
#include "motor.h"
#include "encoder.h"
#include "pid.h"
#include "trap_profile.h"
#include "comm.h"
#include "home_sen.h"
#include "gripper.h"

#define CONTROL_COUNT       4          /* so dong co */
#define CONTROL_DT          0.001f     /* chu ky vong dieu khien (s) = chu ky ngat TIM9 */
#define CONTROL_TEL_MS      20         /* chu ky telemetry (ms) = 50 Hz */
#define CONTROL_ERR_TRIP    76500L     /* MAC DINH (truoc khi PC gui TRIP): |vi tri dat - vi tri thuc| vuot muc nay (counts) -> phanh + FAULT */
#define CONTROL_POS_LIMIT   20000000L  /* |dich| toi da cua lenh JOG/GOTO/HOME (counts): chi de chan nhap sai, KHONG phai hanh trinh co khi.
                                          Gioi han hanh trinh that dat bang lenh LIMIT (mac dinh = +-CONTROL_POS_LIMIT). */
#define CONTROL_STATUS_MS   50         /* chu ky dong trang thai "S" cho ca 4 dong co (ms) = 20 Hz */
#define CONTROL_HOMING_SEEK 16000000L  /* HOMING: dich "rat xa" ve phia cam bien (counts, < 2^24 de float cua quy dao con chinh xac) */
#define CONTROL_HOMING_ERR_TRIP 6000L  /* MAC DINH (truoc khi PC gui TRIP): HOMING: sai so bam quy dao > muc nay (counts) = dong co dang
                                          bi chan/ket -> dung, FAULT home. Bao ve khong de PID giu PWM bao hoa vao chan co khi neu cam
                                          bien khong tac dong. PC dat lai tung truc bang lenh TRIP (Settings -> Fault Thresholds). */
#define CONTROL_SETTLE_MS   1000       /* quy dao xong ma van ngoai vung chet qua ngan nay (ms) -> coi la da on dinh (busy=0), KHONG bao loi */

typedef struct {                       /* 1 mau telemetry (counts, counts/s) */
  uint32_t ms;
  int32_t  en, goal, sp, pos, sv, v;
} ControlTel_t;

/* Gom cac module thanh 1 vong dieu khien vi tri cho 1 dong co: encoder -> quy dao hinh thang -> PID -> motor.
   Giu trang thai chung (en, goal, vung chet, FAULT) va tao telemetry. */
typedef struct {
  Motor_t       *motor;
  Encoder_t     *enc;
  PID_t         *pid;
  TrapProfile_t *trap;
  Comm_t        *comm;

  uint8_t           id;                /* so dong co trong giao thuc (1..CONTROL_COUNT) */
  volatile uint8_t  en;                /* 1: PID dang chay; 0: dang phanh */
  volatile int32_t  goal;              /* dich (counts) */
  volatile int32_t  deadband;          /* vung chet +-n counts quanh dich */
  volatile int32_t  err_trip;          /* sai so bam quy dao (counts) vuot muc nay -> FAULT trip (lenh TRIP, mac dinh CONTROL_ERR_TRIP) */
  volatile int32_t  homing_trip;       /* nhu tren nhung khi HOMING -> FAULT home (lenh TRIP, mac dinh CONTROL_HOMING_ERR_TRIP) */
  volatile int32_t  lim_min, lim_max;  /* gioi han hanh trinh (counts), ap dung cho JOG/GOTO/HOME */
  volatile uint8_t  paused;            /* 1: dang PAUSE (quy dao giam toc ve pause_goal roi dung) */
  volatile uint8_t  busy;              /* 1: chua on dinh tai dich (dang chay / dang PAUSE) */
  volatile uint8_t  faulted;           /* FAULT trip con chot; xoa bang lenh CLEAR. != 0 thi tu choi JOG/GOTO/HOME */
  volatile uint8_t  fault;             /* != 0: vua bi FAULT, chua bao: main loop se gui "FAULT <id> trip|home" (1 = trip, 2 = home) */
  double            pause_goal;        /* diem dung khi PAUSE = vi tri quy dao + quang duong phanh */
  uint16_t          settle_cnt;        /* so ms da o ngoai vung chet sau khi quy dao xong */

  uint8_t           tel_cnt;
  uint32_t          ms_tick;
  ControlTel_t      tel;
  volatile uint8_t  tel_ready;

  HomeSen_t        *home;              /* cam bien home (NULL = chua cau hinh -> HOMING tra "ERR ... nosensor") */
  volatile int32_t  home_pos;          /* vi tri (counts) gan cho encoder khi cham cam bien home; PC dat bang HPOS (mac dinh 0) */
  volatile uint8_t  homing;            /* 1: dang tim cam bien home */
  volatile uint8_t  homed;             /* 1: da HOME that (vi tri da dat theo cam bien); xoa khi bat dau HOMING hoac khi FAULT */
  uint32_t          homing_ms;         /* thoi gian da tim (ms), de bao timeout */
} Control_t;

/* id = 1..CONTROL_COUNT */
void Control_Init(Control_t *c, uint8_t id, Motor_t *m, Encoder_t *e, PID_t *p, TrapProfile_t *t, Comm_t *comm,
                  int32_t deadband);

/* Gan cam bien home cho dong co (goi sau Control_Init; h da qua HomeSen_Init). Khong goi = dong co khong co HOMING */
void Control_SetHome(Control_t *c, HomeSen_t *h);

/* Goi moi 1 ms tu ngat TIM9 (cho tung dong co) */
void Control_Tick(Control_t *c);

/* Goi trong main loop: thong bao FAULT; neu send_tel thi dua telemetry vao hang doi TX (khong thi bo mau) */
void Control_Poll(Control_t *c, int send_tel);

/* ---- Nhieu dong co dung chung 1 UART ----
   Lenh van ban: <LENH> <so dong co> [tham so...], vi du "GOTO 2 12750", "PID 3 4.2 0 0", "STOP 1".
   Don vi: counts, counts/s, counts/s^2 (PC tu doi sang do/mm).
     JOG   <id> <counts>         dich += counts (tuong doi)
     GOTO  <id> <counts>         dich = counts (tuyet doi, so voi vi tri luc cap nguon = 0)
     HOME  <id> | STOP <id>      dich = 0 | phanh gap, tat PID (goal = pos)
     HPOS  <id> <counts>         vi tri home: gia tri gan cho encoder khi HOMING cham cam bien (PC gui luc Connect/Apply,
                                 doi tu do/mm). Khong lam robot chay; chi co hieu luc tu lan HOMING ke tiep.
     HOMING <id>                 chay cham (speed_pct % VMAX) ve phia cam bien home; cham cam bien thi DUNG NGAY, dat vi tri
                                 encoder = HPOS, bat co homed. Qua timeout / bi chan -> FAULT <id> home.
                                 Dang HOMING thi JOG/GOTO/HOME bi tu choi (ERR ... homing); chi STOP moi huy duoc.
     PAUSE <id> | RESUME <id>    giam toc ve diem dung roi giu (dich cu duoc giu) | tiep tuc ve dich cu
     LIMIT <id> <min> <max>      gioi han hanh trinh (counts); JOG/GOTO/HOME ngoai khoang -> ERR range
     CLEAR <id>                  xoa FAULT da chot
     PID <id> <kp> <ki> <kd> | VMAX <id> <n> | AMAX <id> <n> | DB <id> <n>
     TRIP  <id> <trip> <home>    nguong sai so bam (counts, > 0): <trip> khi chay -> FAULT trip, <home> khi HOMING -> FAULT home
     SEL <id>                    chon dong co gui telemetry "T" (mac dinh: khong dong co nao); SEL 0 = tat telemetry
     PING                        KHONG co so dong co, KHONG tra loi: bao "PC con song" cho watchdog
     WDT <ms>                    KHONG co so dong co: bat watchdog mat ket noi (100..60000 ms; 0 = tat). Tra "OK WDT <ms>".
                                 Qua <ms> khong nhan duoc dong nao -> truc dang chay giam toc dung + giu vi tri, gui "LINKLOST"
     GRIP <0|1>                  KHONG co so dong co: 1 = DONG kep, 0 = MO kep. Tra loi "OK GRIP <0|1>" (= trang thai moi)
                                 hoac "ERR GRIP ? arg". Kep khong tu doi khi STOP / FAULT.
   Tra loi: "OK <lenh> <so>" / "ERR <lenh> <so> <ly do>" (arg | range | fault | unknown | id | homing | nosensor).
   Trang thai ca 4 dong co moi CONTROL_STATUS_MS:
     S <ms> <st> <goal> <sp> <pos>  (lap 4 lan, dong co 1..4) <grip>   (grip = 1 kep DONG, 0 kep MO)
     st = bit0 en | bit1 paused | bit2 busy (chua on dinh tai dich; tu ve 0 sau CONTROL_SETTLE_MS ke tu khi quy dao xong) | bit3 faulted
          | bit4 homed (da HOME that) | bit5 homing (dang tim cam bien) | bit6 cam bien home dang kich hoat (da loc nhieu)
     sp = vi tri quy dao dat (counts), pos = vi tri encoder (counts)
   Telemetry (chi dong co duoc SEL): "T <so> <ms> <en> <goal> <sp> <pos> <sv> <v>".
   FAULT: "FAULT <so> trip" (sai so bam quy dao > err_trip) hoac "FAULT <so> home" (HOMING that bai). Dong co do bi tat PID + phanh cho den khi CLEAR. */
typedef struct {
  Control_t  m[CONTROL_COUNT];
  Comm_t    *comm;
  Gripper_t *grip;                     /* kep (NULL = chua gan -> GRIP tra "ERR GRIP ? nogrip") */
  uint8_t    sel;                     /* chi so (0..CONTROL_COUNT-1) cua dong co gui telemetry T; 0xFF = khong gui */
  uint32_t   status_ms;                /* moc thoi gian (HAL_GetTick) lan gui dong "S" gan nhat */
  /* Watchdog mat ket noi: PC gui PING deu dan; qua wdt_ms ms khong nhan duoc dong nao -> moi truc dang chay giam toc
     dung lai roi GIU vi tri (khong tat PID, khong mat moc vi tri), gui "LINKLOST". wdt_ms = 0: tat (mac dinh). */
  uint32_t   last_rx_ms;               /* HAL_GetTick() luc nhan dong lenh gan nhat */
  uint16_t   wdt_ms;
  uint8_t    wdt_tripped;              /* 1: da dung vi mat ket noi; xoa khi nhan duoc dong lenh moi */
} ControlSet_t;

/* Goi TRUOC Control_Init cua tung dong co (xoa toan bo roi gan comm, sel = 0xFF: chua gui telemetry T) */
void ControlSet_Init(ControlSet_t *s, Comm_t *comm);

/* Gan kep cho bo dieu khien (g da qua Gripper_Init) */
void ControlSet_SetGripper(ControlSet_t *s, Gripper_t *g);

/* Goi moi 1 ms tu ngat TIM9: Control_Tick cho ca CONTROL_COUNT dong co */
void ControlSet_Tick(ControlSet_t *s);

/* Goi trong main loop */
void ControlSet_Poll(ControlSet_t *s);

/* Xu ly 1 dong lenh: dung lam on_line cho Comm_Init (ctx = ControlSet_t*) */
void ControlSet_OnLine(void *ctx, char *line);

#endif
