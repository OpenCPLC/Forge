# opencplc/utils/common.py

"""Small CLI helpers: prompts, files of a project as messages point at them, name validation."""

import sys
from typing import Any
from xaeian import Print, grey
from ..config import DIR_FRAMEWORK, DIR_TESTS
from .files import core_version, project_dir
from .palette import color_bad, color_file, color_good

p = Print()

def is_yes(msg:str="Proceed automatically") -> bool:
  """Ask `msg` and read a yes/no answer; y, yes, t, tak and true count as yes."""
  p.inf(f"{msg}? [{color_good('YES')}/{color_bad('NO')}]:", end=" ")
  try:
    ans = input().lower()
  except EOFError: # no console to answer, as under CI, is no consent
    print()
    return False
  return ans in ("yes", "y", "true", "tak", "t")

def color_pro_file(name:str, file:str) -> str:
  """`file` of project `name` as messages point at it: grey folder, then the file."""
  return f"{grey(f'{project_dir(name)}/')}{color_file(file)}"

def color_main_h(name:str) -> str:
  """`main.h` of project `name` as messages point at it."""
  return color_pro_file(name, "main.h")

def assign_name(name:Any, flag:Any, msg:str) -> tuple[str, Any]:
  """Take the project name from a flag that carries one; a second, different name exits."""
  if isinstance(flag, str):
    if not name:
      name = flag
    elif name != flag:
      p.err(f"Name given twice: argument and flag {msg}")
      sys.exit(1)
    flag = True
  return name, flag

def validate_project_name(name:str) -> tuple[bool, str]:
  """Validate project name for safety and compatibility. Checks every path segment."""
  if not name: return False, "Name cannot be empty"
  if name.startswith("/") or (len(name) > 1 and name[1] == ":"):
    return False, "Name cannot be absolute path"
  if len(name) > 100: return False, "Name too long (max 100 chars)"
  if name.split("/")[-1] == DIR_TESTS:
    return False, f"Name cannot end in {DIR_TESTS}, the folder of tests"
  if name.startswith(f"{DIR_FRAMEWORK}/") and not core_version(name):
    return False, f"Project in Core needs a folder, {DIR_FRAMEWORK}/<version>/<folder>"
  invalid_chars = '<>:"|?*\\'
  reserved = (
    ["CON", "PRN", "AUX", "NUL"]
    + [f"COM{i}" for i in range(1, 10)]
    + [f"LPT{i}" for i in range(1, 10)]
  )
  # The name is a path, so each segment has to stand on its own as a folder
  for seg in name.split("/"):
    if not seg: return False, "Name cannot contain an empty folder"
    if seg in (".", ".."): return False, f"Name cannot contain folder '{seg}'"
    for ch in invalid_chars:
      if ch in seg: return False, f"Name cannot contain '{ch}'"
    if not seg.isprintable(): return False, "Name contains a non-printable character"
    if seg != seg.strip(): return False, "Folder cannot start/end with spaces"
    if seg.endswith("."): return False, "Folder cannot end with a dot"
    if seg.split(".")[0].upper() in reserved: return False, f"'{seg}' is reserved on Windows"
  return True, ""