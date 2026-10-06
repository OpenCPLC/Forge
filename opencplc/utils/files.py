# opencplc/utils/files.py

"""File and directory helpers: listing, mtimes, rendering, project discovery."""

from datetime import datetime
from xaeian import Print, Color as c, FILE, DIR, PATH, replace_map
from .text import line_remove

p = Print()

def load_lines(path:str) -> list[str]:
  """File as lines without endings; an unreadable file reads as empty."""
  try: return [ln.rstrip("\n\r") for ln in FILE.load_lines(path)]
  except Exception: return []

def files_list(path:str="", ext:str="") -> dict[str, list[str]]:
  """folder → files under `path`, absolute and normalized; only `ext` when given."""
  result = {}
  for file in DIR.iter_files(path or "."):
    # `exts=` ignores case, and GCC reads `.S` and `.C` as other languages than `.s` and `.c`
    if file.endswith(ext): result.setdefault(PATH.dirname(file), []).append(file)
  return result

def last_modification(path:str="", exts:list[str]|None=None) -> str:
  """Newest file under `path`, only `exts` when given, formatted for display."""
  files = list(DIR.iter_files(path or ".", exts=exts))
  if not files: return f"{c.GREY}Unknown{c.END}"
  newest = max(files, key=FILE.mtime)
  shown = PATH.local(newest, path) if path else PATH.basename(newest)
  stamp = datetime.fromtimestamp(FILE.mtime(newest))
  return f"{c.BLUE}{shown}{c.END} {c.GREY}({stamp:%Y-%m-%d %H:%M:%S}){c.END}"

def create_file(
  name:str,
  content:str,
  path:str = "",
  replacements:dict|None = None,
  remove_line:str = "",
  color:str = "",
) -> str:
  """Render and write a file; an unchanged file keeps its bytes and its mtime."""
  fp = PATH.resolve(f"{path or '.'}/{name}")
  content = content.strip()
  if remove_line:
    content = line_remove(content, remove_line)
  content = replace_map(content, replacements or {})
  exists = FILE.exists(fp)
  if exists and FILE.load(fp) == content: return fp
  FILE.save(fp, content)
  if not color: color = c.ORANGE
  where = PATH.local(path)
  suffix = f" in {c.GREY}{where}{c.END}" if where else ""
  action = "Overwritten" if exists else "Created"
  p.ok(f"{action} {color}{name}{c.END}{suffix}")
  return fp

def get_project_list(path:str) -> dict[str, str]:
  """Folders containing main.h, keyed by name relative to `path`."""
  path = PATH.resolve(path or ".")
  result = {}
  for main_h in DIR.iter_files(path, match="main.h"):
    pro_path = PATH.dirname(main_h)
    name = PATH.local(pro_path, path)
    if name.lower() not in (n.lower() for n in result):
      result[name] = pro_path
    else:
      p.wrn(f"Duplicate project name {c.MAGNTA}{name}{c.END} at {c.GREY}{pro_path}{c.END}")
  return result

def project_key(projects:dict[str, str], name:str) -> str|None:
  """Project `name` as `get_project_list` keys it, case aside; `None` when there is none."""
  return next((k for k in projects if k.lower() == name.lower()), None)

def check_write_permission(path:str) -> bool:
  """`True` when a probe file can be created in `path`; the directory is created when missing."""
  probe = f"{path}/.forge_test"
  try:
    FILE.save(probe, "")
    FILE.remove(probe)
    return True
  except OSError:
    return False
