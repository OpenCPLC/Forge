# opencplc/configure.py

"""
Project configuration.

A new project is configured from -b/-c/-m/-o/-f/-D flags.
An existing one is read back from `#define` entries in its main.h.
-f, -b and -c override main.h for a load, and the reloads of make keep them.
Ready boards come from the selected Core (`brd/*/*.ini`), and a board decides about PLC layer.
Without a board the project is bare metal, or PLC on your own hardware with -P.
Both paths return the same `Config` that `resolve_project()` consumes.
"""

import sys
from xaeian import Print, Color as c, Ico, FILE, DIR, PATH
from .config import URL_CORE, DIR_TESTS, BOOT_LINE, OPT_DEFAULT, LOG_LEVEL_DEFAULT
from .args import flag
from .platforms import Chip, parse_chip
from .boards import load_boards, board_pick, board_list, parse_drivers
from .model import Hardware, Config
from .headers import main_h_defines, boot_included, read_boot_h, layers_check, boot_keys
from .workspace import ensure_refs
from .utils import keys
from . import utils

p = Print()

BOOT_FREQ_Hz = 16000000  # bare metal starts on the internal oscillator
PLC_FREQ_Hz = 64000000   # the PLC layer sets the clock up before `PLC_Main` runs

def hardware_text(board:str, chip:str) -> str:
  """Board and chip as messages name them, either one alone."""
  board = f"{c.TURQUS}{board}{c.END}" if board else ""
  chip = f"{c.PINK}{chip}{c.END}" if chip else ""
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
    p.err(f"{c.BLUE}{args.name}{c.END} is a Core, it loads as it is")
    p.run("Create a project inside it, e.g. "
      f"{utils.color_command(f'opencplc -n {args.name}/{DIR_TESTS}/<name>')}")
    sys.exit(1)
  if args.name.lower() in (n.lower() for n in projects):
    p.err(f"Project {c.MAGNTA}{args.name}{c.END} already exists")
    p.run(f"Use a different name or load it without flag {flag.n}")
    sys.exit(1)
  # No nesting: a project cannot live inside another one; a Core holds its own in `.tests/`
  for existing in projects:
    if utils.is_core(existing): continue
    if PATH.is_under(args.name, existing):
      p.err(f"Cannot create {c.MAGNTA}{args.name}{c.END} "
        f"inside existing project {c.BLUE}{existing}{c.END}")
      sys.exit(1)
    if PATH.is_under(existing, args.name):
      p.err(f"Cannot create {c.MAGNTA}{args.name}{c.END} - "
        f"project {c.BLUE}{existing}{c.END} already exists inside")
      sys.exit(1)
  parent_dir = PATH.dirname(PATH.resolve(utils.project_dir(args.name), read=False))
  if not utils.check_write_permission(parent_dir):
    p.err(f"No write permission in {c.CREAM}{parent_dir}{c.END}")
    sys.exit(1)

def hardware_config(board_name:str|None, chip:str|None, plc:bool, core:str) -> Hardware:
  """Board and chip of Core folder `core` with their defaults, as -b, -c and -P give them."""
  boards = load_boards(core)
  board_name = (board_name or "").lower()
  if not board_name and not chip:
    p.err(f"Specify board with flag {flag.b} or chip with flag {flag.c}")
    p.inf(f"Boards in this Core: {board_list(boards)}")
    p.inf(f"Own hardware: {flag.c} alone is bare metal, with {flag.P} adds the PLC layer")
    sys.exit(1)
  if board_name:
    board = board_pick(boards, board_name)
    part = parse_chip(chip or board.chip)
    # The manifest only gives defaults: -c swaps the chip and its memory, -P adds the layer
    own = part.name == board.chip
    flash_kB = board.flash_kB - board.reserve_kB if own else part.flash_kB
    ram_kB = board.ram_kB if own else part.ram_kB
    return Hardware(part, board, board.plc or plc, flash_kB, ram_kB, board.freq_Hz)
  part = parse_chip(chip)
  if plc and part.platform != "STM32":
    p.err("The PLC layer needs an STM32 chip")
    sys.exit(1)
  return Hardware(part, None, plc, part.flash_kB, part.ram_kB, boardless_freq(part, plc))

