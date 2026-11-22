# opencplc/utils/tools.py

"""
Tools a build runs on: which, where, installed when missing.

On Windows every build uses the packages Forge keeps under `%LOCALAPPDATA%/OpenCPLC`,
what the console has on PATH plays no part.
On Linux the tools come from PATH.
Git is the exception on both: winget on Windows, the distribution on Linux.
"""

import os, sys, stat, subprocess, platform
from xaeian import Print, DIR, FILE, JSON, PATH, grey
from xaeian.cmd import which, run
from .palette import color_folder, color_program, color_symbol, color_link
from .common import is_yes
from .network import fetch
from ..config import URL_DL

p = Print()

WINDOWS = platform.system() == "Windows"
DEFAULT_DIR = PATH.normalize(f"{os.environ.get('LOCALAPPDATA', '')}/OpenCPLC")
INSTALLED = "tools.json" # in the tools directory, package on disk per tool

# Zip in the bucket per tool, unpacked into `<name>/`; the version is what Forge builds with
PACKAGES = {
  "arm-gcc": "arm-gcc-15.3.zip",
  "openocd": "openocd-0.12.zip",
  "mingw": "mingw-16.1.zip",
  "make": "make-4.4.zip",
  "cppcheck": "cppcheck-2.22.zip",
}
COMMANDS = {
  "arm-gcc": "arm-none-eabi-gcc",
  "openocd": "openocd",
  "mingw": "gcc",
  "make": "make",
  "cppcheck": "cppcheck",
}
STM32_TOOLS = ("make", "arm-gcc", "openocd")
HOST_TOOLS = ("make", "mingw")
LINT_TOOLS = ("cppcheck",) # a build never needs them, the first `make lint` installs them

def tool_names(is_embedded:bool, tests:bool) -> tuple[str, ...]:
  """Packages of a project: its toolchain, and MinGW beside `arm-gcc` for tests on the computer."""
  if not is_embedded: return HOST_TOOLS
  return STM32_TOOLS + (("mingw",) if tests else ())

def tools_dir() -> str:
  """Where the packages live; `OPENCPLC_TOOLS` moves them, PATH is then the user's own business."""
  return PATH.normalize(os.environ.get("OPENCPLC_TOOLS") or DEFAULT_DIR)

def tool_path(name:str) -> str:
  """Where a package lands."""
  return f"{tools_dir()}/{name}"

def bin_suffix(name:str) -> str:
  """`/bin` when the package ships one, else nothing: the tool runs from the package itself."""
  return "/bin" if DIR.exists(f"{tool_path(name)}/bin") else ""

def bin_dir(name:str) -> str:
  """Where a tool runs from."""
  return tool_path(name) + bin_suffix(name)

def template_paths(is_embedded:bool, tests:bool=False) -> dict[str, str]:
  """
  Tool paths for generated files, spelled through the environment, never as text:
  `$(LOCALAPPDATA)` for Make, `${env:LOCALAPPDATA}` for VS Code.

  Make reads a makefile as ANSI, so a profile named `Łukasz` written out would never be found,
  and a `#` or `$` in it would cut the line; a variable carries neither problem.

  On Linux the tools come from PATH: commands bare, the cortex-debug paths dropped.
  """
  if not WINDOWS:
    return {
      "${TOOLS_PATH}": "",
      "${TOOLS_ARM_GCC}": "arm-none-eabi-gcc",
      "${TOOLS_GCC}": "gcc",
      "${TOOLS_GDB}": "gdb",
    }
  moved = bool(os.environ.get("OPENCPLC_TOOLS"))
  var, home = ("OPENCPLC_TOOLS", "") if moved else ("LOCALAPPDATA", "/OpenCPLC")
  mk, vs = f"$({var}){home}", f"${{env:{var}}}{home}"
  names = tool_names(is_embedded, tests)
  return {
    "${TOOLS_PATH}": ";".join(f"{mk}/{n}{bin_suffix(n)}" for n in names),
    "${TOOLS_ARM_DIR}": f"{vs}/arm-gcc/bin",
    "${TOOLS_OPENOCD_EXE}": f"{vs}/openocd/bin/openocd.exe",
    "${TOOLS_ARM_GCC}": f"{vs}/arm-gcc/bin/arm-none-eabi-gcc.exe",
    "${TOOLS_GCC}": f"{vs}/mingw/bin/gcc.exe",
    "${TOOLS_GDB}": f"{vs}/mingw/bin/gdb.exe",
  }

