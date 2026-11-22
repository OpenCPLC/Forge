# opencplc/configure.py

"""
Project configuration.

A new project is configured from -b/-c/-m/-o/-f, --plc, --drv and --boot.
An existing one is read back from `#define` entries in its main.h.
Given to it, -o, -m, --plc, --drv and --boot write main.h as at creation.
-f, -b and -c override main.h for a load instead, and the reloads of make keep them:
a newer Core is tried before pinning it, and one test or demo runs on any hardware.
Ready boards come from the selected Core (`brd/*/*.ini`), and a board decides about PLC layer.
Without a board the project is bare metal, or PLC on your own hardware with --plc.
Both paths return the same `Config` that `resolve_project()` consumes.
"""

import sys
from xaeian import Print, FILE, DIR, PATH, grey
from .config import URL_CORE, DIR_TESTS, BOOT_LINE, OPT_DEFAULT, LOG_LEVEL_DEFAULT
from .args import flag
from .platforms import Chip, parse_chip
from .boards import load_boards, board_pick, board_list, parse_drivers
from .model import Hardware, Config
from .headers import main_h_defines, boot_included, read_boot_h, layers_check, boot_keys
from .headers import header_lines, text_load
from .workspace import ensure_refs, local_project_at
from .utils import keys
from . import utils

p = Print()

BOOT_FREQ_Hz = 16000000  # bare metal starts on the internal oscillator
PLC_FREQ_Hz = 64000000   # the PLC layer sets the clock up before `PLC_Main` runs
# Flags that write main.h, by the field each fills in `Args`
WRITING = {"o": "opt_level", "m": "memory", "plc": "plc", "drv": "drv", "boot": "boot"}

def hardware_text(board:str, chip:str) -> str:
  """Board and chip as messages name them, either one alone."""
  board = utils.color_board(board) if board else ""
  chip = utils.color_chip(chip) if chip else ""
  return " ".join(part for part in (board, chip) if part)

def load_flags(args, own_core:bool, own_hardware:bool) -> str:
  """-f, -b and -c of this load where they override main.h, so the reloads of make keep them."""
  given = (
    ("-f", not own_core and args.framework),
    ("-b", not own_hardware and args.board),
    ("-c", not own_hardware and args.chip),
  )
  return " ".join(f"{name} {value}" for name, value in given if value)

def boardless_freq(chip:Chip, plc:bool) -> int:
  """Clock a project starts with when no board sets one."""
  if chip.platform != "STM32": return 0
  return PLC_FREQ_Hz if plc else BOOT_FREQ_Hz

def reject_existing(args, projects:dict):
  """A new project needs a free name, a free path and a writable parent."""
  if utils.is_core(args.name):
    p.err(f"{utils.color_file(args.name)} is a Core, it loads as it is")
    p.tip("Create a project inside it: "
      f"{utils.color_command(f'opencplc -n {args.name}/{DIR_TESTS}/<name>')}")
    sys.exit(1)
  if args.name.lower() in (n.lower() for n in projects):
    p.err(f"Project {utils.color_wrong(args.name)} already exists")
    p.tip(f"Use a different name or load it without flag {flag.n}")
    sys.exit(1)
  # No nesting: a project cannot live inside another one; a Core holds its own in `.tests/`
  for existing in projects:
    if utils.is_core(existing): continue
    if PATH.is_under(args.name, existing):
      p.err(f"Cannot create {utils.color_wrong(args.name)} "
        f"inside existing project {utils.color_file(existing)}")
      sys.exit(1)
    if PATH.is_under(existing, args.name):
      p.err(f"Cannot create {utils.color_wrong(args.name)} - "
        f"project {utils.color_file(existing)} already exists inside")
      sys.exit(1)
  # Outside the workspace no list holds the projects: a folder above with `main.h` is one
  holder = local_project_at(PATH.dirname(args.name)) if utils.is_local(args.name) else ""
  if holder:
    p.err(f"Cannot create {utils.color_wrong(args.name)} "
      f"inside existing project {utils.color_file(holder)}")
    sys.exit(1)
  parent_dir = PATH.dirname(PATH.resolve(utils.project_dir(args.name), read=False))
  if not utils.check_write_permission(parent_dir):
    p.err(f"No write permission in {utils.color_folder(parent_dir)}")
    sys.exit(1)

