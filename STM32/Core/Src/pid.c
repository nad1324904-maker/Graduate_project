#include "pid.h"

void PID_Init(PID_t *p, float kp, float ki, float kd, float out_limit)
{
  p->kp = kp; p->ki = ki; p->kd = kd;
  p->out_limit = out_limit;
  p->integ = 0.0f;
}

void PID_SetGains(PID_t *p, float kp, float ki, float kd)
{
  p->kp = kp; p->ki = ki; p->kd = kd;
  p->integ = 0.0f;
}

void PID_Reset(PID_t *p)
{
  p->integ = 0.0f;
}

float PID_Update(PID_t *p, float err, float meas_vel, float dt)
{
  p->integ += err * dt;
  if (p->ki > 0.0f) {                              /* chong bao hoa tich phan */
    float im = p->out_limit / p->ki;
    if (p->integ > im) p->integ = im; else if (p->integ < -im) p->integ = -im;
  }
  float u = p->kp * err + p->ki * p->integ - p->kd * meas_vel;
  if (u > p->out_limit) u = p->out_limit; else if (u < -p->out_limit) u = -p->out_limit;
  return u;
}
