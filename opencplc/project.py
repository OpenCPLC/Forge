# opencplc/project.py

"""
Project generators.

`prepare_project()` creates skeleton files a project keeps for life: main.c and main.h.
`generate()` renders everything Forge owns from the resolved `Project` model:
makefile and flash.ld in the project, workspace dispatcher, VS Code configuration.
An unchanged file keeps its bytes and its mtime.
"""

import os, shutil, platform
from datetime import datetime
from xaeian import Print, Color as c, FILE, DIR, PATH, replace_end
from .templates import load_templates
from .resolver import Project, flash_layout
from . import utils

p = Print()

def mk_list(items:list[str]) -> str:
  """Backslash-continued makefile list, one entry per line."""
  return " \\\n".join(items)

def colored_path(path:str, name:str) -> str:
  """Workspace-relative path with the project name picked out of it."""
  return f"{c.GREY}./{path[:-len(name)]}{c.END}{c.BLUE}{name}{c.END}"

def rel_from(items:list[str], base:str) -> list[str]:
  """Paths stripped of a directory prefix, e.g. core paths relative to the Core dir."""
  return [item[len(base) + 1:] for item in items if item.startswith(base + "/")]

def bash_exe() -> str:
  """
  Bash that can open a Windows path.

  On Windows `bash` from PATH is usually WSL, blind to `C:/...`.
  Git brings its own, so that one wins when present.
  """
  if platform.system() != "Windows": return "bash"
  git = shutil.which("git")
  if not git: return "bash"
  root = os.path.dirname(git) # git.exe sits in cmd, bin or mingw64/bin
  for _ in range(3):
    root = os.path.dirname(root)
    for rel in ("bin/bash.exe", "usr/bin/bash.exe"):
      bash = f"{root}/{rel}".replace("\\", "/")
      if FILE.exists(bash): return f'"{bash}"'
  return "bash"

def without(text:str, phrases:list[str]) -> str:
  """Lines of text holding none of the phrases."""
  return "\n".join(ln for ln in text.splitlines() if not any(ph in ln for ph in phrases))

def stack_command(pro:Project) -> str:
  """Radio stack rule of a project: Core script, or a refusal on a chip without one."""
  if not pro.stack_script:
    return f"echo Chip {c.PINK}{pro.chip}{c.END} has no radio stack&& exit 1"
  script = f'{bash_exe()} "$(OPENCPLC)/scr/{pro.stack_script}"'
  return f"{script} $(if $(STLINK),--sn=$(STLINK)) $(if $(FUS),--fus)"

def config_inputs(pro:Project) -> list[str]:
  """Reload inputs of the project makefile, anchored in $(PROJECT)."""
  dirs = ["$(PROJECT)" if d == pro.pro_dir else "$(PROJECT)/" + d[len(pro.pro_dir) + 1:]
    for d in pro.project_dirs]
  return ["$(PROJECT)/main.h"] + dirs

def include_flags(pro:Project) -> list[str]:
  """-I flags anchored in $(OPENCPLC)/$(PROJECT), resolved by Make at build time."""
  flags = []
  for d in pro.include_dirs:
    if d == pro.pro_dir:
      flags.append("-I$(PROJECT)")
    elif d.startswith(pro.pro_dir + "/"):
      flags.append("-I$(PROJECT)/" + d[len(pro.pro_dir) + 1:])
    elif d.startswith(pro.core_dir + "/"):
      flags.append("-I$(OPENCPLC)/" + d[len(pro.core_dir) + 1:])
    else:
      flags.append("-I$(WORKSPACE)/" + d)
  return flags

