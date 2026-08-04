# opencplc/__main__.py

import signal, sys
from xaeian import Print, Color as c, Ico, FILE, DIR, JSON, PATH, replace_end
from .config import URL_FTP, URL_CORE, URL_FORGE, URL_DEMO
from .args import flag, load_args, check_flags
from .platforms import resolve_chip
from .templates import load_templates
from .project import generate_project
from . import utils, __version__

p = Print()

def handle_sigint(signum, frame):
  p.wrn(f"Closing {c.GREY}(Ctrl+C){c.END}...")
  sys.exit(0)

signal.signal(signal.SIGINT, handle_sigint)

def load_lines(path:str) -> list[str]:
  try: return [ln.rstrip('\n\r') for ln in FILE.load_lines(path)]
  except Exception: return []

def forge_config(templates:dict) -> dict:
  """Load opencplc.json, refresh framework versions from GitHub, persist config."""
  cfg = JSON.load("opencplc.json", templates["opencplc.json"])
  missing = utils.find_missing_keys(templates["opencplc.json"], cfg)
  if missing:
    p.err(f"Missing key {c.SKY}{missing[0]}{c.END} in {c.ORANGE}opencplc.json{c.END}")
    sys.exit(1)
  versions = utils.git_get_refs(URL_CORE, "--ref")
  if versions:
    cfg["available-versions"] = versions
  else:
    p.wrn(f"No internet access or {c.TEAL}GitHub{c.END} is not responding")
    if "available-versions" not in cfg:
      p.err("First run requires network access to fetch available framework versions")
      sys.exit(1)
  cfg["windows"] = utils.detect_os() == "windows"
  # ST-Link map {"<project>": "<uid>"} is a workstation thing, so it lives here, not in main.h
  cfg.setdefault("stlink", {})
  if not isinstance(cfg["stlink"], dict):
    p.wrn(f"Invalid {c.SKY}stlink{c.END} in {c.ORANGE}opencplc.json{c.END} - expected map {{project: uid}}, resetting")
    cfg["stlink"] = {}
  JSON.save_pretty("opencplc.json", cfg)
  cfg["version"] = utils.version_real(cfg["version"], cfg["available-versions"][0])
  return cfg

def info_actions(args, forge_cfg:dict) -> bool:
  """One-shot actions: -v, -F, -hl, -u, -a. True when any of them ran."""
  ran = False
  if args.version:
    p.inf(f"OpenCPLC Forge {c.VIOLET}{__version__}{c.END}")
    p.gap(utils.color_url("https://github.com/OpenCPLC/Forge"))
    ran = True
  if args.framework_versions:
    available = forge_cfg["available-versions"]
    active = utils.version_active(args.framework, forge_cfg)
    parts = []
    for i, ver in enumerate(available):
      tags = [t for t, on in (("branch", not utils.version_is_release(ver)),
        ("latest", i == 0), ("active", ver == active)) if on]
      suffix = f" {c.GREY}({', '.join(tags)}){c.END}" if tags else ""
      color = c.VIOLET if ver == active else c.CYAN
      parts.append(f"{color}{ver}{c.END}{suffix}")
    print("Framework Versions: " + ", ".join(parts))
    ran = True
  if args.hash_list:
    print(utils.c_code_enum(args.hash_list, args.hash_title, args.hash_define))
    ran = True
  if args.update:
    new_ver = args.update in ("last", "latest")
    versions = utils.git_get_refs(URL_FORGE, "--tags")
    if not versions:
      p.err(f"No access to {c.TEAL}GitHub{c.END}")
      sys.exit(1)
    target = utils.version_real(args.update, versions[0])
    if target != __version__:
      p.inf(f"Installed: {c.GREY}{__version__}{c.END}")
      p.inf(f"{'Latest' if new_ver else 'Target'}: {c.VIOLET}{target}{c.END}")
      p.run(f"{'Update' if new_ver else 'Replace'} required")
      utils.install("opencplc.exe", f"{URL_FORGE}/releases/download/{target}", ".", args.yes, False)
    else:
      p.ok(f"Forge is at {'latest' if new_ver else 'target'} version {c.VIOLET}{__version__}{c.END}")
    ran = True
  if args.assets:
    DIR.ensure(args.assets)
    files = [
      "reference-manual-stm32g0x1.pdf", "datasheet-stm32g081rb.pdf",
      "datasheet-stm32g0c1re.pdf", "pinout-nucleo.pdf", "pinout-opencplc.pdf",
    ]
    for f in files:
      dst = PATH.resolve(f"{args.assets}/{f}", read=False)
      if not FILE.exists(dst):
        utils.download(f"{URL_FTP}/{f}", dst)
    p.ok(f"Assets downloaded to {c.ORANGE}{args.assets}{c.END}")
    ran = True
  return ran

