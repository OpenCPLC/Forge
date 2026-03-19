# opencplc/utils/version.py

import sys, subprocess, re, json, urllib.parse
from typing import Literal
import packaging.version
from xaeian import Print, Color as c, DIR, PATH
from .common import is_yes, color_url

p = Print()

def version_real(ver:str, latest:str) -> str:
  """Normalize version string."""
  if ver in ("latest", "last"): return latest
  if ver in ("dev", "develop"): return "develop"
  if ver in ("main", "master"): return "main"
  return ver

def version_older_than(a:str, b:str) -> bool:
  return packaging.version.Version(a) < packaging.version.Version(b)

def version_check(ver:str, available:list[str], err_msg:str):
  """Exit if version not in available list."""
  if ver not in available:
    p.err(f"Framework version {c.MAGNTA}{ver}{c.END} does not exist")
    print(err_msg)
    sys.exit(1)

def git_clone(url:str, path:str, ref:str|None=None, drop_on_err:bool=False):
  """Clone git repository."""
  cmd = ["git", "clone"]
  if ref: cmd += ["--branch", ref]
  cmd += [url, path]
  result = subprocess.run(cmd, capture_output=True, text=True)
  if result.returncode:
    if drop_on_err and PATH.exists(path): DIR.remove(path, force=True)
    p.err(f"Clone failed: {c.ORANGE}{url}{c.END}")
    sys.exit(1)

def git_get_refs(
  url: str,
  option: Literal["--heads", "--tags", "--ref"] = "--ref",
  use_git: bool = True,
) -> list[str]:
  """Get remote refs (tags/branches) from git repository."""
  if option == "--ref":
    tags = git_get_refs(url, "--tags", use_git)
    heads = git_get_refs(url, "--heads", use_git)
    return tags + heads
  if use_git:
    result = subprocess.run(["git", "ls-remote", option, url], capture_output=True, text=True)
    lines = result.stdout.strip().splitlines()
    rx = r"refs/tags/([^\^{}]+)$" if option == "--tags" else r"refs/heads/(.+)$"
    refs = [re.search(rx, ln).group(1) for ln in lines if re.search(rx, ln)]
    if option == "--tags":
      return sorted(refs, key=packaging.version.parse, reverse=True)
    return refs
  # API fallback
  host = "github" if "github.com" in url else "gitlab" if "gitlab.com" in url else None
  if not host: raise ValueError("Only GitHub/GitLab supported")
  repo = url.replace(f"https://{host}.com/", "").rstrip("/")
  if host == "gitlab":
    api = f"https://{host}.com/api/v4/projects/{urllib.parse.quote_plus(repo)}"
    endpoint = "/repository/tags" if option == "--tags" else "/repository/branches"
  else:
    api = f"https://api.github.com/repos/{repo}"
    endpoint = "/tags" if option == "--tags" else "/branches"
  data = subprocess.run(["curl", "-s", api + endpoint], capture_output=True, text=True).stdout
  out = json.loads(data)
  names = [x["name"] for x in out]
  if option == "--tags":
    return sorted(names, key=packaging.version.parse, reverse=True)
  return names

def git_clone_missing(url:str, path:str, ref:str, yes:bool=False, required:bool=True) -> bool:
  """Clone repository if not present."""
  full_path = PATH.resolve(path, read=False)
  if PATH.exists(full_path): return True
  p.wrn(f"Framework {c.MAGNTA}opencplc{c.END} not installed for version {c.BLUE}{ref}{c.END}")
  if not yes and not is_yes():
    if not required: return False
    p.err(f"You can download it manually from {color_url(url)}")
    sys.exit(0)
  git_clone(url, full_path, ref)
  p.ok(f"Cloned {c.ORANGE}{url}{c.END} to {c.GREY}{PATH.local(full_path)}{c.END}")
  return True