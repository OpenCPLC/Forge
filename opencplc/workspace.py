# opencplc/workspace.py

"""
Workspace state.

Finds the opencplc.json root from any directory inside the workspace,
or from a local project outside it, whose makefile names its workspace.
Loads and persists configuration, fetches framework refs once per run,
keeps the Core checkout present and answers what projects exist here.
"""

import os, re, sys, json
from xaeian import Print, Ico, FILE, DIR, JSON, PATH, replace_end, set_context, grey
from .config import URL_CORE, DIR_PROJECTS, DIR_FRAMEWORK, DIR_TESTS, DIR_BOOT, FORGE_HEADER
from .args import flag
from . import utils

p = Print()

#----------------------------------------------------------------------------------- Root discovery

def find_workspace(start:str=".") -> str|None:
  """Nearest directory at or above `start` holding opencplc.json."""
  path = PATH.normalize(os.path.abspath(start)) # the process cwd: no file root is set yet
  while not FILE.exists(f"{path}/opencplc.json"):
    parent = PATH.dirname(path)
    if parent == path: return None
    path = parent
  return path

def project_from_path(path:str, pro_root:str) -> str|None:
  """
  Folder of the project holding `path`: the closest dir with main.h under `pro_root`,
  or `.tests/` of a Core, the folder of the Core itself.
  """
  if not PATH.is_under(path, pro_root): return None
  name = PATH.rel(path, pro_root)
  while name:
    tests = PATH.basename(name) == DIR_TESTS
    # `.tests/` of a project only sets its tests up, whatever `main.h` it holds
    if tests and utils.is_core(PATH.dirname(name)): return name
    if not tests and FILE.exists(f"{pro_root}/{name}/main.h"): return name
    name = PATH.dirname(name)
  return None

def linked_workspace(start:str=".") -> str|None:
  """
  Workspace the makefile of a local project names, in `start` or a folder above it.

  Only a makefile Forge wrote counts, as one of another tool may hold its own `WORKSPACE`.
  A project of the workspace spells it from its own folder, so only an absolute one counts.
  A workspace gone from there exits, since the project needs a load from another one.
  """
  path = PATH.normalize(os.path.abspath(start)) # the process cwd: no file root is set yet
  while True:
    lines = utils.load_lines(f"{path}/makefile")
    if lines and lines[0].startswith(FORGE_HEADER):
      found = utils.get_vars(utils.lines_clear(lines, "#"), ["WORKSPACE"], ":=", required=False)
      root = found.get("WORKSPACE", "")
      if PATH.is_abs(root):
        if FILE.exists(f"{root}/opencplc.json"): return root
        p.err(f"Workspace {utils.color_folder(root)} of this project "
          f"has no {utils.color_config('opencplc.json')}")
        p.run(f"Load the project from a workspace with {utils.color_command('opencplc <path>')}")
        sys.exit(1)
    parent = PATH.dirname(path)
    if parent == path: return None
    path = parent

def enter_workspace(named:str="") -> str:
  """
  Move to the nearest workspace root, or to the one a local project names.

  The makefile of a local project names it, found from the working directory
  or from `named`, the path of a project the command line gives.
  Returns the original working directory.
  """
  cwd = os.getcwd()
  root = find_workspace() or linked_workspace()
  if not root and named and is_path(named): root = linked_workspace(os.path.join(cwd, named))
  root = root or cwd
  if not os.path.samefile(root, cwd):
    os.chdir(root) # subprocesses (git, make) follow the process cwd
    p.inf(f"Workspace: {utils.color_folder(root)}")
  # `xaeian` file API follows its own root: import-time cwd, or exe dir when frozen
  set_context(root_path=root)
  return cwd

#------------------------------------------------------------------------------------ Configuration

def forge_config(templates:dict) -> dict:
  """Load and normalize opencplc.json; no network access and no writes here."""
  template = templates["opencplc.json"]
  cfg = JSON.load("opencplc.json", template)
  missing = utils.find_missing_keys(template, cfg)
  if missing:
    p.err(f"Missing key {utils.color_symbol(missing[0])} in {utils.color_config('opencplc.json')}")
    p.run(f"Add it back, or remove {utils.color_config('opencplc.json')} to start from defaults")
    sys.exit(1)
  # A save keeps only documented fields, `ignore` when set and Forge's own version cache
  cfg = {k: cfg[k] for k in (*template, "ignore", "available-versions") if k in cfg}
  cfg["stlink"] = cfg["stlink"] if isinstance(cfg["stlink"], dict) else {}
  ignore = cfg.get("ignore", [])
  if not isinstance(ignore, list) or not all(isinstance(pattern, str) for pattern in ignore):
    p.err(f"Key {utils.color_symbol('ignore')} in {utils.color_config('opencplc.json')} "
      "takes a list of patterns")
    example = '"ignore": ["demo/"]'
    p.run(f"Write it as {utils.color_symbol(example)}")
    sys.exit(1)
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