def project_header(cfg:dict, paths:dict, new:bool=False):
  """
  Print which project and configuration this run works on.

  A new project under the bootloader says what that costs.
  The flag halves flash it can use and nothing else on screen would show it.
  """
  rel_path = PATH.local(paths["pro"])
  path_prefix = replace_end(rel_path, cfg["pro_name"], "")
  p.inf(f"Project {c.GREY}{path_prefix}{c.END}{c.BLUE}{cfg['pro_name']}{c.END}")
  is_windows = platform.system() == "Windows"
  plc_msg = f" {c.TURQUS}PLC{c.END}" if cfg.get("plc") else ""
  if cfg.get("board"):
    chip_msg = f"{c.TURQUS}{cfg['board_title']}{c.END}{plc_msg}"
  elif cfg["platform"] == "STM32":
    chip_msg = f"{c.PINK}{cfg['chip']}{c.END}{plc_msg}"
  else:
    host_os = "Windows" if is_windows else "Linux"
    chip_msg = f"{c.PINK}{cfg['platform']}{c.END} {c.GREY}({host_os}){c.END}"
  p.gap(f"using framework version {c.VIOLET}{cfg['fw_ver']}{c.END} configured for {chip_msg}")
  if new and cfg.get("boot"):
    origin, slot_kB, _ = flash_layout(cfg)
    p.gap(f"bootloader takes {c.GOLD}{cfg['boot_kB']}{c.END}kB, image at "
      f"{c.GOLD}0x{origin:08X}{c.END} in one of two {c.GOLD}{slot_kB}{c.END}kB slots")

def prepare_project(cfg:dict, paths:dict):
  """Create the project skeleton: its directory plus main.c/main.h when missing."""
  templates = load_templates()
  is_embedded = cfg["platform"] == "STM32"
  tpl = templates.get(cfg["hal"], {})
  project_header(cfg, paths, new=not FILE.exists(f"{paths['pro']}/main.h"))
  DIR.ensure(paths["pro"])
  if cfg.get("plc"):
    DIR.ensure(f"{paths['fw']}/plc")
  subs = {
    "${NAME}": cfg["pro_name"],
    "${DATE}": datetime.now().strftime("%Y-%m-%d"),
    "${PRO_VERSION}": cfg["pro_ver"],
    "${OPT_LEVEL}": cfg.get("opt_level", "Og" if is_embedded else "O2"),
    "${LOG_LEVEL}": cfg.get("log_level", "LOG_LEVEL_INF"),
    "${BOARD}": cfg["board_title"] or "None",
    "${PLC}": "true" if cfg.get("plc") else "false",
    "${BOOT}": "true" if cfg.get("boot") else "false",
    "${DRIVERS}": ", ".join(cfg.get("project_drivers", [])),
    "${CHIP}": cfg.get("chip", "").upper(),
    "${FLASH}": cfg["flash_kB"],
    "${RAM}": cfg["ram_kB"],
    "${FREQ}": cfg.get("freq_Hz", 64000000),
    "${PLATFORM}": cfg["platform"],
    "${UART_NBR}": cfg["uart"]["nbr"],
    "${UART_TX}": cfg["uart"]["tx"],
    "${UART_RX}": cfg["uart"]["rx"],
    "${UART_DMA}": cfg["uart"]["dma"],
    "${LED_PORT}": cfg["led"]["port"],
    "${LED_PIN}": cfg["led"]["pin"],
    "${LED_NAME}": cfg["led"]["name"],
  }
  if not FILE.exists(f"{paths['pro']}/main.c"):
    if is_embedded:
      # A board on the PLC layer ships PLC_Main; the rest starts from the plain skeleton
      on_plc = cfg.get("board") and cfg.get("plc")
      main_c = templates["main.c"] if on_plc else templates["main-none.c"]
    else:
      main_c = tpl.get("main.c", templates["main-none.c"])
    utils.create_file("main.c", main_c, paths["pro"], subs, color=c.BLUE)
  if not FILE.exists(f"{paths['pro']}/main.h"):
    main_h = tpl.get("main.h", templates["main.h"])
    drop = "" if cfg["project_drivers"] else "PRO_DRIVERS"
    utils.create_file("main.h", main_h, paths["pro"], subs, remove_line=drop, color=c.BLUE)

