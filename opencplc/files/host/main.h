/**
 * @name  Project: ${NAME}
 * @brief Project configuration for the host platform (Windows/Linux), read by Forge on every load.
 *        Edit the values, keep the definitions; make reloads the project after a change.
 * @date  ${DATE}
 */
#ifndef OPENCPLC_PROJECT_CONFIG_H_
#define OPENCPLC_PROJECT_CONFIG_H_

#include <xdef.h>

#define PRO_CHIP_${CHIP}
#define PRO_VERSION "${PRO_VERSION}"
#define PRO_OPT_LEVEL "${OPT_LEVEL}"

// Framework settings overridden by this project; many modules include this file
#define LOG_LEVEL ${LOG_LEVEL}

#endif
