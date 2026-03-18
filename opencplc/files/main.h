/**
 * @name  Project: ${NAME}
 * @brief Project configuration. These values are used by Forge when loading project.
 *        They should not be removed, but can be edited. Changing requires running Forge again.
 * @date  ${DATE}
 */
#include <xdef.h>

#ifndef PRO_x
#define PRO_x

#define PRO_BOARD_${BOARD}
#define PRO_CHIP_${CHIP}
#define PRO_VERSION "${PRO_VERSION}"
#define PRO_FLASH_kB ${FLASH}
#define PRO_RAM_kB ${RAM}
#define PRO_OPT_LEVEL "${OPT_LEVEL}"

#endif

/**
 * @brief Put here config parameters `#define` that should be overridden.
 * @note  Many libraries include this file, so it must exist even if empty.
 */
#define LOG_LEVEL ${LOG_LEVEL}
#define SYS_CLOCK_FREQ ${FREQ}
