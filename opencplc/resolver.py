# opencplc/resolver.py

"""
Project resolution.

`resolve_project()` walks framework and project trees once and returns a `Project`.
That is the single model every generator and `-i` read from.
Paths in it are workspace-relative and sorted, so identical inputs resolve identically.
Absolute paths appear only while scanning.
"""

import sys
from dataclasses import replace
from xaeian import Print, Color as c, DIR, FILE, PATH
from .config import DIR_TESTS, DIR_BOOT, DIR_BUILD, BOOT_LINE
from .platforms import get_hal_dirs, FLASH_BASE
from .model import Config, Project
from . import utils, __version__

p = Print()

def rel_tree(root:str, ext:str) -> dict[str, list[str]]:
  """folder → files under `root`, both workspace-relative."""
  found = utils.files_list(root, ext)
  return {PATH.local(folder): [PATH.local(f) for f in files] for folder, files in found.items()}

def core_tree(cfg:Config, core_dir:str, ext:str) -> dict[str, list[str]]:
  """
  Core source tree for the selected variant.

  HAL, lib, boards and selected drivers are always in, PLC layer only when asked for.
  Boards and drivers live outside plc/, so a project without that layer can use them too.
  """
  found = {}
  for sub in get_hal_dirs(cfg.chip.hal):
    hal_path = f"{core_dir}/hal/{sub}"
    if DIR.exists(hal_path):
      found.update(rel_tree(hal_path, ext))
  found.update(rel_tree(f"{core_dir}/lib", ext))
  found.update(rel_tree(f"{core_dir}/drv", ext))
  found.update(rel_tree(f"{core_dir}/brd", ext))
  if cfg.plc:
    found.update(rel_tree(f"{core_dir}/plc", ext))
  return found

def other_board(cfg:Config, core_dir:str, folder:str) -> bool:
  """
  Board directories other than the selected one are excluded.

  Boards sit in brd/ at Core root, and under plc/ in versions that kept them there.
  A project on any Core compiles its own board and no other.
  """
  # below brd only, brd itself holds the header all boards share
  roots = (f"{core_dir}/brd/", f"{core_dir}/plc/brd/")
  if not any(folder.startswith(root) for root in roots): return False
  # exact directory, so uno never drags in uno_mini
  return not (cfg.board and PATH.is_under(folder, cfg.board.dir))

def in_drivers(core_dir:str, folder:str) -> bool:
  """`True` for drv of `core_dir` and every folder below it."""
  return PATH.is_under(folder, f"{core_dir}/drv")

def unused_driver(cfg:Config, core_dir:str, folder:str, file:str) -> bool:
  """
  Core drivers compile only when selected by the board or by `PRO_DRIVERS`.

  A driver is named by its file, whatever folder under drv it sits in.
  """
  if not in_drivers(core_dir, folder): return False
  return PATH.stem(file).lower() not in cfg.drivers

def core_sources(cfg:Config, core_dir:str, ext:str) -> list[str]:
  """Core files with `ext` for this variant, sorted and workspace-relative."""
  tree = core_tree(cfg, core_dir, ext)
  return sorted(f for folder, fs in tree.items() if not other_board(cfg, core_dir, folder)
    for f in fs if not unused_driver(cfg, core_dir, folder, f))

def core_includes(cfg:Config, core_dir:str) -> list[str]:
  """Core header directories for this variant, under drv only the selected drivers."""
  tree = core_tree(cfg, core_dir, ".h")
  return sorted(folder for folder, fs in tree.items() if not other_board(cfg, core_dir, folder)
    and any(not unused_driver(cfg, core_dir, folder, f) for f in fs))

def driver_includes(cfg:Config, core_dir:str) -> list[str]:
  """Folders under drv holding a header of a selected driver."""
  return sorted(folder for folder, fs in rel_tree(f"{core_dir}/drv", ".h").items()
    if any(not unused_driver(cfg, core_dir, folder, f) for f in fs))

