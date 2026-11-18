# opencplc/__main__.py

"""
CLI entry point: parses arguments and runs the stages of one run, a function each.

Modules stack up from the bottom, each importing only those below it:
`platforms` and `boards` describe the hardware, `model` holds the shapes the modules pass on,
`headers` reads main.h and boot.h, `workspace` settles root, config, refs and project inventory,
`configure` makes a `Config`, `resolver` the `Project` model of it, `project` writes its files,
and the commands act on them: `pack`, `cipher`, `upload`, `runner`, `lint`, `keygen`, `lock`
and `actions`.
"""

import signal, sys
from xaeian import Print, Color as c, PATH
from .config import URL_DEMO, DIR_DEMO, DIR_PROJECTS
from .args import flag, load_args, check_flags
from .templates import load_templates
from .model import Config
from .project import prepare_project, generate, project_delete
from .resolver import resolve_project, has_tests, tests_of
from .actions import info_actions, info_show, program_image
from .lint import run_lint
from .keygen import keygen
from .lock import lock_board
from .configure import config_new, config_load, opt_normalize
from .workspace import (
  enter_workspace, forge_config, persist_config, ensure_refs, framework_version,
  ensure_framework, makefile_info, reload_from_cwd, reload_from_makefile,
  is_path, path_name, project_inventory, project_select, stlink_bind,
)
from . import utils

p = Print()

def handle_sigint(signum, frame):
  """Ctrl+C ends the run quietly."""
  p.wrn(f"Closing {c.GREY}(Ctrl+C){c.END}...")
  sys.exit(0)

signal.signal(signal.SIGINT, handle_sigint)

def name_project(args, cwd:str, forge_cfg:dict) -> bool:
  """
  Project of the run named, after the flags that may carry its name; `True` when scoped to it.

  Without a name, a reload and the commands on a project take the folder of `cwd`,
  then the active project of the dispatcher.
  """
  # Mutually exclusive modes; mode flags may also carry the project name
  check_flags(args, ("reload", flag.r), ("info", flag.i))
  # --sign writes into boot.h of a project that exists already
  check_flags(args, ("new", flag.n), ("delete", flag.d), ("get", flag.g), ("sign", flag.sign))
  args.name, args.new = utils.assign_name(args.name, args.new, flag.n)
  args.name, args.reload = utils.assign_name(args.name, args.reload, flag.r)
  args.name, args.delete = utils.assign_name(args.name, args.delete, flag.d)
  # A path names a project from anywhere: from here on it goes by its name, outside by its path
  if args.name and is_path(args.name): args.name = path_name(args.name, cwd)
  persist_config(forge_cfg, create=bool(args.new or args.demo)) # a workspace starts here
  if not forge_cfg.get("available-versions"):
    ensure_refs(forge_cfg, args.yes) # first run: the version list must exist
  # -r <name> and -r inside a project directory touch that project only, never the workspace
  scoped = bool(args.reload and args.name)
  # These act on the active project when no name is given
  acting = args.program or args.sign or args.lock is not None or args.lint
  if not args.name and (args.reload or args.info or acting):
    scoped = reload_from_cwd(args, cwd)
    if not scoped:
      reload_from_makefile(args, makefile_info())
  return scoped

def fetch_project(args, fw_ver:str, forge_cfg:dict):
  """Core of a new project, the remote project of -g; Demo of -e ends the run."""
  # A new project takes the workspace default Core, an existing one the version it pins
  if args.new:
    ensure_framework(fw_ver, forge_cfg, args.yes)
  # Remote project: name read from its `main.h` when not given
  if args.get:
    if not args.get[0].endswith(".zip"):
      utils.ensure_git(args.yes)
    ref = args.get[1] if len(args.get) > 1 else None
    args.name = utils.project_remote(args.get[0], DIR_PROJECTS, ref, args.name)
  if args.demo:
    utils.ensure_git(args.yes)
    utils.git_clone_missing(URL_DEMO, DIR_DEMO, "main", args.yes)
    p.inf(f"Demo in {c.GREY}{DIR_DEMO}{c.END}, "
      f"load one with {utils.color_command('opencplc demo/<name>')}")
    sys.exit(0)

def pick_project(args, forge_cfg:dict) -> dict:
  """Projects of the workspace by name, the one of the run picked by -l or its number."""
  projects = project_inventory(args.name)
  project_select(args, projects, forge_cfg.get("ignore", []))
  if not args.name and not args.reload and not args.info:
    p.err("Project name not given")
    p.run(f"Load one with {utils.color_command('opencplc <name>')}, "
      f"or reload the active project with {flag.r}")
    sys.exit(1)
  # A local project goes by its folder, not by a name of the workspace
  if args.name and not utils.is_local(args.name):
    valid, reason = utils.validate_project_name(args.name)
    if not valid:
      p.err(f"Invalid project name: {c.MAGNTA}{reason}{c.END}")
      sys.exit(1)
  return projects

def configure_project(args, projects:dict, fw_ver:str, forge_cfg:dict) -> Config:
  """Config of the project, over the Core that builds it, with its ST-Link."""
  # The keys go into `boot.h` first, so this very run builds the project under them
  named = utils.project_key(projects, args.name)
  if args.sign and named:
    keygen(args.sign, named, PATH.resolve(projects[named], read=False))
  if args.new:
    cfg = config_new(args, projects, fw_ver)
  else:
    cfg = config_load(args, projects, fw_ver, forge_cfg)
  ensure_framework(cfg.fw_ver, forge_cfg, args.yes)
  opt_normalize(cfg)
  cfg.stlink = stlink_bind(forge_cfg, utils.project_dir(cfg.name), args.stlink)
  return cfg

def run_project(args, cfg:Config, scoped:bool):
  """What the flags ask of the project: -i, --lint, --program and --lock, or else a load."""
  if args.info:
    info_show(resolve_project(cfg))
  tests = has_tests(tests_of(cfg.name, utils.project_dir(cfg.name)))
  utils.ensure_toolchain(cfg.chip.platform == "STM32", args.yes, tests)
  if args.lint:
    sys.exit(run_lint(resolve_project(cfg)))
  # The factory programs the full image of `dist`, then locks the board
  if args.program or args.lock is not None:
    model = resolve_project(cfg)
    if args.program: program_image(model, args.program, args.yes)
    if args.lock is not None: lock_board(model, args.lock, args.yes)
    sys.exit(0)
  prepare_project(cfg)
  generate(resolve_project(cfg), activate=not scoped)

def main():
  """Parse arguments, settle the workspace and run what the flags ask for."""
  args = load_args()
  templates = load_templates()
  # A local project named by its path finds the workspace through its makefile, from anywhere
  named = next((n for n in (args.name, args.new, args.delete) if isinstance(n, str) and n), "")
  cwd = enter_workspace(named)
  forge_cfg = forge_config(templates)
  if info_actions(args, forge_cfg): sys.exit(0)
  scoped = name_project(args, cwd, forge_cfg)
  # After the name is known: a project in Core sets the version
  fw_ver = framework_version(args, forge_cfg)
  fetch_project(args, fw_ver, forge_cfg)
  projects = pick_project(args, forge_cfg)
  if args.delete:
    project_delete(args, projects, makefile_info(), forge_cfg)
  cfg = configure_project(args, projects, fw_ver, forge_cfg)
  run_project(args, cfg, scoped)

if __name__ == "__main__":
  main()
