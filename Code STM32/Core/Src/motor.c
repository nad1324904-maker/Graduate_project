#include "motor.h"

void Motor_Init(Motor_t *m, TIM_HandleTypeDef *htim_fwd, uint32_t ch_fwd,
                TIM_HandleTypeDef *htim_rev, uint32_t ch_rev,
                GPIO_TypeDef *en_port, uint16_t en_pin, int32_t pwm_limit)
{
  m->htim_fwd = htim_fwd; m->ch_fwd = ch_fwd;
  m->htim_rev = htim_rev; m->ch_rev = ch_rev;
  m->en_port = en_port;   m->en_pin = en_pin;
  m->pwm_limit = pwm_limit;

  __HAL_TIM_SET_COMPARE(htim_fwd, ch_fwd, 0);
  __HAL_TIM_SET_COMPARE(htim_rev, ch_rev, 0);
  HAL_TIM_PWM_Start(htim_fwd, ch_fwd);
  HAL_TIM_PWM_Start(htim_rev, ch_rev);
  HAL_GPIO_WritePin(en_port, en_pin, GPIO_PIN_SET);        /* EN = HIGH ngay khi khoi dong va giu luon */
}

void Motor_Set(Motor_t *m, int32_t duty)
{
  if (duty > m->pwm_limit)  duty = m->pwm_limit;
  if (duty < -m->pwm_limit) duty = -m->pwm_limit;
  __HAL_TIM_SET_COMPARE(m->htim_fwd, m->ch_fwd, duty > 0 ? duty : 0);
  __HAL_TIM_SET_COMPARE(m->htim_rev, m->ch_rev, duty < 0 ? -duty : 0);
}
