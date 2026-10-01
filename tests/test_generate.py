# tests/test_generate.py

"""Generators: project makefile, dispatcher, idempotency, preserved mtime."""

import json, re, time
import pytest
from xaeian import file_context
from opencplc import utils
from opencplc.project import generate, prepare_project
from opencplc.resolver import resolve_project
from conftest import build_workspace, uno_cfg, wb55_cfg, ws_paths, parse_dispatcher, resolve_uno

@pytest.fixture()
def ws(tmp_path):
  build_workspace(tmp_path)
  with file_context(root_path=str(tmp_path)):
    yield tmp_path

def project_makefile_and_linker_land_in_the_project(ws):
  generate(resolve_uno())
  make = (ws / "projects" / "myapp" / "makefile").read_text()
  assert "NAME := myapp" in make
  assert "WORKSPACE := $(abspath $(PROJECT)/../..)" in make
  assert "$(WORKSPACE)/opencplc/1.0.0" in make
  assert "$(WORKSPACE)/build/projects/myapp" in make
  assert "hal/arm/core.c" in make        # core-relative source
  assert "brd/uno/opencplc_uno.c" in make
  assert "brd/eco" not in make
  assert "main.c \\\nutil/extra.c" in make
  assert "stm32g0x mass_erase 0" in make
  assert (ws / "projects" / "myapp" / "flash.ld").exists()

def dispatcher_points_at_the_active_project(ws):
  generate(resolve_uno())
  root = (ws / "makefile").read_text()
  assert parse_dispatcher(root) == "projects/myapp"
  assert "clean_all" in root
  assert "--no-print-directory" in root
  assert "[" in root and "myapp" in root

def one_flash_rule_and_the_debugger_load_the_packed_image(ws):
  """Neither the makefile nor the debugger knows whether a bootloader sits in front."""
  rule = "program $(BUILD)/$(TARGET)-dist.hex verify reset exit"
  for cfg in (uno_cfg(), uno_cfg() | {"boot": True}):
    generate(resolve_project(cfg, ws_paths(), {}))
    make = (ws / "projects" / "myapp" / "makefile").read_text()
    assert make.count(rule) == 1 and "$(TARGET).elf verify" not in make
    launch = json.loads((ws / ".vscode" / "launch.json").read_text())["configurations"][0]
    assert launch["loadFiles"] == ["build/projects/myapp/myapp-dist.hex"]
    assert launch["executable"].endswith("myapp.elf") # symbols stay with the elf

def dist_carries_the_programmer_file_and_the_update_one(ws):
  """`plain` ships two files: the full image for a bare chip, the image alone for `UPDATE`."""
  generate(resolve_uno())
  make = (ws / "projects" / "myapp" / "makefile").read_text()
  assert "$(BUILD)/$(TARGET)-dist.hex,$(PROJECT)/$(DIST).hex" in make
  dist = make[make.index("\ndist:"):]
  update = "$(BUILD)/$(TARGET)-dist.bin,$(PROJECT)/$(DIST).bin"
  assert dist.index("ifeq ($(BOOT),true)") < dist.index(update) < dist.index("else")
  assert dist.index("Full image") < dist.index("else") < dist.index("Flash image")

def vscode_points_at_the_project_build_dir(ws):
  generate(resolve_uno())
  launch = (ws / ".vscode" / "launch.json").read_text()
  assert "build/projects/myapp/myapp.elf" in launch
  for name in ("c_cpp_properties.json", "tasks.json", "settings.json"):
    assert (ws / ".vscode" / name).exists(), name

def objects_map_into_disjoint_trees(ws):
  make = ""
  generate(resolve_uno())
  make = (ws / "projects" / "myapp" / "makefile").read_text()
  assert "$(BUILD)/opencplc/%.o: $(OPENCPLC)/%.c" in make
  assert "$(BUILD)/project/%.o: $(PROJECT)/%.c" in make
  assert "vpath" not in make

def unchanged_regeneration_keeps_bytes_and_mtime(ws):
  generate(resolve_uno())
  files = [
    ws / "projects" / "myapp" / "makefile",
    ws / "projects" / "myapp" / "flash.ld",
    ws / "makefile",
    ws / ".vscode" / "launch.json",
  ]
  stamps = {f: (f.read_bytes(), f.stat().st_mtime_ns) for f in files}
  time.sleep(0.02)
  generate(resolve_uno())
  for f in files:
    assert (f.read_bytes(), f.stat().st_mtime_ns) == stamps[f], f.name

def stlink_binds_makefile_and_debugger(ws):
  generate(resolve_uno())
  make = (ws / "projects" / "myapp" / "makefile").read_text()
  assert "STLINK := \n" in make
  assert "OPENOCD = openocd -f interface/stlink.cfg -f target/stm32g0x.cfg" in make
  assert "openOCDPreConfigLaunchCommands" not in (ws / ".vscode" / "launch.json").read_text()
  generate(resolve_uno({"stlink": {"projects/myapp": "ABC123"}}))
  make = (ws / "projects" / "myapp" / "makefile").read_text()
  assert "STLINK := ABC123" in make
  assert 'stlink.cfg -c "adapter serial ABC123" -f target/stm32g0x.cfg' in make
  launch = (ws / ".vscode" / "launch.json").read_text()
  assert "openOCDPreConfigLaunchCommands" in launch
  assert "ABC123" in launch

