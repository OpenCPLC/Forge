# tests/test_resolver.py

"""Model resolution: source selection, board filtering, stability."""

import pytest
from xaeian import file_context
from opencplc import resolver
from opencplc.resolver import resolve_project, available_drivers, forge_version
from opencplc.platforms import parse_chip
from conftest import build_workspace, uno_cfg, ws_paths, resolve_uno, KEY, ship_key_bootloader
from conftest import resolve_key_uno

@pytest.fixture()
def ws(tmp_path):
  """Synthetic workspace as file root."""
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
  assert pro.defines == [
    "STM32", "STM32G0", "STM32G0C1xx", f"FORGE_VERSION={forge_version()}", "OpenCPLC",
    "BOOT_PAGES=4", "BOOT_CHIP=0x467",
  ]
  assert pro.mcu_flags == "-mcpu=cortex-m0plus -mthumb -mfloat-abi=soft"

def forge_version_is_one_number_for_core_to_compare(monkeypatch):
  """`#if` in Core compares integers alone."""
  for version, number in (("0.4.8", 408), ("1.2.10", 10210)):
    monkeypatch.setattr(resolver, "__version__", version)
    assert forge_version() == number

def without_boot_the_image_takes_the_whole_region(ws):
  pro = resolve_uno()
  assert not pro.boot
  assert pro.flash_origin == 0x08000000 and pro.flash_kB == 492 and pro.image_kB == 492
  assert not any(d.startswith("BOOT_SLOT_PAGES") for d in pro.defines)

def boot_links_the_image_into_the_application_slot(ws):
  """492kB minus the 8kB bootloader, halved into whole 2kB pages: 242kB per slot."""
  pro = resolve_project(uno_cfg() | {"boot": True}, ws_paths(), {})
  assert pro.boot and pro.flash_origin == 0x08002000
  assert pro.flash_kB == 492 and pro.image_kB == 242 # `PRO_FLASH_kB` stays, the slot is derived
  assert "BOOT_PAGES=4" in pro.defines and "BOOT_SLOT_PAGES=121" in pro.defines

def wb55_slots_are_whole_pages_of_4k(ws):
  cfg = uno_cfg() | parse_chip("STM32WB55") | {"boot": True, "flash_kB": 818}
  pro = resolve_project(cfg, ws_paths(), {})
  assert pro.flash_origin == 0x08004000 and pro.image_kB == 400
  assert "BOOT_PAGES=4" in pro.defines and "BOOT_SLOT_PAGES=100" in pro.defines

def boot_needs_room_for_two_slots(ws):
  with pytest.raises(SystemExit):
    resolve_project(uno_cfg() | {"boot": True, "flash_kB": 10}, ws_paths(), {})

def key_image_links_behind_the_32k_bootloader(ws):
  """492kB minus the 32kB `key` bootloader, halved: 230kB per slot, its key below the mailbox."""
  ship_key_bootloader(ws)
  pro = resolve_key_uno()
  assert pro.flash_origin == 0x08008000 and pro.image_kB == 230
  assert "BOOT_PAGES=16" in pro.defines and "BOOT_SLOT_PAGES=115" in pro.defines
  assert pro.boot_key == KEY and pro.boot_key_at == 0x080077E0

def wb55_key_sits_below_its_4k_mailbox_page(ws):
  ship_key_bootloader(ws, "stm32wb")
  cfg = uno_cfg() | parse_chip("STM32WB55") | {"boot": True, "flash_kB": 818, "boot_key": KEY}
  pro = resolve_project(cfg, ws_paths(), {})
  assert pro.flash_origin == 0x08008000 and pro.image_kB == 392
  assert pro.boot_key_at == 0x08006FE0

def key_bootloader_build_takes_the_key_region(ws):
  """`BOOT_KEY ON` is the bootloader itself: more pages of its own, nothing to pack or sign."""
  pro = resolve_project(uno_cfg() | {"flash_kB": 30, "boot_key_build": True}, ws_paths(), {})
  assert pro.flash_origin == 0x08000000 and pro.image_kB == 30
  assert "BOOT_PAGES=16" in pro.defines
  assert not any(d.startswith("BOOT_SLOT_PAGES") for d in pro.defines)
  assert pro.boot_key == "" and pro.boot_key_at == 0

def boot_key_without_boot_exits(ws):
  with pytest.raises(SystemExit):
    resolve_project(uno_cfg() | {"boot_key": KEY}, ws_paths(), {})

def key_bootloader_switch_under_a_bootloader_exits(ws):
  with pytest.raises(SystemExit):
    resolve_project(uno_cfg() | {"boot": True, "boot_key_build": True}, ws_paths(), {})

def bootloader_project_with_its_switch_off_under_a_bootloader_exits(ws):
  """`BOOT_KEY OFF` marks the bootloader project as much as `ON`."""
  with pytest.raises(SystemExit):
    resolve_project(uno_cfg() | {"boot": True, "bootloader": True}, ws_paths(), {})

def core_without_the_key_bootloader_refuses_boot_key(ws):
  """A Core with the `plain` bootloader alone has none to go with a `key` image."""
  with pytest.raises(SystemExit):
    resolve_key_uno()

def host_carries_no_flash_layout(ws):
  from conftest import host_model
  pro = host_model()
  assert not pro.boot and pro.flash_origin == 0
  assert not any(d.startswith("BOOT_") for d in pro.defines)

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
  """`-P` on your own hardware: the PLC layer compiles, no board directory does."""
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

def a_driver_is_found_in_any_folder_under_dvr(ws):
  pro = resolve_project(uno_cfg() | {"project_drivers": ["ism330"]}, ws_paths(), {})
  assert "opencplc/1.0.0/dvr/acc/ism330.c" in pro.core_c_sources
  assert any(d.endswith("/dvr/acc") for d in pro.include_dirs)
  assert not any("sht4x" in f for f in pro.core_c_sources)
  assert not any(d.endswith("/dvr/temp") for d in pro.include_dirs)

def a_driver_folder_is_included_only_with_one_of_its_drivers(ws):
  pro = resolve_project(uno_cfg() | {"project_drivers": ["sht4x"]}, ws_paths(), {})
  assert "opencplc/1.0.0/dvr/temp/sht4x.c" in pro.core_c_sources
  assert any(d.endswith("/dvr/temp") for d in pro.include_dirs)
  assert not any(d.endswith("/dvr/acc") for d in pro.include_dirs)

def available_drivers_reach_into_folders(ws):
  assert available_drivers("opencplc/1.0.0") == ["ism330", "max31865", "sht4x", "shtc3"]

def a_board_prefix_is_not_the_board(ws, tmp_path):
  """Selecting uno never drags in uno_mini."""
  from conftest import make_board
  mini = make_board(tmp_path / "opencplc" / "1.0.0", "uno_mini")
  (mini / "opencplc_uno_mini.c").write_text("// mini\n")
  pro = resolve_uno()
  assert "opencplc/1.0.0/brd/uno/opencplc_uno.c" in pro.core_c_sources
  assert not any("uno_mini" in f for f in pro.core_c_sources)
  assert not any("uno_mini" in d for d in pro.include_dirs)