def available_drivers(core_dir:str) -> list[str]:
  """Core drivers with both .c and .h anywhere under drv."""
  drv = f"{core_dir}/drv"
  names_c = {PATH.stem(f).lower() for fs in rel_tree(drv, ".c").values() for f in fs}
  names_h = {PATH.stem(f).lower() for fs in rel_tree(drv, ".h").values() for f in fs}
  return sorted(names_c & names_h)

def validate_drivers(cfg:Config, core_dir:str):
  """Fail early when a board or `PRO_DRIVERS` names a driver this Core does not ship."""
  if not cfg.drivers or not DIR.exists(f"{core_dir}/drv"): return
  available = available_drivers(core_dir)
  unknown = [n for n in cfg.drivers if n not in available]
  if not unknown: return
  p.err(f"Unknown driver: {c.MAGNTA}{unknown[0]}{c.END}")
  listed = ", ".join(f"{c.TURQUS}{n}{c.END}" for n in available) or f"{c.GREY}none{c.END}"
  p.inf(f"Drivers in this Core: {listed}")
  sys.exit(1)

def forge_version() -> int:
  """Forge version as one number Core compares in `#if`: 0.4.8 → 408, 1.2.10 → 10210."""
  major, minor, patch = (int(n) for n in __version__.split("."))
  return major * 10000 + minor * 100 + patch

def project_target(name:str) -> str:
  """Artifact base name of project `name`; a leading dot would hide the files on Linux."""
  return utils.home_name(name).replace("/", "-").lstrip(".")

def boot_region_kB(cfg:Config) -> int:
  """Bootloader region [kB]: `boot_key_kB` with `BOOT_KEYS`, `boot_kB` for a `plain` one."""
  if not cfg.boot_keys: return cfg.chip.boot_kB
  if not cfg.chip.boot_key_kB:
    p.err(f"Chip {c.PINK}{cfg.chip.name}{c.END} has no {c.SKY}key{c.END} bootloader")
    sys.exit(1)
  return cfg.chip.boot_key_kB

def flash_layout(cfg:Config) -> tuple[int, int, list[str]]:
  """
  Link origin, link length [kB] and `BOOT_*` defines of the image.

  Without a bootloader the image takes the whole region, a bootloader its code region.
  Under the bootloader the flash past its region splits into two equal slots of whole pages.
  Image is linked into the application slot, an update lands in the staging one first.
  Every STM32 build carries `BOOT_PAGES` and `BOOT_CHIP`, chip constants.
  `BOOT_SLOT_PAGES` marks the image as one in a slot.
  """
  flash_kB = cfg.flash_kB
  boot_kB, page_kB = boot_region_kB(cfg), cfg.chip.page_kB
  defines = [f"BOOT_PAGES={boot_kB // page_kB}"] if boot_kB and page_kB else []
  if cfg.chip.dev_id: defines.append(f"BOOT_CHIP=0x{cfg.chip.dev_id:03X}")
  if not cfg.boot: return FLASH_BASE, flash_kB, defines
  if not boot_kB:
    p.err(f"Chip {c.PINK}{cfg.chip.name}{c.END} has no bootloader")
    p.run(f"Open {utils.color_main_h(cfg.name)} and remove {c.SKY}{BOOT_LINE}{c.END}")
    sys.exit(1)
  slot_kB = (flash_kB - boot_kB) // 2 // page_kB * page_kB
  if slot_kB < page_kB:
    p.err(f"{c.SKY}PRO_FLASH_kB{c.END} {c.GOLD}{flash_kB}{c.END}kB leaves no room "
      f"for two slots behind the {c.GOLD}{boot_kB}{c.END}kB bootloader")
    p.run(f"Open {utils.color_main_h(cfg.name)} and raise {c.SKY}PRO_FLASH_kB{c.END} "
      f"or remove {c.SKY}{BOOT_LINE}{c.END}")
    sys.exit(1)
  return FLASH_BASE + boot_kB * 1024, slot_kB, defines + [f"BOOT_SLOT_PAGES={slot_kB // page_kB}"]

BOOT_MAIN = f"{DIR_BOOT}/main.c" # the bootloader program of Core, Core-relative

