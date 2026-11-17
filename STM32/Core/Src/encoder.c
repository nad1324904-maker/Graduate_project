#include "encoder.h"
#include <string.h>

void Encoder_Init(Encoder_t *e, TIM_HandleTypeDef *htim, int8_t sign)
{
  memset(e, 0, sizeof *e);
  e->htim = htim;
  e->sign = sign;
  HAL_TIM_Encoder_Start(htim, TIM_CHANNEL_ALL);
  e->last = (uint16_t)__HAL_TIM_GET_COUNTER(htim);
}

void Encoder_Update(Encoder_t *e)
{
  /* Timer 16 bit: lay hieu 16 bit roi cong don vao bien 32 bit (dung ca khi counter tran) */
  uint16_t now = (uint16_t)__HAL_TIM_GET_COUNTER(e->htim);
  int32_t  d   = e->sign * (int32_t)(int16_t)(now - e->last);
  e->last = now;
  e->pos += d;

  e->wsum += d - e->win[e->widx];                 /* cua so truot ENCODER_VEL_WINDOW mau */
  e->win[e->widx] = d;
  e->widx = (uint8_t)((e->widx + 1) % ENCODER_VEL_WINDOW);
  e->vel = e->wsum * (ENCODER_RATE_HZ / ENCODER_VEL_WINDOW);                    /* counts/s */
  e->vfilt += ENCODER_VFILT_ALPHA * ((float)d * (float)ENCODER_RATE_HZ - e->vfilt);
}
