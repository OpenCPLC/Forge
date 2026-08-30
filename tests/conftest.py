# tests/conftest.py

"""
Collection rules and shared helpers for the suite.

`python_functions = ["*"]` would collect any function a test file imports,
so collection is narrowed to the ones each module defines itself.
"""

import inspect, os

import pytest

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

@pytest.fixture(autouse=True, scope="session")
def the_suite_leaves_no_droppings():
  """The xaeian file API resolves relative paths against the repo root, not the test cwd."""
  before = set(os.listdir(REPO_ROOT))
  yield
  new = set(os.listdir(REPO_ROOT)) - before - {".pytest_cache", "__pycache__"}
  assert not new, f"the test run dropped files in the repo root: {sorted(new)}"

def pytest_pycollect_makeitem(collector, name, obj):
  if inspect.isfunction(obj) and obj.__module__ != collector.obj.__name__:
    return [] # ignore library functions imported into the test file

FILES_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "opencplc", "files"))

def load_template(name:str) -> str:
  """Raw template content from opencplc/files."""
  with open(os.path.join(FILES_DIR, name), encoding="utf-8") as f:
    return f.read()

def render(template:str, subs:dict) -> str:
  """Substitute ${KEY} placeholders the way utils.create_file does."""
  content = template.strip()
  for key, val in subs.items():
    content = content.replace(key, str(val))
  return content

from opencplc import utils

def parse_main_h(text:str) -> dict:
  """Read PRO_* definitions the exact way config_load does."""
  lines = utils.lines_clear(text.splitlines(), "//")
  info = utils.get_vars(lines, ["PRO_BOARD", "PRO_CHIP"], "_", "#define", required=False)
  info |= utils.get_vars(lines, ["PRO_VERSION", "PRO_FLASH_kB", "PRO_RAM_kB",
    "PRO_OPT_LEVEL", "LOG_LEVEL", "SYS_CLOCK_FREQ"], " ", "#define", required=False)
  return info

def parse_dispatcher(text:str) -> str:
  """Read ACTIVE the exact way makefile_info does."""
  lines = utils.lines_clear(text.splitlines(), "#")
  return utils.get_vars(lines, ["ACTIVE"], ":=", required=False).get("ACTIVE", "")

from opencplc.platforms import parse_chip

CORE_FILES = [
  "hal/arm/core.c", "hal/arm/core.h", "hal/arm/startup.s",
  "hal/stm32/gpio.c", "hal/stm32/gpio.h",
  "hal/stm32g0/uart.c", "hal/stm32g0/uart.h",
  "lib/log/log.c", "lib/log/log.h",
  "plc/plc.c", "plc/plc.h",
  "plc/brd/opencplc.h",
  "plc/brd/uno/opencplc_uno.c", "plc/brd/uno/opencplc_uno.h",
  "plc/brd/eco/opencplc_eco.c", "plc/brd/eco/opencplc_eco.h",
  "plc/dvr/max31865.c", "plc/dvr/max31865.h",
  "plc/dvr/shtc3.c", "plc/dvr/shtc3.h",
]
UNO_INI = "chip = STM32G0C1\nflash_kB = 492\nram_kB = 144\nclock_Hz = 59904000\n" \
  "drivers = max31865\n"

def build_workspace(ws, core:str="1.0.0", project:str="myapp"):
  """Synthetic workspace: minimal Core tree plus one project."""
  for rel in CORE_FILES:
    fp = ws / "opencplc" / core / rel
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(f"// {rel}\n")
  (ws / "opencplc" / core / "plc" / "brd" / "uno" / "opencplc_uno.ini").write_text(UNO_INI)
  pro = ws / "projects" / project
  (pro / "util").mkdir(parents=True)
  (pro / "main.c").write_text("// main\n")
  (pro / "main.h").write_text("// conf\n")
  (pro / "util" / "extra.c").write_text("// extra\n")
  (ws / "opencplc.json").write_text("{}")
  return ws

def uno_cfg(name:str="myapp", core:str="1.0.0") -> dict:
  """cfg of an Uno project, as configure.py would build it from board.ini."""
  return parse_chip("STM32G0C1") | {
    "pro_name": name, "pro_ver": core, "fw_ver": core,
    "opt_level": "Og", "log_level": "LOG_LEVEL_INF",
    "board": "uno", "board_dir": f"opencplc/{core}/plc/brd/uno", "board_drivers": ["max31865"],
    "project_drivers": [], "flash_kB": 492, "ram_kB": 144, "freq_Hz": 59904000,
  }

def ws_paths(core:str="1.0.0", name:str="myapp") -> dict:
  return {
    "projects": "projects", "framework": "opencplc", "build": "build",
    "fw": f"opencplc/{core}", "pro": f"projects/{name}",
  }

def resolve_uno(forge_cfg=None):
  """Resolved Uno model over the synthetic workspace."""
  from opencplc.resolver import resolve_project
  return resolve_project(uno_cfg(), ws_paths(), forge_cfg or {})

def refs_cfg() -> dict:
  """Workspace config with a cached version list, offline."""
  return {"available-versions": ["1.0.0"], "stlink": {}}

def pro_map(ws, name:str="myapp") -> dict:
  return {name: str(ws / "projects" / name)}

def write_forge_config(ws):
  """opencplc.json with a cached version list, so the CLI never touches the network."""
  (ws / "opencplc.json").write_text(
    '{"version": "1.0.0", "available-versions": ["1.0.0"], "stlink": {}}'
  )

def run_cli(monkeypatch, *argv) -> int:
  """Run the CLI main() in-process with argv; returns the exit code (0 for a normal return)."""
  import sys
  import opencplc.__main__ as forge
  monkeypatch.setattr(sys, "argv", ["opencplc", *argv])
  try:
    forge.main()
  except SystemExit as e:
    return int(e.code or 0)
  return 0

def host_cfg(name:str) -> dict:
  return parse_chip("HOST") | {
    "pro_name": name, "pro_ver": "1.0.0", "fw_ver": "1.0.0", "freq_Hz": 0,
    "opt_level": "O0", "log_level": "LOG_LEVEL_INF",
    "board": None, "board_dir": None, "board_drivers": [],
    "project_drivers": [],
  }

def host_model(name:str="app"):
  """Resolved HOST model for a project in the synthetic workspace."""
  from opencplc.resolver import resolve_project
  return resolve_project(host_cfg(name), ws_paths(name=name), {})

def make_run(ws, project:str, *goals:str):
  """GNU Make on a project directory; returns the CompletedProcess."""
  import subprocess
  return subprocess.run(["make", "-C", str(ws / "projects" / project), *goals],
    capture_output=True, text=True)

def write_file(path, text:str):
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(text)

def forge_env():
  """Environment and FORGE override that let Make run this interpreter's opencplc."""
  import os, sys
  env = os.environ.copy()
  env["PYTHONPATH"] = REPO_ROOT
  return env, f"FORGE={sys.executable} -m opencplc"

def age(*paths, seconds:float=10.0):
  """Move mtimes into the past, so a fresh touch is newer at any timestamp resolution."""
  import os
  for path in paths:
    stamp = os.path.getmtime(path) - seconds
    os.utime(path, (stamp, stamp))

INI = "chip = STM32G0C1\nflash_kB = 492\nram_kB = 144\nclock_Hz = 59904000\n"

def make_board(core, name:str, ini:str=INI, header:bool=True):
  d = core / "plc" / "brd" / name
  d.mkdir(parents=True, exist_ok=True)
  (d / f"opencplc_{name}.ini").write_text(ini)
  if header:
    (d / f"opencplc_{name}.h").write_text("")
  return d
