#include "control.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Vung gang ngat: ISR TIM9 va main loop cung sua trang thai dieu khien */
#define CRIT_ENTER()  uint32_t primask_ = __get_PRIMASK(); __disable_irq()
#define CRIT_EXIT()   __set_PRIMASK(primask_)

static int32_t iround(double x) { return (int32_t)(x >= 0.0 ? x + 0.5 : x - 0.5); }

void Control_Init(Control_t *c, uint8_t id, Motor_t *m, Encoder_t *e, PID_t *p, TrapProfile_t *t, Comm_t *comm,
                  int32_t deadband)
{
  memset(c, 0, sizeof *c);
  c->id = id;
  c->motor = m; c->enc = e; c->pid = p; c->trap = t; c->comm = comm;
  c->deadband = deadband;
  c->err_trip = CONTROL_ERR_TRIP;                              /* mac dinh; PC gui TRIP khi Connect/Apply */
  c->homing_trip = CONTROL_HOMING_ERR_TRIP;
  c->lim_min = -CONTROL_POS_LIMIT;                             /* chua dat LIMIT: chi chan nhap sai */
  c->lim_max =  CONTROL_POS_LIMIT;
}

void Control_SetHome(Control_t *c, HomeSen_t *h)
{
  c->home = h;
}

/* Chot FAULT trip (goi tu ISR): phanh, tat PID, giu lai co loi cho den khi PC gui CLEAR */
static void latch_fault(Control_t *c, uint8_t code)
{
  c->en = 0; c->busy = 0; c->paused = 0;
  c->homing = 0; c->homed = 0;
  c->fault = code; c->faulted = code;
  c->goal = c->enc->pos;
  TrapProfile_Reset(c->trap, (double)c->enc->pos);
  PID_Reset(c->pid);
  Motor_Set(c->motor, 0);
}

/* E-STOP (goi trong vung gang ngat): phanh, tat PID, BO moc vi tri (homed = 0) va khoa chuyen dong cho den RESET.
   Khac latch_fault: khong bao FAULT; khac STOP: duoc chot lai (c->estop), moi lenh chuyen dong bi tu choi "estop".
   Bo moc vi tri vi cat nguon dong luc co the lam co cau tu di chuyen -> sau RESET phai HOMING lai. */
static void estop_motor(Control_t *c)
{
  c->en = 0; c->busy = 0; c->paused = 0;
  c->homing = 0; c->homed = 0;
  c->goal = c->enc->pos;
  TrapProfile_Reset(c->trap, (double)c->enc->pos);
  PID_Reset(c->pid);
  Motor_Set(c->motor, 0);
  c->tel_ready = 0;
  c->estop = 1;
}

/* HOMING (goi moi ms khi c->homing, trong ngat): cham cam bien -> dung ngay + dat vi tri = vi tri home;
   qua timeout hoac dong co bi chan (sai so bam qua lon) -> FAULT home. Toc do tim do Control_Tick ap dung. */
static void homing_tick(Control_t *c)
{
  if (HomeSen_Active(c->home)) {
    c->enc->pos = c->home_pos;                                 /* dat lai vi tri encoder = vi tri home (HPOS tu PC) */
    TrapProfile_Reset(c->trap, (double)c->enc->pos);           /* quy dao + dich tai cho: sai so = 0 -> PID giu nguyen o day */
    PID_Reset(c->pid);
    c->goal = c->enc->pos;
    c->homing = 0; c->homed = 1;
    c->paused = 0; c->settle_cnt = 0;
    return;
  }
  if (!c->paused) c->homing_ms++;
  if (c->homing_ms > c->home->timeout_ms ||
      fabs(c->trap->pos - (double)c->enc->pos) > (double)c->homing_trip) {
    latch_fault(c, 2);                                         /* phanh, tat PID, homing = 0 */
  }
}

