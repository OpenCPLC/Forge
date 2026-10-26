# tests/test_resolver.py

"""Model resolution: source selection, board filtering, stability."""

import pytest
from xaeian import file_context
from opencplc import resolver
from opencplc.resolver import resolve_project, available_drivers, forge_version
from opencplc.platforms import parse_chip
from opencplc.configure import config_core
from conftest import build_workspace, uno_cfg, ws_paths, resolve_uno, KEY
from conftest import resolve_key_uno, resolve_key_wb55

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

def projects_in_core_stay_out_of_every_build(ws):
  """`.tests/` of a Core holds whole projects, each with its own `main()`."""
  test = ws / "opencplc" / "1.0.0" / ".tests" / "g081"
  test.mkdir(parents=True)
  (test / "main.c").write_text("// .tests/g081/main.c\n")
  (test / "main.h").write_text("")
  pro = resolve_uno()
  assert not any("/.tests/" in f for f in pro.core_c_sources)
  assert not any("/.tests/" in d for d in pro.include_dirs)

def project_in_core_is_named_from_core_root(ws):
  """Build follows its folder, images leave the version and a leading dot out."""
  name = "opencplc/1.0.0/.tests/g081"
  (ws / name).mkdir(parents=True)
  (ws / name / "main.c").write_text("// .tests/g081/main.c\n")
  pro = resolve_project(uno_cfg(name), ws_paths() | {"pro": name}, {"stlink": {name: "ABC123"}})
  assert pro.target == "tests-g081"
  assert pro.build_dir == "build/opencplc/1.0.0/.tests/g081"
  assert pro.project_c_sources == ["opencplc/1.0.0/.tests/g081/main.c"]
  assert pro.stlink == "ABC123"

def tests_stay_out_of_firmware(ws):
  """Programs of `.tests/` run on the computer, never in the image."""
  tests = ws / "projects" / "myapp" / ".tests"
  (tests / "fake").mkdir(parents=True)
  (tests / "frame.c").write_text("// frame\n")
  (tests / "fake" / "link.h").write_text("")
  pro = resolve_uno()
  assert pro.project_c_sources == ["projects/myapp/main.c", "projects/myapp/util/extra.c"]
  assert not any(".tests" in d for d in pro.include_dirs)
  assert pro.tests and pro.test_dir == "projects/myapp/.tests"

def test_build_trades_the_platform_for_the_host(ws):
  """Chip, `FORGE_VERSION`, `OpenCPLC` and `BOOT_*` stay, `STM32` and its family give way."""
  for rel in ("hal/host/sys.c", "lib/sh/test.c", "lib/sh/test.h"):
    (ws / "opencplc" / "1.0.0" / rel).parent.mkdir(parents=True, exist_ok=True)
    (ws / "opencplc" / "1.0.0" / rel).write_text("")
  pro = resolve_uno()
  assert pro.test_defines == ["HOST", "HOST_TEST", "STM32G0C1xx",
    f"FORGE_VERSION={forge_version()}", "OpenCPLC", "BOOT_PAGES=6", "BOOT_CHIP=0x467"]
  assert pro.test_core_sources == ["opencplc/1.0.0/hal/host/sys.c",
    "opencplc/1.0.0/lib/log/log.c", "opencplc/1.0.0/lib/sh/test.c"]
  assert pro.test_include_dirs[0] == "projects/myapp/.tests"
  assert "projects/myapp/util" in pro.test_include_dirs # `extra.c` by name, it has no header
  assert pro.test_include_dirs[-1] == "opencplc/1.0.0" # a module by its path from Core root
  assert not pro.tests

def test_build_finds_driver_headers_by_name(ws):
  """A board header takes `sht4x.h` by name, while a test takes `sht4x.c` by its path."""
  pro = resolve_project(uno_cfg() | {"project_drivers": ["sht4x"]}, ws_paths(), {})
  assert "opencplc/1.0.0/drv/temp" in pro.test_include_dirs
  assert "opencplc/1.0.0/drv/acc" not in pro.test_include_dirs # `ism330` not selected
  assert pro.test_include_dirs[-1] == "opencplc/1.0.0"

