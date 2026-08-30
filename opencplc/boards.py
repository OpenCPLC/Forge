# opencplc/boards.py

"""
Ready boards discovered in the selected Core.

A board is one directory `plc/brd/<name>/` holding an .ini manifest,
the public header `opencplc_<name>.h` and its sources. The manifest describes the chip,
the initial memory and clock of a new project and the drivers the board
implementation requires. Nothing here is hard-coded in Forge: adding a board
means adding a directory to Core.
"""

import os, re, sys, configparser
from dataclasses import dataclass, field
from xaeian import Print, Color as c, PATH
from .platforms import CHIPS

p = Print()

NAME_RX = re.compile(r"^[a-z0-9_]+$")
REQUIRED = ("chip", "flash_kB", "ram_kB", "clock_Hz")

@dataclass
class Board:
  """One ready board as described by its board.ini."""
  name: str  # directory name, e.g. "uno"
  dir: str   # workspace-relative board directory
  chip: str  # canonical chip key from CHIPS
  flash_kB: int
  ram_kB: int
  freq_Hz: int
  drivers: list[str] = field(default_factory=list)

def parse_drivers(value:str) -> list[str]:
  """Normalized, unique driver names from a comma-separated list."""
  return list(dict.fromkeys(n.strip().lower() for n in value.split(",") if n.strip()))

def parse_board(ini_path:str, name:str, board_dir:str) -> Board:
  """Board from its manifest; raises ValueError naming what is wrong."""
  if not NAME_RX.match(name):
    raise ValueError(f"board name '{name}' - use lowercase letters, digits and '_'")
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
  header = f"opencplc_{name}.h"
  if not os.path.isfile(os.path.join(os.path.dirname(ini_path), header)):
    raise ValueError(f"missing public header {header}")
  try:
    flash_kB = int(section["flash_kB"])
    ram_kB = int(section["ram_kB"])
    freq_Hz = int(section["clock_Hz"])
  except ValueError as e:
    raise ValueError(f"numeric field: {e}") from e
  return Board(
    name=name, dir=board_dir, chip=chip,
    flash_kB=flash_kB, ram_kB=ram_kB, freq_Hz=freq_Hz,
    drivers=parse_drivers(section.get("drivers", "")),
  )

def load_boards(core_dir:str) -> dict[str, Board]:
  """Boards of a Core checkout: every plc/brd/<name>/ with a manifest, keyed by name."""
  brd = PATH.resolve(f"{core_dir}/plc/brd", read=False)
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
  key = next((k for k in boards if k == name.lower()), None)
  if key is None:
    p.err(f"Unknown board: {c.MAGNTA}{name}{c.END}")
    listed = ", ".join(f"{c.TURQUS}{k}{c.END}" for k in boards) or f"{c.GREY}none{c.END}"
    p.inf(f"Boards in this Core: {listed}, {c.TURQUS}Custom{c.END} for your own hardware")
    sys.exit(1)
  return boards[key]
