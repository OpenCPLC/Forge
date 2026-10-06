# tests/conftest.py

"""
Collection rules and shared helpers for the suite.

`python_functions = ["*"]` would collect any function a test file imports,
so collection is narrowed to the ones each module defines itself.
"""

import inspect, os, json, sys, subprocess

import pytest

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

@pytest.fixture(autouse=True, scope="session")
def the_suite_leaves_no_droppings():
  """The xaeian file API resolves relative paths against the repo root, not the test cwd."""
  before = set(os.listdir(REPO_ROOT))
  yield
  new = set(os.listdir(REPO_ROOT)) - before - {".pytest_cache", "__pycache__"}
  assert not new, f"the test run dropped files in the repo root: {sorted(new)}"

@pytest.fixture(autouse=True)
def keys_dir(tmp_path, monkeypatch):
  """Keys of a machine made for the test, so no test reads or makes the real development key."""
  monkeypatch.setenv(keys.KEYS_ENV, str(tmp_path / "keys"))
  return tmp_path / "keys"

def pytest_pycollect_makeitem(collector, name, obj):
  # ignore library functions imported into the test file
  if inspect.isfunction(obj) and obj.__module__ != collector.obj.__name__: return []

from xaeian import FILE, replace_map
import opencplc
# Templates of the package under test: the source tree, or a wheel installed without it
from opencplc.templates import FILES_DIR

def load_template(name:str) -> str:
  """Raw template content from `FILES_DIR`."""
  return FILE.load(f"{FILES_DIR}/{name}")

def render(template:str, subs:dict) -> str:
  """Substitute `${KEY}` placeholders the way `utils.create_file` does."""
  return replace_map(template.strip(), subs)

from opencplc import utils
from opencplc.utils import keys
from opencplc.configure import main_h_defines

def parse_main_h(text:str) -> dict:
  """Read `PRO_*` definitions the exact way `config_load` does."""
  return main_h_defines(utils.lines_clear(text.splitlines(), "//"))

def parse_dispatcher(text:str) -> str:
  """Read `ACTIVE` the exact way `makefile_info` does."""
  lines = utils.lines_clear(text.splitlines(), "#")
  return utils.get_vars(lines, ["ACTIVE"], ":=", required=False).get("ACTIVE", "")

from opencplc.platforms import parse_chip
from opencplc.resolver import resolve_project

CORE_FILES = [
  "hal/arm/core.c", "hal/arm/core.h", "hal/arm/startup.s",
  "hal/stm32/gpio.c", "hal/stm32/gpio.h",
  "hal/stm32g0/uart.c", "hal/stm32g0/uart.h",
  "lib/log/log.c", "lib/log/log.h",
  "scr/boot_stm32g0.hex", "scr/boot_stm32wb.hex", # `plain` bootloaders, only their names count
  "plc/plc.c", "plc/plc.h",
  "brd/opencplc.h",
  "brd/uno/opencplc_uno.c", "brd/uno/opencplc_uno.h",
  "brd/eco/opencplc_eco.c", "brd/eco/opencplc_eco.h",
  "dvr/max31865.c", "dvr/max31865.h",
  "dvr/shtc3.c", "dvr/shtc3.h",
  "dvr/temp/sht4x.c", "dvr/temp/sht4x.h",
  "dvr/acc/ism330.c", "dvr/acc/ism330.h",
]
MAIN_H_UNO = """#define PRO_BOARD_UNO
#define PRO_CHIP_STM32G0C1
#define PRO_PLC true
#define PRO_FRAMEWORK "1.0.0"
#define PRO_FLASH_kB 492
#define PRO_RAM_kB 144
#define PRO_OPT_LEVEL "Og"
#define LOG_LEVEL LOG_LEVEL_INF
#define SYS_CLOCK_FREQ 59904000
"""

MAIN_H_HOST = """#define PRO_CHIP_HOST
#define PRO_FRAMEWORK "1.0.0"
#define PRO_OPT_LEVEL "O0"
#define LOG_LEVEL LOG_LEVEL_INF
"""

UNO_INI = "name = Uno\nchip = STM32G0C1\nplc = true\nflash_kB = 492\n" \
  "ram_kB = 144\nclock_Hz = 59904000\ndrivers = max31865\n"

def build_workspace(ws, core:str="1.0.0", project:str="myapp"):
  """Synthetic workspace: minimal Core tree plus one project."""
  for rel in CORE_FILES:
    fp = ws / "opencplc" / core / rel
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(f"// {rel}\n")
  (ws / "opencplc" / core / "brd" / "uno" / "opencplc_uno.ini").write_text(UNO_INI)
  pro = ws / "projects" / project
  (pro / "util").mkdir(parents=True)
  (pro / "main.c").write_text("// main\n")
  (pro / "main.h").write_text(MAIN_H_UNO)
  (pro / "util" / "extra.c").write_text("// extra\n")
  (ws / "opencplc.json").write_text("{}")
  return ws

