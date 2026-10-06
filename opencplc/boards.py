# opencplc/boards.py

"""
Ready boards discovered in the selected Core.

A board is one directory `brd/<name>/`: an .ini manifest, header `opencplc_<name>.h`, sources.
Manifest gives defaults of a new project: chip, initial memory and clock, drivers it needs.
Optional `reserve_kB` is flash the board keeps for itself, taken off the top like -m third value.
Only `plc` is binding: a board that needs the PLC layer does not build without it.
A board that does not need it still accepts it from -P.
Nothing here is hard-coded in Forge, adding a board means adding a directory to Core.
"""

import re, sys
from dataclasses import dataclass, field
from xaeian import Print, Color as c, FILE, DIR, INI, PATH
from .platforms import CHIPS

p = Print()

NAME_RX = re.compile(r"^[a-z0-9_]+$")             # board directory
TITLE_RX = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")  # board name, one chunk of `PRO_BOARD_*`
REQUIRED = ("name", "chip", "plc", "flash_kB", "ram_kB", "clock_Hz")
NUMBERS = ("flash_kB", "reserve_kB", "ram_kB", "clock_Hz")

@dataclass
class Board:
  """One ready board as described by its manifest."""
  name: str   # directory name, e.g. "card_g0"
  title: str  # name from the manifest, as it reads in C and in messages, e.g. "CardG0"
  dir: str    # workspace-relative board directory
  plc: bool   # board needs the PLC layer; a project may add it anyway with -P
  chip: str   # canonical chip key from `CHIPS`
  flash_kB: int
  reserve_kB: int
  ram_kB: int
  freq_Hz: int
  drivers: list[str] = field(default_factory=list)

def board_list(boards:dict[str, "Board"]) -> str:
  """Board names of a Core, colored and comma separated, for a message."""
  listed = ", ".join(f"{c.TURQUS}{b.title}{c.END}" for b in boards.values())
  return listed or f"{c.GREY}none{c.END}"

def board_key(name:str) -> str:
  """Comparable form of a board name: neither case nor underscores matter."""
  return name.replace("_", "").lower()

def parse_drivers(value:str) -> list[str]:
  """Normalized, unique driver names from a comma-separated list."""
  return list(dict.fromkeys(n.strip().lower() for n in value.split(",") if n.strip()))

def parse_board(ini_path:str, name:str, board_dir:str) -> Board:
  """Board from its manifest; raises `ValueError` naming what is wrong."""
  if not NAME_RX.match(name):
    raise ValueError(f"board name '{name}' - use lowercase letters, digits and '_'")
  if board_key(name) == "none":
    raise ValueError("board name 'None' is reserved for a project without a board")
  section = INI.load(ini_path) # plain key = value lines, each read as bool, int or text
  missing = [k for k in REQUIRED if k not in section]
  if missing: raise ValueError(f"missing field '{missing[0]}'")
  chip = next((k for k in CHIPS if k.upper() == str(section["chip"]).upper()), None)
  if chip is None or CHIPS[chip]["platform"] != "STM32":
    raise ValueError(f"unknown chip '{section['chip']}'")
  title = str(section["name"])
  if not TITLE_RX.match(title):
    raise ValueError(f"name '{title}' - use letters and digits, no separators")
  if board_key(title) != board_key(name):
    raise ValueError(f"name '{title}' does not match directory '{name}'")
  if not isinstance(section["plc"], bool):
    raise ValueError(f"field 'plc' is '{section['plc']}', use true or false")
  header = f"opencplc_{name}.h"
  if not FILE.exists(f"{PATH.dirname(ini_path)}/{header}"):
    raise ValueError(f"missing public header {header}")
  # `type`, not `isinstance`, which counts `true` as an int
  wrong = next((k for k in NUMBERS if type(section.get(k, 0)) is not int), None)
  if wrong: raise ValueError(f"field '{wrong}' is '{section[wrong]}', use a whole number")
  flash_kB, reserve_kB = section["flash_kB"], section.get("reserve_kB", 0)
  if not 0 <= reserve_kB < flash_kB:
    raise ValueError(f"reserve_kB {reserve_kB} does not fit in flash_kB {flash_kB}")
  return Board(
    name=name, title=title, dir=board_dir, plc=section["plc"], chip=chip,
    flash_kB=flash_kB, reserve_kB=reserve_kB, ram_kB=section["ram_kB"],
    freq_Hz=section["clock_Hz"],
    drivers=parse_drivers(str(section.get("drivers") or "")),
  )

def load_boards(core_dir:str) -> dict[str, Board]:
  """Boards of a Core checkout: every brd/<name>/ with a manifest, keyed by name."""
  boards = {}
  for board_dir in sorted(DIR.folder_list(f"{core_dir}/brd")):
    name = PATH.basename(board_dir)
    inis = sorted(DIR.file_list(board_dir, exts=[".ini"], deep=False))
    if not inis: continue
    ini_path = inis[0] # the board's manifest, whatever its name
    try:
      boards[name] = parse_board(ini_path, name, PATH.local(board_dir))
    except ValueError as e:
      p.err(f"Invalid {c.ORANGE}{PATH.local(ini_path)}{c.END}: {e}")
      sys.exit(1)
  return boards

def board_pick(boards:dict[str, Board], name:str) -> Board:
  """Board by name, case-insensitive; exits listing what the Core offers."""
  key = next((k for k in boards if board_key(k) == board_key(name)), None)
  if key is None:
    p.err(f"Unknown board: {c.MAGNTA}{name}{c.END}")
    p.inf(f"Boards in this Core: {board_list(boards)}")
    sys.exit(1)
  return boards[key]
