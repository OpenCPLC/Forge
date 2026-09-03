# opencplc/args.py

"""Command line: flags, their colored names for messages and the parsed Args."""

import argparse, sys
from dataclasses import dataclass
from xaeian import Color, Print

p = Print()

class Flag:
  """Colored flag display strings."""
  n = f"{Color.GREY}-n --new{Color.END}"
  r = f"{Color.GREY}-r --reload{Color.END}"
  d = f"{Color.GREY}-d --delete{Color.END}"
  g = f"{Color.GREY}-g --get{Color.END}"
  b = f"{Color.GREY}-b --board{Color.END}"
  c = f"{Color.GREY}-c --chip{Color.END}"
  P = f"{Color.GREY}-P --plc{Color.END}"
  D = f"{Color.GREY}-D --dvr{Color.END}"
  m = f"{Color.GREY}-m --memory{Color.END}"
  f = f"{Color.GREY}-f --framework{Color.END}"
  o = f"{Color.GREY}-o --opt-level{Color.END}"
  i = f"{Color.GREY}-i --info{Color.END}"
  F = f"{Color.GREY}-F --framework-versions{Color.END}"

flag = Flag()

@dataclass
class Args:
  """Parsed command line; every flag has a neutral default."""
  name: str = ""
  new: str|bool = False
  demo: bool = False
  reload: bool = False
  delete: str|bool = False
  get: list[str] = None
  board: str = ""
  plc: bool = False
  dvr: str = ""
  chip: str = ""
  memory: list[int] = None
  framework: str = ""
  opt_level: str = ""
  project_list: bool = False
  info: bool = False
  framework_versions: bool = False
  version: bool = False
  stlink: str|None = None
  size: list[str] = None
  assets: str|None = None
  update: str|None = None
  yes: bool = False
  hash_list: list[str] = None
  hash_title: str = ""
  hash_define: bool = False

def fmt(prog):
  """Help formatter with wider columns."""
  return argparse.RawDescriptionHelpFormatter(prog, max_help_position=34, width=100)

EXAMPLE_USED = """
example used:
  opencplc -n myapp -b uno        Create new project for OpenCPLC Uno
  opencplc -n myapp -c STM32G081  Create bare-metal project for STM32G081
  opencplc -r                     Reload the active project
  opencplc -l                     List all available projects
  opencplc myapp                  Load project 'myapp'
  opencplc 3                      Load project #3 from list
"""

class MyParser(argparse.ArgumentParser):
  """argparse parser with a blank line around the help text."""
  def format_help(self):
    return "\n" + super().format_help().rstrip() + "\n\n"

def load_args() -> Args:
  """Parse sys.argv into Args."""
  parser = MyParser(
    description=f"{Color.TEAL}OpenCPLC Forge{Color.GREY}:{Color.END} "
      "Project configuration and build tool",
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
  parser.add_argument("-e", "--demo", action="store_true",
    help="Download Demo projects into projects/demo")
  parser.add_argument("-r", "--reload", action="store_true",
    help="Reload the active project, or the one in the current directory")
  parser.add_argument("-d", "--delete", type=str, nargs="?", const=True, metavar="NAME",
    help="Delete project and its files")
  parser.add_argument("-g", "--get", nargs='+', metavar=("URL", "REF"),
    help="Clone project from Git repository or download ZIP", default=[])
  # Hardware configuration
  parser.add_argument("-b", "--board", type=str, metavar="BOARD",
    help="Board from the Core (uno); without it the project has no board", default="")
  parser.add_argument("-c", "--chip", type=str, metavar="CHIP",
    help="Target MCU: STM32G0C1, STM32G081, STM32WB55, HOST", default="")
  parser.add_argument("-P", "--plc", action="store_true",
    help="Add the PLC layer to a project without a board")
  parser.add_argument("-D", "--dvr", type=str, metavar="DRIVERS", default="",
    help="Core drivers for a new project, comma separated")
  parser.add_argument("-m", "--memory", type=int, nargs="*", metavar=("FLASH", "RAM"),
    help="Override memory size in kB: FLASH RAM [RESERVED]", default=[])
  # Build configuration
  parser.add_argument("-f", "--framework", type=str, metavar="VER",
    help="Core version (tag/branch) for a new project, or a one-run override", default="")
  parser.add_argument("-o", "--opt-level", type=str, metavar="LEVEL",
    help="Optimization level: O0, Og (default), O1, O2, O3", default="")
  parser.add_argument("-s", "--stlink", type=str, nargs="?", const="", metavar="SERIAL",
    help="Bind an ST-Link serial to the project; -s alone clears the binding")
  # Information
  parser.add_argument("-l", "--list", action="store_true",
    help="List all projects in current workspace")
  parser.add_argument("-i", "--info", action="store_true",
    help="Show detailed project configuration")
  parser.add_argument("-F", "--framework-versions", action="store_true",
    help="List Core versions")
  parser.add_argument("-v", "--version", action="store_true",
    help="Show OpenCPLC Forge version and exit")
  # Utilities
  parser.add_argument("-z", "--size", nargs=3, metavar=("ELF", "FLASH_kB", "RAM_kB"),
    help="Report FLASH and RAM usage of an .elf against the chip memory")
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

  if len(sys.argv) == 1:
    parser.print_help()
    sys.exit(0)
  ns = parser.parse_args()
  return Args(
    name=ns.name,
    new=ns.new,
    demo=ns.demo,
    reload=ns.reload,
    delete=ns.delete,
    get=ns.get or [],
    board=ns.board,
    plc=ns.plc,
    dvr=ns.dvr,
    chip=ns.chip,
    memory=ns.memory or [],
    framework=ns.framework,
    opt_level=ns.opt_level,
    project_list=ns.list,
    info=ns.info,
    framework_versions=ns.framework_versions,
    version=ns.version,
    stlink=ns.stlink,
    size=ns.size,
    assets=ns.assets,
    update=ns.update,
    yes=ns.yes,
    hash_list=ns.hash_list,
    hash_title=ns.hash_title,
    hash_define=ns.hash_define,
  )

def check_flags(args, *flags:tuple[str, str]):
  """Exit when mutually exclusive flags are combined. Pass (attr, display) tuples."""
  used = None
  for attr, disp in flags:
    if getattr(args, attr, False):
      if used:
        p.err(f"Flags {used}, {disp} cannot be used together")
        sys.exit(1)
      used = disp