def paths_setup(args, forge_cfg:dict) -> tuple[dict, str]:
  """Workspace paths + target framework version; rejects path traversal."""
  paths = forge_cfg["paths"].copy()
  for key, path in paths.items():
    if ".." in path:
      p.err(f"Invalid path in {c.ORANGE}opencplc.json{c.END}: {c.SKY}{key}{c.END} contains {c.MAGNTA}'..'{c.END}")
      sys.exit(1)
    if path.startswith("/") or (len(path) > 1 and path[1] == ":"):
      p.wrn(f"Absolute path in {c.ORANGE}opencplc.json{c.END}: {c.SKY}{key}{c.END}={c.ORANGE}{path}{c.END}")
  fw_ver = utils.version_active(args.framework, forge_cfg)
  paths["fw"] = PATH.resolve(f"{paths['framework']}/{fw_ver}", read=False)
  paths["pro"] = paths["examples"] if args.example else paths["projects"]
  return paths, fw_ver

def makefile_info() -> dict|None:
  """NAME/LIB/PRO of the currently active makefile, if any."""
  if not FILE.exists("makefile"): return None
  lines = utils.lines_clear(load_lines("makefile"), "#")
  return utils.get_vars(lines, ["NAME", "LIB", "PRO"]) or None

def reload_from_makefile(args, PATHS:dict, make_info:dict|None):
  """-r/-i without a name: recover the active project from the makefile."""
  if not make_info:
    p.err(f"No {c.ORANGE}makefile{c.END} found - required for reload and info")
    p.inf(f"Provide project name as positional argument")
    sys.exit(1)
  if PATH.local(make_info["PRO"]).startswith(PATH.local(PATHS["examples"])):
    args.example = True
    PATHS["pro"] = PATHS["examples"]
  args.name = make_info["NAME"]

def ensure_toolchains(is_embedded:bool, yes:bool):
  """Install missing tools, then make sure the compiler actually runs."""
  utils.install_toolchains(is_embedded, yes)
  if utils.RESET_CONSOLE:
    p.wrn(f"New tools were installed and added to system {c.SKY}PATH{c.END}")
    p.tip(f"Restart your console after finishing to use them directly")
  if not utils.verify_compiler(is_embedded):
    compiler = "arm-none-eabi-gcc" if is_embedded else "gcc"
    p.err(f"Compiler {c.YELLOW}{compiler}{c.END} not working")
    p.inf(f"Check installation and {c.SKY}PATH{c.END}")
    sys.exit(1)

def ensure_framework(fw_ver:str, PATHS:dict, forge_cfg:dict, yes:bool):
  """Clone the framework when missing and sanity-check its layout."""
  # Already cloned versions work offline, even when gone from remote
  if not PATH.exists(PATHS["fw"]):
    utils.version_check(fw_ver, forge_cfg["available-versions"],
      f"{Ico.RUN} Check version list: {flag.F}")
    utils.git_clone_missing(URL_CORE, PATHS["fw"], fw_ver, yes)
  fw_hal = PATH.resolve(f"{PATHS['fw']}/hal", read=False)
  fw_lib = PATH.resolve(f"{PATHS['fw']}/lib", read=False)
  if not PATH.exists(fw_hal) or not PATH.exists(fw_lib):
    p.err(f"Framework {c.VIOLET}{fw_ver}{c.END} is incomplete or corrupted")
    p.inf(f"Try removing {c.ORANGE}{PATHS['fw']}{c.END} and run again")
    sys.exit(1)

