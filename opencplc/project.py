# opencplc/project.py

import platform
from datetime import datetime
from xaeian import Print, Color as c, FILE, DIR, PATH, replace_start, replace_end
from .templates import load_templates
from .platforms import get_hal_dirs
from . import utils
from . import host as host_utils

p = Print()

def scan_tree(cfg:dict, paths:dict, ext:str) -> dict[str, list[str]]:
  """Project source tree: HAL + lib + PLC drivers (with board) + project files."""
  found = {}
  for sub in get_hal_dirs(cfg["hal"]):
    sub_path = f"{paths['hal']}/{sub}"
    if DIR.exists(sub_path):
      found.update(utils.files_list(sub_path, ext))
  found.update(utils.files_list(paths["lib"], ext))
  if cfg.get("board"):
    found.update(utils.files_list(paths["plc"], ext))
  found.update(utils.files_list(paths["pro"], ext))
  return found

def other_board(cfg:dict, paths:dict, folder:str) -> bool:
  """Driver folders of boards other than the selected one are excluded."""
  if not cfg.get("board"): return False
  brd = f"{paths['plc']}/brd/"
  return brd in folder and not folder.startswith(f"{brd}{cfg['board'].lower()}")

def makefile_list(items:list[str], paths:dict, prefix:str="") -> str:
  """Wrapped makefile list with $(PRO)/$(LIB) shorthands."""
  result = ""
  for item in items:
    rel = PATH.local(item)
    rel = replace_start(rel, paths["pro_rel"], "$(PRO)")
    rel = replace_start(rel, paths["fw_rel"], "$(LIB)")
    if utils.last_line_len(result) > 80:
      result += "\\\n"
    result += f"{prefix}{rel} "
  return result.rstrip()

def collect_sources(cfg:dict, paths:dict, ext:str) -> str:
  tree = scan_tree(cfg, paths, ext)
  files = [f for folder, fs in tree.items() if not other_board(cfg, paths, folder) for f in fs]
  return makefile_list(files, paths)

def collect_includes(cfg:dict, paths:dict) -> str:
  folders = [f for f in scan_tree(cfg, paths, ".h") if not other_board(cfg, paths, f)]
  return makefile_list(folders, paths, "-I")