/* ================= Vong dieu khien 1 kHz (trong ngat) ================= */
void Control_Tick(Control_t *c)
{
  Encoder_Update(c->enc);

  if (c->home) {                                               /* cam bien home: doc moi ms (loc nhieu); xu ly HOMING */
    HomeSen_Update(c->home);
    if (c->homing) homing_tick(c);
  }

  if (c->en) {
    /* PAUSE: quy dao giam toc (theo amax) ve pause_goal roi dung; dich goal van giu nguyen de RESUME */
    double tgt  = c->paused ? c->pause_goal : (double)c->goal;
    float  vmax_keep = c->trap->vmax;
    if (c->homing) c->trap->vmax = vmax_keep * (float)c->home->speed_pct * 0.01f;   /* HOMING: tim cham, speed_pct % VMAX */
    int    done = TrapProfile_Update(c->trap, tgt, CONTROL_DT);
    c->trap->vmax = vmax_keep;
    float  err  = (float)(c->trap->pos - (double)c->enc->pos); /* sai so bam quy dao (counts) */

    if (fabsf(err) > (float)c->err_trip) {                     /* chay mat kiem soat (vd: dao chieu encoder) */
      latch_fault(c, 1);
    } else {
      float u;
      int in_db = labs((long)iround(tgt) - (long)c->enc->pos) <= (long)c->deadband;
      if (done && in_db) {
        u = 0.0f;                                              /* trong vung chet quanh dich: nha, giu phanh */
      } else {
        u = PID_Update(c->pid, err, c->enc->vfilt, CONTROL_DT);
      }
      Motor_Set(c->motor, iround((double)u));

      c->busy = (uint8_t)(c->paused || !(done && in_db));
      if (done && !in_db && !c->paused) {                      /* quy dao xong ma chua vao vung chet (ma sat tinh...) */
        if (c->settle_cnt < CONTROL_SETTLE_MS) c->settle_cnt++;
        else c->busy = 0;                                      /* du lau -> coi la da on dinh (KHONG bao loi); PID van chay */
      } else {
        c->settle_cnt = 0;
      }
    }
  }

  /* Chot mau telemetry moi CONTROL_TEL_MS */
  c->ms_tick++;
  if (++c->tel_cnt >= CONTROL_TEL_MS) {
    c->tel_cnt = 0;
    c->tel.ms = c->ms_tick; c->tel.en = c->en; c->tel.goal = c->goal;
    c->tel.sp = iround(c->trap->pos); c->tel.pos = c->enc->pos;
    c->tel.sv = iround((double)c->trap->vel); c->tel.v = c->enc->vel;
    c->tel_ready = 1;
  }
}

/* ================= Telemetry: T <id> <ms> <en> <goal> <sp> <pos> <sv> <v> ================= */
void Control_Poll(Control_t *c, int send_tel)
{
  if (c->fault) {
    const char *kind = (c->fault == 2) ? "home" : "trip";
    c->fault = 0;
    char f[24];
    int m = snprintf(f, sizeof f, "FAULT %u %s\n", (unsigned)c->id, kind);
    if (m > 0 && m < (int)sizeof f) Comm_Send(c->comm, f, m);
  }
  if (!c->tel_ready) return;
  ControlTel_t t;
  { CRIT_ENTER(); t = c->tel; c->tel_ready = 0; CRIT_EXIT(); }
  if (!send_tel) return;                                       /* dong co khong duoc chon: bo mau */
  char b[96];
  int n = snprintf(b, sizeof b, "T %u %lu %ld %ld %ld %ld %ld %ld\n", (unsigned)c->id, (unsigned long)t.ms,
                   (long)t.en, (long)t.goal, (long)t.sp, (long)t.pos, (long)t.sv, (long)t.v);
  if (n > 0 && n < (int)sizeof b && Comm_TxFree(c->comm) > n) Comm_Send(c->comm, b, n);   /* day thi bo mau */
}

/* ================= Lenh van ban ================= */
static void reply(Comm_t *comm, const char *cmd, int id, const char *err)
{
  char b[56], ids[12];
  if (id > 0) snprintf(ids, sizeof ids, "%d", id); else strcpy(ids, "?");
  int n = err ? snprintf(b, sizeof b, "ERR %s %s %s\n", cmd, ids, err) : snprintf(b, sizeof b, "OK %s %s\n", cmd, ids);
  if (n > (int)sizeof b - 1) n = (int)sizeof b - 1;
  Comm_Send(comm, b, n);
}