def project_select(args, PRO:dict):
  """-l listing and picking a project by its number on that list."""
  if not (args.project_list or (args.name and args.name.isdigit())): return
  if not PRO:
    kind = "samples" if args.example else "projects"
    p.wrn(f"No {kind} found")
    p.inf(f"Create new with flag {flag.n}")
    sys.exit(1)
  for i, (name, path) in enumerate(PRO.items(), 1):
    if args.project_list:
      path = replace_end(PATH.local(path), name, "")
      nbr = f"{c.GOLD}{str(i).ljust(3)}{c.END}"
      clr = c.TEAL if args.example else c.BLUE
      print(f"{nbr} {c.GREY}{path}{c.END}{clr}{name}{c.END}")
    elif int(args.name) == i:
      args.name = name
      break
  if args.project_list: sys.exit(0)

def project_delete(args, PRO:dict, make_info:dict|None):
  """Remove project folder and, when it was the active one, the generated root files."""
  key = next((k for k in PRO if k.lower() == args.name.lower()), None)
  if key is None:
    p.err(f"Project {c.MAGNTA}{args.name}{c.END} does not exist")
    sys.exit(1)
  try:
    DIR.remove(PRO[key], force=True)
    if make_info and key == make_info["NAME"]:
      FILE.remove("makefile")
      FILE.remove("flash.ld")
    p.ok(f"Project {c.BLUE}{args.name}{c.END} deleted")
    sys.exit(0)
  except Exception as e:
    p.err(f"Failed to delete: {e}")
    sys.exit(1)

def config_new(args, PRO:dict, PATHS:dict, fw_ver:str, forge_cfg:dict, noun:str) -> dict:
  """Config for a fresh project from -c/-b flags (bare run assumes Uno after confirm)."""
  if args.name.lower() in (n.lower() for n in PRO):
    p.err(f"{noun} {c.MAGNTA}{args.name}{c.END} already exists")
    p.run(f"Use a different name or load it without flag {flag.n}")
    sys.exit(1)
  # No nesting: a project cannot live inside another one
  new_name = args.name.replace("\\", "/").strip("/")
  for existing_name in PRO:
    existing = existing_name.replace("\\", "/").strip("/")
    if new_name.startswith(existing + "/"):
      p.err(f"Cannot create {c.MAGNTA}{args.name}{c.END} inside existing project {c.BLUE}{existing_name}{c.END}")
      sys.exit(1)
    if existing.startswith(new_name + "/"):
      p.err(f"Cannot create {c.MAGNTA}{args.name}{c.END} - project {c.BLUE}{existing_name}{c.END} already exists inside")
      sys.exit(1)
  parent_dir = PATH.dirname(PATHS["pro"])
  if not utils.check_write_permission(parent_dir):
    p.err(f"No write permission in {c.ORANGE}{parent_dir}{c.END}")
    sys.exit(1)
  chip_cfg, board = resolve_chip(args.chip, args.board)
  if not board and not args.chip:
    if not args.yes and not utils.is_yes(f"Are you using OpenCPLC {c.TURQUS}Uno{c.END}"):
      p.err(f"Specify board with flag {flag.b} or chip with flag {flag.c}")
      sys.exit(1)
    chip_cfg, board = resolve_chip("STM32G0C1", "uno")
  # Memory override: -m FLASH RAM [RESERVED]
  if args.memory and len(args.memory) >= 2:
    user_kB = args.memory[2] if len(args.memory) > 2 else 0
    chip_cfg["flash_kB"] = args.memory[0] - user_kB
    chip_cfg["ram_kB"] = args.memory[1]
  return chip_cfg | {
    "pro_name": args.name,
    "board": board,
    "pro_ver": fw_ver,
    "fw_ver": fw_ver,
    "opt_level": args.opt_level or forge_cfg["default"]["optLevel"],
    "log_level": "LOG_LEVEL_INF",
  }

