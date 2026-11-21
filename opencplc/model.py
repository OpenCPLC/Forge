# opencplc/model.py

"""
Data shapes the modules hand to each other.

`Config` is what `configure` reads: flags of a new project, or main.h and boot.h of one
under the flags of its load.
`Project` is what `resolve_project()` makes of it: the model every generator,
`-i`, `--program` and `--lock` read from.
"""

from dataclasses import dataclass, field
from .config import OPT_DEFAULT, LOG_LEVEL_DEFAULT
from .platforms import Chip
from .boards import Board

@dataclass
class Hardware:
  """Chip and board a project builds for, with the memory and clock it gets there."""
  chip: Chip
  board: Board|None  # `None` without a board
  plc: bool          # PLC layer compiled in
  flash_kB: int      # flash region of the project, `PRO_FLASH_kB`
  ram_kB: int
  freq_Hz: int       # clock the project starts with, `SYS_CLOCK_FREQ`

  @property
  def board_title(self) -> str:
    """Board name as C and messages spell it, "" without a board."""
    return self.board.title if self.board else ""

@dataclass
class Config(Hardware):
  """Hardware with the settings of the project on it."""
  name: str
  pro_ver: str          # version of Core `main.h` pins, or the Core a project lies in
  fw_ver: str           # version of Core that builds it
  opt_level: str = OPT_DEFAULT
  log_level: str = LOG_LEVEL_DEFAULT
  boot: bool = False    # image behind the bootloader: main.h includes boot.h, or --boot adds it
  # --boot of this load adds the bootloader: to a new project, or to a main.h lacking it
  boot_new: bool = False
  boot_keys: str = ""   # `BOOT_KEYS` of boot.h, "" for a `plain` bootloader
  signing_key: int = 0  # `PRO_SIGNING_KEY`, the key `make dist` signs with
  project_drivers: list[str] = field(default_factory=list)
  load_flags: str = ""  # -f, -b and -c of the load, which the reloads of make keep
  # `#define` values the flags of the load write into main.h, as written there
  settings: dict[str, str] = field(default_factory=dict)
  stlink: str = ""      # ST-Link bound to the project in opencplc.json

  @property
  def drivers(self) -> list[str]:
    """Core drivers that compile: those of the board, then those of `PRO_DRIVERS`."""
    board_drivers = self.board.drivers if self.board else []
    return list(dict.fromkeys(board_drivers + self.project_drivers))

@dataclass
class Project:
  """Fully resolved project model."""
  # Identity
  name: str     # "firm/app", "opencplc/develop/.tests/g081" in a Core, "D:/repos/app" outside
  pro_dir: str  # source directory, workspace-relative or absolute outside it
  target: str   # artifact base name, "tests-g081" in a Core

  # Core
  pro_ver: str   # version of Core `main.h` pins, or the Core a project lies in
  core_ref: str  # version of Core used for this build
  core_dir: str  # workspace-relative Core directory

  # Hardware
  platform: str     # "STM32" | "Host"
  chip: str
  board: str|None   # board directory name, `None` without a board
  board_title: str  # board name for generated code and messages, "" without a board
  plc: bool         # PLC layer compiled in
  family: str
  hal: str
  define: str
  cpu: str
  device: str
  svd: str

  # Build configuration
  flash_kB: int  # `PRO_FLASH_kB`, the flash region of the project
  image_kB: int  # what the image may take: the region, or its slot under the bootloader
  ram_kB: int
  freq_Hz: int
  opt_level: str
  log_level: str
  defines: list[str]
  mcu_flags: str

  # Sources and includes, sorted, workspace-relative or absolute outside it
  core_c_sources: list[str]
  core_asm_sources: list[str]
  project_c_sources: list[str]
  project_asm_sources: list[str]
  include_dirs: list[str]
  project_dirs: list[str] # project root and every dir holding project sources or headers

  # Flash and debug
  linker: str        # linker template key, "" for HOST
  openocd_target: str
  erase_command: str
  stack_script: str  # script of Core that flashes the radio stack, "" when the chip has none
  boot: bool         # image runs under the bootloader, linked into the application slot
  flash_origin: int  # address the image is linked at
  boot_keys: str     # `BOOT_KEYS` as written, "" for a `plain` bootloader
  signing_key: int   # `PRO_SIGNING_KEY`, the number of the key `dist` signs with
  stlink: str
  build_dir: str

  # Bootloader of Core compiled under the image, all empty without one
  boot_kB: int                  # its code region, the mailbox page left out
  boot_c_sources: list[str]
  boot_asm_sources: list[str]
  boot_include_dirs: list[str]  # `.boot/` of Core first, then the project for its `boot.h`
  boot_defines: list[str]

  # Tests: `.c` programs of `test_dir` built for this computer against Core in test mode
  test_dir: str  # `.tests/` of the project, the folder of the Core itself
  tests: bool    # `test_dir` holds a program, so an STM32 project needs MinGW too
  test_core_sources: list[str]
  test_include_dirs: list[str]
  test_defines: list[str]
  # Device drivers selected by the board and by `PRO_DRIVERS`
  board_drivers: list[str] = field(default_factory=list)
  project_drivers: list[str] = field(default_factory=list)
  # -f, -b and -c of the load, which main.h does not hold and the reloads of make keep
  load_flags: str = ""