#------------------------------------------------------------------------------------------ Install

def retire(path:str):
  """
  Empty a package for the new one, file by file.

  Windows lets a running image be renamed but not removed,
  and the reload that installs a new `make` runs inside the old one;
  gdb or openocd may be up in VS Code just the same.
  Such a file is renamed aside as `.old` and swept by a later run.
  """
  for root, dirs, files in os.walk(path, topdown=False):
    for name in files:
      file = os.path.join(root, name)
      os.chmod(file, stat.S_IWRITE)
      try:
        os.remove(file)
      except OSError:
        os.rename(file, f"{file}.{os.getpid()}.old")
    for name in dirs: # emptied already, the deepest first
      try:
        os.rmdir(os.path.join(root, name))
      except OSError:
        pass
  try:
    os.rmdir(path) # by its own name: POSIX refuses `path/.`
  except OSError:
    pass

def sweep(root:str):
  """Remove what `retire` had to leave behind, once the system lets go of it."""
  for file in DIR.iter_files(root, match="*.old"):
    try:
      FILE.remove(file)
    except OSError:
      pass

def install(name:str):
  """Fetch the package of a tool and unpack it in place, whatever was there retired first."""
  root, package = tools_dir(), PACKAGES[name]
  dst, archive = tool_path(name), f"{root}/{package}"
  DIR.ensure(root)
  fetch(f"{URL_DL}/tools/{package}", archive)
  if DIR.exists(dst): retire(dst)
  try:
    DIR.unzip(archive, dst)
  except Exception: # `zipfile` and `zlib` raise errors of their own on a broken archive
    retire(dst)
    FILE.remove(archive)
    p.err(f"Package {color_program(package)} arrived broken, run again to download it anew")
    sys.exit(1)
  FILE.remove(archive)
  installed = JSON.load(f"{root}/{INSTALLED}", {})
  installed[name] = package
  JSON.save_smart(f"{root}/{INSTALLED}", installed)
  p.ok(f"{name} installed in {grey(f'{root}/')}{color_program(name)}")

def use_installed_git() -> bool:
  """Git installed but off this console's PATH: put its `cmd` first for this process."""
  user_home = f"{os.environ.get('LOCALAPPDATA', '')}/Programs/Git"
  machine_home = f"{os.environ.get('ProgramFiles', '')}/Git"
  for home in (user_home, machine_home):
    if FILE.exists(f"{home}/cmd/git.exe"):
      os.environ["PATH"] = f"{home}/cmd;{os.environ['PATH']}"
      return True
  return False

def ensure_git(yes:bool):
  """Git on PATH or in its known home, else winget puts it there."""
  if which("git"): return
  if not WINDOWS:
    p.err(f"{color_program('git')} not found, install it with your package manager")
    sys.exit(1)
  if use_installed_git(): return
  if not yes and not is_yes(f"Install {color_program('Git')} with winget"):
    p.err(f"Install Git from {color_link('https://git-scm.com')} and run again")
    sys.exit(1)
  cmd = ["winget", "install", "--id", "Git.Git", "-e", "--silent",
    "--accept-package-agreements", "--accept-source-agreements"]
  # User scope needs no admin rights, machine scope is the fallback
  try:
    if run(cmd + ["--scope", "user"], capture=False).returncode:
      run(cmd, capture=False, check=True)
  except (OSError, subprocess.CalledProcessError):
    p.err(f"winget failed, install Git from {color_link('https://git-scm.com')}")
    sys.exit(1)
  if use_installed_git():
    p.ok(f"{color_program('Git')} installed")
    return
  p.err("Git installed, open a new console and run again")
  sys.exit(1)