def config_load(args, PRO:dict, PATHS:dict, fw_ver:str, forge_cfg:dict, noun:str) -> dict:
  """Config for an existing project - read back from #define entries in its main.h."""
  key = next((k for k in PRO if k.lower() == args.name.lower()), None)
  if key is None:
    p.err(f"{noun} {c.MAGNTA}{args.name}{c.END} does not exist")
    if args.example:
      p.run(f"Check available examples with flag {flag.l} or download with {flag.e}")
    else:
      p.run(f"Use flag {flag.n} to create a new project")
    sys.exit(1)
  args.name = key
  main_h_path = PATH.resolve(f"{PRO[key]}/main.h", read=False)
  if not FILE.exists(main_h_path):
    p.err(f"File {c.BLUE}main.h{c.END} not found in project")
    p.inf(f"Project may be corrupted, consider recreating with {flag.n}")
    sys.exit(1)
  lines = load_lines(main_h_path)
  if not lines:
    p.err(f"File {c.BLUE}main.h{c.END} is empty or unreadable")
    sys.exit(1)
  lines = utils.lines_clear(lines, "//")
  info = utils.get_vars(lines, ["PRO_BOARD", "PRO_CHIP"], "_", "#define", required=False)
  info |= utils.get_vars(lines, ["PRO_VERSION", "PRO_FLASH_kB", "PRO_RAM_kB",
    "PRO_OPT_LEVEL", "LOG_LEVEL", "SYS_CLOCK_FREQ"], " ", "#define", required=False)
  if not info.get("PRO_CHIP"):
    p.err(f"File {c.BLUE}main.h{c.END} missing {c.SKY}PRO_CHIP{c.END} definition")
    p.inf(f"Check {c.GREY}{PATHS['pro']}/{c.END}{c.BLUE}main.h{c.END}")
    sys.exit(1)
  pro_ver = info.get("PRO_VERSION", fw_ver)
  stored_chip = info["PRO_CHIP"]
  stored_board = info.get("PRO_BOARD", "").lower()
  if stored_board == "none": stored_board = ""
  if args.board and args.board.lower() != "none" and stored_board:
    if args.board.lower() != stored_board.lower():
      p.wrn(f"Compiling for {c.TURQUS}{args.board.capitalize()}{c.END}, "
        f"but project was prepared for {c.TURQUS}{stored_board.capitalize()}{c.END}")
  chip_cfg, board = resolve_chip(
    args.chip or stored_chip,
    args.board or stored_board or "none"
  )
  # Flag wins over main.h, main.h over none
  if args.board and args.board.lower() != "none":
    board = args.board.capitalize()
  elif not args.board and stored_board:
    board = stored_board.capitalize()
  else:
    board = None
  cfg = chip_cfg | {
    "pro_name": args.name,
    "board": board.lower() if board else None,
    "pro_ver": pro_ver,
    "fw_ver": fw_ver,
    "flash_kB": int(info.get("PRO_FLASH_kB", chip_cfg["flash_kB"])),
    "ram_kB": int(info.get("PRO_RAM_kB", chip_cfg["ram_kB"])),
    "opt_level": info.get("PRO_OPT_LEVEL", "Og"),
    "log_level": info.get("LOG_LEVEL", "LOG_LEVEL_INF"),
    "freq_Hz": int(info.get("SYS_CLOCK_FREQ", chip_cfg.get("freq_Hz", 64000000))),
  }
  if not PATH.exists(PATH.resolve(f"{PATHS['framework']}/{pro_ver}", read=False)):
    utils.version_check(pro_ver, forge_cfg["available-versions"],
      f"{Ico.ERR} Invalid {c.SKY}PRO_VERSION{c.END} in {c.BLUE}main.h{c.END}")
  # Version priority: -f flag > PRO_VERSION pin > workspace default
  use_ver = fw_ver if args.framework else pro_ver
  if args.framework and fw_ver != pro_ver:
    p.inf(f"{noun} pinned to {c.GREY}{pro_ver}{c.END}, building with {c.VIOLET}{fw_ver}{c.END} {flag.f}")
  elif use_ver != fw_ver:
    fw_path = PATH.resolve(f"{PATHS['framework']}/{use_ver}", read=False)
    if not utils.git_clone_missing(URL_CORE, fw_path, use_ver, args.yes, required=False):
      p.wrn(f"{noun} {c.BLUE}{args.name}{c.END} version {c.GREY}({pro_ver}){c.END} differs from framework {c.VIOLET}({fw_ver}){c.END}")
      p.wrn("This may prevent compilation or cause incorrect behavior")
      use_ver = fw_ver
    else:
      p.inf(f"{noun} uses {c.VIOLET}{use_ver}{c.END}, workspace default is {c.GREY}{fw_ver}{c.END}")
  else:
    # Quiet upgrade hint - only when an active release is older than the latest release
    latest = forge_cfg["available-versions"][0]
    if (not args.example and utils.version_is_release(use_ver)
        and utils.version_is_release(latest) and utils.version_older_than(use_ver, latest)):
      p.inf(f"{noun} uses {c.VIOLET}{use_ver}{c.END}, newer release {c.GREY}{latest}{c.END} is available")
  cfg["fw_ver"] = use_ver
  PATHS["fw"] = PATH.resolve(f"{PATHS['framework']}/{use_ver}", read=False)
  msg = f"is ignored when loading an existing {noun.lower()} — it's read from {c.BLUE}main.h{c.END}"
  if args.chip: p.wrn(f"Flag {flag.c} {msg}")
  if args.memory: p.wrn(f"Flag {flag.m} {msg}")
  return cfg

