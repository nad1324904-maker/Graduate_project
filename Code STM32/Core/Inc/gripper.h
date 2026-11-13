#ifndef GRIPPER_H
#define GRIPPER_H

#include "main.h"

/* Kep dieu khien bang 1 chan GPIO output (CubeMX: PD9, muc khoi dong LOW = MO).
   Khong co cam bien phan hoi: trang thai = trang thai da ra lenh.
   Kep KHONG tu doi khi STOP / FAULT / mat ket noi -- chi doi bang lenh "GRIP <0|1>". */
typedef struct {
  GPIO_TypeDef     *port;
  uint16_t          pin;
  GPIO_PinState     on_level;      /* muc logic khi kep DONG (ON) */
  volatile uint8_t  on;            /* 1: dang DONG, 0: dang MO */
} Gripper_t;

/* Luu cau hinh va dat kep ve MO (chan da duoc MX_GPIO_Init cau hinh output) */
void Gripper_Init(Gripper_t *g, GPIO_TypeDef *port, uint16_t pin, GPIO_PinState on_level);

/* on = 1: DONG kep, on = 0: MO kep */
void Gripper_Set(Gripper_t *g, uint8_t on);

static inline uint8_t Gripper_IsOn(const Gripper_t *g) { return g->on; }

#endif
