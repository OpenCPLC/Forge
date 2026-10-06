# opencplc/platforms.py

"""Chip table: platform, memory, CPU flags, HAL directories and OpenOCD names."""

import os, sys, struct
from xaeian import Print, Color as c

p = Print()

def host_define() -> str:
  """Compiler define of the host platform: `_WIN64`/`_WIN32` or `_GNU_SOURCE`."""
  if os.name == "nt": return "_WIN64" if struct.calcsize("P") * 8 == 64 else "_WIN32"
  return "_GNU_SOURCE"

HAL_DIRS = {
  "stm32g0": ["arm", "stm32", "stm32g0"],
  "stm32wb": ["arm", "stm32", "stm32wb"],
  "host": ["host"],
}

def get_hal_dirs(hal:str) -> list:
  """HAL subdirectories compiled for a chip family, shared layers first."""
  return HAL_DIRS.get(hal, [hal])

# Bootloader owns `boot_kB` at the start of flash: its code and one page as the mailbox
# The `key` bootloader owns `boot_key_kB`, its key in the last 32B of the code
# Both sizes place the slots of shipped devices, so they never change
# Bootloaders of each family in Core `scr/`, see `boot_stem`
# `dev_id` is `DEV_ID` of the chip, the bootloader matches it against the image header
# `PRO_BOOT true` halves the rest of `PRO_FLASH_kB` into application and staging slots
CHIPS = {
  "STM32G081": {
    "platform": "STM32", "family": "G0",
    "flash_kB": 128, "ram_kB": 36,
    "cpu": "cortex-m0plus", "fpu": False,
    "uart": {"nbr": 1, "tx": "PC4", "rx": "PC5", "dma": 4},
    "led": {"port": "GPIOA", "pin": 5, "name": "Nucleo-G071RB green `LD2`"},
    "define": "STM32G081xx", "device": "STM32G081RB",
    "svd": "stm32g081.svd", "hal": "stm32g0",
    "ld": "stm32g0.ld", "openocd": "stm32g0x",
    "erase": "stm32g0x mass_erase 0",
    "page_kB": 2, "boot_kB": 8, "boot_key_kB": 32, "dev_id": 0x460,
  },
  "STM32G0C1": {
    "platform": "STM32", "family": "G0",
    "flash_kB": 512, "ram_kB": 144,
    "cpu": "cortex-m0plus", "fpu": False,
    "uart": {"nbr": 1, "tx": "PC4", "rx": "PC5", "dma": 4},
    "led": {"port": "GPIOA", "pin": 5, "name": "Nucleo-G0B1RE green `LD2`"},
    "define": "STM32G0C1xx", "device": "STM32G0C1RE",
    "svd": "stm32g0c1.svd", "hal": "stm32g0",
    "ld": "stm32g0.ld", "openocd": "stm32g0x",
    "erase": "stm32g0x mass_erase 0",
    "page_kB": 2, "boot_kB": 8, "boot_key_kB": 32, "dev_id": 0x467,
  },
  "STM32WB55": {
    "platform": "STM32", "family": "WB",
    # Of 1024kB CPU1 owns what lies below the wireless stack, installed by `make stack`
    # Stack sits at 0x080D0000: SFSA 0xD0 is 208 pages of 4kB, so CPU1 gets 832kB
    "flash_kB": 832, "ram_kB": 192,
    "cpu": "cortex-m4", "fpu": True,
    "uart": {"nbr": 1, "tx": "PB6", "rx": "PB7", "dma": 4},
    "led": {"port": "GPIOB", "pin": 0, "name": "Nucleo-WB55RG green `LD2`"},
    "define": "STM32WB55xx", "device": "STM32WB55RG",
    "svd": "stm32wb55.svd", "hal": "stm32wb",
    "ld": "stm32wb.ld", "openocd": "stm32wbx",
    # `mass_erase` fails beside the wireless stack, so `make erase` clears CPU1 pages one by one
    "erase": "flash erase_address 0x08000000 0xD0000", "stack": "flash_cpu2.sh",
    "page_kB": 4, "boot_kB": 16, "boot_key_kB": 32, "dev_id": 0x495,
  },
  "HOST": {
    "platform": "Host", "family": "",
    "flash_kB": 0, "ram_kB": 0,
    "cpu": "native", "fpu": True,
    "uart": {"nbr": 0, "tx": "", "rx": "", "dma": 0},
    "led": {"port": "", "pin": 0, "name": ""},
    "define": host_define(), "device": "Desktop",
    "svd": "", "hal": "host",
    "ld": "", "openocd": "", "erase": "",
    "page_kB": 0, "boot_kB": 0, "boot_key_kB": 0, "dev_id": 0,
  },
}

def boot_stem(hal:str, key:bool) -> str:
  """Bootloader files of a family in Core, Core-relative and without extension."""
  return f"scr/boot_{hal}{'_key' if key else ''}"

def parse_chip(name:str) -> dict:
  """Chip table entry with its compiler defines; an unknown chip exits."""
  name_upper = name.upper()
  chip_key = next((k for k in CHIPS if k.upper() == name_upper), None)
  if not chip_key:
    p.err(f"Unknown chip: {c.MAGNTA}{name}{c.END}")
    p.inf(f"Chips Forge knows: {', '.join(f'{c.PINK}{k}{c.END}' for k in CHIPS)}")
    sys.exit(1)
  cfg = CHIPS[chip_key].copy()
  cfg["chip"] = chip_key
  cfg["defines"] = (
    ["HOST", cfg["define"]] if cfg["platform"] == "Host"
    else [cfg["platform"], f"{cfg['platform']}{cfg['family']}", cfg["define"]]
  )
  return cfg
