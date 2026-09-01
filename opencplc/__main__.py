# opencplc/__main__.py

"""
CLI entry point: parses arguments and orchestrates the run.

The moving parts live in their own modules: `workspace` (root, config, refs,
project inventory), `configure` (project configuration), `actions` (one-shot
answers), `resolver` (the project model) and `project` (generators).
"""

import signal, sys
from xaeian import Print, Color as c, PATH
from .config import URL_DEMO, DIR_EXAMPLES
from .args import flag, load_args, check_flags
from .templates import load_templates
from .project import prepare_project, generate
from .resolver import resolve_project
from .actions import info_actions, info_show
from .configure import config_new, config_load, opt_normalize
from .workspace import (
  enter_workspace, forge_config, persist_config, ensure_refs, paths_setup,
  ensure_framework, makefile_info, reload_from_cwd, reload_from_makefile,
  project_select, project_delete, stlink_bind,
)
from . import utils

p = Print()

def handle_sigint(signum, frame):
  """Ctrl+C ends the run quietly."""
  p.wrn(f"Closing {c.GREY}(Ctrl+C){c.END}...")
  sys.exit(0)

signal.signal(signal.SIGINT, handle_sigint)

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

def main():
  """Parse arguments, settle the workspace and run the requested action."""
  args = load_args()
  templates = load_templates()
  cwd = enter_workspace()
  forge_cfg = forge_config(templates)
  if info_actions(args, forge_cfg): sys.exit(0)
  # Mutually exclusive modes; mode flags may also carry the project name
  check_flags(args, ("reload", flag.r), ("info", flag.i))
  check_flags(args, ("new", flag.n), ("delete", flag.d), ("get", flag.g))
  args.name, args.new = utils.assign_name(args.name, args.new, flag.n)
  args.name, args.reload = utils.assign_name(args.name, args.reload, flag.r)
  args.name, args.delete = utils.assign_name(args.name, args.delete, flag.d)
  persist_config(forge_cfg, create=bool(args.new or args.example)) # a workspace starts here
  if not forge_cfg.get("available-versions"):
    ensure_refs(forge_cfg, args.yes) # first run: the version list must exist
  PATHS, fw_ver = paths_setup(args, forge_cfg)
  make_info = makefile_info()
  # -r <name> and -r inside a project directory touch that project only, never the workspace
  scoped = bool(args.reload and args.name)
  if not args.name and (args.reload or args.info):
    scoped = reload_from_cwd(args, PATHS, cwd)
    if not scoped:
      reload_from_makefile(args, PATHS, make_info)
  # A new project takes the workspace default Core, an existing one the version it pins
  if args.new:
    ensure_framework(fw_ver, PATHS, forge_cfg, args.yes)
  # Remote project - name read from its main.h when not given
  if args.get:
    if not args.get[0].endswith(".zip"):
      utils.install_git(args.yes)
    ref = args.get[1] if len(args.get) > 1 else None
    args.name = utils.project_remote(args.get[0], PATHS["pro"], ref, args.name)
  if args.example:
    utils.install_git(args.yes)
    utils.git_clone_missing(URL_DEMO, DIR_EXAMPLES, "main", args.yes)
    p.inf(f"Examples in {c.ORANGE}{DIR_EXAMPLES}{c.END}, "
      f"load one with {c.CYAN}opencplc examples/<name>{c.END}")
    sys.exit(0)
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
    project_delete(args, PRO, make_info, forge_cfg)
  PATHS["pro"] = PATH.resolve(f"{PATHS['pro']}/{args.name}", read=False)
  if args.new:
    CFG = config_new(args, PRO, PATHS, fw_ver, forge_cfg)
  else:
    CFG = config_load(args, PRO, PATHS, fw_ver, forge_cfg)
  ensure_framework(CFG["fw_ver"], PATHS, forge_cfg, args.yes)
  opt_normalize(CFG)
  stlink_bind(forge_cfg, f"projects/{args.name}", args.stlink)
  if args.info:
    info_show(resolve_project(CFG, PATHS, forge_cfg))
  ensure_toolchains(CFG["platform"] == "STM32", args.yes)
  prepare_project(CFG, PATHS)
  model = resolve_project(CFG, PATHS, forge_cfg)
  generate(model, activate=not scoped)

if __name__ == "__main__":
  main()
