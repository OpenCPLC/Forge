/**
 * @name  Project: ${NAME}
 * @brief Project configuration, read by Forge on every load and by the framework at build.
 *        Edit the values, keep the definitions; make reloads the project after a change.
 * @date  ${DATE}
 */
#ifndef MAIN_H_
#define MAIN_H_

#include <xdef.h>

#define PRO_BOARD_${BOARD}
#define PRO_CHIP_${CHIP}
#define PRO_VERSION "${PRO_VERSION}"
#define PRO_FLASH_kB ${FLASH}
#define PRO_RAM_kB ${RAM}
#define PRO_OPT_LEVEL "${OPT_LEVEL}"
// #define PRO_DRIVERS "shtc3, hd44780"

#endif

// Framework settings this project overrides, applied on every include
#define LOG_LEVEL ${LOG_LEVEL}
#define SYS_CLOCK_FREQ ${FREQ}
