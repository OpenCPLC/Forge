// ${NAME}/main.c

#include <vrts.h>
#include <sys.h>
#include <rtc.h>
#include <log.h>

#include "main.h"

//--------------------------------------------------------------------------------------------- dbg

static UART_t dbg_uart = {
  .reg = USART${UART_NBR},
  .tx = UART${UART_NBR}_TX_${UART_TX},
  .rx = UART${UART_NBR}_RX_${UART_RX},
  .dma = DMA_CH${UART_DMA},
  .irq_priority = IRQ_Priority_Low,
  .UART_115200
};

//--------------------------------------------------------------------------------------------- app

static GPIO_t led = { // ${LED_NAME}
  .port = ${LED_PORT},
  .pin = ${LED_PIN},
  .mode = GPIO_Mode_Output
};

static void loop(void)
{
  GPIO_Init(&led); // initialize LED
  while(1) {
    GPIO_Tgl(&led); // toggle LED state
    LOG_Info("Do nothing"); // print message in loop
    delay(1000); // wait 1s
  }
}

//-------------------------------------------------------------------------------------------- main

stack(stack_dbg, 256); // memory stack for debugger thread (logs + bash)
stack(stack_loop, 256); // memory stack for `loop` function

int main(void)
{
  sys_init(); // configure system clock, systick and heap
  RTC_Init(); // enable real-time clock (RTC)
  DBG_Init(&dbg_uart); // initialize debugger (logs + bash)
  DBG_Enter();
  LOG_Info("OpenCPLC framework version: " ANSI_VIOLET "%s" ANSI_END, PRO_FRAMEWORK);
  LOG_Info("Build: %s %s", __DATE__, __TIME__);
  LOG_Info("Target MCU: " ANSI_PINK "${CHIP}" ANSI_END);
  thread(DBG_Loop, stack_dbg); // add debugger thread (logs + bash)
  thread(loop, stack_loop); // add `loop` function as thread
  vrts_init(); // start VRTS thread switching system
  while(1); // program should never reach this point
}
