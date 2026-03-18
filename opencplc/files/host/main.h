/**
 * @name  Project: ${NAME}
 * @brief Project configuration for host platform (Windows/Linux)
 * @date  ${DATE}
 */
#ifndef MAIN_H_
#define MAIN_H_

#include <xdef.h>

#define PRO_CHIP_${CHIP}
#define PRO_VERSION "${PRO_VERSION}"
#define PRO_OPT_LEVEL "${OPT_LEVEL}"

#endif

/**
 * @brief Put here config parameters `#define` that should be overridden.
 * @note  Many libraries include this file, so it must exist even if empty.
 */
#define LOG_LEVEL ${LOG_LEVEL}
