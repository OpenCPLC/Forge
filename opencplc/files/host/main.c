// ${NAME}/main.c

#include <vrts.h>
#include <sys.h>
#include <rtc.h>
#include <log.h>

#include "main.h"

#if defined(_WIN32) || defined(_WIN64)
  #define HOST_OS_NAME "Windows"
#else
  #define HOST_OS_NAME "Linux"
#endif

//--------------------------------------------------------------------------------------------- dbg

static UART_t dbg_uart = {
  .UART_115200,
  .timeout = 50
};

//--------------------------------------------------------------------------------------------- app

static void loop(void)
{
  while(1) {
    LOG_Info("Do nothing"); // print message in loop
    delay(1000); // wait 1s
  }
}

//-------------------------------------------------------------------------------------------- main

stack(stack_dbg, 256); // memory stack for debugger thread (logs + bash)
stack(stack_loop, 256); // memory stack for `loop` function

int main(void)
{
  sys_init(); // configure heap and disable CTRL+C
  RTC_Init(); // enable real-time clock (RTC)
  DBG_Init(&dbg_uart); // initialize debugger (logs + bash)
  DBG_Enter();
  LOG_Info("OpenCPLC framework version: " ANSI_VIOLET "%s" ANSI_END, PRO_FRAMEWORK);
  LOG_Info("Build: %s %s", __DATE__, __TIME__);
  LOG_Info("Platform: " ANSI_PINK "${PLATFORM}" ANSI_GREY " (" HOST_OS_NAME ")" ANSI_END);
  thread(DBG_Loop, stack_dbg); // add debugger thread (logs + bash)
  thread(loop, stack_loop); // add `loop` function as thread
  vrts_init(); // start VRTS thread switching system
  while(1); // program should never reach this point
}
