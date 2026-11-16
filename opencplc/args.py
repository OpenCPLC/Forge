# opencplc/args.py

"""
Command line: every flag declared once by `option()`.

That one call adds the flag to the parser and keeps its colored name for messages,
`flag.n` for `-n --new`; the parsed values come as `Args`, a field per flag.
"""

import argparse, sys
from dataclasses import dataclass, field
from types import SimpleNamespace
from xaeian import Color, Print

p = Print()

@dataclass
class Args:
  """Parsed command line; every field holds the default of its flag until the flag is given."""
  name: str = ""
  new: str|bool = False
  demo: bool = False
  reload: bool = False
  delete: str|bool = False
  get: list[str] = field(default_factory=list)
  board: str = ""
  plc: bool = False
  drv: str = ""
  boot: bool = False
  chip: str = ""
  memory: list[int] = field(default_factory=list)
  framework: str = ""
  opt_level: str = ""
  project_list: bool = False
  info: bool = False
  framework_versions: bool = False
  version: bool = False
  stlink: str|None = None
  size: list[str]|None = None
  program: str|bool|None = None
  lock: int|None = None
  keygen: list[str]|None = None
  upload: list[str]|None = None
  pack: list[str]|None = None
  test: list[str]|None = None
  lint: bool = False
  assets: str|None = None
  update: str|None = None
  yes: bool = False
  hash_list: list[str]|None = None
  hash_title: str = ""
  hash_define: bool = False

EXAMPLE_USED = """
example used:
  opencplc -n myapp -b uno        Create new project for OpenCPLC Uno
  opencplc -n myapp -c STM32G081  Create bare-metal project for STM32G081
  opencplc -r                     Reload the active project
  opencplc -l                     List all available projects
  opencplc myapp                  Load project 'myapp'
  opencplc 3                      Load project #3 from list
"""

class Parser(argparse.ArgumentParser):
  """argparse parser with a blank line around the help text."""
  def format_help(self):
    return "\n" + super().format_help().rstrip() + "\n\n"

def fmt(prog):
  """Help formatter with wider columns."""
  return argparse.RawDescriptionHelpFormatter(prog, max_help_position=34, width=100)

PARSER = Parser(
  description=f"{Color.TEAL}OpenCPLC Forge{Color.GREY}:{Color.END} "
    "Project configuration and build tool",
  formatter_class=fmt,
  add_help=False,
  usage=argparse.SUPPRESS,
  epilog=EXAMPLE_USED,
)
flag = SimpleNamespace() # colored names for messages: `flag.n` is `-n --new`, `flag.lock` `--lock`

def option(*names:str, **kwargs):
  """One flag of the command line: in the parser, and its colored name on `flag`."""
  PARSER.add_argument(*names, **kwargs)
  if names[0].startswith("-"):
    setattr(flag, names[0].lstrip("-"), f"{Color.GREY}{' '.join(names)}{Color.END}")

# Project selection
option("name", type=str, nargs="?", default="", help="Project name or number from list")
# Project actions
option("-n", "--new", type=str, nargs="?", const=True, default=False, metavar="NAME",
  help="Create new project (optionally with NAME)")
option("-e", "--demo", action="store_true", help="Download Demo projects into projects/demo")
option("-r", "--reload", action="store_true",
  help="Reload the active project, or the one in the current directory")
option("-d", "--delete", type=str, nargs="?", const=True, default=False, metavar="NAME",
  help="Delete project and its files")
option("-g", "--get", nargs="+", metavar=("URL", "REF"), default=[],
  help="Clone project from Git repository or download ZIP")
# Hardware configuration
option("-b", "--board", type=str, metavar="BOARD", default="",
  help="Board from the Core (uno); without it the project has no board")
option("-c", "--chip", type=str, metavar="CHIP", default="",
  help="Target MCU: STM32G0C1, STM32G081, STM32WB55, HOST")
option("-P", "--plc", action="store_true", help="Add the PLC layer to a project without a board")
option("-D", "--drv", type=str, metavar="DRIVERS", default="",
  help="Core drivers for a new project, comma separated")
