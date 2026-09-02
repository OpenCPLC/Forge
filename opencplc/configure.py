# opencplc/configure.py

"""
Project configuration.

A new project is configured from the -b/-c/-m/-o/-f/-D flags; an existing one is
read back from the #define entries in its main.h. Ready boards come from the
selected Core (`brd/*/*.ini`) and the board decides whether the PLC layer is in;
without a board the project is bare metal, or PLC on your own hardware with -P.
Both paths return the same cfg dict that `resolve_project()` consumes.
"""

import sys
from xaeian import Print, Color as c, Ico, FILE, DIR, PATH
from .config import URL_CORE
from .args import flag
from .platforms import parse_chip
from .boards import Board, load_boards, board_pick, parse_drivers
from .workspace import ensure_refs
from . import utils

p = Print()

OPT_DEFAULT = "Og"
BOOT_FREQ_Hz = 16000000 # bare metal starts on the internal oscillator
PLC_FREQ_Hz = 64000000  # the PLC layer sets the clock up before PLC_Main runs

def board_fields(board:Board|None, memory:bool=True) -> dict:
  """cfg entries that describe the board: no board at all, or a ready one."""
  if board is None:
    return {"board": None, "board_dir": None, "board_drivers": []}
  fields = {"board": board.name, "board_dir": board.dir,
    "board_drivers": list(board.drivers), "freq_Hz": board.freq_Hz}
  if memory: # a forced chip brings its own memory sizes, the board keeps its clock
    fields |= {"flash_kB": board.flash_kB, "ram_kB": board.ram_kB}
  return fields

def boardless_freq(cfg:dict) -> int:
  """Clock a project starts with when no board sets one."""
  if cfg["platform"] != "STM32": return 0
  return PLC_FREQ_Hz if cfg.get("plc") else BOOT_FREQ_Hz

def config_new(args, PRO:dict, PATHS:dict, fw_ver:str, forge_cfg:dict) -> dict:
  """Config for a fresh project from -c/-b flags."""
  if args.name.lower() in (n.lower() for n in PRO):
    p.err(f"Project {c.MAGNTA}{args.name}{c.END} already exists")
    p.run(f"Use a different name or load it without flag {flag.n}")
    sys.exit(1)
  # No nesting: a project cannot live inside another one
  new_name = args.name.replace("\\", "/").strip("/")
  for existing_name in PRO:
    existing = existing_name.replace("\\", "/").strip("/")
    if new_name.startswith(existing + "/"):
      p.err(f"Cannot create {c.MAGNTA}{args.name}{c.END} inside existing project "
        f"{c.BLUE}{existing_name}{c.END}")
      sys.exit(1)
    if existing.startswith(new_name + "/"):
      p.err(f"Cannot create {c.MAGNTA}{args.name}{c.END} - project "
        f"{c.BLUE}{existing_name}{c.END} already exists inside")
      sys.exit(1)
  parent_dir = PATH.dirname(PATHS["pro"])
  if not utils.check_write_permission(parent_dir):
    p.err(f"No write permission in {c.ORANGE}{parent_dir}{c.END}")
    sys.exit(1)
  boards = load_boards(PATHS["fw"])
  board_name = (args.board or "").lower()
  if not board_name and not args.chip:
    p.err(f"Specify board with flag {flag.b} or chip with flag {flag.c}")
    listed = ", ".join(f"{c.TURQUS}{k}{c.END}" for k in boards) or f"{c.GREY}none{c.END}"
    p.inf(f"Boards in this Core: {listed}")
    p.inf(f"Own hardware: {flag.c} alone is bare metal, with {flag.P} adds the PLC layer")
    sys.exit(1)
  if board_name:
    board = board_pick(boards, board_name)
    # The manifest only gives defaults: -c swaps the chip, -P adds the layer a board skips
    forced = bool(args.chip) and args.chip.upper() != board.chip.upper()
    cfg = (parse_chip(args.chip or board.chip) | board_fields(board, memory=not forced)
      | {"plc": board.plc or args.plc})
  else:
    cfg = parse_chip(args.chip) | board_fields(None) | {"plc": args.plc}
    if cfg["plc"] and cfg["platform"] != "STM32":
      p.err(f"Flag {flag.P} needs an STM32 chip {flag.c}")
      sys.exit(1)
    cfg["freq_Hz"] = boardless_freq(cfg)
  # Memory override: -m FLASH RAM [RESERVED]
  if args.memory and len(args.memory) >= 2:
    user_kB = args.memory[2] if len(args.memory) > 2 else 0
    cfg["flash_kB"] = args.memory[0] - user_kB
    cfg["ram_kB"] = args.memory[1]
  return cfg | {
    "pro_name": args.name,
    "pro_ver": fw_ver,
    "fw_ver": fw_ver,
    "opt_level": args.opt_level or OPT_DEFAULT,
    "log_level": "LOG_LEVEL_INF",
    "project_drivers": parse_drivers(args.dvr),
  }

