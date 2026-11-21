# opencplc/platforms.py

"""Chip table: platform, memory, CPU flags, HAL directories and OpenOCD names."""

import os, sys, struct
from dataclasses import dataclass
from xaeian import Print
from . import utils

p = Print()

def host_define() -> str:
  """Compiler define of the host platform: `_WIN64`/`_WIN32` or `_GNU_SOURCE`."""
  if os.name == "nt": return "_WIN64" if struct.calcsize("P") * 8 == 64 else "_WIN32"
  return "_GNU_SOURCE"

FLASH_BASE = 0x08000000 # main flash of every STM32 in the table

HAL_DIRS = {
  "stm32g0": ["arm", "stm32", "stm32g0"],
  "stm32wb": ["arm", "stm32", "stm32wb"],
  "host": ["host"],
}

def get_hal_dirs(hal:str) -> list:
  """HAL subdirectories compiled for a chip family, shared layers first."""
  return HAL_DIRS.get(hal, [hal])

@dataclass(frozen=True)
class Chip:
  """One row of the chip table."""
  name: str        # canonical key, e.g. "STM32G0C1"
  platform: str    # "STM32" | "Host"
  family: str
  flash_kB: int
  # All flash of the part, the bound of `PRO_FLASH_kB`; `flash_kB` is what a new project gets
  flash_max_kB: int
  ram_kB: int
  cpu: str
  fpu: bool
  uart: dict       # console of a new project: `nbr`, `tx`, `rx`, `dma`
  led: dict        # LED a new bare-metal project blinks: `port`, `pin`, `name`
  define: str
  device: str
  svd: str
  hal: str
  ld: str          # linker template, "" for the host
  openocd: str     # openocd target, "" for the host
  erase: str       # openocd command of `make erase`
  page_kB: int
  boot_kB: int
  boot_key_kB: int
  dev_id: int
  stack: str = ""  # script of Core that installs the radio stack, only a WB has one

  @property
  def defines(self) -> list[str]:
    """Compiler defines of the chip: platform, family and part, or `HOST` and the host's own."""
    if self.platform == "Host": return ["HOST", self.define]
    return [self.platform, f"{self.platform}{self.family}", self.define]

# Bootloader owns `boot_kB` at the start of flash: its code and one page as the mailbox
# The `key` bootloader owns `boot_key_kB`, its keys and the signature check in its code
# Both sizes place the slots, so a change takes a new bootloader on every board
# 12kB on G0: the `plain` code with its mailbox on PDB takes more than the 6kB of an 8kB region
# `dev_id` is `DEV_ID` of the chip, the bootloader matches it against the image header
# A project behind the bootloader halves the rest of `PRO_FLASH_kB` into two slots
CHIPS = {chip.name: chip for chip in (
  Chip(
    name="STM32G081", platform="STM32", family="G0",
    flash_kB=128, flash_max_kB=128, ram_kB=36,
    cpu="cortex-m0plus", fpu=False,
    uart={"nbr": 1, "tx": "PC4", "rx": "PC5", "dma": 4},
    led={"port": "GPIOA", "pin": 5, "name": "green `LD2` of Nucleo-G071RB"},
    define="STM32G081xx", device="STM32G081RB",
    svd="stm32g081.svd", hal="stm32g0",
    ld="stm32g0.ld", openocd="stm32g0x",
    erase="stm32g0x mass_erase 0",
    page_kB=2, boot_kB=12, boot_key_kB=32, dev_id=0x460,
  ),
  Chip(
    name="STM32G0C1", platform="STM32", family="G0",
    flash_kB=512, flash_max_kB=512, ram_kB=144,
    cpu="cortex-m0plus", fpu=False,
    uart={"nbr": 1, "tx": "PC4", "rx": "PC5", "dma": 4},
    led={"port": "GPIOA", "pin": 5, "name": "green `LD2` of Nucleo-G0B1RE"},
    define="STM32G0C1xx", device="STM32G0C1RE",
    svd="stm32g0c1.svd", hal="stm32g0",
    ld="stm32g0.ld", openocd="stm32g0x",
    erase="stm32g0x mass_erase 0",
    page_kB=2, boot_kB=12, boot_key_kB=32, dev_id=0x467,
  ),
  Chip(
    name="STM32WB55", platform="STM32", family="WB",
    # Of 1024kB CPU1 owns what lies below the wireless stack, installed by `make stack`
    # Stack sits at 0x080D0000: SFSA 0xD0 is 208 pages of 4kB, so CPU1 gets 832kB
    flash_kB=832, flash_max_kB=1024, ram_kB=192,
    cpu="cortex-m4", fpu=True,
    uart={"nbr": 1, "tx": "PB6", "rx": "PB7", "dma": 4},
    led={"port": "GPIOB", "pin": 0, "name": "green `LD2` of Nucleo-WB55RG"},
    define="STM32WB55xx", device="STM32WB55RG",
    svd="stm32wb55.svd", hal="stm32wb",
    ld="stm32wb.ld", openocd="stm32wbx",
    # `mass_erase` fails beside the wireless stack, so `make erase` clears CPU1 pages one by one
    erase="flash erase_address 0x08000000 0xD0000", stack="flash_cpu2.sh",
    page_kB=4, boot_kB=16, boot_key_kB=32, dev_id=0x495,
  ),
  Chip(
    name="HOST", platform="Host", family="",
    flash_kB=0, flash_max_kB=0, ram_kB=0,
    cpu="native", fpu=True,
    uart={"nbr": 0, "tx": "", "rx": "", "dma": 0},
    led={"port": "", "pin": 0, "name": ""},
    define=host_define(), device="Desktop",
    svd="", hal="host",
    ld="", openocd="", erase="",
    page_kB=0, boot_kB=0, boot_key_kB=0, dev_id=0,
  ),
)}

def parse_chip(name:str) -> Chip:
  """Chip of the table by name, case aside; an unknown chip exits."""
  chip = next((chip for key, chip in CHIPS.items() if key.upper() == name.upper()), None)
  if chip is None:
    p.err(f"Unknown chip: {utils.color_wrong(name)}")
    p.inf(f"Chips Forge knows: {', '.join(utils.color_chip(k) for k in CHIPS)}")
    sys.exit(1)
  return chip
