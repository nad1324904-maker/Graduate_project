#ifndef MOTOR_H
#define MOTOR_H

#include "main.h"

/* Dong co 1 chieu dieu khien bang BTS7960: RPWM (chay thuan), LPWM (chay nghich),
   R_EN va L_EN noi chung 1 chan GPIO. RPWM va LPWM co the nam tren 2 timer khac nhau.
   Phanh = ca hai kenh PWM bang 0 (2 MOSFET low-side cung bat). */
typedef struct {
  TIM_HandleTypeDef *htim_fwd;             /* timer PWM cua RPWM (vd htim12) */
  TIM_HandleTypeDef *htim_rev;             /* timer PWM cua LPWM (vd htim13) */
  uint32_t           ch_fwd, ch_rev;       /* TIM_CHANNEL_x cua RPWM va LPWM */
  GPIO_TypeDef      *en_port;  uint16_t en_pin;    /* R_EN = L_EN */
  int32_t            pwm_limit;            /* duty toi da (<= ARR) */
} Motor_t;

/* Luu cau hinh, bat 2 kenh PWM o duty 0 (phanh), bat EN = HIGH va giu luon */
void Motor_Init(Motor_t *m, TIM_HandleTypeDef *htim_fwd, uint32_t ch_fwd,
                TIM_HandleTypeDef *htim_rev, uint32_t ch_rev,
                GPIO_TypeDef *en_port, uint16_t en_pin, int32_t pwm_limit);

/* duty > 0: RPWM (thuan); duty < 0: LPWM (nghich); duty = 0: phanh. Tu gioi han theo pwm_limit */
void Motor_Set(Motor_t *m, int32_t duty);

#endif
