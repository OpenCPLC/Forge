// ${NAME}/main.h

/**
 * @name  Project: ${NAME}
 * @brief Project configuration for the host platform, read by Forge on every load.
 *        Edit values, keep definitions; `make` reloads the project after a change.
 * @date  ${DATE}
 */
#ifndef MAIN_H_
#define MAIN_H_

#include <xdef.h>

#define PRO_CHIP_${CHIP}
#define PRO_FRAMEWORK "${PRO_FRAMEWORK}"
#define PRO_OPT_LEVEL "${OPT_LEVEL}"

#endif

// Framework settings this project overrides, applied on every include
#define LOG_LEVEL ${LOG_LEVEL}
