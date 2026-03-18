# opencplc/platforms.py

import os, sys, struct
from xaeian import Print, Color as c
from .args import flag

p = Print()

def host_define() -> str:
  if os.name == "nt":
    return "_WIN64" if struct.calcsize("P") * 8 == 64 else "_WIN32"
  return "_GNU_SOURCE"

HAL_DIRS = {
  "stm32g0": ["arm", "stm32", "stm32g0"],
  "stm32wb": ["arm", "stm32", "stm32wb"],
  "host": ["host"],
}

def get_hal_dirs(hal:str) -> list:
  return HAL_DIRS.get(hal, [hal])

CHIPS = {
  "STM32G081": {
    "platform": "STM32", "family": "G0",
    "flash_kB": 128, "ram_kB": 36, "ram_shared_kB": 0,
    "cpu": "cortex-m0plus", "fpu": False,
    "uart": {"nbr": 1, "tx": "PC4", "rx": "PC5", "dma": 4},
    "define": "STM32G081xx", "device": "STM32G081RB",
    "svd": "stm32g081.svd", "hal": "stm32g0",
    "ld": "stm32g0.ld", "openocd": "stm32g0x"
  },
  "STM32G0C1": {
    "platform": "STM32", "family": "G0",
    "flash_kB": 512, "ram_kB": 144, "ram_shared_kB": 0,
    "cpu": "cortex-m0plus", "fpu": False,
    "uart": {"nbr": 1, "tx": "PC4", "rx": "PC5", "dma": 4},
    "define": "STM32G0C1xx", "device": "STM32G0C1RE",
    "svd": "stm32g0c1.svd", "hal": "stm32g0",
    "ld": "stm32g0.ld", "openocd": "stm32g0x"
  },
  "STM32WB55": {
    "platform": "STM32", "family": "WB",
    "flash_kB": 1024, "ram_kB": 192, "ram_shared_kB": 10,
    "cpu": "cortex-m4", "fpu": True,
    "uart": {"nbr": 1, "tx": "PB6", "rx": "PB7", "dma": 4},
    "define": "STM32WB55xx", "device": "STM32WB55RG",
    "svd": "stm32wb55.svd", "hal": "stm32wb",
    "ld": "stm32wb.ld", "openocd": "stm32wbx"
  },
  "HOST": {
    "platform": "Host", "family": "",
    "flash_kB": 0, "ram_kB": 0, "ram_shared_kB": 0,
    "cpu": "native", "fpu": True,
    "uart": {"nbr": 0, "tx": "", "rx": "", "dma": 0},
    "define": host_define(), "device": "Desktop",
    "svd": "", "hal": "host",
    "ld": "", "openocd": ""
  }
}

BOARDS = {
  "Uno":    {"chip": "STM32G0C1", "flash_kB": 492, "ram_kB": 144, "freq_Hz": 59904000},
  "Dio":    {"chip": "STM32G0C1", "flash_kB": 492, "ram_kB": 144, "freq_Hz": 59904000},
  "Aio":    {"chip": "STM32G0C1", "flash_kB": 492, "ram_kB": 144, "freq_Hz": 59904000},
  "Eco":    {"chip": "STM32G081", "flash_kB": 116, "ram_kB": 36,  "freq_Hz": 64000000},
  "Custom": {"chip": None},
}

def parse_chip(name:str) -> dict:
  name_upper = name.upper()
  chip_key = next((k for k in CHIPS if k.upper() == name_upper), None)
  if not chip_key:
    p.err(f"Unknown chip: {c.MAGNTA}{name}{c.END}")
    p.inf(f"Available: {', '.join(CHIPS.keys())}")
    sys.exit(1)
  cfg = CHIPS[chip_key].copy()
  cfg["chip"] = chip_key
  cfg["defines"] = (
    ["HOST", cfg["define"]] if cfg["platform"] == "Host"
    else [cfg["platform"], f"{cfg['platform']}{cfg['family']}", cfg["define"]]
  )
  return cfg

def resolve_chip(chip_arg:str, board_arg:str) -> tuple[dict, str|None]:
  board_lower = board_arg.lower() if board_arg else ""
  chip_lower = chip_arg.lower() if chip_arg else ""
  # Host
  if chip_lower == "host":
    cfg = parse_chip("HOST")
    cfg["freq_Hz"] = 0
    return cfg, None
  # Bare metal
  if not board_arg or board_lower == "none":
    cfg = parse_chip(chip_arg or "STM32G0C1")
    cfg["freq_Hz"] = 16000000
    return cfg, None
  # Chip only
  if chip_arg and not board_arg:
    cfg = parse_chip(chip_arg)
    cfg["freq_Hz"] = 16000000
    return cfg, None
  # Custom board
  if board_lower == "custom":
    if not chip_arg:
      p.err(f"Custom board requires chip {flag.c}")
      sys.exit(1)
    cfg = parse_chip(chip_arg)
    cfg["freq_Hz"] = 64000000
    return cfg, "Custom"
  # OpenCPLC board
  board_key = next((k for k in BOARDS if k.lower() == board_lower), None)
  if not board_key:
    p.err(f"Unknown board: {c.MAGNTA}{board_arg}{c.END}")
    p.inf(f"Available: {', '.join(k for k in BOARDS if k != 'Custom')}, Custom, None")
    sys.exit(1)
  board_cfg = BOARDS[board_key]
  cfg = parse_chip(board_cfg["chip"])
  cfg["flash_kB"] = board_cfg.get("flash_kB", cfg["flash_kB"])
  cfg["ram_kB"] = board_cfg.get("ram_kB", cfg["ram_kB"])
  cfg["freq_Hz"] = board_cfg.get("freq_Hz", 64000000)
  return cfg, board_key