def hardware_config(board_name:str|None, chip:str|None, plc:bool, core:str) -> Hardware:
  """Board and chip of Core folder `core` with their defaults, as -b, -c and --plc give them."""
  boards = load_boards(core)
  board_name = (board_name or "").lower()
  if not board_name and not chip:
    p.err(f"Specify board with flag {flag.b} or chip with flag {flag.c}")
    p.inf(f"Boards in this Core: {board_list(boards)}")
    p.inf(f"Own hardware: {flag.c} alone is bare metal, with {flag.plc} adds the PLC layer")
    sys.exit(1)
  if board_name:
    board = board_pick(boards, board_name)
    part = parse_chip(chip or board.chip)
    # The manifest only gives defaults: -c swaps the chip and its memory, --plc adds the layer
    own = part.name == board.chip
    flash_kB = board.flash_kB - board.reserve_kB if own else part.flash_kB
    ram_kB = board.ram_kB if own else part.ram_kB
    return Hardware(part, board, board.plc or plc, flash_kB, ram_kB, board.freq_Hz)
  part = parse_chip(chip)
  if plc and part.platform != "STM32":
    p.err("The PLC layer needs an STM32 chip")
    sys.exit(1)
  return Hardware(part, None, plc, part.flash_kB, part.ram_kB, boardless_freq(part, plc))

def boot_chip(args, chip:Chip):
  """--boot needs an STM32 chip, as no other runs the bootloader."""
  if not args.boot or chip.platform == "STM32": return
  p.err(f"Flag {flag.boot} needs an STM32 chip, {utils.color_chip(chip.name)} runs no bootloader")
  sys.exit(1)

def memory_kB(memory:list[int]) -> tuple[int, int]:
  """Flash and RAM of -m FLASH RAM [RESERVED], the reserve taken off the flash."""
  if len(memory) not in (2, 3):
    p.err(f"Flag {flag.m} takes FLASH RAM [RESERVED] in kB")
    sys.exit(1)
  reserve_kB = memory[2] if len(memory) > 2 else 0
  return memory[0] - reserve_kB, memory[1]

def memory_check(hardware:Hardware):
  """Flash and RAM from 1kB up to what the chip has, as -m or main.h set them."""
  chip = hardware.chip
  if chip.platform != "STM32": return
  for name, value, most in (
    ("PRO_FLASH_kB", hardware.flash_kB, chip.flash_max_kB),
    ("PRO_RAM_kB", hardware.ram_kB, chip.ram_kB),
  ):
    if 0 < value <= most: continue
    p.err(f"{utils.color_symbol(name)} takes 1 to {utils.color_value(most)}kB "
      f"on {utils.color_chip(chip.name)}, not {utils.color_wrong(value)}")
    p.tip(f"Set memory: {flag.m} FLASH RAM")
    sys.exit(1)

def written_reject(args, used:str, defines:str):
  """
  Flags writing main.h exit beside `used`, which overrides main.h for this load:
  checked against the hardware or Core of the load, they would land in main.h of another.
  """
  written = [getattr(flag, name) for name, field in WRITING.items() if getattr(args, field)]
  if not written: return
  p.err(f"With {used} this load overrides main.h, so {', '.join(written)} cannot write it")
  p.tip(f"Load it without {used}, or set {defines} in main.h first")
  sys.exit(1)

def config_new(args, projects:dict, fw_ver:str) -> Config:
  """Config of a fresh project from its flags."""
  reject_existing(args, projects)
  hardware = hardware_config(args.board, args.chip, args.plc, utils.core_dir(fw_ver))
  boot_chip(args, hardware.chip)
  if args.memory: hardware.flash_kB, hardware.ram_kB = memory_kB(args.memory)
  memory_check(hardware)
  return Config(**vars(hardware), name=args.name, pro_ver=fw_ver, fw_ver=fw_ver,
    opt_level=opt_flag(args.opt_level) if args.opt_level else OPT_DEFAULT,
    boot=args.boot, boot_new=args.boot, project_drivers=parse_drivers(args.drv))

def flag_settings(args, info:dict) -> dict[str, str]:
  """
  `#define` values -o, -m, --plc and --drv give main.h of an existing project, as written there.

  --drv adds its drivers to those `PRO_DRIVERS` names already.
  """
  settings = {}
  if args.opt_level: settings["PRO_OPT_LEVEL"] = f'"{opt_flag(args.opt_level)}"'
  if args.memory:
    flash_kB, ram_kB = memory_kB(args.memory)
    settings |= {"PRO_FLASH_kB": str(flash_kB), "PRO_RAM_kB": str(ram_kB)}
  if args.plc: settings["PRO_PLC"] = "true"
  if args.drv:
    drivers = parse_drivers(f"{info.get('PRO_DRIVERS', '')},{args.drv}")
    settings["PRO_DRIVERS"] = f'"{", ".join(drivers)}"'
  return settings