static int parse_l(const char *s, long *out)
{
  if (!s) return 0;
  char *end; long v = strtol(s, &end, 10);
  if (end == s || *end != '\0') return 0;
  *out = v; return 1;
}

static int parse_f(const char *s, float *out)
{
  if (!s) return 0;
  char *end; float v = strtof(s, &end);
  if (end == s || *end != '\0' || !isfinite(v)) return 0;
  *out = v; return 1;
}

/* Thuc thi 1 lenh cho 1 dong co (cmd, a1..a3 da tach; khong con so dong co) */
static void exec(Control_t *c, const char *cmd, const char *a1, const char *a2, const char *a3)
{
  long n = 0, hi = 0; float x, y, z;
  int id = c->id;

  if (c->estop && (!strcmp(cmd, "JOG") || !strcmp(cmd, "GOTO") || !strcmp(cmd, "HOME") || !strcmp(cmd, "HOMING") ||
                   !strcmp(cmd, "PAUSE") || !strcmp(cmd, "RESUME"))) {
    reply(c->comm, cmd, id, "estop");                              /* dang E-STOP: phai RESET (ESTOP 0) truoc */
    return;
  }

  if (!strcmp(cmd, "JOG") || !strcmp(cmd, "GOTO") || !strcmp(cmd, "HOME")) {
    int mode = (cmd[0] == 'J') ? 0 : (cmd[0] == 'G') ? 1 : 2;      /* 0: JOG (+n), 1: GOTO (=n), 2: HOME (=0) */
    const char *err = NULL;
    if (mode != 2 && !parse_l(a1, &n)) err = "arg";
    else {
      CRIT_ENTER();
      if (c->faulted) err = "fault";                               /* phai CLEAR truoc */
      else if (c->homing) err = "homing";                          /* dang tim cam bien home: chi STOP moi huy duoc */
      else {
        int64_t base = c->en ? c->goal : c->enc->pos;
        int64_t ng = (mode == 0) ? base + n : (mode == 1) ? (int64_t)n : 0;
        if (ng < c->lim_min || ng > c->lim_max) err = "range";
        else {
          if (!c->en) {                                            /* bat PID tu vi tri hien tai */
            TrapProfile_Reset(c->trap, (double)c->enc->pos);
            PID_Reset(c->pid);
            c->en = 1;
          }
          c->goal = (int32_t)ng;
          c->paused = 0; c->settle_cnt = 0;
          c->busy = 1;                                             /* chua on dinh: tranh S "cu" bao busy=0 sau OK */
          c->tel_ready = 0;                                        /* bo mau cu (truoc lenh) de GUI khong thay en=0 cu sau OK */
        }
      }
      CRIT_EXIT();
    }
    reply(c->comm, cmd, id, err);
  }
  else if (!strcmp(cmd, "HOMING")) {                       /* chay cham ve cam bien home, cham thi dat vi tri = vi tri home */
    const char *err = NULL;
    CRIT_ENTER();
    if (!c->home) err = "nosensor";
    else if (c->faulted) err = "fault";
    else if (!c->homing) {                                 /* dang HOMING roi thi coi nhu OK (lenh lap), khong lam lai */
      if (!c->en) {                                        /* bat PID tu vi tri hien tai */
        TrapProfile_Reset(c->trap, (double)c->enc->pos);
        PID_Reset(c->pid);
        c->en = 1;
      }
      c->goal = (int32_t)((int64_t)c->enc->pos + (int64_t)c->home->dir * CONTROL_HOMING_SEEK);   /* dich rat xa, khong bi LIMIT chan */
      c->homing = 1; c->homed = 0; c->homing_ms = 0;
      c->paused = 0; c->settle_cnt = 0;
      c->busy = 1;                                         /* nhu JOG/GOTO: tranh S "cu" bao busy=0 sau OK */
      c->tel_ready = 0;
    }
    CRIT_EXIT();
    reply(c->comm, cmd, id, err);
  }
  else if (!strcmp(cmd, "STOP")) {                         /* phanh gap, tat PID cho den lenh JOG/GOTO/HOME ke tiep */
    CRIT_ENTER();
    c->en = 0; c->busy = 0; c->paused = 0; c->homing = 0; c->goal = c->enc->pos;
    TrapProfile_Reset(c->trap, (double)c->enc->pos);
    PID_Reset(c->pid);
    Motor_Set(c->motor, 0); c->tel_ready = 0;
    CRIT_EXIT();
    reply(c->comm, cmd, id, NULL);
  }
  else if (!strcmp(cmd, "PAUSE")) {                        /* giam toc theo amax ve diem dung, giu nguyen dich cu */
    CRIT_ENTER();
    if (c->en && c->busy && !c->paused) {
      double v = (double)c->trap->vel;
      c->pause_goal = c->trap->pos + v * fabs(v) / (2.0 * (double)c->trap->amax);
      c->paused = 1;
    }
    CRIT_EXIT();
    reply(c->comm, cmd, id, NULL);
  }
  else if (!strcmp(cmd, "RESUME")) {
    CRIT_ENTER();
    if (c->paused) { c->paused = 0; c->settle_cnt = 0; c->busy = 1; }
    CRIT_EXIT();
    reply(c->comm, cmd, id, NULL);
  }
  else if (!strcmp(cmd, "CLEAR")) {                        /* xoa FAULT da chot (khong tu chay lai) */
    c->faulted = 0;
    reply(c->comm, cmd, id, NULL);
  }
  else if (!strcmp(cmd, "LIMIT")) {                        /* LIMIT <min> <max> (counts) */
    if (!parse_l(a1, &n) || !parse_l(a2, &hi)) reply(c->comm, cmd, id, "arg");
    else if (n >= hi || n < -CONTROL_POS_LIMIT || hi > CONTROL_POS_LIMIT) reply(c->comm, cmd, id, "range");
    else {
      CRIT_ENTER();
      c->lim_min = (int32_t)n; c->lim_max = (int32_t)hi;
      if (c->en && !c->homing) {                           /* dich hien tai nam ngoai khoang moi -> kep lai (tru luc HOMING) */
        if (c->goal < c->lim_min)      { c->goal = c->lim_min; c->busy = 1; }
        else if (c->goal > c->lim_max) { c->goal = c->lim_max; c->busy = 1; }
      }
      CRIT_EXIT();
      reply(c->comm, cmd, id, NULL);
    }
  }
  else if (!strcmp(cmd, "PID")) {                          /* PID <kp> <ki> <kd> */
    if (!parse_f(a1, &x) || !parse_f(a2, &y) || !parse_f(a3, &z)) reply(c->comm, cmd, id, "arg");
    else if (x < 0.0f || y < 0.0f || z < 0.0f) reply(c->comm, cmd, id, "range");
    else { CRIT_ENTER(); PID_SetGains(c->pid, x, y, z); CRIT_EXIT(); reply(c->comm, cmd, id, NULL); }
  }
  else if (!strcmp(cmd, "VMAX") || !strcmp(cmd, "AMAX")) { /* counts/s, counts/s^2 */
    if (!parse_l(a1, &n)) reply(c->comm, cmd, id, "arg");
    else if (n <= 0) reply(c->comm, cmd, id, "range");
    else {
      CRIT_ENTER();
      if (cmd[0] == 'V') TrapProfile_SetLimits(c->trap, (float)n, c->trap->amax);
      else               TrapProfile_SetLimits(c->trap, c->trap->vmax, (float)n);
      CRIT_EXIT();
      reply(c->comm, cmd, id, NULL);
    }
  }
  else if (!strcmp(cmd, "TRIP")) {                         /* TRIP <trip> <home_trip> (counts) */
    if (!parse_l(a1, &n) || !parse_l(a2, &hi)) reply(c->comm, cmd, id, "arg");
    else if (n <= 0 || hi <= 0 || n > CONTROL_POS_LIMIT || hi > CONTROL_POS_LIMIT) reply(c->comm, cmd, id, "range");
    else {
      CRIT_ENTER();
      c->err_trip = (int32_t)n; c->homing_trip = (int32_t)hi;
      CRIT_EXIT();
      reply(c->comm, cmd, id, NULL);
    }
  }
  else if (!strcmp(cmd, "HPOS")) {                        /* HPOS <counts>: vi tri home (ap dung tu lan HOMING ke tiep) */
    if (!parse_l(a1, &n)) reply(c->comm, cmd, id, "arg");
    else if (n < -CONTROL_POS_LIMIT || n > CONTROL_POS_LIMIT) reply(c->comm, cmd, id, "range");
    else { c->home_pos = (int32_t)n; reply(c->comm, cmd, id, NULL); }
  }
  else if (!strcmp(cmd, "DB")) {                          /* vung chet +-n counts */
    if (!parse_l(a1, &n)) reply(c->comm, cmd, id, "arg");
    else if (n < 0 || n > 100000L) reply(c->comm, cmd, id, "range");
    else { c->deadband = (int32_t)n; reply(c->comm, cmd, id, NULL); }
  }
  else reply(c->comm, "?", id, "unknown");
}

