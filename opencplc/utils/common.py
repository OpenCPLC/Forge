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

def is_windows() -> bool:
  return detect_os() == "windows"

def is_linux() -> bool:
  return detect_os() == "linux"

def to_int(value:Any) -> int|None:
  if value is None: return None
  s = str(value)
  digits = ""
  for ch in s:
    if ch.isdigit(): digits += ch
    else: break
  return int(digits) if digits else None

def is_yes(msg:str="Proceed automatically") -> bool:
  yn = f"[{c.GREEN}YES{c.END}/{c.RED}NO{c.END}]"
  print(f"{Ico.INF} {msg}? {yn}:", end=" ")
  ans = input().lower()
  return ans in ("yes", "y", "true", "tak", "t")

def color_url(url:str) -> str:
  return url.replace("https://", f"{c.GREY}https://{c.END}").replace(
    "OpenCPLC", f"{c.TURQUS}OpenCPLC{c.END}")

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
  """Validate project name for safety and compatibility."""
  if not name: return False, "Name cannot be empty"
  if ".." in name: return False, "Name cannot contain '..'"
  if name.startswith("/") or (len(name) > 1 and name[1] == ":"):
    return False, "Name cannot be absolute path"
  invalid_chars = '<>:"|?*\\'
  for ch in invalid_chars:
    if ch in name: return False, f"Name cannot contain '{ch}'"
  reserved = (
    ["CON", "PRN", "AUX", "NUL"]
    + [f"COM{i}" for i in range(1, 10)]
    + [f"LPT{i}" for i in range(1, 10)]
  )
  base = name.split("/")[0].upper()
  if base in reserved: return False, f"'{base}' is reserved on Windows"
  if name != name.strip(): return False, "Name cannot start/end with spaces"
  if len(name) > 100: return False, "Name too long (max 100 chars)"
  return True, ""