option("-B", "--boot", action="store_true",
  help="Put the new project behind the bootloader of Core: boot.h and its #include in main.h")
option("-m", "--memory", type=int, nargs="*", metavar=("FLASH", "RAM"), default=[],
  help="Override memory size in kB: FLASH RAM [RESERVED]")
# Build configuration
option("-f", "--framework", type=str, metavar="VER", default="",
  help="Core version (tag/branch) for a new project, over main.h until a load without it, "
    "or alone: download it")
option("-o", "--opt-level", type=str, metavar="LEVEL", default="",
  help="Optimization level: O0, Og (default), O1, O2, O3, Os")
option("-s", "--stlink", type=str, nargs="?", const="", metavar="SERIAL",
  help="Bind an ST-Link serial to the project; -s alone clears the binding")
# Information
option("-l", "--list", dest="project_list", action="store_true",
  help="List all projects in current workspace")
option("-i", "--info", action="store_true", help="Show detailed project configuration")
option("-F", "--framework-versions", action="store_true", help="List Core versions")
option("-v", "--version", action="store_true", help="Show OpenCPLC Forge version and exit")
# Utilities
option("-z", "--size", nargs="+", metavar="ARG",
  help="Report FLASH and RAM of an .elf: ELF FLASH_kB RAM_kB, "
    "then CPU CORE PROJECT for the stack of each thread and the quick rules of make lint")
option("-p", "--pack", nargs="+", metavar="FILE",
  help="Pack the flash image: APP.hex OUT.hex [BOOT [KEYS NUMBER [dist]]], a makefile step")
option("--test", nargs="+", metavar="PATH",
  help="Run test programs: BUILD NAME [NAME ...], a makefile step")
option("--lint", action="store_true",
  help="Check the build of the project: rules of Forge, cppcheck and the gcc analyzer")
option("--program", type=str, nargs="?", const=True, metavar="FILE",
  help="Send a .hex to the board through the programmer; alone, the one make dist left")
option("--lock", type=int, nargs="?", const=1, choices=(0, 1, 2), metavar="LEVEL",
  help="Lock board for production: 1 RDP1, 2 for good, 0 unlocks, erasing flash")
option("--keygen", nargs="+", metavar=("NAME", "COUNT"),
  help="Make or take product key NAME and COUNT-1 spare ones, add them to BOOT_KEYS")
option("--upload", nargs="+", metavar=("FILE", "PORT"),
  help="Send an update image over the console: FILE [PORT], a makefile step")
option("-a", "--assets", type=str, nargs="?", const="assets", metavar="DIR",
  help="Download datasheets and reference manuals to DIR")
option("-u", "--update", type=str, nargs="?", const="latest", metavar="VER",
  help="Update OpenCPLC Forge to specified version (default: latest)")
option("-y", "--yes", action="store_true", help="Auto-confirm all prompts (non-interactive mode)")
# Hash utilities
option("-hl", "--hash-list", nargs="+", metavar="TAG",
  help="Generate DJB2 hash enum from tag list")
option("-ht", "--hash-title", type=str, metavar="NAME", default="",
  help="Enum type name for hash generation")
option("-hd", "--hash-define", action="store_true",
  help="Use #define instead of enum for hash output")
option("-h", "--help", action="help", help="Show this help message and exit")

def load_args() -> Args:
  """Parse `sys.argv` into `Args`; no argument at all shows the help."""
  if len(sys.argv) == 1:
    PARSER.print_help()
    sys.exit(0)
  return Args(**vars(PARSER.parse_args()))

def given(args:Args) -> set[str]:
  """Fields of `args` the command line set, away from their defaults."""
  defaults = vars(Args())
  return {name for name, value in vars(args).items() if value != defaults[name]}

def check_flags(args, *flags:tuple[str, str]):
  """Exit when mutually exclusive flags are combined. Pass (attr, display) tuples."""
  used = None
  for attr, disp in flags:
    if getattr(args, attr, False):
      if used:
        p.err(f"Flags {used}, {disp} cannot be used together")
        sys.exit(1)
      used = disp
