# tests/test_resolver.py

"""Model resolution: source selection, board filtering, stability."""

import pytest
from xaeian import file_context
from opencplc.resolver import resolve_project
from conftest import build_workspace, uno_cfg, ws_paths, resolve_uno

@pytest.fixture()
def ws(tmp_path):
  build_workspace(tmp_path)
  with file_context(root_path=str(tmp_path)):
    yield tmp_path

def core_and_project_sources_are_separate(ws):
  pro = resolve_uno()
  assert "opencplc/1.0.0/hal/stm32g0/uart.c" in pro.core_c_sources
  assert "opencplc/1.0.0/lib/log/log.c" in pro.core_c_sources
  assert pro.core_asm_sources == ["opencplc/1.0.0/hal/arm/startup.s"]
  assert pro.project_c_sources == ["projects/myapp/main.c", "projects/myapp/util/extra.c"]
  assert not any(f.startswith("projects/") for f in pro.core_c_sources)

def selected_board_stays_other_boards_drop(ws):
  pro = resolve_uno()
  assert "opencplc/1.0.0/brd/uno/opencplc_uno.c" in pro.core_c_sources
  assert not any("brd/eco" in f for f in pro.core_c_sources)
  assert any(d.endswith("brd/uno") for d in pro.include_dirs)
  assert not any("brd/eco" in d for d in pro.include_dirs)

def bare_metal_excludes_plc_layer(ws):
  cfg = uno_cfg() | {"board": None, "board_dir": None, "board_drivers": [], "plc": False}
  pro = resolve_project(cfg, ws_paths(), {})
  assert not any("/plc/" in f for f in pro.core_c_sources)
  assert not any("/brd/" in f for f in pro.core_c_sources)
  assert "OpenCPLC" not in pro.defines

def sources_are_sorted(ws):
  pro = resolve_uno()
  assert pro.core_c_sources == sorted(pro.core_c_sources)
  assert pro.include_dirs.index("projects/myapp") > 0

def identity_and_flash_fields(ws):
  pro = resolve_uno({"stlink": {"projects/myapp": "ABC123"}})
  assert pro.target == "myapp"
  assert pro.build_dir == "build/projects/myapp"
  assert pro.core_dir == "opencplc/1.0.0"
  assert pro.erase_command == "stm32g0x mass_erase 0"
  assert pro.openocd_target == "stm32g0x"
  assert pro.linker == "stm32g0.ld"
  assert pro.stlink == "ABC123"
  assert pro.defines == ["STM32", "STM32G0", "STM32G0C1xx", "OpenCPLC"]
  assert pro.mcu_flags == "-mcpu=cortex-m0plus -mthumb -mfloat-abi=soft"

def resolution_is_stable(ws):
  assert resolve_uno() == resolve_uno()

def project_dirs_cover_root_and_source_folders(ws):
  pro = resolve_uno()
  assert pro.project_dirs == ["projects/myapp", "projects/myapp/util"]

def board_drivers_select_core_driver_sources(ws):
  pro = resolve_uno()
  assert "opencplc/1.0.0/dvr/max31865.c" in pro.core_c_sources
  assert not any("shtc3" in f for f in pro.core_c_sources)
  assert pro.board_drivers == ["max31865"]
  assert any(d.endswith("/dvr") for d in pro.include_dirs)

def project_drivers_extend_the_board_set(ws):
  cfg = uno_cfg() | {"project_drivers": ["shtc3", "max31865"]}
  pro = resolve_project(cfg, ws_paths(), {})
  assert "opencplc/1.0.0/dvr/shtc3.c" in pro.core_c_sources
  assert "opencplc/1.0.0/dvr/max31865.c" in pro.core_c_sources

def unknown_driver_exits(ws):
  cfg = uno_cfg() | {"project_drivers": ["ghost"]}
  with pytest.raises(SystemExit):
    resolve_project(cfg, ws_paths(), {})

def plc_layer_without_any_board(ws):
  """-P on your own hardware: the PLC layer compiles, no board directory does."""
  cfg = uno_cfg() | {"board": None, "board_dir": None, "board_drivers": []}
  pro = resolve_project(cfg, ws_paths(), {})
  assert "opencplc/1.0.0/plc/plc.c" in pro.core_c_sources
  assert not any("/brd/" in f for f in pro.core_c_sources)
  assert "OpenCPLC" in pro.defines

def drivers_are_not_validated_when_core_has_no_dvr(ws, tmp_path):
  import shutil
  shutil.rmtree(tmp_path / "opencplc" / "1.0.0" / "dvr")
  cfg = uno_cfg() | {"project_drivers": ["ghost"]}
  pro = resolve_project(cfg, ws_paths(), {}) # a Core before plc/dvr: names are informational
  assert pro.board_drivers == ["max31865"]

def bare_metal_can_use_drivers(ws):
  """Drivers live outside plc/, so a project without a board still compiles them."""
  cfg = uno_cfg() | {"board": None, "board_dir": None, "board_drivers": [],
    "plc": False, "project_drivers": ["shtc3"]}
  pro = resolve_project(cfg, ws_paths(), {})
  assert "opencplc/1.0.0/dvr/shtc3.c" in pro.core_c_sources
  assert any(d.endswith("/dvr") for d in pro.include_dirs)
  assert not any("/plc/" in f for f in pro.core_c_sources)

def unselected_drivers_stay_out_of_a_bare_metal_build(ws):
  cfg = uno_cfg() | {"board": None, "board_dir": None, "board_drivers": [], "project_drivers": []}
  pro = resolve_project(cfg, ws_paths(), {})
  assert not any("/dvr/" in f for f in pro.core_c_sources)
  assert not any(d.endswith("/dvr") for d in pro.include_dirs)

def a_board_prefix_is_not_the_board(ws, tmp_path):
  """Selecting uno never drags in uno_mini."""
  from conftest import make_board
  mini = make_board(tmp_path / "opencplc" / "1.0.0", "uno_mini")
  (mini / "opencplc_uno_mini.c").write_text("// mini\n")
  pro = resolve_uno()
  assert "opencplc/1.0.0/brd/uno/opencplc_uno.c" in pro.core_c_sources
  assert not any("uno_mini" in f for f in pro.core_c_sources)
  assert not any("uno_mini" in d for d in pro.include_dirs)
