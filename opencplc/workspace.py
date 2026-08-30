# opencplc/workspace.py

"""
Workspace state.

Finds the opencplc.json root from any directory inside the workspace,
loads and persists the configuration, fetches framework refs once per run,
keeps the Core checkout present and answers what projects exist here.
"""

import os, sys, json
from xaeian import Print, Color as c, Ico, FILE, DIR, JSON, PATH, replace_end, set_context
from .config import URL_CORE, DIR_PROJECTS, DIR_FRAMEWORK, DIR_BUILD
from .args import flag
from .templates import load_templates
from . import utils

p = Print()

#----------------------------------------------------------------------------------- Root discovery

def find_workspace(start:str=".") -> str|None:
  """Nearest directory at or above start holding opencplc.json."""
  path = os.path.abspath(start)
  while True:
    if os.path.isfile(os.path.join(path, "opencplc.json")): return path
    parent = os.path.dirname(path)
    if parent == path: return None
    path = parent

def project_from_path(path:str, pro_root:str) -> str|None:
  """Name of the project holding path: the closest dir with main.h under pro_root."""
  path = os.path.abspath(path)
  root = os.path.abspath(pro_root)
  while path.lower().startswith(root.lower()) and path != root:
    if os.path.isfile(os.path.join(path, "main.h")):
      return os.path.relpath(path, root).replace("\\", "/")
    path = os.path.dirname(path)
  return None

def enter_workspace() -> str:
  """Move to the nearest workspace root; returns the original working directory."""
  cwd = os.getcwd()
  root = find_workspace()
  if root and not os.path.samefile(root, cwd):
    os.chdir(root) # subprocesses (git, make) follow the process cwd
    set_context(root_path=root) # the xaeian file API follows its own root
    p.inf(f"Workspace: {c.ORANGE}{PATH.normalize(root)}{c.END}")
  return cwd

#------------------------------------------------------------------------------------ Configuration

def forge_config(templates:dict) -> dict:
  """Load and normalize opencplc.json; no network access and no writes here."""
  template = templates["opencplc.json"]
  cfg = JSON.load("opencplc.json", template)
  missing = utils.find_missing_keys(template, cfg)
  if missing:
    p.err(f"Missing key {c.SKY}{missing[0]}{c.END} in {c.ORANGE}opencplc.json{c.END}")
    sys.exit(1)
  # Only the documented fields survive a save; the version list is Forge's own cache
  cfg = {k: cfg[k] for k in (*template, "available-versions") if k in cfg}
  cfg["stlink"] = cfg["stlink"] if isinstance(cfg["stlink"], dict) else {}
  return cfg

def config_text(cfg:dict) -> str:
  """JSON with one key per line and lists inline: maps are edited by hand, lists only read."""
  out = []
  for key, val in cfg.items():
    if isinstance(val, dict) and val:
      body = ",\n".join(f"    {json.dumps(k)}: {json.dumps(v)}" for k, v in val.items())
      out.append(f"  {json.dumps(key)}: {{\n{body}\n  }}")
    else:
      out.append(f"  {json.dumps(key)}: {json.dumps(val)}")
  return "{\n" + ",\n".join(out) + "\n}\n"

def persist_config(forge_cfg:dict, create:bool=False):
  """Save opencplc.json only when its content changed; create the file only when asked."""
  exists = FILE.exists("opencplc.json")
  if not exists and not create: return
  if exists and JSON.load("opencplc.json", None) == forge_cfg: return
  FILE.save("opencplc.json", config_text(forge_cfg))

REFS_FRESH = False

def ensure_refs(forge_cfg:dict, yes:bool) -> list[str]:
  """Framework refs from GitHub, fetched once per run and cached in opencplc.json."""
  global REFS_FRESH
  if REFS_FRESH: return forge_cfg["available-versions"]
  utils.install_git(yes)
  versions = utils.git_get_refs(URL_CORE, "--ref")
  if versions:
    forge_cfg["available-versions"] = versions
    REFS_FRESH = True
    persist_config(forge_cfg)
  else:
    p.wrn(f"No internet access or {c.TEAL}GitHub{c.END} is not responding")
    if not forge_cfg.get("available-versions"):
      p.err("First run requires network access to fetch available framework versions")
      sys.exit(1)
  return forge_cfg["available-versions"]

def paths_setup(args, forge_cfg:dict) -> tuple[dict, str]:
  """Workspace paths of the fixed layout and the target framework version."""
  fw_ver = utils.version_active(args.framework, forge_cfg)
  paths = {"projects": DIR_PROJECTS, "framework": DIR_FRAMEWORK, "build": DIR_BUILD}
  paths["fw"] = PATH.resolve(f"{DIR_FRAMEWORK}/{fw_ver}", read=False)
  paths["pro"] = DIR_PROJECTS
  return paths, fw_ver

