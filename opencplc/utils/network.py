# opencplc/utils/network.py

"""Downloads, ZIP extraction and fetching a remote project."""

import sys, re
import urllib.request, urllib.error, http.client
from xaeian import Print, Color as c, FILE, DIR, PATH
from xaeian.net import download as download_file
from .version import git_clone
from .common import color_url, validate_project_name
from .. import __version__

p = Print()

# Forge speaks under its own name: Cloudflare in front of dl.opencplc.com refuses `Python-urllib`
_opener = urllib.request.build_opener()
_opener.addheaders = [("User-Agent", f"opencplc/{__version__}")]
urllib.request.install_opener(_opener)

def _unreachable(url:str, e:Exception):
  """Say why a fetch failed and exit: an HTTP status, a timeout, or a connection that failed."""
  if isinstance(e, urllib.error.HTTPError):
    p.err(f"HTTP {c.GOLD}{e.code}{c.END} for {color_url(url)}")
  elif isinstance(e, TimeoutError) or isinstance(getattr(e, "reason", None), TimeoutError):
    p.err(f"Timed out on {color_url(url)}")
  else:
    p.err(f"Connection failed on {color_url(url)} | {e}")
  sys.exit(1)

def download(url:str, save_path:str="", timeout:float=10) -> bytes:
  """Fetch `url` into memory, saving to `save_path` when given; a network or HTTP error exits."""
  try:
    data = urllib.request.urlopen(url, timeout=timeout).read()
  except (OSError, http.client.HTTPException) as e: # `URLError` and a mid-transfer cut alike
    _unreachable(url, e)
  if save_path:
    FILE.save(save_path, data)
  return data

def fetch(url:str, path:str):
  """Fetch `url` straight into `path`; a network or HTTP error exits."""
  try:
    download_file(url, path)
  except (OSError, http.client.HTTPException) as e:
    _unreachable(url, e)

def unzip(data:bytes, path:str, drop_on_err:bool=True):
  """Unpack ZIP bytes into path; a bad archive exits and drops the partial directory."""
  try:
    DIR.unzip_bytes(data, path)
  except Exception:
    if drop_on_err:
      DIR.remove(path, force=True)
    p.err("Invalid ZIP file")
    sys.exit(1)

def project_remote(url:str, path:str, ref:str|None=None, name:str="") -> str:
  """Fetch a project from a ZIP url or git repository; name falls back to @name in its main.h."""
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
  # Name comes from the remote main.h, so it is validated before it becomes a path
  valid, reason = validate_project_name(name)
  if not valid:
    p.err(f"Invalid project name {c.MAGNTA}{name}{c.END}: {reason}")
    sys.exit(1)
  dst = PATH.resolve(f"{path}/{name}", read=False)
  if DIR.exists(dst):
    p.err(f"Project {c.BLUE}{name}{c.END} already exists")
    sys.exit(1)
  DIR.move(tmp, dst)
  p.ok(f"Project {c.BLUE}{name}{c.END} downloaded from {color_url(url)}")
  return name
