# tests/test_boards.py

"""Board discovery from brd/<name>/: manifests valid and broken, new directories."""

import pytest
from xaeian import file_context
from opencplc.boards import parse_board, load_boards, board_pick
from conftest import INI, make_board

@pytest.fixture()
def core(tmp_path):
  (tmp_path / "opencplc.json").write_text("{}")
  with file_context(root_path=str(tmp_path)):
    yield tmp_path / "opencplc" / "1.0.0"

def valid_manifest_parses(core):
  d = make_board(core, "uno", INI + "drivers = max31865, shtc3\n")
  board = parse_board(str(d / f"opencplc_{d.name}.ini"), "uno", "opencplc/1.0.0/brd/uno")
  assert board.chip == "STM32G0C1"
  assert (board.flash_kB, board.ram_kB, board.freq_Hz) == (492, 144, 59904000)
  assert board.drivers == ["max31865", "shtc3"]

def drivers_are_optional(core):
  d = make_board(core, "uno")
  assert parse_board(str(d / f"opencplc_{d.name}.ini"), "uno", "x").drivers == []

def missing_field_is_rejected(core):
  d = make_board(core, "uno", "chip = STM32G0C1\nplc = true\nflash_kB = 492\n")
  with pytest.raises(ValueError, match="ram_kB"):
    parse_board(str(d / f"opencplc_{d.name}.ini"), "uno", "x")

def unknown_or_host_chip_is_rejected(core):
  d = make_board(core, "uno", INI.replace("STM32G0C1", "STM32F103"))
  with pytest.raises(ValueError, match="chip"):
    parse_board(str(d / f"opencplc_{d.name}.ini"), "uno", "x")
  d = make_board(core, "pc", INI.replace("STM32G0C1", "HOST"))
  with pytest.raises(ValueError, match="chip"):
    parse_board(str(d / f"opencplc_{d.name}.ini"), "pc", "x")

def missing_header_is_rejected(core):
  d = make_board(core, "uno", header=False)
  with pytest.raises(ValueError, match="opencplc_uno.h"):
    parse_board(str(d / f"opencplc_{d.name}.ini"), "uno", "x")

def bad_name_is_rejected(core):
  d = make_board(core, "Uno")
  with pytest.raises(ValueError, match="name"):
    parse_board(str(d / f"opencplc_{d.name}.ini"), "Uno", "x")

def only_directories_with_a_manifest_are_boards(core):
  make_board(core, "uno")
  (core / "brd" / "eco").mkdir(parents=True)
  (core / "brd" / "eco" / "opencplc_eco.h").write_text("")
  assert list(load_boards("opencplc/1.0.0")) == ["uno"]

def a_new_directory_is_a_new_board(core):
  make_board(core, "uno")
  make_board(core, "nano", INI.replace("STM32G0C1", "STM32G081"))
  boards = load_boards("opencplc/1.0.0")
  assert sorted(boards) == ["nano", "uno"]
  assert boards["nano"].chip == "STM32G081"
  assert boards["nano"].dir == "opencplc/1.0.0/brd/nano"

def broken_manifest_exits(core):
  make_board(core, "uno", "chip = STM32G0C1\n")
  with pytest.raises(SystemExit):
    load_boards("opencplc/1.0.0")

def pick_is_case_insensitive_and_exits_on_unknown(core):
  make_board(core, "uno")
  boards = load_boards("opencplc/1.0.0")
  assert board_pick(boards, "Uno").name == "uno"
  with pytest.raises(SystemExit):
    board_pick(boards, "dio")

def core_without_boards_dir_has_no_boards(core):
  assert load_boards("opencplc/1.0.0") == {}

def any_ini_serves_as_the_manifest(core):
  make_board(core, "uno")
  d = core / "brd" / "nano"
  d.mkdir(parents=True)
  (d / "zzz.ini").write_text(INI.replace("STM32G0C1", "STM32G081"))
  (d / "opencplc_nano.h").write_text("")
  boards = load_boards("opencplc/1.0.0")
  assert sorted(boards) == ["nano", "uno"]
  assert boards["nano"].chip == "STM32G081"

def manifest_decides_the_plc_layer(core):
  make_board(core, "uno")
  make_board(core, "bare", INI.replace("plc = true", "plc = false"))
  boards = load_boards("opencplc/1.0.0")
  assert boards["uno"].plc is True
  assert boards["bare"].plc is False

def plc_field_is_required_and_boolean(core):
  d = make_board(core, "uno", INI.replace("plc = true\n", ""))
  with pytest.raises(ValueError, match="plc"):
    parse_board(str(d / f"opencplc_{d.name}.ini"), "uno", "x")
  d = make_board(core, "uno", INI.replace("plc = true", "plc = yes"))
  with pytest.raises(ValueError, match="plc"):
    parse_board(str(d / f"opencplc_{d.name}.ini"), "uno", "x")