def opt_normalize(cfg:dict, yes:bool):
  """Clamp optimization level; O2/O3 on STM32 needs explicit consent."""
  opt = cfg.get("opt_level", "Og")
  cfg["opt_level"] = opt[0].upper() + opt[1:].lower() if len(opt) > 1 else opt
  valid = ("O0", "Og", "O1", "O2", "O3")
  if cfg["opt_level"] not in valid:
    p.wrn(f"Unknown optimization level {c.MAGNTA}{opt}{c.END}, using {c.CYAN}Og{c.END}")
    p.inf(f"Valid options: {', '.join(f'{c.CYAN}{v}{c.END}' for v in valid)}")
    cfg["opt_level"] = "Og"
  if cfg["platform"] == "STM32" and cfg["opt_level"] in ("O2", "O3"):
    p.wrn(f"Optimization {c.CYAN}{cfg['opt_level']}{c.END} may cause issues on STM32 (timing, debugging)")
    if not yes and not utils.is_yes(f"Continue with {c.CYAN}{cfg['opt_level']}{c.END}"):
      p.inf(f"Using {c.CYAN}Og{c.END} instead")
      cfg["opt_level"] = "Og"

def info_show(cfg:dict, PATHS:dict, args):
  """-i: print the resolved project configuration and exit."""
  rel_path = PATH.local(PATHS["pro"])
  path_prefix = replace_end(rel_path, cfg["pro_name"], "")
  msg = f"{c.GREY}{path_prefix}{c.END}{c.TEAL if args.example else c.BLUE}{cfg['pro_name']}{c.END}"
  sample_msg = f" {c.GREY}(sample){c.END}" if args.example else ""
  p.inf(f"Project: {msg}{sample_msg}")
  p.gap(f"Platform: {c.PINK}{cfg['platform']}{c.END}")
  p.gap(f"Board {flag.b}: {c.TURQUS}{str(cfg.get('board') or 'None').capitalize()}{c.END}")
  p.gap(f"Chip {flag.c}: {c.PINK}{cfg['chip']}{c.END}")
  p.gap(f"Project version: {c.VIOLET}{cfg['pro_ver']}{c.END}")
  p.gap(f"Framework version: {c.VIOLET}{cfg['fw_ver']}{c.END}")
  if cfg["platform"] == "STM32":
    p.gap(f"FLASH{c.GREY}/{c.END}RAM {flag.m}: {c.GOLD}{cfg['flash_kB']}{c.END}kB{c.GREY}/{c.END}{c.GOLD}{cfg['ram_kB']}{c.END}kB")
    p.gap(f"System frequency clock: {c.GOLD}{cfg.get('freq_Hz', 64000000)}{c.END}Hz")
  p.gap(f"Optimization level {flag.o}: {c.CYAN}{cfg['opt_level']}{c.END}")
  p.gap(f"Log level: {c.SKY}{cfg['log_level'].replace('LOG_LEVEL_', '')}{c.END}")
  p.gap(f"Last modification: {utils.last_modification(PATHS['pro'], ext=['.c','.h'])}")
  sys.exit(0)