def config_new(args, projects:dict, fw_ver:str) -> Config:
  """Config of a fresh project from its flags."""
  reject_existing(args, projects)
  hardware = hardware_config(args.board, args.chip, args.plc, utils.core_dir(fw_ver))
  if args.boot and hardware.chip.platform != "STM32":
    p.err(f"Flag {flag.B} needs an STM32 chip, given with {flag.c}")
    sys.exit(1)
  # Memory override: -m FLASH RAM [RESERVED]
  if args.memory and len(args.memory) >= 2:
    reserve_kB = args.memory[2] if len(args.memory) > 2 else 0
    hardware.flash_kB = args.memory[0] - reserve_kB
    hardware.ram_kB = args.memory[1]
  return Config(**vars(hardware), name=args.name, pro_ver=fw_ver, fw_ver=fw_ver,
    opt_level=args.opt_level or OPT_DEFAULT, boot=args.boot,
    project_drivers=parse_drivers(args.drv))

def flags_reject(args):
  """
  Config flags only create projects, an existing one is edited in main.h and reloaded.

  -f, -b and -c are the exception: they override main.h until a load without them.
  So a newer Core can be tried before pinning it, and one test or demo runs on any hardware.
  """
  used = []
  if args.memory: used.append((flag.m, "PRO_FLASH_kB / PRO_RAM_kB"))
  if args.opt_level: used.append((flag.o, "PRO_OPT_LEVEL"))
  if args.plc: used.append((flag.P, "PRO_PLC"))
  if args.drv: used.append((flag.D, "PRO_DRIVERS"))
  if args.boot: used.append((flag.B, BOOT_LINE))
  if not used: return
  used_flag, define = used[0]
  p.err(f"Flag {used_flag} only configures a new project")
  p.run(f"Edit {c.SKY}{define}{c.END} in {c.BLUE}main.h{c.END}, then reload with {flag.r}")
  sys.exit(1)

KEY_LIMIT = 1 << 16 # key numbers fit 16 bits of the image header

def read_main_h(args, projects:dict) -> tuple[dict, list[str]]:
  """`#define` entries of an existing project and its lines cleared; a bad main.h exits."""
  key = utils.project_key(projects, args.name)
  if key is None:
    p.err(f"Project {c.MAGNTA}{args.name}{c.END} does not exist")
    p.run(f"Use flag {flag.n} to create a new project")
    sys.exit(1)
  args.name = key
  main_h_path = PATH.resolve(f"{projects[key]}/main.h", read=False)
  shown = utils.color_main_h(key)
  if not FILE.exists(main_h_path):
    p.err(f"File {shown} not found")
    p.run(f"Restore it from version control, or create the project anew with {flag.n}")
    sys.exit(1)
  lines = utils.load_lines(main_h_path)
  if not lines:
    p.err(f"File {shown} is empty or unreadable")
    sys.exit(1)
  lines = utils.lines_clear(lines, "//")
  info = main_h_defines(lines)
  # in Core the folder names the version, a pin would lie on a checkout of another one
  in_core = bool(utils.core_version(key))
  if in_core and info.get("PRO_FRAMEWORK"):
    p.err(f"File {shown} pins {c.SKY}PRO_FRAMEWORK{c.END}, "
      "a project in Core builds with the Core it lies in")
    p.run(f"Open it and remove {c.SKY}PRO_FRAMEWORK{c.END}")
    sys.exit(1)
  if not in_core and not info.get("PRO_FRAMEWORK"):
    p.err(f"File {shown} has no {c.SKY}PRO_FRAMEWORK{c.END} definition")
    p.run(f"Open it and add the Core version, {c.SKY}#define PRO_FRAMEWORK \"<version>\"{c.END}, "
      f"versions listed by {flag.F}")
    sys.exit(1)
  return info, lines

def main_h_number(info:dict, name:str) -> int:
  """Number `name` of main.h, `0` without it; anything but a number below `KEY_LIMIT` exits."""
  value = info.get(name, "0").strip()
  if not value.isdigit() or int(value) >= KEY_LIMIT:
    p.err(f"Definition {c.SKY}{name}{c.END} in {c.BLUE}main.h{c.END} "
      f"needs a number below {KEY_LIMIT}")
    sys.exit(1)
  return int(value)