_refs_fresh = False

def ensure_refs(forge_cfg:dict, yes:bool) -> list[str]:
  """Framework refs from GitHub, fetched once per run and cached in opencplc.json."""
  global _refs_fresh
  if _refs_fresh: return forge_cfg["available-versions"]
  utils.ensure_git(yes)
  versions = utils.git_get_refs(URL_CORE, "--ref")
  if versions:
    forge_cfg["available-versions"] = versions
    _refs_fresh = True
    persist_config(forge_cfg)
  else:
    p.wrn(f"No internet access or {utils.color_link('GitHub')} is not responding")
    if not forge_cfg.get("available-versions"):
      p.err("First run requires network access to fetch available framework versions")
      sys.exit(1)
  return forge_cfg["available-versions"]

def framework_version(args, forge_cfg:dict) -> str:
  """
  Core version of this run: -f, else the workspace default.

  A project in Core builds with the Core it lies in, so -f has no say over it.
  """
  fw_ver = utils.version_active(args.framework, forge_cfg)
  core = utils.core_version(args.name or "")
  if core and args.framework and fw_ver != core:
    p.err(f"Project {utils.color_file(args.name)} lies in Core {utils.color_version(core)} "
      "and builds with it")
    p.run(f"Drop flag {flag.f}")
    sys.exit(1)
  return core or fw_ver

def ensure_framework(fw_ver:str, forge_cfg:dict, yes:bool):
  """Clone the framework when missing and sanity-check its layout."""
  fw_dir = PATH.resolve(utils.core_dir(fw_ver), read=False)
  # Already cloned versions work offline, even when gone from remote
  if not DIR.exists(fw_dir):
    utils.version_check(fw_ver, ensure_refs(forge_cfg, yes),
      f"{Ico.RUN} Check version list: {flag.fv}")
    utils.git_clone_missing(URL_CORE, fw_dir, fw_ver, yes)
  if not DIR.exists(f"{fw_dir}/hal") or not DIR.exists(f"{fw_dir}/lib"):
    p.err(f"Framework {utils.color_version(fw_ver)} is incomplete or corrupted")
    p.inf(f"Try removing {utils.color_folder(fw_dir)} and run again")
    sys.exit(1)

#----------------------------------------------------------------------------------- Active project

def makefile_info() -> dict|None:
  """Active project of this workspace, read from the root dispatcher."""
  if not FILE.exists("makefile"): return None
  lines = utils.lines_clear(utils.load_lines("makefile"), "#")
  return utils.get_vars(lines, ["ACTIVE"], ":=", required=False) or None

def reload_from_cwd(args, cwd:str) -> bool:
  """
  A run on a project without its name, inside a project directory: that project is the target.

  Outside the workspace it is the local project holding `cwd`.
  """
  if PATH.is_under(cwd, "."): name = utils.project_name(project_from_path(cwd, ".") or "")
  else: name = local_project_at(cwd)
  if not name: return False
  args.name = name
  return True

def reload_from_makefile(args, make_info:dict|None):
  """A run on a project without its name, outside any project: the active one of the dispatcher."""
  args.name = utils.project_name((make_info or {}).get("ACTIVE", ""))
  if not args.name:
    p.err("No active project in this workspace")
    p.run(f"Load one with {utils.color_command('opencplc <name>')}")
    sys.exit(1)

def stlink_bind(forge_cfg:dict, pro_id:str, serial:str|None) -> str:
  """
  ST-Link of a project in opencplc.json: `serial` binds one, "" clears it, `None` leaves it.

  Returns the one bound now, "" without.
  """
  bound = forge_cfg["stlink"]
  if serial:
    bound[pro_id] = serial
    p.ok(f"ST-Link {utils.color_value(serial)} bound to {utils.color_file(pro_id)}")
  elif serial == "" and bound.pop(pro_id, None) is not None:
    p.ok(f"ST-Link binding of {utils.color_file(pro_id)} cleared")
  if serial is not None: persist_config(forge_cfg)
  return bound.get(pro_id, "")

#------------------------------------------------------------------------------------ Local project

