# opencplc/utils/network.py

import sys, re
import urllib.request
from xaeian import Print, Color as c, FILE, DIR, PATH
from .version import git_clone

p = Print()

def download(url:str, save_path:str="", timeout:float=10) -> bytes:
  """Download file from URL."""
  try:
    resp = urllib.request.urlopen(url, timeout=timeout)
    data = resp.read()
    if save_path:
      FILE.save(save_path, data)
    return data
  except urllib.error.URLError:
    p.err(f"Failed to connect to {c.GREY}{url}{c.END}")
    sys.exit(1)
  except urllib.error.HTTPError as e:
    p.err(f"HTTP {e.code} for {c.GREY}{url}{c.END}")
    sys.exit(1)

def unzip(data:bytes, path:str, drop_on_err:bool=True):
  """Extract ZIP archive from bytes."""
  try:
    DIR.unzip_bytes(data, path)
  except Exception:
    if drop_on_err:
      DIR.remove(path, force=True)
    p.err("Invalid ZIP file")
    sys.exit(1)

def project_remote(url:str, path:str, ref:str|None=None, name:str="") -> str:
  """Download remote project (ZIP or git)."""
  tmp = ".remote"
  DIR.ensure(tmp)
  if url.endswith(".zip"):
    data = download(url)
    unzip(data, tmp, drop_on_err=True)
  else:
    git_clone(url, tmp, ref, drop_on_err=True)
  try:
    lines = [ln.rstrip() for ln in FILE.load_lines(f"{tmp}/main.h")]
  except Exception:
    lines = []
  if not lines:
    p.err(f"Remote project does not contain {c.BLUE}main.h{c.END}")
    sys.exit(1)
  if not name:
    name_line = next((ln for ln in lines if "@name" in ln), "")
    name_line = re.sub(r"\(.*?\)|\{.*?\}|\[.*?\]", "", name_line)
    name_line = re.sub(r"[<>:\"|?*]", "", name_line).replace("\\", "/").strip()
    parts = name_line.split()
    if not parts:
      p.err(f"Failed to read project name from {c.BLUE}main.h{c.END}")
      p.inf(f"Provide project name as a positional argument")
      sys.exit(1)
    name = parts[-1]
  dst = PATH.resolve(f"{path}/{name}", read=False)
  if PATH.exists(dst):
    p.err(f"Project {c.CYAN}{name}{c.END} already exists")
    sys.exit(1)
  DIR.move(tmp, dst)
  p.ok(f"Project {c.CYAN}{name}{c.END} downloaded from {c.GREY}{url}{c.END}")
  return name