# tests/conftest.py

"""
Collection rules and shared helpers for the suite.

`python_functions = ["*"]` would collect any function a test file imports,
so collection is narrowed to the ones each module defines itself.
"""

import inspect, os, json, sys, shutil, subprocess

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
def machine_dir(tmp_path, monkeypatch):
  """Key folder of a machine made for the test: no test reads or makes the real development key."""
  monkeypatch.setattr(keys, "machine_dir", lambda: (tmp_path / "machine").as_posix())
  return tmp_path / "machine"

@pytest.fixture(autouse=True)
def keys_dir(tmp_path, monkeypatch, machine_dir):
  """Sign and cipher keys of the test, in a folder `OPENCPLC_KEYS` moves apart from the machine."""
  monkeypatch.setenv(keys.KEYS_ENV, str(tmp_path / "keys"))
  return tmp_path / "keys"

@pytest.fixture(autouse=True)
def console(monkeypatch):
  """A person sits at the console, so a password a test asks for goes to its `getpass`."""
  monkeypatch.setattr(keys, "console", lambda: True)

def pytest_pycollect_makeitem(collector, name, obj):
  # Library functions imported into a test file are no tests, decorated ones such as `@cache` too
  imported = getattr(obj, "__module__", None) != collector.obj.__name__
  if inspect.isfunction(inspect.unwrap(obj)) and imported: return []

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
from opencplc.headers import main_h_defines, header_lines

def parse_main_h(text:str) -> dict:
  """Read `PRO_*` definitions the exact way `config_load` does."""
  return main_h_defines(header_lines(text.split("\n")))

def parse_dispatcher(text:str) -> str:
  """Read `ACTIVE` the exact way `makefile_info` does."""
  lines = utils.lines_clear(text.splitlines(), "#")
  return utils.get_vars(lines, ["ACTIVE"], ":=", required=False).get("ACTIVE", "")

from dataclasses import replace
from opencplc.platforms import parse_chip
from opencplc.boards import Board
from opencplc.model import Config
from opencplc.resolver import resolve_project