def ensure_packages(names:tuple[str, ...], yes:bool):
  """
  Tools `names` ready to run from this process.

  Windows: packages present and first on PATH, the missing ones installed once confirmed.
  Linux: commands on PATH, or a list of what is missing.
  `yes` answers every install prompt.
  """
  if not WINDOWS:
    missing = [COMMANDS[n] for n in names if not which(COMMANDS[n])]
    if missing:
      p.err(f"Not found: {', '.join(color_program(m) for m in missing)}")
      p.inf("Install them with your package manager and run again")
      sys.exit(1)
    return
  root = tools_dir()
  if DIR.exists(root): sweep(root)
  installed = JSON.load(f"{root}/{INSTALLED}", {})
  missing = [n for n in names
    if installed.get(n) != PACKAGES[n] or not DIR.exists(tool_path(n))]
  if missing:
    listed = ", ".join(color_program(n) for n in missing)
    if not yes and not is_yes(f"Install OpenCPLC tools {listed} from {color_link(URL_DL)}"):
      p.err(f"See instructions at {color_link('https://github.com/OpenCPLC/Forge')}")
      sys.exit(1)
    for name in missing: install(name)
  os.environ["PATH"] = ";".join([bin_dir(n) for n in names] + [os.environ.get("PATH", "")])

def ensure_tools(is_embedded:bool, yes:bool, tests:bool=False):
  """Everything a build needs, and on Windows `make` on the user PATH for any new console."""
  ensure_git(yes)
  ensure_packages(tool_names(is_embedded, tests), yes)
  if WINDOWS and tools_dir() == DEFAULT_DIR: user_path_add(bin_dir("make"))

def verify_compiler(is_embedded:bool) -> bool:
  """Compiler answers `--version`, not just sits on PATH."""
  compiler = "arm-none-eabi-gcc" if is_embedded else "gcc"
  # Bytes, never decoded: a localized compiler answers in the code page of its console
  try:
    return subprocess.run([compiler, "--version"], capture_output=True, timeout=5).returncode == 0
  except (OSError, subprocess.TimeoutExpired):
    return False

def ensure_toolchain(is_embedded:bool, yes:bool, tests:bool):
  """Tools of a build installed when missing, then the compiler seen to run; a dead one exits."""
  ensure_tools(is_embedded, yes, tests)
  if verify_compiler(is_embedded): return
  compiler = "arm-none-eabi-gcc" if is_embedded else "gcc"
  p.err(f"Compiler {color_program(compiler)} not working")
  if WINDOWS:
    p.tip(f"Remove {color_folder(tools_dir())} and run again, Forge reinstalls them")
  else:
    p.tip(f"Check that {color_program(compiler)} is installed and on {color_symbol('PATH')}")
  sys.exit(1)

#---------------------------------------------------------------------------------------- User PATH

def user_path_add(path:str):
  """
  `path` on the user PATH (HKCU) once, no admin: `make` in any new console.

  The console this runs in keeps its old PATH, so it is told once, when the entry is new.
  """
  import winreg
  entry = path.replace("/", "\\")
  access = winreg.KEY_READ | winreg.KEY_SET_VALUE
  with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, access) as key:
    try:
      current, kind = winreg.QueryValueEx(key, "Path")
    except FileNotFoundError:
      current, kind = "", winreg.REG_EXPAND_SZ
    entries = [e for e in current.split(";") if e]
    if entry.lower() in (e.lower() for e in entries): return
    winreg.SetValueEx(key, "Path", 0, kind, ";".join(entries + [entry]))
  _broadcast_env_change()
  p.wrn(f"{grey(entry)} added to your PATH, "
    f"open a new console to use {color_program('make')}")

def _broadcast_env_change():
  """Tell open windows the environment changed; a console picks it up when it starts."""
  import ctypes
  HWND_BROADCAST, WM_SETTINGCHANGE, SMTO_ABORTIFHUNG = 0xFFFF, 0x001A, 0x0002
  ctypes.windll.user32.SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment",
    SMTO_ABORTIFHUNG, 5000, ctypes.byref(ctypes.c_ulong(0)))