def boot_rules(cfg:Config):
  """A bootloader needs an STM32 chip, and `PRO_SIGNING_KEY` one of the keys of `BOOT_KEYS`."""
  if not cfg.boot: return
  if cfg.chip.platform != "STM32":
    p.err(f"Chip {c.PINK}{cfg.chip.name}{c.END} runs no bootloader")
    p.run(f"Open {utils.color_main_h(cfg.name)} and remove {c.SKY}{BOOT_LINE}{c.END}")
    sys.exit(1)
  count = len(keys.keys_split(cfg.boot_keys))
  if cfg.signing_key and cfg.signing_key >= count:
    p.err(f"{c.SKY}PRO_SIGNING_KEY{c.END} {c.GOLD}{cfg.signing_key}{c.END} "
      f"is past the {c.GOLD}{count}{c.END} keys of {c.SKY}BOOT_KEYS{c.END}")
    command = f"opencplc --keygen <name> {cfg.signing_key + 1}"
    p.run(f"Add keys with {utils.color_command(command)}")
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
      f"{Ico.ERR} Invalid {c.SKY}PRO_FRAMEWORK{c.END} in {c.BLUE}main.h{c.END}")
  if args.framework:
    if fw_ver != pro_ver:
      p.wrn(f"Project is pinned to {c.GREY}{pro_ver}{c.END}, "
        f"building with {c.VIOLET}{fw_ver}{c.END} until it loads without {flag.f}")
      p.inf(f"Set {c.SKY}PRO_FRAMEWORK{c.END} in {c.BLUE}main.h{c.END} to keep it")
    return fw_ver
  if pro_ver != fw_ver:
    fw_path = utils.core_dir(pro_ver)
    utils.ensure_git(args.yes)
    if not utils.git_clone_missing(URL_CORE, fw_path, pro_ver, args.yes, required=False):
      p.wrn(f"Project {c.BLUE}{args.name}{c.END} version {c.GREY}({pro_ver}){c.END} "
        f"differs from framework {c.VIOLET}({fw_ver}){c.END}")
      p.wrn("This may prevent compilation or cause incorrect behavior")
      return fw_ver
    p.inf(f"Project uses {c.VIOLET}{pro_ver}{c.END}, "
      f"workspace default is {c.GREY}{fw_ver}{c.END}")
    return pro_ver
  # Quiet upgrade hint - only when an active release is older than the latest release
  latest = forge_cfg["available-versions"][0]
  releases = utils.version_is_release(pro_ver) and utils.version_is_release(latest)
  if releases and utils.version_older_than(pro_ver, latest):
    p.inf(f"Project uses {c.VIOLET}{pro_ver}{c.END}, "
      f"newer release {c.GREY}{latest}{c.END} is available")
  return pro_ver

def config_core(name:str, core:str) -> Config:
  """Config of the Core itself: its tests on the host, under the defaults of Core."""
  host = parse_chip("HOST")
  return Config(chip=host, board=None, plc=False, flash_kB=0, ram_kB=0, freq_Hz=0,
    name=name, pro_ver=core, fw_ver=core)

def config_load(args, projects:dict, fw_ver:str, forge_cfg:dict) -> Config:
  """Config of an existing project, under the Core that builds it."""
  flags_reject(args)
  if utils.is_core(args.name):
    if args.board or args.chip:
      p.err(f"{c.BLUE}{args.name}{c.END} is a Core, its own tests run on this computer")
      p.run("Force a board or chip on a project in it, e.g. "
        f"{utils.color_command(f'opencplc {args.name}/{DIR_TESTS}/<name> -c <chip>')}")
      sys.exit(1)
    if utils.project_key(projects, args.name) is None:
      p.err(f"Core {c.VIOLET}{args.name}{c.END} has no {c.GREY}{DIR_TESTS}/{c.END}")
      sys.exit(1)
    return config_core(args.name, utils.core_version(args.name))
  info, lines = read_main_h(args, projects)
  boot = boot_included(lines)
  boot_lines = read_boot_h(args.name, projects[args.name]) if boot else []
  layers_check(args.name, lines, boot_lines)
  core = utils.core_version(args.name)
  pro_ver = core or info["PRO_FRAMEWORK"]
  # settings of main.h and boot.h refuse before any Core is cloned for them
  keys_hex = boot_keys(boot_lines)
  signing_key = main_h_number(info, "PRO_SIGNING_KEY")
  use_ver = core or resolve_version(args, pro_ver, fw_ver, forge_cfg)
  # Board layer comes from the Core that actually builds this project
  hardware, own = load_hardware(args, info, utils.core_dir(use_ver))
  # Memory and clock of main.h belong to the hardware it names
  if own:
    hardware.flash_kB = int(info.get("PRO_FLASH_kB", hardware.flash_kB))
    hardware.ram_kB = int(info.get("PRO_RAM_kB", hardware.ram_kB))
    hardware.freq_Hz = int(info.get("SYS_CLOCK_FREQ", hardware.freq_Hz))
  cfg = Config(**vars(hardware), name=args.name, pro_ver=pro_ver, fw_ver=use_ver,
    opt_level=info.get("PRO_OPT_LEVEL", OPT_DEFAULT),
    log_level=info.get("LOG_LEVEL", LOG_LEVEL_DEFAULT),
    boot=boot, boot_keys=keys_hex, signing_key=signing_key,
    project_drivers=parse_drivers(info.get("PRO_DRIVERS", "")),
    load_flags=load_flags(args, use_ver == pro_ver, own))
  boot_rules(cfg)
  return cfg

