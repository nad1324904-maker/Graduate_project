#ifndef TRAP_PROFILE_H
#define TRAP_PROFILE_H

/* Quy dao van toc hinh thang tinh ONLINE moi chu ky: toc do dat bam duong phanh sqrt(2*amax*quang_con_lai),
   bi gioi han boi vmax va do doc amax. Doi dich giua chung van muot, quang ngan tu thanh hinh tam giac.
   Don vi: counts, counts/s, counts/s^2. Khong phu thuoc phan cung.
   Vi tri quy dao la double: khi vi tri lon (> 2^23 counts) float chi phan biet duoc tung 1 count nen
   buoc nho vel*dt bi lam tron mat, quy dao ket gan dich. */
typedef struct {
  float  vmax, amax;     /* gioi han quy dao (> 0) */
  double pos;            /* vi tri dat (counts) */
  float  vel;            /* toc do dat (counts/s) */
} TrapProfile_t;

void TrapProfile_Init(TrapProfile_t *t, float vmax, float amax);
void TrapProfile_SetLimits(TrapProfile_t *t, float vmax, float amax);
void TrapProfile_Reset(TrapProfile_t *t, double pos);         /* dat quy dao dung yen tai pos */

/* Cap nhat 1 buoc dt (s) ve phia goal. Tra ve 1 khi quy dao da xong (pos == goal va vel == 0) */
int   TrapProfile_Update(TrapProfile_t *t, double goal, float dt);

#endif
