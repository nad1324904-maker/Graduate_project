#ifndef PID_H
#define PID_H

/* PID vi tri. Sai so don vi counts, dau ra la duty PWM co dau (gioi han +-out_limit).
   Thanh phan D lay theo TOC DO DO DUOC (khong lay theo sai so) nen khong bi "da" khi doi dich.
   Tich phan co gioi han chong bao hoa. Khong phu thuoc phan cung. */
typedef struct {
  float kp, ki, kd;
  float out_limit;       /* |dau ra| toi da */
  float integ;           /* tich phan sai so (counts*s) */
} PID_t;

void  PID_Init(PID_t *p, float kp, float ki, float kd, float out_limit);
void  PID_SetGains(PID_t *p, float kp, float ki, float kd);   /* doi he so -> xoa tich phan */
void  PID_Reset(PID_t *p);                                    /* xoa tich phan */

/* err: sai so (counts); meas_vel: toc do do duoc (counts/s); dt: chu ky (s). Tra ve dau ra da gioi han */
float PID_Update(PID_t *p, float err, float meas_vel, float dt);

#endif
