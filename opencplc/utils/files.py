# opencplc/utils/files.py

"""File and directory helpers: listing, mtimes, rendering, project discovery."""

import os, re
from datetime import datetime
from xaeian import Print, Color as c, FILE, DIR, PATH, replace_map, grey
from .palette import CONFIG_COLOR, color_file, color_wrong
from ..config import DIR_PROJECTS, DIR_FRAMEWORK, DIR_TESTS, DIR_LOCAL
from .text import line_remove
from .hash import hash_string

p = Print()

def load_lines(path:str) -> list[str]:
  """File as lines without endings; an unreadable file reads as empty."""
  try: return [ln.rstrip("\n\r") for ln in FILE.load_lines(path)]
  except (OSError, UnicodeDecodeError): return []

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
  if not files: return grey("Unknown")
  newest = max(files, key=FILE.mtime)
  shown = PATH.local(newest, path) if path else PATH.basename(newest)
  stamp = datetime.fromtimestamp(FILE.mtime(newest))
  return f"{color_file(shown)} {grey(f'({stamp:%Y-%m-%d %H:%M:%S})')}"

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
  if not color: color = CONFIG_COLOR
  where = PATH.local(path)
  suffix = f" in {grey(where)}" if where else ""
  action = "Overwritten" if exists else "Created"
  p.ok(f"{action} {color}{name}{c.END}{suffix}")
  return fp

def hidden(rel:str) -> bool:
  """
  `True` when relative path `rel` passes a folder starting with a dot, which Forge leaves alone.

  Such a folder holds other code, a simulator or a cache, and only `.tests` is Forge's own.
  """
  return any(seg.startswith(".") and seg not in (".", "..", DIR_TESTS) for seg in rel.split("/"))

def get_project_list(path:str) -> dict[str, str]:
  """Folders containing main.h, keyed by name relative to `path`."""
  path = PATH.resolve(path or ".")
  result = {}
  # `.git` holds most files of a workspace and never a project
  for main_h in DIR.iter_files(path, match="main.h", blacklist=[".git"]):
    pro_path = PATH.dirname(main_h)
    name = PATH.local(pro_path, path)
    # `.tests/main.h` sets up the test build of the project above, never a project of its own
    if hidden(name) or PATH.basename(pro_path) == DIR_TESTS: continue
    if name.lower() not in (n.lower() for n in result):
      result[name] = pro_path
    else:
      p.wrn(f"Duplicate project name {color_wrong(name)} at {grey(pro_path)}")
  return result

def project_key(projects:dict[str, str], name:str) -> str|None:
  """Project `name` as `get_project_list` keys it, case aside; `None` when there is none."""
  return next((k for k in projects if k.lower() == name.lower()), None)

# `.gitignore` wildcards as regex: `**/` may span no folder, so `**/app` finds a top `app` too
WILDCARDS = {"**/": "(?:.*/)?", "**": ".*", "*": "[^/]*", "?": "[^/]"}

def _glob_rx(glob:str) -> str:
  """Regex of a `.gitignore` pattern over a slash path, matching what lies below it too."""
  glob = glob.rstrip("/")
  head = "" if "/" in glob else "(?:.*/)?" # a slash, trailing one aside, ties it to the start
  tokens = re.split(r"(\*\*/|\*\*|\*|\?)", glob.lstrip("/"))
  return head + "".join(WILDCARDS.get(t) or re.escape(t) for t in tokens) + "(?:/.*)?"

def glob_match(path:str, pattern:str) -> bool:
  """Slash `path`, or a folder above it, matched by a `.gitignore` pattern, case aside."""
  return re.fullmatch(_glob_rx(pattern), path, re.IGNORECASE) is not None

def ignored(name:str, patterns:list[str]) -> bool:
  """
  Project `name` hidden by `patterns` written as in `.gitignore`, case aside.

  A pattern matching the project or a folder above it hides it, one with `!` shows it again.
  The last match decides.
  """
  hidden = False
  for pattern in patterns:
    if glob_match(name, pattern.removeprefix("!")): hidden = not pattern.startswith("!")
  return hidden

