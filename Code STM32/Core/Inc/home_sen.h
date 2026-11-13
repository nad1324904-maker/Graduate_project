#ifndef HOME_SEN_H
#define HOME_SEN_H

#include "main.h"

/* Cam bien HOME cho 1 dong co (cong tac hanh trinh / cam bien quang / tiem can 3.3 V ...).
   Chi dung de TIM HOME: lenh "HOMING <id>" cho dong co chay cham ve phia cam bien, khi cam bien kich hoat thi
   dung ngay va dat vi tri encoder = vi tri home PC gui bang lenh HPOS (Control_t.home_pos, xem control.c).
   Chay binh thuong thi cam bien
   KHONG tac dong gi (chi doc de bao trang thai). */

/* Cau hinh chung cho moi cam bien (co the sua o day hoac #define truoc khi include) */
#ifndef HOMESEN_ACTIVE_LEVEL
#define HOMESEN_ACTIVE_LEVEL  GPIO_PIN_RESET   /* muc logic khi cam bien kich hoat: RESET = muc thap (active LOW) */
#endif
#ifndef HOMESEN_PULL
#define HOMESEN_PULL          GPIO_PULLUP      /* dien tro keo noi: PULLUP neu active LOW, PULLDOWN neu active HIGH */
#endif
#ifndef HOMESEN_DEBOUNCE_MS
#define HOMESEN_DEBOUNCE_MS   3                /* can du bay nhieu ms lien tiep o muc kich hoat moi coi la "da cham" */
#endif

typedef struct {
  GPIO_TypeDef *port;              /* chan doc cam bien */
  uint16_t      pin;
  uint8_t       speed_pct;         /* toc do tim home = speed_pct % VMAX hien tai (1..100) */
  int8_t        dir;               /* chieu tim cam bien theo COUNTS cua firmware: +1 = tang, -1 = giam */
  uint32_t      timeout_ms;        /* qua ngan nay ma chua cham cam bien -> FAULT home */

  uint8_t           cnt;           /* bo dem loc nhieu */
  volatile uint8_t  active;        /* 1: cam bien dang kich hoat (da loc nhieu) */
} HomeSen_t;

/* Cau hinh chan GPIO (input + pull) va luu tham so. Goi 1 lan trong main() truoc khi bat TIM9.
     speed_pct  : toc do tim, % cua VMAX (vd 80)
     dir        : +1 / -1 (chieu counts)
     timeout_ms : thoi gian tim toi da
   (Vi tri home: PC gui bang lenh "HPOS <id> <counts>", khong dat o day.) */
void HomeSen_Init(HomeSen_t *h, GPIO_TypeDef *port, uint16_t pin,
                  uint8_t speed_pct, int8_t dir, uint32_t timeout_ms);

/* Goi dung moi 1 ms (trong ngat, tu Control_Tick): doc chan + loc nhieu */
void HomeSen_Update(HomeSen_t *h);

static inline int HomeSen_Active(const HomeSen_t *h) { return h->active; }

#endif
