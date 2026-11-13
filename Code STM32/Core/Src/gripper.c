#include "gripper.h"

void Gripper_Init(Gripper_t *g, GPIO_TypeDef *port, uint16_t pin, GPIO_PinState on_level)
{
  g->port = port;
  g->pin = pin;
  g->on_level = on_level;
  Gripper_Set(g, 0);                                       /* khoi dong: MO kep */
}

void Gripper_Set(Gripper_t *g, uint8_t on)
{
  GPIO_PinState off_level = (g->on_level == GPIO_PIN_SET) ? GPIO_PIN_RESET : GPIO_PIN_SET;
  HAL_GPIO_WritePin(g->port, g->pin, on ? g->on_level : off_level);
  g->on = on ? 1 : 0;
}