# A project lives in `projects/`, named from there, or in a Core, named `opencplc/<version>/...`.
# `opencplc/<version>` alone is the Core itself, loaded for its own tests in `.tests/`.
# A local project lies outside the workspace, named by its absolute path.

def is_local(name:str) -> bool:
  """`True` for a local project: a name in the workspace is never absolute."""
  return PATH.is_abs(name)

def core_version(name:str) -> str:
  """Core version project `name` lies in, "" for a project in `projects/` or a local one."""
  parts = name.split("/")
  return parts[1] if len(parts) > 1 and parts[0] == DIR_FRAMEWORK else ""

def core_dir(version:str) -> str:
  """Workspace folder of Core `version`."""
  return f"{DIR_FRAMEWORK}/{version}"

def is_core(name:str) -> bool:
  """`True` for the Core itself, `opencplc/<version>`."""
  return bool(core_version(name)) and name.count("/") == 1

def project_dir(name:str) -> str:
  """Workspace folder of project `name`; of the Core itself, its tests; a local one is its own."""
  if is_local(name): return name
  if is_core(name): return f"{name}/{DIR_TESTS}"
  return name if core_version(name) else f"{DIR_PROJECTS}/{name}"

def project_name(pro_dir:str) -> str:
  """
  Name of the project in workspace folder `pro_dir`, "" for a folder in neither place.

  `.tests/` of a Core names the Core itself, while the Core folder alone is no project.
  """
  core = core_version(pro_dir)
  if core:
    home = f"{DIR_FRAMEWORK}/{core}"
    if pro_dir == f"{home}/{DIR_TESTS}": return home
    return "" if pro_dir == home else pro_dir
  prefix = f"{DIR_PROJECTS}/"
  return pro_dir[len(prefix):] if pro_dir.startswith(prefix) else ""

def home_name(name:str) -> str:
  """
  Name its files and images carry: in a Core the path from its root, the version left out.

  A local project carries the name of its folder.
  """
  if is_local(name): return PATH.basename(name)
  if is_core(name): return DIR_TESTS
  return name.split("/", 2)[2] if core_version(name) else name

def full_path(path:str) -> str:
  """
  `path` absolute, `..` folded and spelled as the disk keeps it, links left as they lie.

  On Windows another case finds the same folder, so each existing folder takes the case
  its parent lists, and the drive letter goes upper case.
  A makefile holding the path, or a key of `opencplc.json`, would change with every spelling.
  """
  head, *names = PATH.resolve(path).split("/")
  head = head.upper() if head.endswith(":") else head
  for name in names:
    # `DIR.folder_list` leaves links out, and the name of a link spells a path as well
    try: listed = os.listdir(f"{head}/") if name else []
    except OSError: listed = []
    same = (n for n in listed if os.path.normcase(n) == os.path.normcase(name))
    head = f"{head}/{next(same, name)}"
  return head

def tree_path(path:str) -> str:
  """
  Place of `path` in a tree the workspace keeps, such as `build/`: workspace-relative as it is.

  From outside it goes under `local/`, in a folder named by a hash of the one it lies in,
  so it stays short however deep it lies: `D:/repos/app` → `local/1a2b3c4d/app`.
  Make on Windows crashes on a path over 260 characters.
  """
  path = PATH.local(path)
  if not PATH.is_abs(path): return path
  folder = os.path.normcase(PATH.dirname(path)) # on Windows the case names no other folder
  return f"{DIR_LOCAL}/{hash_string(folder):08x}/{PATH.basename(path)}"

def check_write_permission(path:str) -> bool:
  """`True` when a probe file can be created in `path`; the directory is created when missing."""
  probe = f"{path}/.forge_test"
  try:
    FILE.save(probe, "")
    FILE.remove(probe)
    return True
  except OSError:
    return False
