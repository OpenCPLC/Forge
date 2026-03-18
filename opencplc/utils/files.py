# opencplc/utils/files.py

import os
from datetime import datetime
from xaeian import Print, Color as c, Ico, FILE, PATH

p = Print()

def files_list(path:str="", ext:str="") -> dict[str, list[str]]:
  result = {}
  path = PATH.resolve(path) if path else PATH.resolve(".")
  if not os.path.isdir(path): return result
  for folder, _, files in os.walk(path):
    folder = PATH.normalize(folder)
    matched = [PATH.normalize(f"{folder}/{f}") for f in files if not ext or f.endswith(ext)]
    if matched:
      result[folder] = matched
  return result

def files_mdate(path:str="") -> dict[str, datetime]:
  result = {}
  path = PATH.resolve(path) if path else PATH.resolve(".")
  if not os.path.isdir(path): return result
  for folder, _, files in os.walk(path):
    for f in files:
      fp = PATH.normalize(f"{folder}/{f}")
      result[fp] = datetime.fromtimestamp(os.path.getmtime(fp))
  return result

def files_mdate_max(path:str="", ext=None):
  dates = files_mdate(path)
  if not dates: return None
  if ext:
    exts = [ext] if isinstance(ext, str) else list(ext)
    exts = [e if e.startswith(".") else "." + e for e in exts]
    dates = {k: v for k, v in dates.items() if os.path.splitext(k)[1] in exts}
    if not dates: return None
  max_dt = max(dates.values())
  return next(k for k, v in dates.items() if v == max_dt), max_dt

def last_modification(path:str="", ext=None) -> str:
  result = files_mdate_max(path, ext=ext)
  if not result: return "Unknown"
  fp, dt = result
  rel = PATH.local(fp, path) if path else PATH.basename(fp)
  return f"{c.BLUE}{rel} {c.GREY}({dt:%Y-%m-%d %H:%M:%S}){c.END}"

def create_file(
  name: str,
  content: str,
  path: str = "",
  replacements: dict = None,
  remove_line: str = "",
  rewrite: bool = False,
  color: str = "",
) -> str:
  from .text import line_remove
  replacements = replacements or {}
  fp = (
    f"{PATH.resolve(path)}/{name}" if path and path not in (".", "./")
    else f"{PATH.resolve('.')}/{name}"
  )
  content = content.strip()
  if remove_line:
    content = line_remove(content, remove_line)
  for pattern, value in replacements.items():
    content = content.replace(pattern, str(value))
  FILE.save(fp, content)
  if not color: color = c.ORANGE
  path_display = PATH.normalize(path) if path and path not in (".", "./") else ""
  suffix = f" in {c.GREY}{path_display}{c.END}" if path_display else ""
  action = "Overwritten" if rewrite else "Created"
  p.ok(f"{action} {color}{name}{c.END}{suffix}")
  return fp

def get_project_list(path:str) -> dict[str, str]:
  path = PATH.resolve(path) if path else PATH.resolve(".")
  files = files_list(path, "main.h")
  result = {}
  for pro_path in files.keys():
    name = PATH.local(pro_path, path)
    if name.lower() not in (n.lower() for n in result.keys()):
      result[name] = pro_path
  return result

def check_write_permission(path:str) -> bool:
  """Check if we can write to directory."""
  try:
    os.makedirs(path, exist_ok=True)
    test_file = os.path.join(path, ".forge_test")
    with open(test_file, "w") as f:
      f.write("test")
    os.remove(test_file)
    return True
  except Exception:
    return False