def flags_reject(args):
  """
  Config flags only create projects; an existing one is edited in main.h and reloaded.

  -f is the exception: it builds an existing project on another Core version for one run,
  leaving PRO_VERSION alone - a way to try a newer Core before pinning it.
  """
  used = []
  if args.board: used.append((flag.b, "PRO_BOARD_<NAME>"))
  if args.chip: used.append((flag.c, "PRO_CHIP_<CHIP>"))
  if args.memory: used.append((flag.m, "PRO_FLASH_kB / PRO_RAM_kB"))
  if args.opt_level: used.append((flag.o, "PRO_OPT_LEVEL"))
  if args.plc: used.append((flag.P, "PRO_PLC"))
  if args.dvr: used.append((flag.D, "PRO_DRIVERS"))
  if not used: return
  used_flag, define = used[0]
  p.err(f"Flag {used_flag} only configures a new project")
  p.run(f"Edit {c.SKY}{define}{c.END} in {c.BLUE}main.h{c.END}, then reload with {flag.r}")
  sys.exit(1)

def config_load(args, PRO:dict, PATHS:dict, fw_ver:str, forge_cfg:dict) -> dict:
  """Config for an existing project - read back from #define entries in its main.h."""
  flags_reject(args)
  key = next((k for k in PRO if k.lower() == args.name.lower()), None)
  if key is None:
    p.err(f"Project {c.MAGNTA}{args.name}{c.END} does not exist")
    p.run(f"Use flag {flag.n} to create a new project")
    sys.exit(1)
  args.name = key
  main_h_path = PATH.resolve(f"{PRO[key]}/main.h", read=False)
  if not FILE.exists(main_h_path):
    p.err(f"File {c.BLUE}main.h{c.END} not found in project")
    p.inf(f"Project may be corrupted, consider recreating with {flag.n}")
    sys.exit(1)
  lines = utils.load_lines(main_h_path)
  if not lines:
    p.err(f"File {c.BLUE}main.h{c.END} is empty or unreadable")
    sys.exit(1)
  lines = utils.lines_clear(lines, "//")
  info = utils.get_vars(lines, ["PRO_BOARD", "PRO_CHIP"], "_", "#define", required=False)
  info |= utils.get_vars(lines, ["PRO_VERSION", "PRO_FLASH_kB", "PRO_RAM_kB",
    "PRO_OPT_LEVEL", "PRO_PLC", "PRO_DRIVERS", "LOG_LEVEL", "SYS_CLOCK_FREQ"], " ",
    "#define", required=False)
  if not info.get("PRO_CHIP"):
    p.err(f"File {c.BLUE}main.h{c.END} missing {c.SKY}PRO_CHIP{c.END} definition")
    p.inf(f"Check {c.GREY}{PATHS['pro']}/{c.END}{c.BLUE}main.h{c.END}")
    sys.exit(1)
  pro_ver = info.get("PRO_VERSION", fw_ver)
  stored_board = info.get("PRO_BOARD", "").lower()
  if stored_board == "none": stored_board = ""
  if stored_board == "custom":
    p.err(f"{c.MAGNTA}Custom{c.END} is not a board, the PLC layer is a project setting")
    p.run(f"In {c.BLUE}main.h{c.END} set {c.SKY}PRO_BOARD_None{c.END} "
      f"with {c.SKY}PRO_PLC true{c.END}")
    sys.exit(1)
  stored_plc = info.get("PRO_PLC", "").strip().lower()
  cfg = parse_chip(info["PRO_CHIP"]) | {
    "pro_name": args.name,
    "pro_ver": pro_ver,
    "fw_ver": fw_ver,
    "opt_level": info.get("PRO_OPT_LEVEL", "Og"),
    "log_level": info.get("LOG_LEVEL", "LOG_LEVEL_INF"),
    "project_drivers": parse_drivers(info.get("PRO_DRIVERS", "")),
  }
  if not DIR.exists(PATH.resolve(f"{PATHS['framework']}/{pro_ver}", read=False)):
    utils.version_check(pro_ver, ensure_refs(forge_cfg, args.yes),
      f"{Ico.ERR} Invalid {c.SKY}PRO_VERSION{c.END} in {c.BLUE}main.h{c.END}")
  # Version priority: -f for this run > PRO_VERSION pin > workspace default as fallback
  use_ver = fw_ver if args.framework else pro_ver
  if args.framework and fw_ver != pro_ver:
    p.wrn(f"Project is pinned to {c.GREY}{pro_ver}{c.END}, building with "
      f"{c.VIOLET}{fw_ver}{c.END} for this run {flag.f}")
    p.inf(f"Set {c.SKY}PRO_VERSION{c.END} in {c.BLUE}main.h{c.END} to keep it")
  elif use_ver != fw_ver:
    fw_path = PATH.resolve(f"{PATHS['framework']}/{use_ver}", read=False)
    utils.install_git(args.yes)
    if not utils.git_clone_missing(URL_CORE, fw_path, use_ver, args.yes, required=False):
      p.wrn(f"Project {c.BLUE}{args.name}{c.END} version {c.GREY}({pro_ver}){c.END} "
        f"differs from framework {c.VIOLET}({fw_ver}){c.END}")
      p.wrn("This may prevent compilation or cause incorrect behavior")
      use_ver = fw_ver
    else:
      p.inf(f"Project uses {c.VIOLET}{use_ver}{c.END}, "
        f"workspace default is {c.GREY}{fw_ver}{c.END}")
  else:
    # Quiet upgrade hint - only when an active release is older than the latest release
    latest = forge_cfg["available-versions"][0]
    if (utils.version_is_release(use_ver) and utils.version_is_release(latest)
        and utils.version_older_than(use_ver, latest)):
      p.inf(f"Project uses {c.VIOLET}{use_ver}{c.END}, "
        f"newer release {c.GREY}{latest}{c.END} is available")
  cfg["fw_ver"] = use_ver
  PATHS["fw"] = PATH.resolve(f"{PATHS['framework']}/{use_ver}", read=False)
  # Board layer comes from the Core that actually builds this project
  if stored_board:
    board = board_pick(load_boards(PATHS["fw"]), stored_board)
    # PRO_CHIP_* wins over the manifest, PRO_FLASH_kB and PRO_RAM_kB win below
    cfg |= board_fields(board, memory=board.chip == cfg["chip"])
    # A main.h without PRO_PLC leaves the layer to the board, as at creation
    cfg["plc"] = stored_plc == "true" if stored_plc else board.plc
    if board.plc and not cfg["plc"]:
      p.err(f"Board {c.TURQUS}{board.name}{c.END} runs on the PLC layer")
      p.run(f"Set {c.SKY}PRO_PLC true{c.END} in {c.BLUE}main.h{c.END}")
      sys.exit(1)
  else:
    cfg |= board_fields(None)
    cfg["plc"] = stored_plc == "true"
    cfg["freq_Hz"] = boardless_freq(cfg)
  # Persistent values of main.h win over board and chip defaults
  cfg["flash_kB"] = int(info.get("PRO_FLASH_kB", cfg["flash_kB"]))
  cfg["ram_kB"] = int(info.get("PRO_RAM_kB", cfg["ram_kB"]))
  cfg["freq_Hz"] = int(info.get("SYS_CLOCK_FREQ", cfg["freq_Hz"]))
  return cfg

def opt_normalize(cfg:dict):
  """Clamp optimization level; O2/O3 on STM32 builds as written, with a warning."""
  opt = cfg.get("opt_level", "Og")
  cfg["opt_level"] = opt[0].upper() + opt[1:].lower() if len(opt) > 1 else opt
  valid = ("O0", "Og", "O1", "O2", "O3")
  if cfg["opt_level"] not in valid:
    p.wrn(f"Unknown optimization level {c.MAGNTA}{opt}{c.END}, using {c.CYAN}Og{c.END}")
    p.inf(f"Valid options: {', '.join(f'{c.CYAN}{v}{c.END}' for v in valid)}")
    cfg["opt_level"] = "Og"
  if cfg["platform"] == "STM32" and cfg["opt_level"] in ("O2", "O3"):
    p.wrn(f"Optimization {c.CYAN}{cfg['opt_level']}{c.END} "
      "may affect timing and debugging on STM32")
