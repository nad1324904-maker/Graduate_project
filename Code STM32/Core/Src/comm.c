#include "comm.h"
#include <string.h>

void Comm_Init(Comm_t *c, UART_HandleTypeDef *huart, CommLineHandler on_line, void *ctx)
{
  memset(c, 0, sizeof *c);
  c->huart = huart;
  c->on_line = on_line;
  c->ctx = ctx;
  HAL_UART_Receive_DMA(huart, c->rx_buf, COMM_RX_SZ);
}

/* ---------- TX: hang doi vong + DMA ---------- */
int Comm_TxFree(const Comm_t *c)
{
  int f = (int)c->tx_tail - (int)c->tx_head - 1;
  return f < 0 ? f + COMM_TXQ_SZ : f;
}

int Comm_Send(Comm_t *c, const char *s, int n)
{
  if (n <= 0 || n > Comm_TxFree(c)) return 0;
  for (int i = 0; i < n; i++) {
    c->txq[c->tx_head] = (uint8_t)s[i];
    c->tx_head = (uint16_t)((c->tx_head + 1) % COMM_TXQ_SZ);
  }
  return 1;
}

int Comm_SendStr(Comm_t *c, const char *s)
{
  return Comm_Send(c, s, (int)strlen(s));
}

static void tx_pump(Comm_t *c)
{
  if (c->tx_busy || c->tx_head == c->tx_tail) return;
  uint16_t n = (c->tx_head > c->tx_tail) ? (uint16_t)(c->tx_head - c->tx_tail)
                                         : (uint16_t)(COMM_TXQ_SZ - c->tx_tail);
  c->tx_len = n;
  c->tx_busy = 1;
  if (HAL_UART_Transmit_DMA(c->huart, &c->txq[c->tx_tail], n) != HAL_OK) c->tx_busy = 0;
}

void Comm_TxCplt(Comm_t *c, UART_HandleTypeDef *huart)
{
  if (huart == c->huart) {
    c->tx_tail = (uint16_t)((c->tx_tail + c->tx_len) % COMM_TXQ_SZ);
    c->tx_busy = 0;
  }
}

void Comm_Error(Comm_t *c, UART_HandleTypeDef *huart)
{
  if (huart == c->huart) c->rx_restart = 1;    /* HAL dung DMA RX khi co loi ORE/FE/NE -> main loop bat lai */
}

/* ---------- RX: DMA vong, doc theo NDTR, tach dong ---------- */
static void rx_poll(Comm_t *c)
{
  if (c->rx_restart) {
    c->rx_restart = 0; c->rx_tail = 0; c->line_len = 0; c->line_ovf = 0;
    HAL_UART_Receive_DMA(c->huart, c->rx_buf, COMM_RX_SZ);
  }
  uint16_t head = (uint16_t)(COMM_RX_SZ - __HAL_DMA_GET_COUNTER(c->huart->hdmarx));   /* NDTR dem lui */
  if (head >= COMM_RX_SZ) head = 0;
  while (c->rx_tail != head) {
    char ch = (char)c->rx_buf[c->rx_tail];
    c->rx_tail = (uint16_t)((c->rx_tail + 1) % COMM_RX_SZ);
    if (ch == '\n') {
      if (c->line_ovf) {
        Comm_SendStr(c, "ERR LINE too long\n");
      } else {
        c->line[c->line_len] = '\0';
        if (c->on_line) c->on_line(c->ctx, c->line);
      }
      c->line_len = 0; c->line_ovf = 0;
    } else if (ch != '\r') {
      if (c->line_len < COMM_LINE_SZ - 1) c->line[c->line_len++] = ch; else c->line_ovf = 1;
    }
  }
}

void Comm_Poll(Comm_t *c)
{
  rx_poll(c);
  tx_pump(c);
}
