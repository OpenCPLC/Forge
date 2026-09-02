# opencplc/resolver.py

"""
Project resolution.

`resolve_project()` walks the framework and project trees once and returns a
`Project`: the single model every generator and `-i` read from. Paths in the
model are workspace-relative and sorted, so identical inputs resolve to an
identical model; absolute paths appear only while scanning.
"""

from dataclasses import dataclass, field
import sys
from xaeian import Print, Color as c, DIR, PATH
from .platforms import get_hal_dirs
from . import utils

p = Print()

@dataclass
class Project:
  """Fully resolved project model."""
  # Identity
  name: str      # "firm/app"
  pro_dir: str   # workspace-relative source directory
  target: str    # artifact base name
  # Core
  pro_ver: str   # Core version pinned in main.h
  core_ref: str  # Core version used for this build
  core_dir: str  # workspace-relative Core directory
  # Hardware
  platform: str  # "STM32" | "Host"
  chip: str
  board: str|None
  plc: bool      # PLC layer compiled in
  family: str
  hal: str
  define: str
  cpu: str
  device: str
  svd: str
  # Build configuration
  flash_kB: int
  ram_kB: int
  ram_shared_kB: int
  freq_Hz: int
  opt_level: str
  log_level: str
  defines: list[str]
  mcu_flags: str
  # Sources and includes, workspace-relative and sorted
  core_c_sources: list[str]
  core_asm_sources: list[str]
  project_c_sources: list[str]
  project_asm_sources: list[str]
  include_dirs: list[str]
  project_dirs: list[str] # project root and every dir holding project sources or headers
  # Flash and debug
  linker: str # linker template key, "" for HOST
  openocd_target: str
  erase_command: str
  stlink: str
  build_dir: str
  # Device drivers selected by the board and by PRO_DRIVERS
  board_drivers: list[str] = field(default_factory=list)
  project_drivers: list[str] = field(default_factory=list)

def rel_tree(root:str, ext:str) -> dict[str, list[str]]:
  """folder → files under root, both workspace-relative."""
  found = utils.files_list(root, ext)
  return {PATH.local(folder): [PATH.local(f) for f in files] for folder, files in found.items()}

def core_tree(cfg:dict, core_dir:str, ext:str) -> dict[str, list[str]]:
  """
  Core source tree for the selected variant.

  HAL, lib, the boards and the selected drivers are always in; the PLC layer only
  when the project asks for it. Boards and drivers live outside plc/, so a project
  without the PLC layer can use them too.
  """
  found = {}
  for sub in get_hal_dirs(cfg["hal"]):
    hal_path = f"{core_dir}/hal/{sub}"
    if DIR.exists(hal_path):
      found.update(rel_tree(hal_path, ext))
  found.update(rel_tree(f"{core_dir}/lib", ext))
  found.update(rel_tree(f"{core_dir}/dvr", ext))
  found.update(rel_tree(f"{core_dir}/brd", ext))
  if cfg.get("plc"):
    found.update(rel_tree(f"{core_dir}/plc", ext))
  return found

def other_board(cfg:dict, core_dir:str, folder:str) -> bool:
  """Board directories other than the selected one are excluded."""
  if not folder.startswith(f"{core_dir}/brd/"): return False
  board_dir = cfg.get("board_dir") # exact directory, so uno never drags in uno_mini
  return not (board_dir and (folder == board_dir or folder.startswith(board_dir + "/")))

def driver_folder(core_dir:str, folder:str) -> bool:
  """True for the dvr directory of core_dir."""
  return folder == f"{core_dir}/dvr"

def unused_driver(cfg:dict, core_dir:str, folder:str, file:str) -> bool:
  """Core drivers compile only when selected by the board or by PRO_DRIVERS."""
  if not driver_folder(core_dir, folder): return False
  return PATH.basename(file).rsplit(".", 1)[0].lower() not in cfg["drivers"]

def core_sources(cfg:dict, core_dir:str, ext:str) -> list[str]:
  """Core files with ext for this variant, sorted and workspace-relative."""
  tree = core_tree(cfg, core_dir, ext)
  return sorted(f for folder, fs in tree.items() if not other_board(cfg, core_dir, folder)
    for f in fs if not unused_driver(cfg, core_dir, folder, f))

def core_includes(cfg:dict, core_dir:str) -> list[str]:
  """Core directories holding headers for this variant."""
  return sorted(f for f in core_tree(cfg, core_dir, ".h") if not other_board(cfg, core_dir, f)
    and (not driver_folder(core_dir, f) or cfg["drivers"]))