KEY = "8a" * 32 # `PRO_BOOT_KEY` of a test product, the key `dist` signs with

def ship_key_bootloader(ws, hal:str="stm32g0", core:str="1.0.0"):
  """Core with the `key` bootloader of a family beside the `plain` one."""
  scr = ws / "opencplc" / core / "scr"
  scr.mkdir(parents=True, exist_ok=True)
  (scr / f"boot_{hal}_key.hex").write_text(":00000001FF\n")

def add_define(ws, line:str, project:str="myapp"):
  """One more `#define` at the end of the project `main.h`, where Forge reads it as well."""
  main_h = ws / "projects" / project / "main.h"
  main_h.write_text(main_h.read_text().rstrip("\n") + f"\n{line}\n")

def uno_cfg(name:str="myapp", core:str="1.0.0") -> dict:
  """cfg of an Uno project, as `config_new` would build it from the manifest."""
  return parse_chip("STM32G0C1") | {
    "pro_name": name, "pro_ver": core, "fw_ver": core,
    "opt_level": "Og", "log_level": "LOG_LEVEL_INF",
    "board": "uno", "board_title": "Uno", "board_dir": f"opencplc/{core}/brd/uno",
    "board_drivers": ["max31865"],
    "plc": True,
    "project_drivers": [], "flash_kB": 492, "ram_kB": 144, "freq_Hz": 59904000,
  }

def wb55_cfg(name:str="myapp", core:str="1.0.0") -> dict:
  """cfg of a bare-metal STM32WB55 project, the chip with a radio stack."""
  return parse_chip("STM32WB55") | {
    "pro_name": name, "pro_ver": core, "fw_ver": core,
    "opt_level": "Og", "log_level": "LOG_LEVEL_INF",
    "board": None, "board_title": "", "board_dir": None, "board_drivers": [],
    "plc": False, "project_drivers": [], "freq_Hz": 16000000,
  }

def ws_paths(core:str="1.0.0", name:str="myapp") -> dict:
  """Workspace paths of `paths_setup`, with `pro` narrowed to the project."""
  return {
    "projects": "projects", "framework": "opencplc", "build": "build",
    "fw": f"opencplc/{core}", "pro": f"projects/{name}",
  }

def resolve_key_uno():
  """Resolved Uno model under the `key` bootloader."""
  return resolve_project(uno_cfg() | {"boot": True, "boot_key": KEY}, ws_paths(), {})

def resolve_uno(forge_cfg=None):
  """Resolved Uno model over the synthetic workspace."""
  return resolve_project(uno_cfg(), ws_paths(), forge_cfg or {})

def refs_cfg() -> dict:
  """Workspace config with a cached version list, offline."""
  return {"available-versions": ["1.0.0"], "stlink": {}}

def pro_map(ws, name:str="myapp") -> dict:
  """Project map as `get_project_list` returns it, holding `name` alone."""
  return {name: str(ws / "projects" / name)}

def load_myapp(ws) -> dict:
  """cfg of myapp read back from its main.h, as a reload reads it."""
  from opencplc.args import Args
  from opencplc.configure import config_load
  return config_load(Args(name="myapp"), pro_map(ws), ws_paths(), "1.0.0", refs_cfg())

def read_makefile(ws, project:str="myapp") -> str:
  """Makefile Forge generated for `project`."""
  return (ws / "projects" / project / "makefile").read_text()

def write_forge_config(ws):
  """opencplc.json with a cached version list, so the CLI never touches the network."""
  (ws / "opencplc.json").write_text(
    '{"version": "1.0.0", "available-versions": ["1.0.0"], "stlink": {}}',
  )

def run_cli(monkeypatch, *argv) -> int:
  """Run the CLI `main()` in-process with `argv`; returns the exit code (0 for a normal return)."""
  import opencplc.__main__ as forge
  monkeypatch.setattr(sys, "argv", ["opencplc", *argv])
  try:
    forge.main()
  except SystemExit as e:
    return int(e.code or 0)
  return 0

def host_cfg(name:str) -> dict:
  """cfg of a HOST project, a desktop program with no board and no flash."""
  return parse_chip("HOST") | {
    "pro_name": name, "pro_ver": "1.0.0", "fw_ver": "1.0.0", "freq_Hz": 0,
    "opt_level": "O0", "log_level": "LOG_LEVEL_INF",
    "board": None, "board_title": "", "board_dir": None, "board_drivers": [],
    "plc": False,
    "project_drivers": [],
  }

