# opencplc/boards.py

"""
Ready boards discovered in the selected Core.

A board is one directory `brd/<name>/` holding an .ini manifest, the public header
`opencplc_<name>.h` and its sources. The manifest gives the defaults of a new project:
the chip, the initial memory and clock and the drivers the board implementation needs.
Optional `reserve_kB` is flash the board keeps for itself, taken off the top like the third
value of -m.
Only `plc` is binding - a board that needs the PLC layer does not build without it,
while a board that does not still accepts it from -P. Nothing here is hard-coded in
Forge: adding a board means adding a directory to Core.
"""

import os, re, sys, configparser
from dataclasses import dataclass, field
from xaeian import Print, Color as c, PATH
from .platforms import CHIPS

p = Print()

NAME_RX = re.compile(r"^[a-z0-9_]+$")   # board directory
TITLE_RX = re.compile(r"^[A-Za-z][A-Za-z0-9]*$") # board name, one chunk of PRO_BOARD_*
REQUIRED = ("name", "chip", "plc", "flash_kB", "ram_kB", "clock_Hz")

@dataclass
class Board:
  """One ready board as described by its manifest."""
  name: str  # directory name, e.g. "card_g0"
  title: str # name from the manifest, as it reads in C and in messages, e.g. "CardG0"
  dir: str   # workspace-relative board directory
  plc: bool  # board needs the PLC layer; a project may add it anyway with -P
  chip: str  # canonical chip key from CHIPS
  flash_kB: int
  reserve_kB: int # flash the board keeps for itself, taken off the top
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
  """Board from its manifest; raises ValueError naming what is wrong."""
  if not NAME_RX.match(name):
    raise ValueError(f"board name '{name}' - use lowercase letters, digits and '_'")
  if board_key(name) == "none":
    raise ValueError("board name 'None' is reserved for a project without a board")
  ini = configparser.ConfigParser(interpolation=None)
  ini.optionxform = str # keys keep their case: flash_kB, clock_Hz
  with open(ini_path, encoding="utf-8") as f:
    ini.read_string("[board]\n" + f.read()) # plain key = value lines, no section header
  section = ini["board"]
  missing = [k for k in REQUIRED if k not in section]
  if missing:
    raise ValueError(f"missing field '{missing[0]}'")
  chip = next((k for k in CHIPS if k.upper() == section["chip"].upper()), None)
  if chip is None or CHIPS[chip]["platform"] != "STM32":
    raise ValueError(f"unknown chip '{section['chip']}'")
  title = section["name"].strip()
  if not TITLE_RX.match(title):
    raise ValueError(f"name '{title}' - use letters and digits, no separators")
  if board_key(title) != board_key(name):
    raise ValueError(f"name '{title}' does not match directory '{name}'")
  plc = section["plc"].strip().lower()
  if plc not in ("true", "false"):
    raise ValueError(f"field 'plc' is '{section['plc']}', use true or false")
  header = f"opencplc_{name}.h"
  if not os.path.isfile(os.path.join(os.path.dirname(ini_path), header)):
    raise ValueError(f"missing public header {header}")
  try:
    flash_kB = int(section["flash_kB"])
    reserve_kB = int(section.get("reserve_kB", 0))
    ram_kB = int(section["ram_kB"])
    freq_Hz = int(section["clock_Hz"])
  except ValueError as e:
    raise ValueError(f"numeric field: {e}") from e
  if not 0 <= reserve_kB < flash_kB:
    raise ValueError(f"reserve_kB {reserve_kB} does not fit in flash_kB {flash_kB}")
  return Board(
    name=name, title=title, dir=board_dir, plc=plc == "true", chip=chip,
    flash_kB=flash_kB, reserve_kB=reserve_kB, ram_kB=ram_kB, freq_Hz=freq_Hz,
    drivers=parse_drivers(section.get("drivers", "")),
  )

def load_boards(core_dir:str) -> dict[str, Board]:
  """Boards of a Core checkout: every brd/<name>/ with a manifest, keyed by name."""
  brd = PATH.resolve(f"{core_dir}/brd", read=False)
  boards = {}
  if not os.path.isdir(brd): return boards
  for name in sorted(os.listdir(brd)):
    board_dir = os.path.join(brd, name)
    if not os.path.isdir(board_dir): continue
    inis = sorted(f for f in os.listdir(board_dir) if f.endswith(".ini"))
    if not inis: continue
    ini_path = os.path.join(board_dir, inis[0]) # the board's manifest, whatever its name
    try:
      boards[name] = parse_board(ini_path, name, PATH.local(os.path.join(brd, name)))
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
