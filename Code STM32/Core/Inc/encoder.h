#ifndef ENCODER_H
#define ENCODER_H

#include "main.h"

#define ENCODER_RATE_HZ       1000     /* tan so goi Encoder_Update (moi 1 ms) */
#define ENCODER_VEL_WINDOW    20       /* cua so tinh toc do: 20 mau = 20 ms */
#define ENCODER_VFILT_ALPHA   0.1f     /* he so loc nhe toc do dung cho thanh phan D */

/* Encoder x4 doc bang timer 16 bit o che do encoder. Cong don thanh vi tri 32 bit. */
typedef struct {
  TIM_HandleTypeDef *htim;             /* timer encoder (vd htim3) */
  int8_t             sign;             /* +1 / -1: doi chieu dem ma khong phai doi day A/B */
  uint16_t           last;             /* gia tri counter lan doc truoc */
  volatile int32_t   pos;              /* vi tri (counts) */
  int32_t            vel;              /* toc do (counts/s), trung binh cua so ENCODER_VEL_WINDOW */
  float              vfilt;            /* toc do (counts/s) da loc nhe, dung cho thanh phan D */
  int32_t            win[ENCODER_VEL_WINDOW], wsum;
  uint8_t            widx;
} Encoder_t;

/* Xoa trang thai (vi tri = 0), bat timer encoder */
void Encoder_Init(Encoder_t *e, TIM_HandleTypeDef *htim, int8_t sign);

/* Goi dung moi 1 ms (trong ngat): cap nhat pos, vel, vfilt */
void Encoder_Update(Encoder_t *e);

#endif
