#include <vrts.h>
#include <sys.h>
#include <rtc.h>
#include <log.h>
#include "main.h"

//----------------------------------------------------------------------------------------- dbg

UART_t dbg_uart = {
  .reg = USART${UART_NBR},
  .tx = UART${UART_NBR}_TX_${UART_TX},
  .rx = UART${UART_NBR}_RX_${UART_RX},
  .dma = DMA_CH${UART_DMA},
  .irq_priority = IRQ_Priority_Low,
  .UART_115200
};

//---------------------------------------------------------------------------------=------- app

GPIO_t led = { // Nucleo LED
  .port = GPIOA,
  .pin = 5,
  .mode = GPIO_Mode_Output
}; 

void loop(void)
{
  GPIO_Init(&led); // Initialize LED
  while(1) {
    GPIO_Tgl(&led); // Toggle LED state
    LOG_Info("Do nothing"); // Print message in loop
    delay(1000); // Wait 1s
  }
}

//---------------------------------------------------------------------------------------- main

stack(stack_dbg, 256); // Memory stack for debugger thread (logs + bash)
stack(stack_loop, 256); // Memory stack for loop function

int main(void)
{
  sys_init(); // Configure system clock, systick and heap 
  RTC_Init(); // Enable real-time clock (RTC)
  DBG_Init(&dbg_uart); // Initialize debugger (logs + bash)
  DBG_Enter();
  LOG_Info("OpenCPLC framework version: " ANSI_VIOLET "%s" ANSI_END, PRO_VERSION);
  LOG_Info("Build: %s %s", __DATE__, __TIME__);
  LOG_Info("Target MCU: " ANSI_PINK "${CHIP}" ANSI_END);
  thread(DBG_Loop, stack_dbg); // Add debugger thread (logs + bash)
  thread(loop, stack_loop); // Add loop function as thread
  vrts_init(); // Start VRTS thread switching system
  while(1); // Program should never reach this point
}