def main():
  templates = load_templates()
  forge_cfg = forge_config(templates)
  args = load_args()
  if info_actions(args, forge_cfg): sys.exit(0)
  # Mutually exclusive modes; mode flags may also carry the project name
  check_flags(args, ("example", flag.e), ("reload", flag.r), ("info", flag.i))
  check_flags(args, ("example", flag.e), ("new", flag.n), ("delete", flag.d), ("get", flag.g))
  args.name, args.new = utils.assign_name(args.name, args.new, flag.n)
  args.name, args.example = utils.assign_name(args.name, args.example, flag.e)
  args.name, args.reload = utils.assign_name(args.name, args.reload, flag.r)
  args.name, args.delete = utils.assign_name(args.name, args.delete, flag.d)
  PATHS, fw_ver = paths_setup(args, forge_cfg)
  make_info = makefile_info()
  if not args.name and (args.reload or args.info):
    reload_from_makefile(args, PATHS, make_info)
  is_embedded = not (args.chip and args.chip.lower() == "host")
  ensure_toolchains(is_embedded, args.yes)
  ensure_framework(fw_ver, PATHS, forge_cfg, args.yes)
  # Remote project - name read from its main.h when not given
  if args.get:
    ref = args.get[1] if len(args.get) > 1 else None
    args.name = utils.project_remote(args.get[0], PATHS["pro"], ref, args.name)
  PRO = utils.get_project_list(PATHS["pro"])
  if args.example and not PRO:
    p.wrn("Examples not downloaded")
    utils.git_clone_missing(URL_DEMO, PATHS["examples"], "main", args.yes)
    PRO = utils.get_project_list(PATHS["pro"])
  project_select(args, PRO)
  if not args.name and not args.reload and not args.info:
    p.err(f"Name {c.GREY}name{c.END} not provided")
    p.inf(f"Provide project name or use flag {flag.r}")
    p.run(f"To reload the currently active project use flag {flag.r}")
    sys.exit(1)
  if args.name:
    valid, reason = utils.validate_project_name(args.name)
    if not valid:
      p.err(f"Invalid project name: {c.MAGNTA}{reason}{c.END}")
      sys.exit(1)
  if args.delete:
    project_delete(args, PRO, make_info)
  PATHS["pro"] = PATH.resolve(f"{PATHS['pro']}/{args.name}", read=False)
  noun = "Sample" if args.example else "Project"
  if args.new:
    CFG = config_new(args, PRO, PATHS, fw_ver, forge_cfg, noun)
  else:
    CFG = config_load(args, PRO, PATHS, fw_ver, forge_cfg, noun)
  opt_normalize(CFG, args.yes)
  if args.info:
    info_show(CFG, PATHS, args)
  generate_project(CFG, PATHS, forge_cfg, is_example=args.example)

if __name__ == "__main__":
  main()
