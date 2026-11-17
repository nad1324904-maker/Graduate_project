#include "home_sen.h"
#include <string.h>

/* Bat clock cho port bat ky, de doi chan cam bien chi can sua trong main.c (khong can vao CubeMX) */
static void gpio_clk_enable(GPIO_TypeDef *p)
{
  if      (p == GPIOA) { __HAL_RCC_GPIOA_CLK_ENABLE(); }
  else if (p == GPIOB) { __HAL_RCC_GPIOB_CLK_ENABLE(); }
  else if (p == GPIOC) { __HAL_RCC_GPIOC_CLK_ENABLE(); }
  else if (p == GPIOD) { __HAL_RCC_GPIOD_CLK_ENABLE(); }
  else if (p == GPIOE) { __HAL_RCC_GPIOE_CLK_ENABLE(); }
#ifdef GPIOF
  else if (p == GPIOF) { __HAL_RCC_GPIOF_CLK_ENABLE(); }
#endif
#ifdef GPIOG
  else if (p == GPIOG) { __HAL_RCC_GPIOG_CLK_ENABLE(); }
#endif
#ifdef GPIOH
  else if (p == GPIOH) { __HAL_RCC_GPIOH_CLK_ENABLE(); }
#endif
#ifdef GPIOI
  else if (p == GPIOI) { __HAL_RCC_GPIOI_CLK_ENABLE(); }
#endif
}

void HomeSen_Init(HomeSen_t *h, GPIO_TypeDef *port, uint16_t pin,
                  uint8_t speed_pct, int8_t dir, uint32_t timeout_ms)
{
  memset((void *)h, 0, sizeof *h);
  h->port = port;
  h->pin = pin;
  h->speed_pct = (speed_pct < 1) ? 1 : (speed_pct > 100) ? 100 : speed_pct;
  h->dir = (dir < 0) ? -1 : +1;
  h->timeout_ms = timeout_ms;

  gpio_clk_enable(port);
  GPIO_InitTypeDef g = {0};
  g.Pin = pin;
  g.Mode = GPIO_MODE_INPUT;
  g.Pull = HOMESEN_PULL;
  HAL_GPIO_Init(port, &g);
}

void HomeSen_Update(HomeSen_t *h)
{
  if (HAL_GPIO_ReadPin(h->port, h->pin) == HOMESEN_ACTIVE_LEVEL) {
    if (h->cnt < HOMESEN_DEBOUNCE_MS) h->cnt++;
    if (h->cnt >= HOMESEN_DEBOUNCE_MS) h->active = 1;      /* cham: can du HOMESEN_DEBOUNCE_MS mau lien tiep */
  } else {
    h->cnt = 0;                                            /* nha: bo ngay */
    h->active = 0;
  }
}