def main_h_hardware(name:str, board:str, chip:str, plc:str, core:str) -> Hardware:
  """Board and chip main.h of project `name` names; `plc` is its `PRO_PLC`."""
  hardware = hardware_config(board, chip, plc == "true", core)
  # C tells boards apart by the name as Core spells it: `PRO_BOARD_UNO` includes no `Uno`
  title = hardware.board_title
  if board and board != title:
    p.err(f"Definition {c.SKY}PRO_BOARD_{board}{c.END} spells board "
      f"{c.TURQUS}{title}{c.END} otherwise than Core")
    p.run(f"Open {utils.color_main_h(name)} and set {c.SKY}#define PRO_BOARD_{title}{c.END}")
    sys.exit(1)
  # A main.h without `PRO_PLC` leaves the layer to the board, as at creation
  if hardware.plc and plc not in ("", "true"):
    p.err(f"Board {c.TURQUS}{title}{c.END} runs on the PLC layer")
    p.run(f"Open {utils.color_main_h(name)} and set {c.SKY}#define PRO_PLC true{c.END}")
    sys.exit(1)
  return hardware

def load_hardware(args, info:dict, core:str) -> tuple[Hardware, bool]:
  """
  Hardware of a load, `True` beside it when it is the one main.h names.

  -b and -c pick it as at creation, `PRO_PLC true` standing for -P,
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
    p.run(f"Load the project with {flag.b} or {flag.c}, the reloads of make keep it")
    sys.exit(1)
  hardware = hardware_config(args.board, args.chip, plc == "true", core)
  if not (board or chip): return hardware, False
  # flags naming what main.h names: a plain load, its checks included
  named = hardware.board.name if hardware.board else None
  if named == (board.lower() or None) and chip.upper() in ("", hardware.chip.name):
    return main_h_hardware(args.name, board, chip, plc, core), True
  used = " ".join(name for name, given in ((flag.b, args.board), (flag.c, args.chip)) if given)
  new = hardware_text(hardware.board_title, hardware.chip.name)
  p.wrn(f"Project is set up for {hardware_text(board, chip)}, building for {new} "
    f"until it loads without {used}")
  p.inf(f"Set {c.SKY}PRO_BOARD{c.END} and {c.SKY}PRO_CHIP{c.END} "
    f"in {c.BLUE}main.h{c.END} to keep it")
  return hardware, False

def opt_normalize(cfg:Config):
  """Clamp optimization level; O2/O3 on STM32 builds as written, with a warning."""
  opt = cfg.opt_level
  cfg.opt_level = opt[0].upper() + opt[1:].lower() if len(opt) > 1 else opt
  valid = ("O0", "Og", "O1", "O2", "O3", "Os")
  if cfg.opt_level not in valid:
    p.wrn(f"Unknown optimization level {c.MAGNTA}{opt}{c.END}, using {c.CYAN}Og{c.END}")
    p.inf(f"Valid options: {', '.join(f'{c.CYAN}{v}{c.END}' for v in valid)}")
    cfg.opt_level = OPT_DEFAULT
  if cfg.chip.platform == "STM32" and cfg.opt_level in ("O2", "O3"):
    p.wrn(f"Optimization {c.CYAN}{cfg.opt_level}{c.END} "
      "may affect timing and debugging on STM32")
