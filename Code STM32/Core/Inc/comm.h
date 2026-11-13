#ifndef COMM_H
#define COMM_H

#include "main.h"

#define COMM_RX_SZ    256      /* bo dem nhan DMA vong */
#define COMM_TXQ_SZ   512      /* hang doi gui (vong) */
#define COMM_LINE_SZ  64       /* do dai toi da 1 dong lenh (gom ky tu ket thuc) */

/* Ham xu ly 1 dong lenh da tach (khong con \r\n). Duoc goi tu Comm_Poll() trong main loop. */
typedef void (*CommLineHandler)(void *ctx, char *line);

/* UART giao tiep dang van ban, moi lenh 1 dong ket thuc bang \n.
   RX: DMA vong, doc theo con tro NDTR. TX: hang doi vong, gui bang DMA. Khong biet gi ve y nghia cua lenh. */
typedef struct {
  UART_HandleTypeDef *huart;
  CommLineHandler     on_line;
  void               *ctx;

  uint8_t   rx_buf[COMM_RX_SZ];
  uint16_t  rx_tail;
  volatile uint8_t rx_restart;                 /* dat boi callback loi UART */
  char      line[COMM_LINE_SZ];
  uint8_t   line_len, line_ovf;

  uint8_t   txq[COMM_TXQ_SZ];
  uint16_t  tx_head;                           /* chi main loop ghi */
  volatile uint16_t tx_tail, tx_len;           /* tx_tail do callback DMA xong cap nhat */
  volatile uint8_t  tx_busy;
} Comm_t;

/* Bat nhan DMA vong tren huart */
void Comm_Init(Comm_t *c, UART_HandleTypeDef *huart, CommLineHandler on_line, void *ctx);

/* Goi trong main loop: tach dong tu RX roi goi on_line; day hang doi TX ra UART */
void Comm_Poll(Comm_t *c);

/* Dua vao hang doi gui (chi goi tu main loop). Tra ve 1 neu du cho, 0 neu day (bo ca thong diep) */
int  Comm_Send(Comm_t *c, const char *s, int n);
int  Comm_SendStr(Comm_t *c, const char *s);
int  Comm_TxFree(const Comm_t *c);

/* Goi tu HAL_UART_TxCpltCallback / HAL_UART_ErrorCallback */
void Comm_TxCplt(Comm_t *c, UART_HandleTypeDef *huart);
void Comm_Error(Comm_t *c, UART_HandleTypeDef *huart);

#endif
