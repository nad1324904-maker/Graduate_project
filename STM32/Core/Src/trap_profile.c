#include "trap_profile.h"
#include <math.h>

void TrapProfile_Init(TrapProfile_t *t, float vmax, float amax)
{
  t->vmax = vmax; t->amax = amax;
  t->pos = 0.0;   t->vel = 0.0f;
}

void TrapProfile_SetLimits(TrapProfile_t *t, float vmax, float amax)
{
  t->vmax = vmax; t->amax = amax;
}

void TrapProfile_Reset(TrapProfile_t *t, double pos)
{
  t->pos = pos; t->vel = 0.0f;
}

int TrapProfile_Update(TrapProfile_t *t, double goal, float dt)
{
  double e  = goal - t->pos;
  float  ef = (float)e;                                                         /* |e| < 2^24 nen chinh xac */
  float vd  = copysignf(fminf(t->vmax, sqrtf(2.0f * t->amax * fabsf(ef))), ef); /* toc do mong muon */
  float lim = t->amax * dt, dv = vd - t->vel;
  t->vel += (dv > lim) ? lim : (dv < -lim) ? -lim : dv;                         /* gioi han gia toc */
  double np = t->pos + (double)t->vel * (double)dt;
  if ((goal - np) * e <= 0.0) { np = goal; t->vel = 0.0f; }                     /* toi dich -> chot */
  t->pos = np;
  return (t->vel == 0.0f && t->pos == goal);
}
