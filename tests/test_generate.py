# tests/test_generate.py

"""Generators: project makefile, dispatcher, idempotency, preserved mtime."""

import time
import pytest
from xaeian import file_context
from opencplc.project import generate, prepare_project
from opencplc.resolver import resolve_project
from conftest import build_workspace, uno_cfg, ws_paths, parse_dispatcher, resolve_uno

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
  assert "STLINK := \n" in (ws / "projects" / "myapp" / "makefile").read_text()
  assert "openOCDPreConfigLaunchCommands" not in (ws / ".vscode" / "launch.json").read_text()
  generate(resolve_uno({"stlink": {"projects/myapp": "ABC123"}}))
  assert "STLINK := ABC123" in (ws / "projects" / "myapp" / "makefile").read_text()
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

def the_dispatcher_forwards_every_project_target(ws):
  """Anything a project declares in .PHONY is reachable from the workspace root."""
  generate(resolve_uno())
  phony = lambda text: set(text.split(".PHONY:")[1].split(chr(10))[0].split())
  assert phony((ws / "projects" / "myapp" / "makefile").read_text()) \
    - phony((ws / "makefile").read_text()) == set()