def available_drivers(core_dir:str) -> list[str]:
  """Core drivers with both .c and .h in dvr."""
  dvr = f"{core_dir}/dvr"
  names_c = {PATH.basename(f).rsplit(".", 1)[0].lower()
    for fs in rel_tree(dvr, ".c").values() for f in fs}
  names_h = {PATH.basename(f).rsplit(".", 1)[0].lower()
    for fs in rel_tree(dvr, ".h").values() for f in fs}
  return sorted(names_c & names_h)

def validate_drivers(cfg:dict, core_dir:str):
  """Fail early when a board or PRO_DRIVERS names a driver this Core does not ship."""
  if not cfg["drivers"] or not DIR.exists(f"{core_dir}/dvr"): return
  available = available_drivers(core_dir)
  unknown = [n for n in cfg["drivers"] if n not in available]
  if not unknown: return
  p.err(f"Unknown driver: {c.MAGNTA}{unknown[0]}{c.END}")
  listed = ", ".join(f"{c.TURQUS}{n}{c.END}" for n in available) or f"{c.GREY}none{c.END}"
  p.inf(f"Drivers in this Core: {listed}")
  sys.exit(1)

def project_sources(pro_dir:str, ext:str) -> list[str]:
  """Project files with ext, sorted and workspace-relative."""
  return sorted(f for fs in rel_tree(pro_dir, ext).values() for f in fs)

def project_includes(pro_dir:str) -> list[str]:
  """Project directories holding headers."""
  return sorted(rel_tree(pro_dir, ".h"))

def project_dirs(pro_dir:str, sources:list[str], includes:list[str]) -> list[str]:
  """Directories whose content decides the source list - the inputs of a makefile reload."""
  dirs = {pro_dir, *includes, *(f.rsplit("/", 1)[0] for f in sources)}
  return sorted(dirs)

def resolve_project(cfg:dict, paths:dict, forge_cfg:dict) -> Project:
  """Resolve the full project model from its configuration and workspace paths."""
  is_embedded = cfg["platform"] == "STM32"
  name = cfg["pro_name"]
  core_dir = PATH.local(paths["fw"])
  pro_dir = PATH.local(paths["pro"])
  board = cfg.get("board")
  cpu_flags = f"-mcpu={cfg['cpu']}" if is_embedded else ""
  if is_embedded and cfg.get("fpu"):
    mcu_flags = f"{cpu_flags} -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard"
  elif is_embedded:
    mcu_flags = f"{cpu_flags} -mthumb -mfloat-abi=soft"
  else:
    mcu_flags = ""
  defines = list(cfg["defines"])
  if cfg.get("plc"):
    defines.append("OpenCPLC")
  board_drivers = list(cfg.get("board_drivers", []))
  project_drivers = list(cfg.get("project_drivers", []))
  cfg["drivers"] = list(dict.fromkeys(board_drivers + project_drivers))
  validate_drivers(cfg, core_dir)
  pro_c = project_sources(pro_dir, ".c")
  pro_s = project_sources(pro_dir, ".s") if is_embedded else []
  pro_inc = project_includes(pro_dir)
  return Project(
    name=name,
    pro_dir=pro_dir,
    target=name.replace("/", "-"),
    pro_ver=cfg["pro_ver"],
    core_ref=cfg["fw_ver"],
    core_dir=core_dir,
    platform=cfg["platform"],
    chip=cfg["chip"],
    board=board,
    plc=bool(cfg.get("plc")),
    family=f"{cfg['platform']}{cfg['family']}" if is_embedded else cfg["platform"],
    hal=cfg["hal"],
    define=cfg["define"],
    cpu=cfg["cpu"],
    device=cfg["device"],
    svd=cfg.get("svd", ""),
    flash_kB=cfg["flash_kB"],
    ram_kB=cfg["ram_kB"],
    ram_shared_kB=cfg.get("ram_shared_kB", 0),
    freq_Hz=cfg.get("freq_Hz", 0),
    opt_level=cfg.get("opt_level", "Og"),
    log_level=cfg.get("log_level", "LOG_LEVEL_INF"),
    defines=defines,
    mcu_flags=mcu_flags,
    core_c_sources=core_sources(cfg, core_dir, ".c"),
    core_asm_sources=core_sources(cfg, core_dir, ".s") if is_embedded else [],
    project_c_sources=pro_c,
    project_asm_sources=pro_s,
    include_dirs=core_includes(cfg, core_dir) + pro_inc,
    project_dirs=project_dirs(pro_dir, pro_c + pro_s, pro_inc),
    linker=cfg.get("ld", ""),
    openocd_target=cfg.get("openocd", ""),
    erase_command=cfg.get("erase", ""),
    stlink=(forge_cfg.get("stlink") or {}).get(f"projects/{name}", ""),
    build_dir=f"{PATH.local(paths['build'])}/projects/{name}",
    board_drivers=board_drivers,
    project_drivers=project_drivers,
  )
