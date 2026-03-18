# opencplc/args.py

import argparse, sys
from dataclasses import dataclass
from xaeian import Color, Print

p = Print()

class Flag:
  """Colored flag display strings."""
  n = f"{Color.GREY}-n --new{Color.END}"
  e = f"{Color.GREY}-e --example{Color.END}"
  r = f"{Color.GREY}-r --reload{Color.END}"
  d = f"{Color.GREY}-d --delete{Color.END}"
  g = f"{Color.GREY}-g --get{Color.END}"
  f = f"{Color.GREY}-f --framework{Color.END}"
  F = f"{Color.GREY}-F --framework_versions{Color.END}"
  b = f"{Color.GREY}-b --board{Color.END}"
  c = f"{Color.GREY}-c --chip{Color.END}"
  m = f"{Color.GREY}-m --memory{Color.END}"
  o = f"{Color.GREY}-o --opt-level{Color.END}"
  i = f"{Color.GREY}-i --info{Color.END}"

flag = Flag()

@dataclass
class Args:
  name: str = ""
  new: str|bool = False
  example: str|bool = False
  reload: bool = False
  delete: str|bool = False
  get: list[str] = None
  board: str = ""
  chip: str = ""
  memory: list[int] = None
  framework: str = ""
  opt_level: str = "Og"
  project_list: bool = False
  info: bool = False
  framework_versions: bool = False
  version: bool = False
  assets: str|None = None
  update: str|None = None
  yes: bool = False
  hash_list: list[str] = None
  hash_title: str = ""
  hash_define: bool = False

def fmt(prog):
  return argparse.RawDescriptionHelpFormatter(prog, max_help_position=34, width=100)

EXAMPLE_USED = """
example used:
  opencplc -n myapp -b uno           Create new project for OpenCPLC Uno
  opencplc -n myapp -c STM32G081     Create bare-metal project for STM32G081
  opencplc -r                        Reload current project from makefile
  opencplc -l                        List all available projects
  opencplc myapp                     Load project 'myapp'
  opencplc 3                         Load project #3 from list
"""

class MyParser(argparse.ArgumentParser):
  def format_help(self):
    return "\n" + super().format_help().rstrip() + "\n\n"

def load_args() -> Args:
  parser = MyParser(
    description=f"{Color.TEAL}OpenCPLC Forge{Color.GREY}:{Color.END} Project configuration and build tool",
    formatter_class=fmt,
    add_help=False,
    usage=argparse.SUPPRESS,
    epilog=EXAMPLE_USED
  )
  # Project selection
  parser.add_argument("name", type=str, nargs="?", default="",
    help="Project name or number from list")
  # Project actions
  parser.add_argument("-n", "--new", type=str, nargs="?", const=True, metavar="NAME",
    help="Create new project (optionally with NAME)")
  parser.add_argument("-e", "--example", type=str, nargs="?", const=True, metavar="NAME",
    help="Create/load example project from Demo repository")
  parser.add_argument("-r", "--reload", action="store_true",
    help="Reload project configuration from existing makefile")
  parser.add_argument("-d", "--delete", type=str, nargs="?", const=True, metavar="NAME",
    help="Delete project and its files")
  parser.add_argument("-g", "--get", nargs='+', metavar=("URL", "REF"),
    help="Clone project from GIT repository or download ZIP", default=[])
  # Hardware configuration
  parser.add_argument("-b", "--board", type=str, metavar="BOARD",
    help="Target board: Uno, Dio, Aio, Eco, Custom, None", default="")
  parser.add_argument("-c", "--chip", type=str, metavar="CHIP",
    help="Target MCU: STM32G0C1, STM32G081, STM32WB55, HOST", default="")
  parser.add_argument("-m", "--memory", type=int, nargs="*", metavar=("FLASH", "RAM"),
    help="Override memory size in kB: FLASH RAM [RESERVED]", default=[])
  # Build configuration  
  parser.add_argument("-f", "--framework", type=str, metavar="VER",
    help="Framework version (tag/branch): latest, develop, 1.0.0", default="")
  parser.add_argument("-o", "--opt-level", type=str, metavar="LEVEL",
    help="Compiler optimization: O0 (debug), Og (default), O1", default="Og")
  # Information
  parser.add_argument("-l", "--list", action="store_true",
    help="List all projects in current workspace")
  parser.add_argument("-i", "--info", action="store_true",
    help="Show detailed project configuration")
  parser.add_argument("-F", "--framework-versions", action="store_true",
    help="List available framework versions from GitHub")
  parser.add_argument("-v", "--version", action="store_true",
    help="Show OpenCPLC Forge version and exit")
  # Utilities
  parser.add_argument("-a", "--assets", type=str, nargs="?", const="assets", metavar="DIR",
    help="Download datasheets and reference manuals to DIR")
  parser.add_argument("-u", "--update", type=str, nargs="?", const="latest", metavar="VER",
    help="Update OpenCPLC Forge to specified version (default: latest)")
  parser.add_argument("-y", "--yes", action="store_true",
    help="Auto-confirm all prompts (non-interactive mode)")
  # Hash utilities
  parser.add_argument("-hl", "--hash-list", nargs="+", metavar="TAG",
    help="Generate DJB2 hash enum from tag list")
  parser.add_argument("-ht", "--hash-title", type=str, metavar="NAME",
    help="Enum type name for hash generation", default="")
  parser.add_argument("-hd", "--hash-define", action="store_true",
    help="Use #define instead of enum for hash output")
  parser.add_argument("-h", "--help", action="help",
    help="Show this help message and exit")
  
  ns = parser.parse_args()
  return Args(
    name=ns.name,
    new=ns.new,
    example=ns.example,
    reload=ns.reload,
    delete=ns.delete,
    get=ns.get or [],
    board=ns.board,
    chip=ns.chip,
    memory=ns.memory or [],
    framework=ns.framework,
    opt_level=ns.opt_level,
    project_list=ns.list,
    info=ns.info,
    framework_versions=ns.framework_versions,
    version=ns.version,
    assets=ns.assets,
    update=ns.update,
    yes=ns.yes,
    hash_list=ns.hash_list,
    hash_title=ns.hash_title,
    hash_define=ns.hash_define,
  )

def check_flags(args, *flags:tuple[str, str]) -> str|None:
  """Check for mutually exclusive flags. Pass (attr, display) tuples."""
  used_attr, used_disp = None, None
  for attr, disp in flags:
    if getattr(args, attr, False):
      if used_attr:
        p.err(f"Flags {used_disp}, {disp} cannot be used together")
        sys.exit(1)
      used_attr, used_disp = attr, disp
  return used_attr