/* ================= Nhieu dong co ================= */
void ControlSet_Init(ControlSet_t *s, Comm_t *comm)
{
  memset(s, 0, sizeof *s);
  s->comm = comm;
  s->sel = 0xFF;                                           /* chua chon dong co nao: khong gui telemetry T */
}

void ControlSet_SetGripper(ControlSet_t *s, Gripper_t *g)
{
  s->grip = g;
}

void ControlSet_Tick(ControlSet_t *s)
{
  for (int i = 0; i < CONTROL_COUNT; i++) Control_Tick(&s->m[i]);
}

/* Dong trang thai 4 dong co: S <ms> (st goal sp pos) x4 -- PC dung de biet "dang chay / da on dinh / loi" */
static void status_poll(ControlSet_t *s)
{
  uint32_t now = HAL_GetTick();
  if (now - s->status_ms < CONTROL_STATUS_MS) return;
  s->status_ms = now;

  char b[192];
  int n = snprintf(b, sizeof b, "S %lu", (unsigned long)now);
  for (int i = 0; i < CONTROL_COUNT; i++) {
    Control_t *c = &s->m[i];
    long st, goal, sp, pos;
    {
      CRIT_ENTER();
      st   = (c->en ? 1 : 0) | (c->paused ? 2 : 0) | (c->busy ? 4 : 0) | (c->faulted ? 8 : 0)
           | (c->homed ? 16 : 0) | (c->homing ? 32 : 0) | ((c->home && HomeSen_Active(c->home)) ? 64 : 0)
           | (c->estop ? 128 : 0);
      goal = (long)c->goal;
      sp   = (long)iround(c->trap->pos);
      pos  = (long)c->enc->pos;
      CRIT_EXIT();
    }
    n += snprintf(b + n, sizeof b - (size_t)n, " %ld %ld %ld %ld", st, goal, sp, pos);
  }
  n += snprintf(b + n, sizeof b - (size_t)n, " %u\n", (unsigned)((s->grip && Gripper_IsOn(s->grip)) ? 1 : 0));
  if (n > 0 && n < (int)sizeof b && Comm_TxFree(s->comm) > n) Comm_Send(s->comm, b, n);   /* day thi bo mau */
}