def nested_project_anchors_deeper(ws, tmp_path):
  build_workspace(tmp_path, project="firm/app")
  cfg = uno_cfg("firm/app")
  paths = ws_paths(name="firm/app")
  pro = resolve_project(cfg, paths, {})
  generate(pro)
  make = (tmp_path / "projects" / "firm" / "app" / "makefile").read_text()
  assert "WORKSPACE := $(abspath $(PROJECT)/../../..)" in make
  assert "$(WORKSPACE)/build/projects/firm/app" in make

def prepare_creates_skeleton_once(ws, tmp_path):
  cfg = uno_cfg("fresh")
  paths = ws_paths(name="fresh")
  prepare_project(cfg, paths)
  main_c = tmp_path / "projects" / "fresh" / "main.c"
  assert main_c.exists()
  main_c.write_text("// user edit\n")
  prepare_project(cfg, paths)
  assert main_c.read_text() == "// user edit\n"

def plain_project_links_at_the_start_of_flash(ws):
  generate(resolve_uno())
  ld = (ws / "projects" / "myapp" / "flash.ld").read_text()
  assert "ORIGIN = 0x08000000, LENGTH = 492K" in ld
  assert ".app_header ORIGIN(FLASH) + 0x200" in ld and ".app_trailer" in ld
  make = (ws / "projects" / "myapp" / "makefile").read_text()
  assert "BOOT := false" in make and "FLASH_kB := 492" in make
  assert "-DBOOT_CHIP=0x467" in make # every build, the bootloader one too
  assert "BOOT_IMAGE := \n" in make
  assert "$(FORGE) --pack $< $@ $(BOOT_IMAGE)" in make

def boot_project_links_into_its_slot_and_flashes_one_packed_image(ws):
  generate(resolve_project(uno_cfg() | {"boot": True}, ws_paths(), {}))
  ld = (ws / "projects" / "myapp" / "flash.ld").read_text()
  assert "ORIGIN = 0x08002000, LENGTH = 242K" in ld
  make = (ws / "projects" / "myapp" / "makefile").read_text()
  assert "BOOT := true" in make and "FLASH_kB := 242" in make
  assert "BOOT_IMAGE := $(OPENCPLC)/scr/boot_stm32g0.bin" in make
  assert "-DBOOT_SLOT_PAGES=121" in make

def stack_rule_takes_cube_from_its_default_home(ws, monkeypatch):
  monkeypatch.setattr(utils, "cube_bin", lambda: "C:/Program Files/cube/bin")
  monkeypatch.setattr(utils, "cube_found", lambda: True)
  generate(resolve_project(wb55_cfg(), ws_paths(), {}))
  make = (ws / "projects" / "myapp" / "makefile").read_text()
  assert "stack: export PATH := C:/Program Files/cube/bin;$(PATH)" in make
  assert "flash_cpu2.sh" in make and "$(if $(FAST),--fast)" in make

def stack_rule_leaves_cube_elsewhere_to_path(ws, monkeypatch):
  monkeypatch.setattr(utils, "cube_bin", lambda: "")
  monkeypatch.setattr(utils, "cube_found", lambda: True)
  generate(resolve_project(wb55_cfg(), ws_paths(), {}))
  make = (ws / "projects" / "myapp" / "makefile").read_text()
  assert "stack: export PATH" not in make
  assert "flash_cpu2.sh" in make

def stack_rule_without_cube_says_where_to_get_it(ws, monkeypatch):
  monkeypatch.setattr(utils, "cube_bin", lambda: "")
  monkeypatch.setattr(utils, "cube_found", lambda: False)
  generate(resolve_project(wb55_cfg(), ws_paths(), {}))
  make = (ws / "projects" / "myapp" / "makefile").read_text()
  assert "STM32CubeProgrammer" in make and "stm32cubeprog" in make
  assert "flash_cpu2.sh" not in make

def chip_without_radio_stack_gets_no_cube(ws, monkeypatch):
  monkeypatch.setattr(utils, "cube_bin", lambda: "C:/Program Files/cube/bin")
  generate(resolve_uno())
  make = (ws / "projects" / "myapp" / "makefile").read_text()
  assert "has no radio stack" in make
  assert "stack: export PATH" not in make

def no_placeholder_outlives_generation(ws):
  """Make reads a stray `${KEY}` as an empty variable, so a missing color would vanish silently."""
  files = ("projects/myapp/makefile", "makefile", "projects/myapp/flash.ld",
    ".vscode/launch.json", ".vscode/c_cpp_properties.json")
  for cfg in (uno_cfg(), uno_cfg() | {"boot": True}, wb55_cfg()):
    generate(resolve_project(cfg, ws_paths(), {}))
    for name in files:
      assert not re.findall(r"\$\{[A-Z_]+\}", (ws / name).read_text()), name

def the_dispatcher_forwards_every_project_target(ws):
  """Anything a project declares in .PHONY is reachable from the workspace root."""
  generate(resolve_uno())
  phony = lambda text: set(text.split(".PHONY:")[1].split(chr(10))[0].split())
  assert phony((ws / "projects" / "myapp" / "makefile").read_text()) \
    - phony((ws / "makefile").read_text()) == set()