def core_itself_builds_its_tests_alone(ws):
  """No sources and no `main.h` of its own: Forge writes that one into the build."""
  tests = ws / "opencplc" / "1.0.0" / ".tests"
  tests.mkdir()
  (tests / "test_log.c").write_text("// log\n")
  name = "opencplc/1.0.0"
  pro = resolve_project(config_core(name, "1.0.0"), ws_paths() | {"pro": f"{name}/.tests"}, {})
  assert pro.project_c_sources == [] and pro.target == "tests" and pro.tests
  assert pro.test_include_dirs[:2] == [f"{name}/.tests", f"build/{name}/.tests"]

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
    "BOOT_PAGES=6", "BOOT_CHIP=0x467",
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
  assert pro.boot_kB == 0 and pro.boot_c_sources == []

def boot_links_the_image_into_the_application_slot(ws):
  """492kB minus the 12kB `plain` bootloader, halved into whole 2kB pages: 240kB per slot."""
  pro = resolve_project(uno_cfg() | {"boot": True}, ws_paths(), {})
  assert pro.boot and pro.flash_origin == 0x08003000
  assert pro.flash_kB == 492 and pro.image_kB == 240 # `PRO_FLASH_kB` stays, the slot is derived
  assert "BOOT_PAGES=6" in pro.defines and "BOOT_SLOT_PAGES=120" in pro.defines
  assert pro.boot_kB == 10 and pro.boot_keys == "" # the last page of the 12kB is the mailbox

def wb55_slots_are_whole_pages_of_4k(ws):
  cfg = uno_cfg() | parse_chip("STM32WB55") | {"boot": True, "flash_kB": 818}
  pro = resolve_project(cfg, ws_paths(), {})
  assert pro.flash_origin == 0x08004000 and pro.image_kB == 400
  assert "BOOT_PAGES=4" in pro.defines and "BOOT_SLOT_PAGES=100" in pro.defines

def boot_needs_room_for_two_slots(ws):
  with pytest.raises(SystemExit):
    resolve_project(uno_cfg() | {"boot": True, "flash_kB": 10}, ws_paths(), {})

def key_image_links_behind_the_32k_bootloader(ws):
  """492kB minus the 32kB `key` bootloader, halved: 230kB a slot."""
  pro = resolve_key_uno()
  assert pro.flash_origin == 0x08008000 and pro.image_kB == 230 and pro.boot_kB == 30
  assert "BOOT_PAGES=16" in pro.defines and "BOOT_SLOT_PAGES=115" in pro.defines
  # the image reads its keys from main.h itself, a `-D` would only repeat them
  assert pro.boot_keys == KEY and not any(d.startswith("BOOT_KEYS") for d in pro.defines)

def wb55_key_image_links_behind_the_32k_bootloader(ws):
  pro = resolve_key_wb55()
  assert pro.flash_origin == 0x08008000 and pro.image_kB == 392
  assert "BOOT_PAGES=8" in pro.defines and "BOOT_SLOT_PAGES=98" in pro.defines

def bootloader_of_core_builds_from_the_chip_alone(ws):
  """`.boot/main.c` on HAL and lib, no board, PLC layer or driver."""
  core = "opencplc/1.0.0"
  pro = resolve_key_uno()
  assert f"{core}/.boot/main.c" in pro.boot_c_sources
  assert f"{core}/hal/stm32g0/uart.c" in pro.boot_c_sources
  assert not any(f"{core}/{part}/" in f for f in pro.boot_c_sources
    for part in ("plc", "brd", "drv"))
  assert pro.boot_c_sources == sorted(pro.boot_c_sources)
  assert pro.boot_asm_sources == [f"{core}/hal/arm/startup.s"]
  # its own place in flash: no slot until a request names one
  assert pro.boot_defines == ["STM32", "STM32G0", "STM32G0C1xx",
    f"FORGE_VERSION={forge_version()}", "BOOT_PAGES=16", "BOOT_CHIP=0x467"]

