# opencplc/utils/install.py

import os, sys, subprocess, re
from xaeian import Print, Color as c, FILE, PATH
from .common import is_yes
from .network import download, unzip
from .version import version_older_than

try:
  import winreg
  WINREG_AVAILABLE = True
except ImportError:
  WINREG_AVAILABLE = False

p = Print()

FTP_PATH = "http://sqrt.pl"
INSTALL_PATH = "C:"
RESET_CONSOLE = False

class ENV:
  @staticmethod
  def path_exists(path:str) -> bool:
    return path in os.environ.get("PATH", "")

  @staticmethod
  def var_exists(var:str) -> bool:
    return var in os.environ

  @staticmethod
  def add_path(path:str) -> bool:
    if not WINREG_AVAILABLE: return False
    try:
      key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0,
        winreg.KEY_SET_VALUE | winreg.KEY_READ)
      current, _ = winreg.QueryValueEx(key, "Path")
      winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, f"{current};{path}")
      winreg.CloseKey(key)
      return True
    except Exception:
      return False

  @staticmethod
  def add_variable(name:str, value:str) -> bool:
    if not WINREG_AVAILABLE: return False
    try:
      key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0,
        winreg.KEY_SET_VALUE | winreg.KEY_READ)
      winreg.SetValueEx(key, name, 0, winreg.REG_EXPAND_SZ, value)
      winreg.CloseKey(key)
      return True
    except Exception:
      return False

def program_version(cmd:str) -> str|None:
  try:
    result = subprocess.run([cmd, "--version"], capture_output=True, check=True, text=True)
    output = result.stdout + result.stderr
    m = re.search(r'\b\d+\.\d+\.\d+\b', output)
    return m.group(0) if m else None
  except Exception:
    return None

def install(name:str, url:str, path:str, yes:bool=False, unpack:bool=True):
  if not yes and not is_yes(f"Install {name}"):
    p.err(f"See instructions at {c.GREY}https://{c.END}github.com/OpenCPLC/Forge")
    sys.exit(1)
  try:
    full_url = f"{url}/{name}.zip" if unpack else f"{url}/{name}"
    data = download(full_url)
    os.makedirs(path, exist_ok=True)
    dst = PATH.resolve(f"{path}/{name}")
    if unpack:
      unzip(data, dst)
    else:
      FILE.save(dst, data)
    p.ok("Installation complete")
  except Exception as e:
    p.err(f"Installation error {c.BLUE}{name}{c.END}: {e}")
    sys.exit(1)

def install_missing_add_path(
  name: str,
  cmd: str,
  var: str|None = None,
  yes: bool = False,
  min_ver: str = "",
) -> str|None:
  global RESET_CONSOLE
  ver = program_version(cmd)
  if not ver:
    p.wrn(f"Program {c.BLUE}{name}{c.END} is not installed")
    install(name, FTP_PATH, INSTALL_PATH, yes)
    path = f"{INSTALL_PATH}\\{name}\\bin"
    if var:
      ENV.add_variable(var, path)
    if not ENV.path_exists(path):
      if (var and ENV.add_path(f"%{var}%")) or ENV.add_path(path):
        p.ok(f"Path for {c.YELLOW}{cmd}{c.END} added to PATH")
      else:
        p.err(f"Failed to add path for {c.YELLOW}{cmd}{c.END}")
        sys.exit(1)
      RESET_CONSOLE = True
  elif min_ver and version_older_than(ver, min_ver):
    p.wrn(f"{c.YELLOW}{cmd}{c.END} v{c.ORANGE}{ver}{c.END} - min required: {c.BLUE}{min_ver}{c.END}")
  return ver

def install_toolchains(is_embedded:bool, yes:bool):
  """Install required toolchains based on platform."""
  install_missing_add_path("Git", "git", None, yes, "2.47.1")
  install_missing_add_path("Make", "make", None, yes, "4.4.1")
  if is_embedded:
    install_missing_add_path("ArmGCC", "arm-none-eabi-gcc", "ARMGCC", yes, "14.2.1")
    install_missing_add_path("OpenOCD", "openocd", None, yes, "0.12.0")
  else:
    install_missing_add_path("MinGW", "gcc", None, yes, "14.2.0")

def verify_compiler(is_embedded:bool) -> bool:
  """Verify compiler is working (not just present in PATH)."""
  compiler = "arm-none-eabi-gcc" if is_embedded else "gcc"
  try:
    result = subprocess.run([compiler, "--version"], capture_output=True, timeout=5)
    return result.returncode == 0
  except Exception:
    return False