CORE_FILES = [
  "hal/arm/core.c", "hal/arm/core.h", "hal/arm/startup.s",
  "hal/stm32/gpio.c", "hal/stm32/gpio.h",
  "hal/stm32g0/uart.c", "hal/stm32g0/uart.h",
  "lib/log/log.c", "lib/log/log.h",
  ".boot/main.c", ".boot/main.h", # the bootloader program, which Forge compiles under an image
  "plc/plc.c", "plc/plc.h",
  "brd/opencplc.h",
  "brd/uno/opencplc_uno.c", "brd/uno/opencplc_uno.h",
  "brd/eco/opencplc_eco.c", "brd/eco/opencplc_eco.h",
  "drv/max31865.c", "drv/max31865.h",
  "drv/shtc3.c", "drv/shtc3.h",
  "drv/temp/sht4x.c", "drv/temp/sht4x.h",
  "drv/acc/ism330.c", "drv/acc/ism330.h",
]
MAIN_H_UNO = """#define PRO_BOARD_Uno
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

def local_copy(ws, name:str="app"):
  """Copy of project `myapp` outside the workspace, in `ext/name` beside it."""
  pro = ws.parent / "ext" / name
  shutil.copytree(ws / "projects" / "myapp", pro)
  return pro

KEY = "8a" * 32 # key `0` of `BOOT_KEYS` of a test product

CORE_TEST = "opencplc/1.0.0/.tests/g081"

def core_test(ws, pin:str=""):
  """Project `.tests/g081` of Core 1.0.0, `pin` the `PRO_FRAMEWORK` it should not have."""
  pro = ws / CORE_TEST
  pro.mkdir(parents=True)
  (pro / "main.c").write_text("// .tests/g081/main.c\n")
  (pro / "main.h").write_text(f"#define PRO_CHIP_STM32G081\n{pin}")
  return pro

def add_define(ws, line:str, project:str="myapp"):
  """One more `#define` at the end of the project `main.h`, where Forge reads it as well."""
  main_h = ws / "projects" / project / "main.h"
  main_h.write_text(main_h.read_text().rstrip("\n") + f"\n{line}\n")

def add_boot_define(ws, line:str, project:str="myapp"):
  """One more `#define` at the end of the project `boot.h`, where Forge reads it as well."""
  boot_h = ws / "projects" / project / "boot.h"
  boot_h.write_text(boot_h.read_text().rstrip("\n") + f"\n{line}\n")

def edit_main_h(ws, old:str, new:str, project:str="myapp"):
  """`old` in the project `main.h` replaced by `new`; text it lacks fails the test."""
  main_h = ws / "projects" / project / "main.h"
  text = main_h.read_text()
  assert old in text, f"{old!r} not in {main_h}"
  main_h.write_text(text.replace(old, new))

def uno_cfg(name:str="myapp", core:str="1.0.0") -> Config:
  """Config of an Uno project, as `config_new` would build it from the manifest."""
  uno = Board(name="uno", title="Uno", dir=f"opencplc/{core}/brd/uno", plc=True,
    chip="STM32G0C1", flash_kB=492, reserve_kB=0, ram_kB=144, freq_Hz=59904000,
    drivers=["max31865"])
  return Config(chip=parse_chip("STM32G0C1"), board=uno, plc=True,
    flash_kB=492, ram_kB=144, freq_Hz=59904000, name=name, pro_ver=core, fw_ver=core)

def wb55_cfg(name:str="myapp", core:str="1.0.0") -> Config:
  """Config of a bare-metal STM32WB55 project, the chip with a radio stack."""
  wb55 = parse_chip("STM32WB55")
  return Config(chip=wb55, board=None, plc=False, flash_kB=wb55.flash_kB, ram_kB=wb55.ram_kB,
    freq_Hz=16000000, name=name, pro_ver=core, fw_ver=core)

def key_boot(keys:str=KEY) -> dict:
  """Config fields of a project behind the `key` bootloader of `keys`, as its boot.h gives them."""
  return {"boot": True, "boot_keys": keys}

def resolve_key_uno():
  """Resolved Uno model behind the `key` bootloader of `KEY`."""
  return resolve_project(replace(uno_cfg(), **key_boot()))

def resolve_key_wb55():
  """Resolved WB55 model in 818kB behind the `key` bootloader of `KEY`."""
  cfg = replace(uno_cfg(), chip=parse_chip("STM32WB55"), flash_kB=818, **key_boot())
  return resolve_project(cfg)

def resolve_uno(stlink:str=""):
  """Resolved Uno model over the synthetic workspace."""
  return resolve_project(replace(uno_cfg(), stlink=stlink))

def refs_cfg() -> dict:
  """Workspace config with a cached version list, offline."""
  return {"available-versions": ["1.0.0"], "stlink": {}}

def pro_map(ws, name:str="myapp") -> dict:
  """Project map as `get_project_list` returns it: `name` and the projects right in `projects/`."""
  found = {d.name: str(d) for d in (ws / "projects").iterdir() if (d / "main.h").exists()}
  return {name: str(ws / "projects" / name)} | found

def load_project(ws, name:str="myapp", **flags) -> dict:
  """cfg of a project read back from its main.h, as `opencplc <name>` with `flags` reads it."""
  from opencplc.args import Args
  from opencplc.configure import config_load
  args = Args(name=name, **flags)
  return config_load(args, pro_map(ws, name), "1.0.0", refs_cfg())

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

def host_cfg(name:str) -> Config:
  """Config of a HOST project, a desktop program with no board and no flash."""
  return Config(chip=parse_chip("HOST"), board=None, plc=False, flash_kB=0, ram_kB=0, freq_Hz=0,
    name=name, pro_ver="1.0.0", fw_ver="1.0.0", opt_level="O0")

def host_model(name:str="app"):
  """Resolved HOST model for a project in the synthetic workspace."""
  return resolve_project(host_cfg(name))

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

def write_harness(ws):
  """Harness of Core 1.0.0 counting checks, and `.tests/test_util.c` of the app on it."""
  core = ws / "opencplc" / "1.0.0"
  write_file(core / "lib" / "sh" / "test.h", "extern int checks;\nvoid TEST_Cases(void);\n")
  write_file(core / "lib" / "sh" / "test.c", '#include <stdio.h>\n#include "test.h"\nint checks;\n'
    'int main(void) { TEST_Cases(); printf("%d OK\\n", checks); return 0; }\n')
  write_file(ws / "projects" / "app" / ".tests" / "test_util.c",
    '#include "test.h"\n#include "util.h"\nvoid TEST_Cases(void) { checks += lib_util() == 1; }\n')

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
  # The same opencplc and xaeian these tests import, wherever they come from
  forge_home = os.path.dirname(os.path.dirname(opencplc.__file__))
  xaeian_home = os.path.dirname(os.path.dirname(xaeian.__file__))
  env["PYTHONPATH"] = os.pathsep.join([forge_home, xaeian_home])
  env["OPENCPLC_TOOLS"] = fake_tools(ws)
  return env, f"FORGE={sys.executable} -m opencplc"

def age(*paths, seconds:float=10.0):
  """
  Move mtimes into the past, so a fresh touch is newer at any timestamp resolution.

  Make on Windows compares whole seconds: a quick build leaves its outputs,
  reload stamp `.forge` too, in the second of the next edit.
  """
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
  save_hex(app, str(path))

def write_boot_image(path, data:bytes):
  """Bootloader hex as its build links it: `data` from the start of flash."""
  from opencplc.utils.hexfile import Memory, save_hex
  boot = Memory()
  boot.add(0x08000000, data)
  save_hex(boot, str(path))

def signed_by(public:bytes, update:bytes, size:int) -> bool:
  """`True` when the trailer of `update` holds the signature of its `size` bytes by `public`."""
  from opencplc.utils import ed25519
  return ed25519.verify(public, update[:size], update[size + 8:size + 72])

def build_program(folder, name:str, body:str):
  """Test program `name` from C `body`, where `make test` leaves one."""
  from opencplc.runner import EXE_EXT
  src = folder / f"{name}.c"
  src.write_text(body)
  subprocess.run(["gcc", str(src), "-o", str(folder / f"{name}{EXE_EXT}")], check=True)

def ci_node(title:str, at:str, frame:str|None="8 bytes (static)") -> str:
  """Node of a `.ci` as gcc writes it: defined with its frame, or only declared without one."""
  label = f"{title.split(':')[-1]}\\n{at}" + (f"\\n{frame}" if frame else "")
  shape = "" if frame else " shape : ellipse"
  return f'node: {{ title: "{title}" label: "{label}"{shape} }}'

def ci_edge(caller:str, callee:str, site:str) -> str:
  """Call of a `.ci`, from `caller` to `callee` at `site`."""
  return f'edge: {{ sourcename: "{caller}" targetname: "{callee}" label: "{site}" }}'

def ci_graph(*lines:str):
  """Call graph of one `.ci` made of `lines`."""
  from opencplc.lint.graph import Graph, read
  graph = Graph()
  read("\n".join(['graph: { title: "a.c"', *lines, "}"]), graph)
  return graph

def lint_finding(rule:str, path:str, function:str=""):
  """Finding of `rule` at `path`, inside `function` when one is named."""
  from opencplc.lint.finding import Finding
  return Finding(rule, path, 1, 1, "message", function)

def value_switch(
  enum:str = "MODE_t", default:bool = False, cases:frozenset = frozenset(), values = None,
):
  """`switch` of `act` in `mode.c`, steered by `enum` or by a `uint8_t` when it is ""."""
  from opencplc.lint.dump import Switch, Values
  return Switch("mode.c", 20, "act", enum, enum or "uint8_t", default, cases, values or Values())

def value_entry(values, kind:str="assignment", param=None, checked:bool=False):
  """A `uint8_t` entering `MODE_t` in `parse` of `frame.c`, a raw copy into its field `mode`."""
  from opencplc.lint.dump import Entry
  return Entry("MODE_t", "frame.c", 7, "parse", kind, "uint8_t", values, param, "mode", checked)

def value_found(*units) -> list[tuple[str, str]]:
  """Rule and message of each finding `check_switches` gives over `units`."""
  from opencplc.lint.values import merge, check_switches
  return [(f.rule, f.message) for f in check_switches(merge(list(units)))]
