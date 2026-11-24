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
  "stm32c5": ["arm", "stm32", "stm32c5"],
  "stm32g0": ["arm", "stm32", "stm32g0"],
  "stm32g4": ["arm", "stm32", "stm32g4"],
  "stm32h7": ["arm", "stm32", "stm32h7"],
  "stm32wb": ["arm", "stm32", "stm32wb"],
  "host": ["host"],
}

def get_hal_dirs(hal:str) -> list[str]:
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
  fpu: str         # `-mfpu` of the core, "" without an FPU
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
  # RAM the image runs in; its first 16 bytes hold the report of the bootloader
  ram_base: int = 0x20000000
  # Image header past the vector table, `BOOT_HEADER` of Core
  header_offset: int = 0x200
  # Clock a project without a board starts with
  freq_Hz: int = 16000000

  @property
  def defines(self) -> list[str]:
    """Compiler defines of the chip: platform, family and part, or `HOST` and the host's own."""
    if self.platform == "Host": return ["HOST", self.define]
    return [self.platform, f"{self.platform}{self.family}", self.define]

# Bootloader owns `boot_kB` at the start of flash: its code and one page as the mailbox.
# The `key` bootloader owns `boot_key_kB`, its keys and the signature check in its code.
# Both sizes place the slots, so a change takes a new bootloader on every board.
# 12kB on G0 and G4: `plain` code with its mailbox on PDB outgrows the 6kB of an 8kB region.
# `dev_id` is `DEV_ID` of the chip, the bootloader matches it against the image header.
# A project behind the bootloader halves the rest of `PRO_FLASH_kB` into two slots.
CHIPS = {chip.name: chip for chip in (
  Chip(
    name="STM32G081", platform="STM32", family="G0",
    flash_kB=128, flash_max_kB=128, ram_kB=36,
    cpu="cortex-m0plus", fpu="",
    uart={"nbr": 1, "tx": "PC4", "rx": "PC5", "dma": 4},
    led={"port": "GPIOA", "pin": 5, "name": "green `LD2` of Nucleo-G071RB"},
    define="STM32G081xx", device="STM32G081RB",
    svd="stm32g081.svd", hal="stm32g0",
    ld="stm32.ld", openocd="stm32g0x",
    erase="stm32g0x mass_erase 0",
    page_kB=2, boot_kB=12, boot_key_kB=32, dev_id=0x460,
  ),
  Chip(
    name="STM32G0C1", platform="STM32", family="G0",
    flash_kB=512, flash_max_kB=512, ram_kB=144,
    cpu="cortex-m0plus", fpu="",
    uart={"nbr": 1, "tx": "PC4", "rx": "PC5", "dma": 4},
    led={"port": "GPIOA", "pin": 5, "name": "green `LD2` of Nucleo-G0B1RE"},
    define="STM32G0C1xx", device="STM32G0C1RE",
    svd="stm32g0C1.svd", hal="stm32g0",
    ld="stm32.ld", openocd="stm32g0x",
    erase="stm32g0x mass_erase 0",
    page_kB=2, boot_kB=12, boot_key_kB=32, dev_id=0x467,
  ),
  Chip(
    name="STM32G474", platform="STM32", family="G4",
    # SRAM1, SRAM2 and CCM SRAM aliased behind them lie in one run of 128kB from 0x20000000.
    # Two banks of 2kB pages, `DBANK` as from the factory: Core erases no 4kB page of one bank.
    flash_kB=512, flash_max_kB=512, ram_kB=128,
    cpu="cortex-m4", fpu="fpv4-sp-d16",
    # USART2 reaches USB through ST-Link on PA2/PA3, the pins Nucleo wires for LPUART1
    uart={"nbr": 2, "tx": "PA2", "rx": "PA3", "dma": 4},
    led={"port": "GPIOA", "pin": 5, "name": "green `LD2` of Nucleo-G474RE"},
    define="STM32G474xx", device="STM32G474RE",
    svd="stm32g474.svd", hal="stm32g4",
    ld="stm32.ld", openocd="stm32g4x",
    erase="stm32g4x mass_erase 0",
    page_kB=2, boot_kB=12, boot_key_kB=32, dev_id=0x469,
  ),
  Chip(
    name="STM32WB55", platform="STM32", family="WB",
    # Of 1024kB CPU1 owns what lies below the wireless stack, installed by `make stack`.
    # Stack sits at 0x080D0000: SFSA 0xD0 is 208 pages of 4kB, so CPU1 gets 832kB.
    flash_kB=832, flash_max_kB=1024, ram_kB=192,
    cpu="cortex-m4", fpu="fpv4-sp-d16",
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
    name="STM32H743", platform="STM32", family="H7",
    # Image RAM is AXI SRAM at 0x24000000, which DMA1 and DMA2 reach, DTCM left aside.
    # Two banks of 1MB in 128kB sectors: one holds the bootloader, the next one its mailbox.
    # 150 interrupts take the vector table to 0x298 bytes, so the image header stands at 0x400.
    flash_kB=2048, flash_max_kB=2048, ram_kB=512, ram_base=0x24000000,
    cpu="cortex-m7", fpu="fpv5-d16", freq_Hz=64000000,
    uart={"nbr": 3, "tx": "PD8", "rx": "PD9", "dma": 4},
    led={"port": "GPIOB", "pin": 0, "name": "green `LD1` of Nucleo-H743ZI"},
    define="STM32H743xx", device="STM32H743ZI",
    svd="stm32h743.svd", hal="stm32h7",
    ld="stm32.ld", openocd="stm32h7x_dual_bank",
    erase="stm32h7x mass_erase 0; stm32h7x mass_erase 1",
    page_kB=128, boot_kB=256, boot_key_kB=256, dev_id=0x450, header_offset=0x400,
  ),
  Chip(
    name="STM32C562", platform="STM32", family="C5",
    # SRAM1 and SRAM2 lie in one run of 128kB from 0x20000000.
    # Two banks of 256kB in 8kB pages, flash guarded by product state rather than RDP.
    # After reset HSI of 144MHz runs it divided by 3.
    flash_kB=512, flash_max_kB=512, ram_kB=128,
    cpu="cortex-m33", fpu="fpv5-sp-d16", freq_Hz=48000000,
    uart={"nbr": 2, "tx": "PA2", "rx": "PA3", "dma": 4},
    led={"port": "GPIOA", "pin": 5, "name": "green `LD1` of Nucleo-C562RE"},
    define="STM32C562xx", device="STM32C562RE",
    svd="stm32c562.svd", hal="stm32c5",
    ld="stm32.ld", openocd="stm32c5x",
    erase="stm32c5x mass_erase 0",
    page_kB=8, boot_kB=16, boot_key_kB=32, dev_id=0x44E,
  ),
  Chip(
    name="HOST", platform="Host", family="",
    flash_kB=0, flash_max_kB=0, ram_kB=0,
    cpu="native", fpu="",
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