def generate(pro:Project, activate:bool=True):
  """
  Render the project makefile and linker from the model.

  With `activate` the workspace follows too: dispatcher points here, VS Code gets its config.
  A reload from inside a project directory leaves both alone.
  Parallel builds never fight over the active project.
  """
  templates = load_templates()
  tpl = templates.get(pro.hal, {})
  is_windows = platform.system() == "Windows"
  up_path = "/".join([".."] * (pro.pro_dir.count("/") + 1))
  subs = {
    "${NAME}": pro.name,
    "${TARGET}": pro.target,
    "${STLINK}": pro.stlink,
    "${UP_PATH}": up_path,
    "${CORE_DIR}": pro.core_dir,
    "${PRO_DIR}": pro.pro_dir,
    "${BUILD_DIR}": pro.build_dir,
    "${CORE_C}": mk_list(rel_from(pro.core_c_sources, pro.core_dir)),
    "${CORE_S}": mk_list(rel_from(pro.core_asm_sources, pro.core_dir)),
    "${PRO_C}": mk_list(rel_from(pro.project_c_sources, pro.pro_dir)),
    "${PRO_S}": mk_list(rel_from(pro.project_asm_sources, pro.pro_dir)),
    "${C_INCLUDES}": mk_list(include_flags(pro)),
    "${CONFIG_INPUTS}": " ".join(config_inputs(pro)),
    "${C_DEFS}": " ".join(f"-D{d}" for d in pro.defines),
    "${MCU_FLAGS}": pro.mcu_flags,
    "${OPT_LEVEL}": pro.opt_level,
    "${LOG_LEVEL}": pro.log_level,
    "${BOARD}": pro.board_title or "None",
    "${BOARD_LOWER}": (pro.board or "").lower(),
    "${CHIP}": pro.chip,
    "${FLASH}": pro.image_kB,
    "${FLASH_ORIGIN}": f"0x{pro.flash_origin:08X}",
    "${BOOT}": "true" if pro.boot else "false",
    "${RAM}": pro.ram_kB,
    "${FREQ}": pro.freq_Hz,
    "${HAL}": pro.hal,
    "${PLATFORM}": pro.platform,
    "${FAMILY}": pro.family,
    "${DEFINE}": pro.define,
    "${CPU}": pro.cpu,
    "${DEVICE}": pro.device,
    "${SVD}": pro.svd,
    "${OPENOCD_TARGET}": pro.openocd_target,
    "${ERASE_CMD}": pro.erase_command,
    "${STACK_CMD}": stack_command(pro),
    "${EXE_EXT}": ".exe" if is_windows else "",
    "${PROJECT_COLORED}": colored_path(pro.pro_dir, pro.name),
    "${BUILD_COLORED}": colored_path(pro.build_dir, pro.name),
    "${GOLD}": c.GOLD, "${GREEN}": c.GREEN, "${PINK}": c.PINK, "${VIOLET}": c.VIOLET,
    "${LIME}": c.LIME, "${RED}": c.RED, "${BLUE}": c.BLUE, "${GREY}": c.GREY, "${END}": c.END,
  } | utils.template_paths(pro.platform == "STM32")
  # Linker script and makefile live inside the project - parallel builds stay disjoint
  if pro.linker:
    ld_template = templates["flash"].get(pro.linker, templates["flash"]["stm32g0.ld"])
    utils.create_file("flash.ld", ld_template, pro.pro_dir, subs)
  makefile = tpl.get("project.mk", templates["project.mk"])
  utils.create_file("makefile", makefile, pro.pro_dir, subs)
  if not activate: return
  # Workspace dispatcher - `make` at the root builds the active project
  utils.create_file("makefile", templates["workspace.mk"], "", {
    "${ACTIVE}": pro.pro_dir,
    "${ACTIVE_COLORED}": colored_path(pro.pro_dir, pro.name),
    "${GOLD}": c.GOLD, "${CMD}": c.CYAN, "${GREY}": c.GREY,
    "${END}": c.END,
    "${ERR}": f"{c.RED}ERR{c.END}",
  })
  DIR.ensure(".vscode")
  props = tpl.get("properties.json", templates["properties.json"])
  drop = ([] if pro.plc else ["/plc/", '"OpenCPLC"']) + ([] if pro.board else ["/brd/"])
  utils.create_file("c_cpp_properties.json", without(props, drop), ".vscode", subs)
  # cortex-debug takes its tools from PATH where Forge has no packages to point at
  launch = tpl.get("launch.json", templates["launch.json"])
  drop = [] if pro.stlink else ["openOCDPreConfigLaunchCommands"]
  drop += [] if is_windows else ["TOOLS_ARM_DIR", "TOOLS_OPENOCD_EXE"]
  utils.create_file("launch.json", without(launch, drop), ".vscode", subs)
  utils.create_file("tasks.json", templates["tasks.json"], ".vscode", subs)
  # Shared files - created once, kept afterwards
  if not FILE.exists(".vscode/settings.json"):
    utils.create_file("settings.json", templates["settings.json"], ".vscode", subs)
  if not FILE.exists(".vscode/extensions.json"):
    utils.create_file("extensions.json", templates["extensions.json"], ".vscode", subs)
