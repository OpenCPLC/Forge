# opencplc/utils/common.py

import sys, platform
from typing import Any
from xaeian import Print, Color as c, Ico

p = Print()

def detect_os() -> str:
  system = platform.system().lower()
  if system == "windows": return "windows"
  elif system == "linux": return "linux"
  elif system == "darwin": return "macos"
  return "unknown"

def is_yes(msg:str="Proceed automatically") -> bool:
  yn = f"[{c.GREEN}YES{c.END}/{c.RED}NO{c.END}]"
  print(f"{Ico.INF} {msg}? {yn}:", end=" ")
  ans = input().lower()
  return ans in ("yes", "y", "true", "tak", "t")

def color_url(url:str) -> str:
  """Repository URL: grey scheme, teal body."""
  return url.replace("https://", f"{c.GREY}https://{c.END}{c.TEAL}") + c.END

def assign_name(name:Any, flag:Any, msg:str) -> tuple[str, Any]:
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
    if seg != seg.strip(): return False, "Folder cannot start/end with spaces"
    if seg.endswith("."): return False, "Folder cannot end with a dot"
    if seg.split(".")[0].upper() in reserved:
      return False, f"'{seg}' is reserved on Windows"
  return True, ""