def generate_project(cfg:dict, paths:dict, forge_cfg:dict, is_example:bool=False):
  templates = load_templates()
  is_embedded = cfg["platform"] == "STM32"
  is_windows = platform.system() == "Windows"
  tpl = templates.get(cfg["hal"], {})
  # Print info
  noun = "Example" if is_example else "Project"
  rel_path = PATH.local(paths["pro"])
  path_prefix = replace_end(rel_path, cfg["pro_name"], "")
  p.inf(f"{noun} {c.GREY}{path_prefix}{c.END}{c.TEAL if is_example else c.BLUE}{cfg['pro_name']}{c.END}")
  if cfg.get("board"):
    chip_msg = f"{c.TURQUS}{cfg['board'].capitalize()}{c.END} PLC"
  elif is_embedded:
    chip_msg = f"{c.PINK}{cfg['chip']}{c.END}"
  else:
    chip_msg = f"{c.PINK}{cfg['platform']}{c.END} {c.GREY}({'Windows' if is_windows else 'Linux'}){c.END}"
  p.gap(f"using framework version {c.VIOLET}{cfg['fw_ver']}{c.END} configured for {chip_msg}")
  # Create project directory
  DIR.ensure(paths["pro"])
  # Store relative paths BEFORE resolving to absolute
  paths["fw_rel"] = PATH.local(paths["fw"])
  paths["pro_rel"] = PATH.local(paths["pro"])
  paths["build_rel"] = PATH.local(paths.get("build", "build"))
  target = f"{'example-' if is_example else ''}{cfg['pro_name'].replace('/', '-')}"
  # Common substitution dict
  subs = {
    "${NAME}": cfg["pro_name"],
    "${LIB_PATH}": paths["fw_rel"],
    "${PRO_PATH}": paths["pro_rel"],
    "${BUILD_PATH}": paths["build_rel"],
    "${DATE}": datetime.now().strftime("%Y-%m-%d"),
    "${PRO_VERSION}": cfg["pro_ver"],
    "${OPT_LEVEL}": cfg.get("opt_level", "Og" if is_embedded else "O2"),
    "${LOG_LEVEL}": cfg.get("log_level", "LOG_LEVEL_INF"),
    "${BOARD}": (cfg.get("board") or "NONE").upper(),
    "${BOARD_LOWER}": (cfg.get("board") or "").lower(),
    "${CHIP}": cfg.get("chip", "").upper(),
    "${FLASH}": cfg["flash_kB"],
    "${RAM}": cfg["ram_kB"],
    "${RAM_SHARED}": cfg.get("ram_shared_kB", 0),
    "${FREQ}": cfg.get("freq_Hz", 64000000),
    "${INCLUDE}": "opencplc.h" if cfg.get("board") and cfg["board"].lower() != "custom" else "plc.h",
    "${INCLUDE_COMMENT}": (
      "Define PLC_Main, peripheral mapping and your staff"
      if cfg.get("board") and cfg["board"].lower() == "custom"
      else "Import driver functions"
    ),
    "${UART_NBR}": cfg["uart"]["nbr"],
    "${UART_TX}": cfg["uart"]["tx"],
    "${UART_RX}": cfg["uart"]["rx"],
    "${UART_DMA}": cfg["uart"]["dma"],
    "${HAL}": cfg["hal"],
    "${PLATFORM}": cfg["platform"],
    "${FAMILY}": f"{cfg['platform']}{cfg['family']}",
    "${DEFINE}": cfg["define"],
    "${CPU}": cfg["cpu"],
    "${DEVICE}": cfg["device"],
    "${SVD}": cfg.get("svd", ""),
    "${TARGET}": target,
    "${PLATFORM_DEFINE}": cfg["define"],
    "${INTELLISENSE_MODE}": "windows-gcc-x64" if is_windows else "linux-gcc-x64",
    "${EXE_EXT}": ".exe" if is_windows else "",
    "${HOST_OS}": "Windows" if is_windows else "Linux",
  }
  # main.c (only if not exists)
  if not FILE.exists(f"{paths['pro']}/main.c"):
    if is_embedded:
      main_c = templates["main.c"] if cfg.get("board") else templates["main-none.c"]
    else:
      main_c = tpl.get("main.c", templates["main-none.c"])
    utils.create_file("main.c", main_c, paths["pro"], subs, color=c.BLUE)
  # main.h (only if not exists)
  if not FILE.exists(f"{paths['pro']}/main.h"):
    main_h = tpl.get("main.h", templates["main.h"])
    utils.create_file("main.h", main_h, paths["pro"], subs, color=c.BLUE)
  # Resolve absolute paths AFTER creating main files
  paths["hal"] = PATH.resolve(f"{paths['fw']}/hal")
  paths["lib"] = PATH.resolve(f"{paths['fw']}/lib")
  paths["plc"] = PATH.resolve(f"{paths['fw']}/plc")
  paths["fw"] = PATH.resolve(paths["fw"])
  paths["pro"] = PATH.resolve(paths["pro"])
  # Ensure dirs exist
  DIR.ensure(paths["hal"])
  DIR.ensure(paths["lib"])
  if cfg.get("board"):
    DIR.ensure(paths["plc"])
  # flash.ld
  if cfg.get("ld"):
    drop = FILE.remove("flash.ld")
    ld_template = templates["flash"].get(cfg["ld"], templates["flash"]["stm32g0.ld"])
    paths["ld"] = utils.create_file("flash.ld", ld_template, "", subs, rewrite=drop)
    paths["ld_rel"] = PATH.local(paths["ld"])
  # Collect sources
  C_SOURCES = collect_sources(cfg, paths, ".c")
  ASM_SOURCES = collect_sources(cfg, paths, ".s") if is_embedded else ""
  C_INCLUDES = collect_includes(cfg, paths)
  # CPU/MCU flags
  cpu_flags = f"-mcpu={cfg['cpu']}" if is_embedded else ""
  if cfg.get("fpu"):
    mcu_flags = f"{cpu_flags} -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard"
  elif is_embedded:
    mcu_flags = f"{cpu_flags} -mthumb -mfloat-abi=soft"
  else:
    mcu_flags = ""
  # Defines
  C_DEFS = " ".join(f"-D{d}" for d in cfg["defines"])
  if cfg.get("board"):
    C_DEFS += " -DOpenCPLC"
  # Update subs
  subs.update({
    "${CPU_FLAGS}": cpu_flags,
    "${MCU_FLAGS}": mcu_flags,
    "${C_DEFS}": C_DEFS,
    "${C_SOURCES}": C_SOURCES,
    "${ASM_SOURCES}": ASM_SOURCES,
    "${C_INCLUDES}": C_INCLUDES,
    "${LD_FILE}": paths.get("ld_rel", ""),
    "${GCC_PATH}": "",
    "${OPENOCD_PATH}": "",
    "${OPENOCD_TARGET}": cfg.get("openocd", ""),
    "${STLINK}": (forge_cfg.get("stlink") or {}).get(cfg["pro_name"], ""),
  })
  # Makefile - always regenerate
  FILE.remove("makefile")
  makefile = tpl.get("makefile.mk", templates["makefile.mk"])
  if forge_cfg.get("windows") and is_embedded:
    makefile = utils.swap_comment_lines(makefile)
  utils.create_file("makefile", makefile, "", subs, rewrite=True)
  # VSCode - always regenerate (platform switch)
  DIR.ensure(".vscode")
  if is_embedded:
    props = tpl.get("properties.json", templates["properties.json"])
    if not cfg.get("board"):
      props = "\n".join(ln for ln in props.splitlines() if "/plc/" not in ln and '"OpenCPLC"' not in ln)
    elif cfg.get("board").lower() == "custom":
      props = "\n".join(ln for ln in props.splitlines() if "/plc/brd/" not in ln)
    utils.create_file("c_cpp_properties.json", props, ".vscode", subs, rewrite=True)
    launch = tpl.get("launch.json", templates["launch.json"])
    stlink_drop = "" if subs["${STLINK}"] else "openOCDPreConfigLaunchCommands"
    utils.create_file("launch.json", launch, ".vscode", subs, remove_line=stlink_drop, rewrite=True)
    utils.create_file("tasks.json", tpl.get("tasks.json", templates["tasks.json"]), ".vscode", subs, rewrite=True)
  else:
    # HOST platform
    host_utils.save_json(".vscode/c_cpp_properties.json",
      host_utils.generate_properties(cfg["pro_name"], C_INCLUDES, cfg["define"], paths["fw_rel"], paths["pro_rel"], is_windows))
    host_utils.save_json(".vscode/launch.json",
      host_utils.generate_launch(subs["${TARGET}"], paths["build_rel"], is_windows))
    host_utils.save_json(".vscode/tasks.json",
      host_utils.generate_tasks(C_SOURCES, C_INCLUDES, subs["${TARGET}"], paths["fw_rel"], paths["pro_rel"], is_windows))
  # Shared files - create only if not exists
  if not FILE.exists(".vscode/settings.json"):
    utils.create_file("settings.json", templates["settings.json"], ".vscode", subs)
  if not FILE.exists(".vscode/extensions.json"):
    utils.create_file("extensions.json", templates["extensions.json"], ".vscode", subs)