/* Dung an toan 1 truc khi mat ket noi (goi trong vung gang ngat): truc dang chay / dang PAUSE / dang HOMING thi
   doi dich thanh diem dung theo amax (quang duong phanh = v|v|/2a) -> giam toc em roi GIU vi tri.
   KHONG tat PID (truc van giu vi tri), KHONG xoa homed (moc vi tri van dung), KHONG chot FAULT. */
static void link_lost_stop(Control_t *c)
{
  if (!c->en || !(c->busy || c->paused || c->homing)) return;
  double stop;
  if (c->paused) stop = c->pause_goal;
  else {
    double v = (double)c->trap->vel;
    stop = c->trap->pos + v * fabs(v) / (2.0 * (double)c->trap->amax);
  }
  c->homing = 0;
  c->paused = 0;
  c->goal = iround(stop);
  c->settle_cnt = 0;
  c->busy = 1;
}

static void watchdog_poll(ControlSet_t *s)
{
  if (!s->wdt_ms || s->wdt_tripped) return;
  if (HAL_GetTick() - s->last_rx_ms <= s->wdt_ms) return;
  s->wdt_tripped = 1;
  for (int i = 0; i < CONTROL_COUNT; i++) {
    Control_t *c = &s->m[i];
    CRIT_ENTER();
    link_lost_stop(c);
    CRIT_EXIT();
  }
  Comm_SendStr(s->comm, "LINKLOST\n");      /* xep TRUOC dong S bao busy=0: PC biet day KHONG phai "Step da xong" */
}