# The makefile of a local project holds its path and that of the workspace in full:
# make cuts a word at a space or `#`, `cmd.exe` a command at `&`, and make reads ANSI alone
SAFE_PATH = re.compile(r"(?:[A-Za-z]:)?[A-Za-z0-9_.~/-]+")

def is_path(name:str) -> bool:
  """
  `True` for a path, which names a project from anywhere: `.` or `..` first, or absolute.

  A name in the workspace never starts so, `validate_project_name` refuses both forms.
  """
  return name.replace("\\", "/").split("/")[0] in (".", "..") or PATH.is_abs(name)

def path_name(path:str, cwd:str) -> str:
  """
  Project `path` names, going from `cwd`: one in the workspace by its name, one outside by itself.

  A local project goes by its absolute path, as `utils.full_path` spells it.
  A folder of the workspace beside its projects, or one holding the workspace, exits,
  and so does a local one on a path its makefile could not hold.
  """
  full = utils.full_path(os.path.join(cwd, path))
  if not FILE.exists("opencplc.json"):
    p.err("A local project builds with a workspace, and none is found here")
    p.run(f"Load it once from a workspace with {utils.color_command(f'opencplc {full}')}")
    sys.exit(1)
  # Where a folder lies goes by the disk, through links and `subst` drives
  if PATH.is_under(full, ".", real=True):
    name = utils.project_name(PATH.rel(PATH.real(full), PATH.real(".")))
    if name: return name
    p.err(f"{utils.color_folder(full)} is no project folder of the workspace")
    p.run(f"Point at one in {grey(f'{DIR_PROJECTS}/')}, in a Core or outside the workspace")
    sys.exit(1)
  if PATH.is_under(".", full, real=True):
    p.err(f"{utils.color_folder(full)} holds the workspace, a project cannot")
    sys.exit(1)
  if not PATH.basename(full):
    p.err(f"{utils.color_folder(full)} is the root of a drive, "
      "a project needs a folder of its own")
    sys.exit(1)
  for where in (full, utils.full_path(".")):
    if SAFE_PATH.fullmatch(where): continue
    p.err(f"Path {utils.color_folder(where)} holds a character "
      "make or the console reads as syntax")
    p.run("Keep the project and the workspace on paths "
      f"of ASCII letters, digits and {utils.color_symbol('_.~-')}")
    sys.exit(1)
  return full

def local_project_at(path:str) -> str:
  """Local project holding `path`: the nearest folder at or above it with `main.h`, "" without."""
  path = utils.full_path(path)
  while True:
    # `.tests/main.h` sets up the tests of the project above
    if PATH.basename(path) != DIR_TESTS and FILE.exists(f"{path}/main.h"): return path
    parent = PATH.dirname(path)
    if parent == path: return ""
    path = parent

#-------------------------------------------------------------------------------- Project inventory

def project_inventory(name:str|None) -> dict[str, str]:
  """
  Projects by name: all of `projects/`, and those of the Core `name` lies in, itself too.

  A local `name` joins them by its path, once it holds `main.h`.
  """
  projects = utils.get_project_list(DIR_PROJECTS)
  if name and utils.is_local(name):
    if FILE.exists(f"{name}/main.h"): projects[name] = name
    return projects
  core = utils.core_version(name or "")
  if not core: return projects
  home = f"{DIR_FRAMEWORK}/{core}"
  # `.boot/` has a `main.h` for the bootloader build alone, never loaded as a project
  found = utils.get_project_list(home)
  projects |= {f"{home}/{key}": path for key, path in found.items() if key != DIR_BOOT}
  tests = PATH.resolve(utils.project_dir(home), read=False)
  if DIR.exists(tests): projects[home] = tests # the Core itself is a project of its tests
  return projects

def project_select(args, projects:dict, ignore:list[str]):
  """-l listing and picking a project by its number on that list, which leaves out `ignore`."""
  if not (args.project_list or (args.name and args.name.isdigit())): return
  listed = {name: path for name, path in projects.items() if not utils.ignored(name, ignore)}
  if not listed:
    p.wrn("No projects found")
    p.run(f"Create one with {utils.color_command('opencplc -n <name>')}")
    sys.exit(1)
  for i, (name, path) in enumerate(listed.items(), 1):
    if args.project_list:
      path = replace_end(PATH.local(path), name, "")
      nbr = utils.color_value(str(i).ljust(3))
      p(f"{nbr} {grey(path)}{utils.color_file(name)}")
    elif int(args.name) == i:
      args.name = name
      break
  if args.project_list: sys.exit(0)
