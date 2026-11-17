// ${NAME}/main.c

#include <opencplc.h> // import driver functions

// Application thread
static void loop(void)
{
  while(1) {
    RGB_Set(&RGB, RGB_Red); // set status LED to red
    delay(1000); // wait 1s
    RGB_Set(&RGB, RGB_Green); // set status LED to green
    delay(1000); // wait 1s
    RGB_Set(&RGB, RGB_Blue); // set status LED to blue
    delay(1000); // wait 1s
    RGB_Rst(&RGB); // turn off status LED
    delay(1000); // wait 1s
  }
}

stack(stack_plc, 256); // memory stack for PLC thread
stack(stack_dbg, 256); // memory stack for debugger thread (logs + bash)
stack(stack_loop, 1024); // memory stack for `loop` function

int main(void)
{
  thread(PLC_Main, stack_plc); // add PLC driver thread
  thread(DBG_Loop, stack_dbg); // add debugger thread (logs + bash)
  thread(loop, stack_loop); // add `loop` function as thread
  vrts_init(); // start VRTS thread switching system
  while(1); // program should never reach this point
}
