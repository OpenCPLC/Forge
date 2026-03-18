#include "${INCLUDE}" // ${INCLUDE_COMMENT}

// Application thread
void loop(void)
{
  while(1) {
    // Set status LED to red
    LED_Set(RGB_Red);
    delay(1000); // Wait 1s
    // Set status LED to green
    LED_Set(RGB_Green);
    delay(1000); // Wait 1s
    // Set status LED to blue
    LED_Set(RGB_Blue);
    delay(1000); // Wait 1s
    // Turn off status LED
    LED_Rst();
    delay(1000); // Wait 1s
  }
}

stack(stack_plc, 256); // Memory stack for PLC thread
stack(stack_dbg, 256); // Memory stack for debugger thread (logs + bash)
stack(stack_loop, 1024); // Memory stack for loop function

int main(void)
{
  thread(PLC_Main, stack_plc); // Add PLC driver thread
  thread(DBG_Loop, stack_dbg); // Add debugger thread (logs + bash)
  thread(loop, stack_loop); // Add loop function as thread
  vrts_init(); // Start VRTS thread switching system
  while(1); // Program should never reach this point
}