KEY_LIMIT = 1 << 16 # key numbers fit 16 bits of the image header

def read_main_h(args, projects:dict) -> tuple[dict, list[str]]:
  """`#define` entries of an existing project and its lines cleared; a bad main.h exits."""
  key = utils.project_key(projects, args.name)
  if key is None:
    p.err(f"Project {utils.color_wrong(args.name)} does not exist")
    p.tip(f"Create it: {utils.color_command(f'opencplc -n {args.name}')}")
    sys.exit(1)
  args.name = key
  main_h_path = PATH.resolve(f"{projects[key]}/main.h", read=False)
  shown = utils.color_main_h(key)
  if not FILE.exists(main_h_path):
    p.err(f"File {shown} not found")
    p.tip(f"Restore it from version control, or create the project anew with {flag.n}")
    sys.exit(1)
  text = text_load(main_h_path)
  if not text.strip():
    p.err(f"File {shown} is empty")
    sys.exit(1)
  lines = header_lines(text.split("\n"))
  info = main_h_defines(lines)
  # In Core the folder names the version, a pin would lie on a checkout of another one
  in_core = bool(utils.core_version(key))
  if in_core and info.get("PRO_FRAMEWORK"):
    p.err(f"File {shown} pins {utils.color_symbol('PRO_FRAMEWORK')}, "
      "a project in Core builds with the Core it lies in")
    p.tip(f"Open it and remove {utils.color_symbol('PRO_FRAMEWORK')}")
    sys.exit(1)
  if not in_core and not info.get("PRO_FRAMEWORK"):
    p.err(f"File {shown} has no {utils.color_symbol('PRO_FRAMEWORK')} definition")
    define = '#define PRO_FRAMEWORK "<version>"'
    p.tip(f"Open it and add the Core version, {utils.color_symbol(define)}, "
      f"versions listed by {flag.fv}")
    sys.exit(1)
  return info, lines

def main_h_number(info:dict, name:str) -> int:
  """Number `name` of main.h, `0` without it; anything but a number below `KEY_LIMIT` exits."""
  value = info.get(name, "0").strip()
  if not value.isdigit() or int(value) >= KEY_LIMIT:
    p.err(f"Definition {utils.color_symbol(name)} in {utils.color_file('main.h')} "
      f"needs a number below {KEY_LIMIT}")
    sys.exit(1)
  return int(value)

def boot_rules(cfg:Config):
  """A bootloader needs an STM32 chip, and `PRO_SIGNING_KEY` one of the keys of `BOOT_KEYS`."""
  if not cfg.boot: return
  if cfg.chip.platform != "STM32":
    p.err(f"Chip {utils.color_chip(cfg.chip.name)} runs no bootloader")
    p.tip(f"Open {utils.color_main_h(cfg.name)} and remove {utils.color_include(BOOT_LINE)}")
    sys.exit(1)
  count = len(keys.keys_split(cfg.boot_keys))
  if cfg.signing_key and cfg.signing_key >= count:
    p.err(f"{utils.color_symbol('PRO_SIGNING_KEY')} {utils.color_value(cfg.signing_key)} "
      f"is past {utils.color_value(count)} keys of {utils.color_boot('BOOT_KEYS')}")
    command = f"opencplc --sign <name> {cfg.signing_key + 1}"
    p.tip(f"Add sign keys: {utils.color_command(command)}")
    sys.exit(1)