def boot_build(cfg:Config, core_dir:str, pro_dir:str) -> dict:
  """
  Bootloader of Core under the image: its code region, sources and defines.

  `BOOT_MAIN` builds on HAL and lib of the chip alone, no board, PLC layer or driver,
  with `boot.h` of the project.
  A Core without the program exits.
  """
  if not FILE.exists(f"{core_dir}/{BOOT_MAIN}"):
    p.err(f"Core {c.VIOLET}{cfg.fw_ver}{c.END} has no bootloader {c.BLUE}{BOOT_MAIN}{c.END}")
    p.run(f"Open {utils.color_main_h(cfg.name)} and set {c.SKY}PRO_FRAMEWORK{c.END} "
      f"to a newer Core, or remove {c.SKY}{BOOT_LINE}{c.END}")
    sys.exit(1)
  bare = replace(cfg, plc=False, board=None, project_drivers=[])
  boot_kB, page_kB = boot_region_kB(cfg), cfg.chip.page_kB
  return {
    "boot_kB": boot_kB - page_kB, # the last page is the mailbox
    "boot_c_sources": sorted(core_sources(bare, core_dir, ".c") + [f"{core_dir}/{BOOT_MAIN}"]),
    "boot_asm_sources": core_sources(bare, core_dir, ".s"),
    "boot_include_dirs": [f"{core_dir}/{DIR_BOOT}", pro_dir] + core_includes(bare, core_dir),
    "boot_defines": cfg.chip.defines + [f"FORGE_VERSION={forge_version()}",
      f"BOOT_PAGES={boot_kB // page_kB}", f"BOOT_CHIP=0x{cfg.chip.dev_id:03X}"],
  }

NO_BOOT = {"boot_kB": 0, "boot_c_sources": [], "boot_asm_sources": [],
  "boot_include_dirs": [], "boot_defines": []}

def firmware_tree(pro_dir:str, ext:str) -> dict[str, list[str]]:
  """
  Project tree without `.tests/` at its top.

  Only that one: a test project of Core lies in `.tests/` of the Core itself.
  """
  tests = f"{pro_dir}/{DIR_TESTS}"
  return {folder: fs for folder, fs in rel_tree(pro_dir, ext).items()
    if not PATH.is_under(folder, tests)}

def project_sources(pro_dir:str, ext:str) -> list[str]:
  """Project files with `ext`, sorted and workspace-relative."""
  return sorted(f for fs in firmware_tree(pro_dir, ext).values() for f in fs)

def project_includes(pro_dir:str) -> list[str]:
  """Project directories holding headers."""
  return sorted(firmware_tree(pro_dir, ".h"))

# A test program runs on the computer, against Core built for it from these trees alone
TEST_TREES = ("hal/host", "lib")

def test_tree(core_dir:str, ext:str) -> dict[str, list[str]]:
  """Core files with `ext` of a test build."""
  found = {}
  for sub in TEST_TREES: found.update(rel_tree(f"{core_dir}/{sub}", ext))
  return found

def tests_of(name:str, pro_dir:str) -> str:
  """Folder of the test programs: `.tests/` of a project, of the Core itself its own."""
  return pro_dir if utils.is_core(name) else f"{pro_dir}/{DIR_TESTS}"

def has_tests(test_dir:str) -> bool:
  """`True` when a `.c` lies right in `test_dir`: a program each, deeper folders its helpers."""
  return bool(DIR.file_list(test_dir, exts=[".c"], deep=False))

def project_dirs(pro_dir:str, sources:list[str], includes:list[str]) -> list[str]:
  """Directories whose content decides the source list - the inputs of a makefile reload."""
  dirs = {pro_dir, *includes, *(PATH.dirname(f) for f in sources)}
  return sorted(dirs)

