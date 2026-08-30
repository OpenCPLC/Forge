# opencplc/utils/version.py

"""Framework versions: aliases, ordering, refs and clones from git."""

import sys, subprocess, re
from typing import Literal
import packaging.version
from xaeian import Print, Color as c, DIR, PATH
from .common import is_yes, color_url

p = Print()

def version_real(ver:str, latest:str) -> str:
  """`latest` becomes the newest release; a tag or branch name passes through."""
  return latest if ver == "latest" else ver

def version_is_release(ver:str) -> bool:
  """True for a pinned release tag, False for a moving branch like develop or main."""
  try:
    packaging.version.Version(ver)
    return True
  except packaging.version.InvalidVersion:
    return False

def version_active(framework:str, forge_cfg:dict) -> str:
  """Framework version in effect: the -f flag when given, otherwise the opencplc.json default."""
  return version_real(framework or forge_cfg["version"], forge_cfg["available-versions"][0])

def version_key(ver:str):
  """Sort key: proper versions first (newest wins), free-form names after."""
  try: return (1, packaging.version.Version(ver))
  except packaging.version.InvalidVersion: return (0, ver)

def version_older_than(a:str, b:str) -> bool:
  """True when a < b as semantic versions."""
  return packaging.version.Version(a) < packaging.version.Version(b)

def version_check(ver:str, available:list[str], err_msg:str):
  """Exit with err_msg when ver is not among the available refs."""
  if ver not in available:
    p.err(f"Framework version {c.MAGNTA}{ver}{c.END} does not exist")
    print(err_msg)
    sys.exit(1)

def git_clone(url:str, path:str, ref:str|None=None, drop_on_err:bool=False):
  """git clone url into path at ref; a failure exits, dropping the partial directory when asked."""
  cmd = ["git", "clone"]
  if ref: cmd += ["--branch", ref]
  cmd += [url, path]
  result = subprocess.run(cmd, capture_output=True, text=True)
  if result.returncode:
    if drop_on_err and DIR.exists(path): DIR.remove(path, force=True)
    p.err(f"Clone failed: {c.TEAL}{url}{c.END}")
    sys.exit(1)

def git_get_refs(url:str, option:Literal["--heads", "--tags", "--ref"]="--ref") -> list[str]:
  """Remote refs of a git repository: tags (newest first), branches, or both."""
  if option == "--ref":
    return git_get_refs(url, "--tags") + git_get_refs(url, "--heads")
  try:
    result = subprocess.run(["git", "ls-remote", option, url], capture_output=True, text=True)
  except FileNotFoundError:
    return [] # git not installed yet - caller decides what to do
  rx = r"refs/tags/([^\^{}]+)$" if option == "--tags" else r"refs/heads/(.+)$"
  refs = [m.group(1) for m in map(lambda ln: re.search(rx, ln), result.stdout.splitlines()) if m]
  if option == "--tags":
    return sorted(refs, key=version_key, reverse=True)
  return refs

def git_clone_missing(url:str, path:str, ref:str, yes:bool=False, required:bool=True) -> bool:
  """Clone when path is missing, after confirmation; False when declined and not required."""
  full_path = PATH.resolve(path, read=False)
  if DIR.exists(full_path): return True
  p.wrn(f"Missing {c.ORANGE}{PATH.local(full_path)}{c.END}, "
    f"clone from {c.TEAL}{url}{c.END} {c.GREY}({ref}){c.END}")
  if not yes and not is_yes():
    if not required: return False
    p.err(f"You can download it manually from {color_url(url)}")
    sys.exit(0)
  git_clone(url, full_path, ref)
  loc = PATH.local(full_path)
  if loc.endswith(ref):
    loc = f"{c.GREY}{loc[:len(loc)-len(ref)]}{c.END}{c.VIOLET}{ref}{c.END}"
  else:
    loc = f"{c.GREY}{loc}{c.END}"
  p.ok(f"Cloned {c.TEAL}{url}{c.END} to {loc}")
  return True