def host_model(name:str="app"):
  """Resolved HOST model for a project in the synthetic workspace."""
  return resolve_project(host_cfg(name), ws_paths(name=name), {})

def make_run(ws, *goals:str, project:str="app"):
  """GNU Make on a project directory, with the reload rule pointed at this interpreter."""
  env, forge = forge_env(ws)
  return subprocess.run(["make", "-C", str(ws / "projects" / project), *goals, forge],
    capture_output=True, text=True, env=env)

def make_root(ws, *goals:str):
  """GNU Make in the workspace root, on the active project."""
  env, forge = forge_env(ws)
  return subprocess.run(["make", *goals, forge], cwd=ws, capture_output=True, text=True, env=env)

def write_file(path, text:str):
  """Text file at `path`, parent directories made as needed."""
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(text)

def fake_tools(ws) -> str:
  """
  Tools directory Forge takes as complete, so a reload installs nothing.

  Package folders stay empty and PATH falls through to the real compilers behind them;
  `make/make.exe` is a copy of the real one, since the exported PATH puts that folder first.
  """
  import shutil
  from opencplc.utils.tools import PACKAGES
  root = ws / ".tools"
  for name in PACKAGES:
    (root / name / ("" if name == "make" else "bin")).mkdir(parents=True, exist_ok=True)
  shutil.copy(shutil.which("make"), root / "make" / "make.exe")
  (root / "tools.json").write_text(json.dumps(PACKAGES))
  return str(root)

def forge_env(ws):
  """Environment and FORGE override that let Make run this interpreter's opencplc."""
  import xaeian
  env = os.environ.copy()
  # the same opencplc and xaeian these tests import, wherever they come from
  forge_home = os.path.dirname(os.path.dirname(opencplc.__file__))
  xaeian_home = os.path.dirname(os.path.dirname(xaeian.__file__))
  env["PYTHONPATH"] = os.pathsep.join([forge_home, xaeian_home])
  env["OPENCPLC_TOOLS"] = fake_tools(ws)
  return env, f"FORGE={sys.executable} -m opencplc"

def age(*paths, seconds:float=10.0):
  """Move mtimes into the past, so a fresh touch is newer at any timestamp resolution."""
  for path in paths:
    stamp = os.path.getmtime(path) - seconds
    os.utime(path, (stamp, stamp))

INI = "chip = STM32G0C1\nplc = true\nflash_kB = 492\nram_kB = 144\nclock_Hz = 59904000\n"

def make_board(core, name:str, ini:str=INI, header:bool=True, title:str=""):
  """Board directory with a manifest; the title defaults to the directory name."""
  d = core / "brd" / name
  d.mkdir(parents=True, exist_ok=True)
  if "name = " not in ini: ini = f"name = {title or name}\n" + ini
  (d / f"opencplc_{name}.ini").write_text(ini)
  if header:
    (d / f"opencplc_{name}.h").write_text("")
  return d

def _raise_disk_full(*args, **kwargs):
  raise OSError("no space left on device")

def frozen_forge(tmp_path, monkeypatch, version="9.9.9"):
  """`actions` as a frozen build in `tmp_path`, with GitHub and the download stubbed out."""
  from opencplc import actions
  exe = tmp_path / "opencplc.exe"
  exe.write_bytes(b"old")
  monkeypatch.setattr(actions, "FROZEN", True)
  monkeypatch.setattr(actions.PATH, "script_dir", staticmethod(lambda: str(tmp_path)))
  monkeypatch.setattr(actions.utils, "ensure_git", lambda yes: None)
  monkeypatch.setattr(actions.utils, "git_get_refs", lambda url, opt="--ref": [version])
  monkeypatch.setattr(actions.utils, "download", lambda url, *a, **k: b"new")
  return exe

def write_app_image(path, origin:int, size:int, header:bool=True, trailer:int=72):
  """
  Application hex laid out as linked.

  Vector table, gap up to the header at 0x200, code up to `size`, erased trailer.
  """
  from opencplc.utils.hexfile import Memory, save_hex
  app = Memory()
  stack, reset = 0x20008000, origin + 0x301
  vectors = stack.to_bytes(4, "little") + reset.to_bytes(4, "little")
  app.add(origin, vectors + bytes(0xC0 - len(vectors)))
  body = b"OPEN" + size.to_bytes(4, "little") if header else bytes(8)
  code = bytes(range(256))
  body += code + bytes(size - 0x200 - len(body) - len(code))
  app.add(origin + 0x200, body + b"\xff" * trailer)
  app.start = reset
  save_hex(app, path)

def write_boot_image(path, data:bytes):
  """Bootloader hex as Core ships it: `data` from the start of flash."""
  from opencplc.utils.hexfile import Memory, save_hex
  boot = Memory()
  boot.add(0x08000000, data)
  save_hex(boot, path)