def resolve_project(cfg:Config) -> Project:
  """Project model of `cfg`; a config the Core cannot build exits."""
  chip = cfg.chip
  is_embedded = chip.platform == "STM32"
  name = cfg.name
  core_dir = utils.core_dir(cfg.fw_ver)
  pro_dir = utils.project_dir(name)
  cpu_flags = f"-mcpu={chip.cpu}" if is_embedded else ""
  if is_embedded and chip.fpu:
    mcu_flags = f"{cpu_flags} -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard"
  elif is_embedded:
    mcu_flags = f"{cpu_flags} -mthumb -mfloat-abi=soft"
  else:
    mcu_flags = ""
  # Core refuses a Forge older than its linker script and makefile need
  defines = chip.defines + [f"FORGE_VERSION={forge_version()}"]
  if cfg.plc:
    defines.append("OpenCPLC")
  flash_origin, image_kB, boot_defines = flash_layout(cfg) if is_embedded else (0, 0, [])
  defines += boot_defines
  boot = cfg.boot and is_embedded
  validate_drivers(cfg, core_dir)
  loader = boot_build(cfg, core_dir, pro_dir) if boot else NO_BOOT
  # The Core itself has no sources of its own, only tests, and no `main.h`
  core_itself = utils.is_core(name)
  pro_c = [] if core_itself else project_sources(pro_dir, ".c")
  pro_s = project_sources(pro_dir, ".s") if is_embedded else []
  pro_inc = [] if core_itself else project_includes(pro_dir)
  build_dir = f"{DIR_BUILD}/{pro_dir}"
  test_dir = tests_of(name, pro_dir)
  # `main.h` of the Core itself is Forge's, in its build folder; a module comes by name
  # from any folder of the project, a header of a selected driver too, as the board takes it,
  # and one beyond the test trees by its path from Core root
  pro_dirs = sorted({*pro_inc, *(PATH.dirname(f) for f in pro_c)})
  test_inc = [test_dir] + ([build_dir] if core_itself else pro_dirs)
  test_inc += sorted(test_tree(core_dir, ".h")) + driver_includes(cfg, core_dir) + [core_dir]
  # Platform and family give way to the host, the chip and the rest stay as in firmware
  test_defines = ["HOST", "HOST_TEST", *([chip.define] if is_embedded else [])]
  test_defines += [d for d in defines if d not in chip.defines]
  return Project(
    name=name,
    pro_dir=pro_dir,
    target=project_target(name),
    pro_ver=cfg.pro_ver,
    core_ref=cfg.fw_ver,
    core_dir=core_dir,
    platform=chip.platform,
    chip=chip.name,
    board=cfg.board.name if cfg.board else None,
    board_title=cfg.board_title,
    plc=cfg.plc,
    family=f"{chip.platform}{chip.family}" if is_embedded else chip.platform,
    hal=chip.hal,
    define=chip.define,
    cpu=chip.cpu,
    device=chip.device,
    svd=chip.svd,
    flash_kB=cfg.flash_kB,
    image_kB=image_kB,
    ram_kB=cfg.ram_kB,
    freq_Hz=cfg.freq_Hz,
    opt_level=cfg.opt_level,
    log_level=cfg.log_level,
    defines=defines,
    mcu_flags=mcu_flags,
    core_c_sources=core_sources(cfg, core_dir, ".c"),
    core_asm_sources=core_sources(cfg, core_dir, ".s") if is_embedded else [],
    project_c_sources=pro_c,
    project_asm_sources=pro_s,
    include_dirs=core_includes(cfg, core_dir) + pro_inc,
    project_dirs=project_dirs(pro_dir, pro_c + pro_s, pro_inc),
    linker=chip.ld,
    openocd_target=chip.openocd,
    erase_command=chip.erase,
    stack_script=chip.stack,
    boot=boot,
    flash_origin=flash_origin,
    boot_keys=cfg.boot_keys if boot else "",
    signing_key=cfg.signing_key,
    stlink=cfg.stlink,
    build_dir=build_dir,
    **loader,
    test_dir=test_dir,
    tests=has_tests(test_dir),
    test_core_sources=sorted(f for fs in test_tree(core_dir, ".c").values() for f in fs),
    test_include_dirs=test_inc,
    test_defines=test_defines,
    board_drivers=list(cfg.board.drivers) if cfg.board else [],
    project_drivers=list(cfg.project_drivers),
    load_flags=cfg.load_flags,
  )
