#include <vrts.h>
#include <rtc.h>
#include <log.h>
#include "main.h"

//------------------------------------------------------------------------------------------------- dbg

UART_t dbg_uart = {
  .UART_115200,
  .timeout = 50
};

//------------------------------------------------------------------------------------------------- app

void loop(void)
{
  while(1) {
    LOG_Info("Do nothing"); // Print message in loop
    delay(1000); // Wait 1s
  }
}

//------------------------------------------------------------------------------------------------- main

stack(stack_dbg, 256); // Memory stack for debugger thread (logs + bash)
stack(stack_loop, 256); // Memory stack for loop function

int main(void)
{
  sys_init(); // Configure heap and disable CTRL+C 
  RTC_Init(); // Enable real-time clock (RTC)
  DBG_Init(&dbg_uart); // Initialize debugger (logs + bash)
  DBG_Enter();
  LOG_Info("OpenCPLC framework version: " ANSI_VIOLET "%s" ANSI_END, PRO_VERSION);
  LOG_Info("Build: %s %s", __DATE__, __TIME__);
  LOG_Info("Host platform: " ANSI_PINK "${PLATFORM}" ANSI_END);
  thread(DBG_Loop, stack_dbg); // Add debugger thread (logs + bash)
  thread(loop, stack_loop); // Add loop function as thread
  vrts_init(); // Start VRTS thread switching system
  while(1); // Program should never reach this point
}