def bootloader_takes_main_h_of_core_and_boot_h_of_the_project(ws):
  """`.boot/` first, so its `main.h` stands for the one of the application."""
  pro = resolve_key_uno()
  assert pro.boot_include_dirs[:2] == ["opencplc/1.0.0/.boot", "projects/myapp"]

def core_without_the_bootloader_program_exits(ws):
  (ws / "opencplc" / "1.0.0" / ".boot" / "main.c").unlink()
  with pytest.raises(SystemExit):
    resolve_project(uno_cfg() | {"boot": True}, ws_paths(), {})

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
  assert "opencplc/1.0.0/drv/max31865.c" in pro.core_c_sources
  assert not any("shtc3" in f for f in pro.core_c_sources)
  assert pro.board_drivers == ["max31865"]
  assert any(d.endswith("/drv") for d in pro.include_dirs)

def project_drivers_extend_the_board_set(ws):
  cfg = uno_cfg() | {"project_drivers": ["shtc3", "max31865"]}
  pro = resolve_project(cfg, ws_paths(), {})
  assert "opencplc/1.0.0/drv/shtc3.c" in pro.core_c_sources
  assert "opencplc/1.0.0/drv/max31865.c" in pro.core_c_sources

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

def drivers_are_not_validated_when_core_has_no_drv(ws, tmp_path):
  import shutil
  shutil.rmtree(tmp_path / "opencplc" / "1.0.0" / "drv")
  cfg = uno_cfg() | {"project_drivers": ["ghost"]}
  pro = resolve_project(cfg, ws_paths(), {}) # a Core without drv: names are informational
  assert pro.board_drivers == ["max31865"]

def bare_metal_can_use_drivers(ws):
  """Drivers live outside plc/, so a project without a board still compiles them."""
  cfg = uno_cfg() | {"board": None, "board_dir": None, "board_drivers": [],
    "plc": False, "project_drivers": ["shtc3"]}
  pro = resolve_project(cfg, ws_paths(), {})
  assert "opencplc/1.0.0/drv/shtc3.c" in pro.core_c_sources
  assert any(d.endswith("/drv") for d in pro.include_dirs)
  assert not any("/plc/" in f for f in pro.core_c_sources)

def unselected_drivers_stay_out_of_a_bare_metal_build(ws):
  cfg = uno_cfg() | {"board": None, "board_dir": None, "board_drivers": [], "project_drivers": []}
  pro = resolve_project(cfg, ws_paths(), {})
  assert not any("/drv/" in f for f in pro.core_c_sources)
  assert not any(d.endswith("/drv") for d in pro.include_dirs)

def a_driver_is_found_in_any_folder_under_drv(ws):
  pro = resolve_project(uno_cfg() | {"project_drivers": ["ism330"]}, ws_paths(), {})
  assert "opencplc/1.0.0/drv/acc/ism330.c" in pro.core_c_sources
  assert any(d.endswith("/drv/acc") for d in pro.include_dirs)
  assert not any("sht4x" in f for f in pro.core_c_sources)
  assert not any(d.endswith("/drv/temp") for d in pro.include_dirs)

def a_driver_folder_is_included_only_with_one_of_its_drivers(ws):
  pro = resolve_project(uno_cfg() | {"project_drivers": ["sht4x"]}, ws_paths(), {})
  assert "opencplc/1.0.0/drv/temp/sht4x.c" in pro.core_c_sources
  assert any(d.endswith("/drv/temp") for d in pro.include_dirs)
  assert not any(d.endswith("/drv/acc") for d in pro.include_dirs)

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
