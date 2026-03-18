# opencplc/__main__.py

import signal, sys
from xaeian import Print, Color as c, Ico, FILE, DIR, JSON, PATH, replace_end
from .config import VER, URL_FTP, URL_CORE, URL_FORGE, URL_DEMO
from .args import flag, load_args, check_flags
from .platforms import resolve_chip
from .templates import load_templates
from .project import generate_project
from . import utils

p = Print()

def handle_sigint(signum, frame):
  p.wrn(f"Closing {c.GREY}(Ctrl+C){c.END}...")
  sys.exit(0)

signal.signal(signal.SIGINT, handle_sigint)

def load_lines(path:str) -> list[str]:
  try: return [ln.rstrip('\n\r') for ln in FILE.load_lines(path)]
  except Exception: return []

def main():
  templates = load_templates()
  # Load opencplc.json
  forge_cfg = JSON.load("opencplc.json", templates["opencplc.json"])
  missing = utils.find_missing_keys(templates["opencplc.json"], forge_cfg)
  if missing:
    p.err(f"Missing key {c.BLUE}{missing[0]}{c.END} in {c.ORANGE}opencplc.json{c.END}")
    sys.exit(1)
  # Check available versions
  versions = utils.git_get_refs(URL_CORE, "--ref", use_git=True)
  if versions:
    forge_cfg["available-versions"] = versions
  else:
    p.wrn(f"No access to {c.BLUE}GitHub{c.END}")
    if "available-versions" not in forge_cfg:
      p.err("First run requires network access")
      sys.exit(1)
  JSON.save_pretty("opencplc.json", forge_cfg)
  forge_cfg["version"] = utils.version_real(forge_cfg["version"], forge_cfg["available-versions"][0])
  # Parse arguments
  args = load_args()
  # Print-only actions
  exit_flag = False
  if args.version:
    p.inf(f"OpenCPLC Forge {c.BLUE}{VER}{c.END}")
    p.gap(utils.color_url("https://github.com/OpenCPLC/Forge"))
    exit_flag = True
  if args.framework_versions:
    latest = f" {c.GREY}(latest){c.END}"
    msg = "Framework Versions: "
    color = c.BLUE
    for ver in forge_cfg["available-versions"]:
      msg += f"{color}{ver}{c.END}{latest}, "
      color, latest = c.CYAN, ""
    print(msg.rstrip(", "))
    exit_flag = True
  if args.hash_list:
    print(utils.c_code_enum(args.hash_list, args.hash_title, args.hash_define))
    exit_flag = True
  if args.update:
    new_ver = args.update in ("last", "latest")
    versions = utils.git_get_refs(URL_FORGE, "--tags", use_git=True)
    if not versions:
      p.err(f"No access to {c.BLUE}GitHub{c.END}")
      sys.exit(1)
    target = utils.version_real(args.update, versions[0])
    if target != VER:
      p.inf(f"Installed: {c.ORANGE}{VER}{c.END}")
      p.inf(f"{'Latest' if new_ver else 'Target'}: {c.BLUE}{target}{c.END}")
      utils.install("forge.exe", f"{URL_FORGE}/releases/download/{target}", ".", args.yes, False)
    else:
      p.ok(f"Forge is at {'latest' if new_ver else 'target'} version {c.BLUE}{VER}{c.END}")
    exit_flag = True
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
    exit_flag = True
  if exit_flag: sys.exit(0)
  # Flag conflict check
  check_flags(args, ("example", flag.e), ("reload", flag.r), ("info", flag.i))
  check_flags(args, ("example", flag.e), ("new", flag.n), ("delete", flag.d), ("get", flag.g))
  args.name, args.new = utils.assign_name(args.name, args.new, flag.n)
  args.name, args.example = utils.assign_name(args.name, args.example, flag.e)
  args.name, args.reload = utils.assign_name(args.name, args.reload, flag.r)
  args.name, args.delete = utils.assign_name(args.name, args.delete, flag.d)
  # Setup paths
  PATHS = forge_cfg["paths"].copy()
  # Validate paths - no path traversal
  for key, path in PATHS.items():
    if ".." in path:
      p.err(f"Invalid path in opencplc.json: {c.ORANGE}{key}{c.END} contains '..'")
      sys.exit(1)
    if path.startswith("/") or (len(path) > 1 and path[1] == ":"):
      p.wrn(f"Absolute path in opencplc.json: {c.ORANGE}{key}={path}{c.END}")
  fw_ver = args.framework or forge_cfg["version"]
  PATHS["fw"] = PATH.resolve(f"{PATHS['framework']}/{fw_ver}", read=False)
  PATHS["pro"] = PATHS["examples"] if args.example else PATHS["projects"]
  # Load existing makefile info
  make_info = None
  if FILE.exists("makefile"):
    lines = load_lines("makefile")
    lines = utils.lines_clear(lines, "#")
    make_info = utils.get_vars(lines, ["NAME", "LIB", "PRO"])
  # Reload/info mode - get name from makefile
  if not args.name and (args.reload or args.info):
    if not make_info:
      p.err(f"No {c.ORANGE}makefile{c.END} - provide project name")
      sys.exit(1)
    pro_rel = PATH.local(make_info["PRO"])
    example_rel = PATH.local(PATHS["examples"])
    if pro_rel.startswith(example_rel):
      args.example = True
      PATHS["pro"] = PATHS["examples"]
    args.name = make_info["NAME"]
  # Determine platform early for toolchain installation
  is_embedded = True
  if args.chip and args.chip.lower() == "host":
    is_embedded = False
  # Install toolchains based on platform
  utils.install_toolchains(is_embedded, args.yes)
  if utils.RESET_CONSOLE:
    p.inf("Reset console after finishing work")
    sys.exit(0)
  # Verify compiler works
  if not utils.verify_compiler(is_embedded):
    compiler = "arm-none-eabi-gcc" if is_embedded else "gcc"
    p.err(f"Compiler {c.CYAN}{compiler}{c.END} not working")
    p.inf("Check installation and PATH")
    sys.exit(1)
  # Version check and clone framework
  utils.version_check(fw_ver, forge_cfg["available-versions"],
    f"{Ico.RUN} Check version list: {flag.F}")
  utils.git_clone_missing(URL_CORE, PATHS["fw"], fw_ver, args.yes)
  # Verify framework was cloned correctly
  fw_hal = PATH.resolve(f"{PATHS['fw']}/hal", read=False)
  fw_lib = PATH.resolve(f"{PATHS['fw']}/lib", read=False)
  if not PATH.exists(fw_hal) or not PATH.exists(fw_lib):
    p.err(f"Framework {c.VIOLET}{fw_ver}{c.END} is incomplete or corrupted")
    p.inf(f"Try removing {c.ORANGE}{PATHS['fw']}{c.END} and run again")
    sys.exit(1)
  # Remote project download
  if args.get:
    url = args.get[0]
    ref = args.get[1] if len(args.get) > 1 else None
    args.name = utils.project_remote(url, PATHS["pro"], ref, args.name)
  # Project list
  PRO = utils.get_project_list(PATHS["pro"])
  if args.example and not PRO:
    p.wrn("Examples not downloaded")
    utils.git_clone_missing(URL_DEMO, PATHS["examples"], "main", args.yes)
    PRO = utils.get_project_list(PATHS["pro"])
  # List projects
  if args.project_list or (args.name and args.name.isdigit()):
    if not PRO:
      kind = "samples" if args.example else "projects"
      p.wrn(f"No {kind} found")
      p.inf(f"Create new with flag {flag.n}")
      sys.exit(1)
    i = 1
    for name, path in PRO.items():
      if args.project_list:
        path = PATH.local(path)
        path = replace_end(path, name, "")
        nbr = f"{c.GOLD}{str(i).ljust(3)}{c.END}"
        clr = c.TEAL if args.example else c.BLUE
        print(f"{nbr} {c.GREY}{path}{c.END}{clr}{name}{c.END}")
      else:
        if int(args.name) == i:
          args.name = name
          break
      i += 1
    if args.project_list: sys.exit(0)
  # Name validation
  if not args.name and not args.reload and not args.info:
    p.err(f"Name {c.YELLOW}name{c.END} not provided")
    p.inf(f"Provide project name or use flag {flag.r}")
    sys.exit(1)
  if args.name:
    valid, reason = utils.validate_project_name(args.name)
    if not valid:
      p.err(f"Invalid project name: {c.MAGNTA}{reason}{c.END}")
      sys.exit(1)
  # Delete project
  if args.delete:
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
  # Set project path
  PATHS["pro"] = PATH.resolve(f"{PATHS['pro']}/{args.name}", read=False)
  noun = "Sample" if args.example else "Project"
  # New project
  if args.new:
    if args.name.lower() in (n.lower() for n in PRO.keys()):
      p.err(f"{noun} {c.MAGNTA}{args.name}{c.END} already exists")
      sys.exit(1)
    # Check for nested projects
    new_name = args.name.replace("\\", "/").strip("/")
    for existing_name in PRO.keys():
      existing = existing_name.replace("\\", "/").strip("/")
      if new_name.startswith(existing + "/"):
        p.err(f"Cannot create {c.MAGNTA}{args.name}{c.END} inside existing project {c.BLUE}{existing_name}{c.END}")
        sys.exit(1)
      if existing.startswith(new_name + "/"):
        p.err(f"Cannot create {c.MAGNTA}{args.name}{c.END} - project {c.BLUE}{existing_name}{c.END} already exists inside")
        sys.exit(1)
    # Check write permission
    parent_dir = PATH.dirname(PATHS["pro"])
    if not utils.check_write_permission(parent_dir):
      p.err(f"No write permission in {c.ORANGE}{parent_dir}{c.END}")
      sys.exit(1)
    # Resolve chip and board
    chip_cfg, board = resolve_chip(args.chip, args.board)
    # If no board and no chip specified, ask about Uno
    if not board and not args.chip:
      if not args.yes and not utils.is_yes(f"Are you using OpenCPLC {c.TURQUS}Uno{c.END}"):
        p.err(f"Specify board with flag {flag.b} or chip with flag {flag.c}")
        sys.exit(1)
      chip_cfg, board = resolve_chip("STM32G0C1", "uno")
    # Memory override: [flash, ram] or [flash, ram, user]
    if args.memory and len(args.memory) >= 2:
      user_kB = args.memory[2] if len(args.memory) > 2 else 0
      chip_cfg["flash_kB"] = args.memory[0] - user_kB
      chip_cfg["ram_kB"] = args.memory[1]
    # Build config
    CFG = chip_cfg.copy()
    CFG["pro_name"] = args.name
    CFG["board"] = board
    CFG["pro_ver"] = fw_ver
    CFG["fw_ver"] = fw_ver
    CFG["opt_level"] = args.opt_level or forge_cfg["default"]["optLevel"]
    CFG["log_level"] = "LOG_LEVEL_INF"
  else:
    # Load existing project
    if args.name.lower() not in (n.lower() for n in PRO.keys()):
      p.err(f"{noun} {c.MAGNTA}{args.name}{c.END} does not exist")
      p.run(f"Use flag {flag.n} to create new")
      sys.exit(1)
    main_h_path = PATH.resolve(f"{PRO[args.name]}/main.h", read=False)
    if not FILE.exists(main_h_path):
      p.err(f"File {c.ORANGE}main.h{c.END} not found in project")
      p.inf(f"Project may be corrupted, consider recreating with {flag.n}")
      sys.exit(1)
    lines = load_lines(main_h_path)
    if not lines:
      p.err(f"File {c.ORANGE}main.h{c.END} is empty or unreadable")
      sys.exit(1)
    lines = utils.lines_clear(lines, "//")
    info1 = utils.get_vars(lines, ["PRO_BOARD", "PRO_CHIP"], "_", "#define", required=False)
    info2 = utils.get_vars(lines, ["PRO_VERSION", "PRO_FLASH_kB", "PRO_RAM_kB",
      "PRO_OPT_LEVEL", "LOG_LEVEL", "SYS_CLOCK_FREQ"], " ", "#define", required=False)
    info = info1 | info2
    if not info.get("PRO_CHIP"):
      p.err(f"File {c.ORANGE}main.h{c.END} missing PRO_CHIP definition")
      sys.exit(1)
    # Get project version from main.h
    pro_ver = info.get("PRO_VERSION", fw_ver)
    # Resolve chip (override with args if provided)
    stored_chip = info["PRO_CHIP"]
    stored_board = info.get("PRO_BOARD", "").lower()
    if stored_board == "none": stored_board = ""
    # Board change warning
    if args.board and args.board.lower() != "none" and stored_board:
      pro_board = stored_board.capitalize()
      arg_board = args.board.capitalize()
      if arg_board.lower() != pro_board.lower():
        p.wrn(f"Compiling for {c.TURQUS}{arg_board}{c.END}, but project was prepared for {c.TURQUS}{pro_board}{c.END}")
    chip_cfg, board = resolve_chip(
      args.chip or stored_chip,
      args.board or stored_board or "none"
    )
    if args.board and args.board.lower() != "none":
      board = args.board.capitalize()
    elif not args.board and stored_board:
      board = stored_board.capitalize()
    else:
      board = None
    # Build config
    CFG = chip_cfg.copy()
    CFG["pro_name"] = args.name
    CFG["board"] = board.lower() if board else None
    CFG["pro_ver"] = pro_ver
    CFG["fw_ver"] = fw_ver
    CFG["flash_kB"] = int(info.get("PRO_FLASH_kB", chip_cfg["flash_kB"]))
    CFG["ram_kB"] = int(info.get("PRO_RAM_kB", chip_cfg["ram_kB"]))
    CFG["opt_level"] = info.get("PRO_OPT_LEVEL", "Og")
    CFG["log_level"] = info.get("LOG_LEVEL", "LOG_LEVEL_INF")
    CFG["freq_Hz"] = int(info.get("SYS_CLOCK_FREQ", chip_cfg.get("freq_Hz", 64000000)))
    # Version check for project version
    utils.version_check(pro_ver, forge_cfg["available-versions"],
      f"{Ico.ERR} Invalid PRO_VERSION in main.h")
    # Warn about outdated project version
    latest = forge_cfg["available-versions"][0]
    if pro_ver != latest and not args.example:
      p.inf(f"Project uses {c.GREY}{pro_ver}{c.END}, latest is {c.VIOLET}{latest}{c.END}")
    # Handle version mismatch
    if args.example:
      CFG["fw_ver"] = pro_ver
      PATHS["fw"] = PATH.resolve(f"{PATHS['framework']}/{pro_ver}", read=False)
    elif pro_ver != fw_ver:
      fw_path = PATH.resolve(f"{PATHS['framework']}/{pro_ver}", read=False)
      if not utils.git_clone_missing(URL_CORE, fw_path, pro_ver, args.yes, required=False):
        p.wrn(f"Project {c.MAGNTA}{args.name}{c.END} version {c.GREY}({pro_ver}){c.END} differs from framework {c.GREY}({fw_ver}){c.END}")
        p.wrn("This may prevent compilation or cause incorrect behavior")
      else:
        CFG["fw_ver"] = pro_ver
        PATHS["fw"] = fw_path
    # Warn about ignored flags
    msg = f"is ignored when loading existing {noun.lower()}"
    if args.chip: p.wrn(f"Flag {flag.c} {msg}")
    if args.memory: p.wrn(f"Flag {flag.m} {msg}")
  # Normalize opt-level
  opt = CFG.get("opt_level", "Og")
  CFG["opt_level"] = opt[0].upper() + opt[1:].lower() if len(opt) > 1 else opt
  valid_opts = ("O0", "Og", "O1", "O2", "O3")
  if CFG["opt_level"] not in valid_opts:
    p.wrn(f"Unknown optimization level {c.MAGNTA}{opt}{c.END}, using {c.CYAN}Og{c.END}")
    p.inf(f"Valid options: {', '.join(valid_opts)}")
    CFG["opt_level"] = "Og"
  if CFG["platform"] == "STM32" and CFG["opt_level"] in ("O2", "O3"):
    p.wrn(f"Optimization {c.MAGNTA}{CFG['opt_level']}{c.END} may cause issues on STM32 (timing, debugging)")
    if not args.yes and not utils.is_yes(f"Continue with {c.CYAN}{CFG['opt_level']}{c.END}"):
      p.inf(f"Using {c.CYAN}Og{c.END} instead")
      CFG["opt_level"] = "Og"
  # Info mode
  if args.info:
    rel_path = PATH.local(PATHS["pro"])
    path_prefix = replace_end(rel_path, CFG["pro_name"], "")
    msg = f"{c.GREY}{path_prefix}{c.END}{c.BLUE}{CFG['pro_name']}{c.END}"
    sample_msg = f" {c.RED}(sample){c.END}" if args.example else ""
    p.inf(f"Project: {msg}{sample_msg}")
    p.gap(f"Platform: {c.CYAN}{CFG['platform']}{c.END}")
    p.gap(f"Board {flag.b}: {c.TURQUS}{str(CFG.get('board') or 'None').capitalize()}{c.END}")
    p.gap(f"Chip {flag.c}: {c.PINK}{CFG['chip']}{c.END}")
    p.gap(f"Project version: {c.MAGNTA}{CFG['pro_ver']}{c.END}")
    p.gap(f"Framework version: {c.MAGNTA}{CFG['fw_ver']}{c.END}")
    if CFG["platform"] == "STM32":
      p.gap(f"FLASH{c.GREY}/{c.END}RAM {flag.m}: {c.CYAN}{CFG['flash_kB']}{c.END}kB{c.GREY}/{c.END}{c.CYAN}{CFG['ram_kB']}{c.END}kB")
      p.gap(f"System frequency clock: {c.CYAN}{CFG.get('freq_Hz', 64000000)}{c.END}Hz")
    p.gap(f"Optimization level {flag.o}: {c.PINK}{CFG['opt_level']}{c.END}")
    p.gap(f"Log level: {c.BLUE}{CFG['log_level'].replace('LOG_LEVEL_', '')}{c.END}")
    p.gap(f"Last modification: {utils.last_modification(PATHS['pro'], ext=['.c','.h'])}")
    sys.exit(0)
  # Generate project
  generate_project(CFG, PATHS, forge_cfg, is_example=args.example)

if __name__ == "__main__":
  main()