def resolve_version(args, pro_ver:str, fw_ver:str, forge_cfg:dict) -> str:
  """
  Core version that builds this project.

  Priority: -f of this load, then the `PRO_FRAMEWORK` pin.
  Workspace default steps in when the pinned version cannot be cloned.
  Every step that is not the plain case says so.
  """
  if not DIR.exists(utils.core_dir(pro_ver)):
    utils.version_check(pro_ver, ensure_refs(forge_cfg, args.yes),
      f"Set {utils.color_symbol('PRO_FRAMEWORK')} in {utils.color_file('main.h')} to a version "
      f"listed by {flag.fv}")
  if args.framework:
    if fw_ver != pro_ver:
      written_reject(args, flag.f, utils.color_symbol("PRO_FRAMEWORK"))
      p.wrn(f"Project is pinned to {grey(pro_ver)}, "
        f"building with {utils.color_version(fw_ver)} until it loads without {flag.f}")
      p.tip(f"Set {utils.color_symbol('PRO_FRAMEWORK')} in {utils.color_file('main.h')} "
        "to keep it")
    return fw_ver
  if pro_ver != fw_ver:
    fw_path = utils.core_dir(pro_ver)
    utils.ensure_git(args.yes)
    if not utils.git_clone_missing(URL_CORE, fw_path, pro_ver, args.yes, required=False):
      p.wrn(f"Project {utils.color_file(args.name)} version {grey(f'({pro_ver})')} "
        f"differs from framework {utils.color_version(f'({fw_ver})')}")
      p.wrn("This may prevent compilation or cause incorrect behavior")
      return fw_ver
    p.inf(f"Project uses {utils.color_version(pro_ver)}, "
      f"workspace default is {grey(fw_ver)}")
    return pro_ver
  # Quiet upgrade hint, only when the active release is older than the latest one
  latest = forge_cfg["available-versions"][0]
  releases = utils.version_is_release(pro_ver) and utils.version_is_release(latest)
  if releases and utils.version_older_than(pro_ver, latest):
    p.inf(f"Project uses {utils.color_version(pro_ver)}, "
      f"newer release {grey(latest)} is available")
  return pro_ver

def config_core(name:str, core:str) -> Config:
  """Config of the Core itself: its tests on the host, under the defaults of Core."""
  host = parse_chip("HOST")
  return Config(chip=host, board=None, plc=False, flash_kB=0, ram_kB=0, freq_Hz=0,
    name=name, pro_ver=core, fw_ver=core)

def config_load(args, projects:dict, fw_ver:str, forge_cfg:dict) -> Config:
  """
  Config of an existing project, under the Core that builds it.

  main.h reads as the flags of the load leave it, and `settings` holds what they write there.
  """
  if utils.is_core(args.name):
    setup = (args.board, args.chip, args.opt_level, args.memory, args.plc, args.drv, args.boot)
    if any(setup):
      p.err(f"{utils.color_file(args.name)} is a Core, its own tests run on this computer")
      p.tip("Configure a project in it instead: "
        f"{utils.color_command(f'opencplc {args.name}/{DIR_TESTS}/<name> -c <chip>')}")
      sys.exit(1)
    if utils.project_key(projects, args.name) is None:
      p.err(f"Core {utils.color_version(args.name)} has no {grey(f'{DIR_TESTS}/')}")
      sys.exit(1)
    return config_core(args.name, utils.core_version(args.name))
  info, lines = read_main_h(args, projects)
  settings = flag_settings(args, info)
  info |= {name: value.strip('"') for name, value in settings.items()}
  # --boot puts the project behind the bootloader in this very load, before main.h says so
  included = boot_included(lines)
  boot = included or args.boot
  boot_lines = read_boot_h(args.name, projects[args.name], made=args.boot) if boot else []
  layers_check(args.name, lines, boot_lines)
  core = utils.core_version(args.name)
  pro_ver = core or info["PRO_FRAMEWORK"]
  # Settings of `main.h` and `boot.h` refuse before any Core is cloned for them
  keys_hex = boot_keys(boot_lines)
  signing_key = main_h_number(info, "PRO_SIGNING_KEY")
  use_ver = core or resolve_version(args, pro_ver, fw_ver, forge_cfg)
  # Board layer comes from the Core that actually builds this project
  hardware, own = load_hardware(args, info, utils.core_dir(use_ver))
  boot_chip(args, hardware.chip)
  # Memory and clock of main.h belong to the hardware it names
  if own:
    hardware.flash_kB = int(info.get("PRO_FLASH_kB", hardware.flash_kB))
    hardware.ram_kB = int(info.get("PRO_RAM_kB", hardware.ram_kB))
    hardware.freq_Hz = int(info.get("SYS_CLOCK_FREQ", hardware.freq_Hz))
  memory_check(hardware)
  cfg = Config(**vars(hardware), name=args.name, pro_ver=pro_ver, fw_ver=use_ver,
    opt_level=info.get("PRO_OPT_LEVEL", OPT_DEFAULT),
    log_level=info.get("LOG_LEVEL", LOG_LEVEL_DEFAULT),
    boot=boot, boot_new=args.boot and not included, boot_keys=keys_hex, signing_key=signing_key,
    project_drivers=parse_drivers(info.get("PRO_DRIVERS", "")),
    load_flags=load_flags(args, use_ver == pro_ver, own), settings=settings)
  boot_rules(cfg)
  return cfg