def ensure_framework(fw_ver:str, PATHS:dict, forge_cfg:dict, yes:bool):
  """Clone the framework when missing and sanity-check its layout."""
  # Already cloned versions work offline, even when gone from remote
  if not DIR.exists(PATHS["fw"]):
    utils.version_check(fw_ver, ensure_refs(forge_cfg, yes),
      f"{Ico.RUN} Check version list: {flag.F}")
    utils.git_clone_missing(URL_CORE, PATHS["fw"], fw_ver, yes)
  fw_hal = PATH.resolve(f"{PATHS['fw']}/hal", read=False)
  fw_lib = PATH.resolve(f"{PATHS['fw']}/lib", read=False)
  if not DIR.exists(fw_hal) or not DIR.exists(fw_lib):
    p.err(f"Framework {c.VIOLET}{fw_ver}{c.END} is incomplete or corrupted")
    p.inf(f"Try removing {c.ORANGE}{PATHS['fw']}{c.END} and run again")
    sys.exit(1)

#----------------------------------------------------------------------------------- Active project

def makefile_info() -> dict|None:
  """Active project of this workspace, read from the root dispatcher."""
  if not FILE.exists("makefile"): return None
  lines = utils.lines_clear(utils.load_lines("makefile"), "#")
  return utils.get_vars(lines, ["ACTIVE"], ":=", required=False) or None

def reload_from_cwd(args, PATHS:dict, cwd:str) -> bool:
  """-r/-i run inside a project directory: that project is the target."""
  name = project_from_path(cwd, PATHS["projects"])
  if name is None: return False
  args.name = name
  return True

def reload_from_makefile(args, PATHS:dict, make_info:dict|None):
  """-r/-i without a name: recover the active project from the dispatcher."""
  active = (make_info or {}).get("ACTIVE", "")
  if active.startswith(DIR_PROJECTS + "/"):
    args.name = active[len(DIR_PROJECTS) + 1:]
  else:
    p.err(f"No active project in this workspace")
    p.inf(f"Provide project name as positional argument")
    sys.exit(1)

def stlink_bind(forge_cfg:dict, pro_id:str, serial:str|None):
  """Bind (serial) or clear (empty) the ST-Link of a project in opencplc.json."""
  if serial is None: return
  if serial:
    forge_cfg["stlink"][pro_id] = serial
    p.ok(f"ST-Link {c.GOLD}{serial}{c.END} bound to {c.BLUE}{pro_id}{c.END}")
  elif forge_cfg["stlink"].pop(pro_id, None) is not None:
    p.ok(f"ST-Link binding of {c.BLUE}{pro_id}{c.END} cleared")
  persist_config(forge_cfg)

#-------------------------------------------------------------------------------- Project inventory

def project_select(args, PRO:dict):
  """-l listing and picking a project by its number on that list."""
  if not (args.project_list or (args.name and args.name.isdigit())): return
  if not PRO:
    p.wrn("No projects found")
    p.inf(f"Create new with flag {flag.n}")
    sys.exit(1)
  for i, (name, path) in enumerate(PRO.items(), 1):
    if args.project_list:
      path = replace_end(PATH.local(path), name, "")
      nbr = f"{c.GOLD}{str(i).ljust(3)}{c.END}"
      print(f"{nbr} {c.GREY}{path}{c.END}{c.BLUE}{name}{c.END}")
    elif int(args.name) == i:
      args.name = name
      break
  if args.project_list: sys.exit(0)

def project_delete(args, PRO:dict, make_info:dict|None, forge_cfg:dict):
  """Remove the project folder, its ST-Link binding and, when active, the dispatcher target."""
  key = next((k for k in PRO if k.lower() == args.name.lower()), None)
  if key is None:
    p.err(f"Project {c.MAGNTA}{args.name}{c.END} does not exist")
    sys.exit(1)
  try:
    active = PATH.local(PRO[key])
    if forge_cfg["stlink"].pop(f"{DIR_PROJECTS}/{key}", None) is not None:
      persist_config(forge_cfg)
    DIR.remove(PRO[key], force=True)
    if make_info and make_info.get("ACTIVE") == active:
      utils.create_file("makefile", load_templates()["workspace.mk"], "",
        {"${ACTIVE}": "", "${ACTIVE_COLORED}": "", "${GOLD}": c.GOLD, "${CMD}": c.CYAN,
         "${GREY}": c.GREY, "${END}": c.END, "${ERR}": f"{c.RED}ERR{c.END}"})
      p.inf(f"Active project removed - select another with {c.CYAN}opencplc <name>{c.END}")
    p.ok(f"Project {c.BLUE}{args.name}{c.END} deleted")
    sys.exit(0)
  except Exception as e:
    p.err(f"Failed to delete: {e}")
    sys.exit(1)
