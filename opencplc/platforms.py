# opencplc/platforms.py

"""Chip table: platform, memory, CPU flags, HAL directories and OpenOCD names."""

import os, sys, struct
from xaeian import Print, Color as c

p = Print()

def host_define() -> str:
  """Compiler define of the host platform: _WIN64/_WIN32 or _GNU_SOURCE."""
  if os.name == "nt":
    return "_WIN64" if struct.calcsize("P") * 8 == 64 else "_WIN32"
  return "_GNU_SOURCE"

HAL_DIRS = {
  "stm32g0": ["arm", "stm32", "stm32g0"],
  "stm32wb": ["arm", "stm32", "stm32wb"],
  "host": ["host"],
}

def get_hal_dirs(hal:str) -> list:
  """HAL subdirectories compiled for a chip family, shared layers first."""
  return HAL_DIRS.get(hal, [hal])

CHIPS = {
  "STM32G081": {
    "platform": "STM32", "family": "G0",
    "flash_kB": 128, "ram_kB": 36, "ram_shared_kB": 0,
    "cpu": "cortex-m0plus", "fpu": False,
    "uart": {"nbr": 1, "tx": "PC4", "rx": "PC5", "dma": 4},
    "define": "STM32G081xx", "device": "STM32G081RB",
    "svd": "stm32g081.svd", "hal": "stm32g0",
    "ld": "stm32g0.ld", "openocd": "stm32g0x",
    "erase": "stm32g0x mass_erase 0"
  },
  "STM32G0C1": {
    "platform": "STM32", "family": "G0",
    "flash_kB": 512, "ram_kB": 144, "ram_shared_kB": 0,
    "cpu": "cortex-m0plus", "fpu": False,
    "uart": {"nbr": 1, "tx": "PC4", "rx": "PC5", "dma": 4},
    "define": "STM32G0C1xx", "device": "STM32G0C1RE",
    "svd": "stm32g0c1.svd", "hal": "stm32g0",
    "ld": "stm32g0.ld", "openocd": "stm32g0x",
    "erase": "stm32g0x mass_erase 0"
  },
  "STM32WB55": {
    "platform": "STM32", "family": "WB",
    "flash_kB": 1024, "ram_kB": 192, "ram_shared_kB": 10,
    "cpu": "cortex-m4", "fpu": True,
    "uart": {"nbr": 1, "tx": "PB6", "rx": "PB7", "dma": 4},
    "define": "STM32WB55xx", "device": "STM32WB55RG",
    "svd": "stm32wb55.svd", "hal": "stm32wb",
    "ld": "stm32wb.ld", "openocd": "stm32wbx",
    "erase": "stm32wbx mass_erase 0"
  },
  "HOST": {
    "platform": "Host", "family": "",
    "flash_kB": 0, "ram_kB": 0, "ram_shared_kB": 0,
    "cpu": "native", "fpu": True,
    "uart": {"nbr": 0, "tx": "", "rx": "", "dma": 0},
    "define": host_define(), "device": "Desktop",
    "svd": "", "hal": "host",
    "ld": "", "openocd": "", "erase": ""
  }
}

def parse_chip(name:str) -> dict:
  """Chip table entry with its compiler defines; an unknown chip exits."""
  name_upper = name.upper()
  chip_key = next((k for k in CHIPS if k.upper() == name_upper), None)
  if not chip_key:
    p.err(f"Unknown chip: {c.MAGNTA}{name}{c.END}")
    p.inf(f"Available: {', '.join(f'{c.PINK}{k}{c.END}' for k in CHIPS)}")
    sys.exit(1)
  cfg = CHIPS[chip_key].copy()
  cfg["chip"] = chip_key
  cfg["defines"] = (
    ["HOST", cfg["define"]] if cfg["platform"] == "Host"
    else [cfg["platform"], f"{cfg['platform']}{cfg['family']}", cfg["define"]]
  )
  return cfg