def main_h_hardware(name:str, board:str, chip:str, plc:str, core:str) -> Hardware:
  """Board and chip main.h of project `name` names; `plc` is its `PRO_PLC`."""
  hardware = hardware_config(board, chip, plc == "true", core)
  # C tells boards apart by the name as Core spells it: `PRO_BOARD_UNO` includes no `Uno`
  title = hardware.board_title
  if board and board != title:
    p.err(f"Definition {utils.color_symbol(f'PRO_BOARD_{board}')} spells board "
      f"{utils.color_board(title)} otherwise than Core")
    p.tip(f"Open {utils.color_main_h(name)} "
      f"and set {utils.color_symbol(f'#define PRO_BOARD_{title}')}")
    sys.exit(1)
  # A main.h without `PRO_PLC` leaves the layer to the board, as at creation
  if hardware.plc and plc not in ("", "true"):
    p.err(f"Board {utils.color_board(title)} runs on the PLC layer")
    p.tip(f"Open {utils.color_main_h(name)} and set {utils.color_symbol('#define PRO_PLC true')}")
    sys.exit(1)
  return hardware

def load_hardware(args, info:dict, core:str) -> tuple[Hardware, bool]:
  """
  Hardware of a load, `True` beside it when it is the one main.h names.

  -b and -c pick it as at creation, `PRO_PLC true` standing for --plc,
  and never look up the board of main.h: this Core may lack it.
  A main.h may name none, then every load names it: one test or demo for any board.
  """
  plc = info.get("PRO_PLC", "").strip().lower()
  board = info.get("PRO_BOARD", "")
  if board.lower() == "none": board = ""
  chip = info.get("PRO_CHIP", "")
  if not (args.board or args.chip):
    if board or chip: return main_h_hardware(args.name, board, chip, plc, core), True
    p.err(f"File {utils.color_main_h(args.name)} names no board or chip")
    p.tip(f"Load the project with {flag.b} or {flag.c}, the reloads of make keep it")
    sys.exit(1)
  hardware = hardware_config(args.board, args.chip, plc == "true", core)
  if not (board or chip):
    if args.memory:
      p.err(f"Flag {flag.m} sets memory of hardware main.h names, "
        f"and {utils.color_main_h(args.name)} names none")
      p.tip(f"Load it without {flag.m}, each load takes memory of the hardware it names")
      sys.exit(1)
    return hardware, False
  # Flags naming what `main.h` names: a plain load, its checks included
  named = hardware.board.name if hardware.board else None
  if named == (board.lower() or None) and chip.upper() in ("", hardware.chip.name):
    return main_h_hardware(args.name, board, chip, plc, core), True
  used = " ".join(name for name, given in ((flag.b, args.board), (flag.c, args.chip)) if given)
  board_chip = f"{utils.color_symbol('PRO_BOARD')} and {utils.color_symbol('PRO_CHIP')}"
  written_reject(args, used, board_chip)
  new = hardware_text(hardware.board_title, hardware.chip.name)
  p.wrn(f"Project is set up for {hardware_text(board, chip)}, building for {new} "
    f"until it loads without {used}")
  p.tip(f"Set {board_chip} in {utils.color_file('main.h')} to keep it")
  return hardware, False

OPT_LEVELS = ("O0", "Og", "O1", "O2", "O3", "Os")
OPT_SHOWN = ", ".join(utils.color_choice(level) for level in OPT_LEVELS)

def opt_level(text:str) -> str:
  """Optimization level as gcc spells it, `og` as `Og`; "" for an unknown one."""
  level = text[:1].upper() + text[1:].lower()
  return level if level in OPT_LEVELS else ""

def opt_flag(text:str) -> str:
  """Level -o gives, as gcc spells it; an unknown one exits before any file is written."""
  level = opt_level(text)
  if level: return level
  p.err(f"Unknown optimization level {utils.color_wrong(text)}")
  p.inf(f"Valid options: {OPT_SHOWN}")
  sys.exit(1)

def opt_normalize(cfg:Config):
  """Clamp optimization level of main.h, an unknown one to `Og`; O2/O3 on STM32 warn."""
  level = opt_level(cfg.opt_level)
  if not level:
    p.wrn(f"Unknown optimization level {utils.color_wrong(cfg.opt_level)}, "
      f"using {utils.color_choice(OPT_DEFAULT)}")
    p.inf(f"Valid options: {OPT_SHOWN}")
  cfg.opt_level = level or OPT_DEFAULT
  if cfg.chip.platform == "STM32" and cfg.opt_level in ("O2", "O3"):
    p.wrn(f"Optimization {utils.color_choice(cfg.opt_level)} "
      "may affect timing and debugging on STM32")