void ControlSet_Poll(ControlSet_t *s)
{
  watchdog_poll(s);
  for (int i = 0; i < CONTROL_COUNT; i++) Control_Poll(&s->m[i], i == s->sel);
  status_poll(s);
}

void ControlSet_OnLine(void *ctx, char *line)
{
  ControlSet_t *s = (ControlSet_t *)ctx;
  char *cmd = strtok(line, " ");
  if (!cmd) return;
  char *ids = strtok(NULL, " ");
  char *a1 = strtok(NULL, " "), *a2 = strtok(NULL, " "), *a3 = strtok(NULL, " ");
  long k;

  s->last_rx_ms = HAL_GetTick();                           /* moi dong nhan duoc deu "nuoi" watchdog */
  s->wdt_tripped = 0;

  if (!strcmp(cmd, "PING")) return;                        /* chi de nuoi watchdog, khong tra loi */

  if (!strcmp(cmd, "WDT")) {                               /* WDT <ms>: 0 = tat, 100..60000 = bat */
    char b[24];
    if (!parse_l(ids, &k) || a1 || (k != 0 && (k < 100 || k > 60000))) { Comm_SendStr(s->comm, "ERR WDT ? arg\n"); return; }
    s->wdt_ms = (uint16_t)k;
    snprintf(b, sizeof b, "OK WDT %ld\n", k);
    Comm_SendStr(s->comm, b);
    return;
  }

  if (!strcmp(cmd, "SEL")) {                               /* SEL <so>: chon dong co gui telemetry; SEL 0 = tat */
    if (!parse_l(ids, &k) || k < 0 || k > CONTROL_COUNT) { reply(s->comm, cmd, 0, "id"); return; }
    s->sel = (k == 0) ? 0xFF : (uint8_t)(k - 1);
    if (k == 0) Comm_SendStr(s->comm, "OK SEL 0\n");      /* reply() in id 0 thanh "?" nen gui truc tiep */
    else        reply(s->comm, cmd, (int)k, NULL);
    return;
  }

  if (!strcmp(cmd, "ESTOP")) {                             /* ESTOP <1|0>: 1 = E-STOP (khoa chuyen dong), 0 = RESET (mo khoa + xoa FAULT) */
    char b[24];
    if (!parse_l(ids, &k) || (k != 0 && k != 1) || a1) { Comm_SendStr(s->comm, "ERR ESTOP ? arg\n"); return; }
    for (int i = 0; i < CONTROL_COUNT; i++) {
      Control_t *c = &s->m[i];
      CRIT_ENTER();
      if (k) estop_motor(c);
      else { c->estop = 0; c->faulted = 0; c->fault = 0; }
      CRIT_EXIT();
    }
    snprintf(b, sizeof b, "OK ESTOP %ld\n", k);
    Comm_SendStr(s->comm, b);
    return;
  }

  if (!strcmp(cmd, "GRIP")) {                             /* GRIP <0|1>: khong co so dong co */
    if (s->m[0].estop) { Comm_SendStr(s->comm, "ERR GRIP ? estop\n"); return; }       /* E-STOP: khoa ca kep */
    if (!s->grip) { Comm_SendStr(s->comm, "ERR GRIP ? nogrip\n"); return; }
    if (!parse_l(ids, &k) || (k != 0 && k != 1) || a1) { Comm_SendStr(s->comm, "ERR GRIP ? arg\n"); return; }
    Gripper_Set(s->grip, (uint8_t)k);
    Comm_SendStr(s->comm, k ? "OK GRIP 1\n" : "OK GRIP 0\n");
    return;
  }

  if (!parse_l(ids, &k) || k < 1 || k > CONTROL_COUNT) { reply(s->comm, cmd, 0, "id"); return; }

  exec(&s->m[k - 1], cmd, a1, a2, a3);
}
