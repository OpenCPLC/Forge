# tests/test_configure.py

"""Flag policy and reading an existing project through the production path."""

import pytest
from xaeian import file_context
from opencplc.args import Args
from opencplc.configure import config_load, opt_normalize, main_h_number
from opencplc.platforms import parse_chip
from dataclasses import replace
from conftest import build_workspace, load_template, render, refs_cfg, pro_map, host_cfg
from conftest import KEY, add_define, add_boot_define, edit_main_h, load_project

MAIN_H = {
  "${NAME}": "myapp", "${DATE}": "2026-01-01", "${BOARD}": "Uno", "${PLC}": "true",
  "${DRIVERS}": "", "${CHIP}": "STM32G0C1", "${PRO_FRAMEWORK}": "1.0.0", "${FLASH}": 480,
  "${RAM}": 140, "${OPT_LEVEL}": "O1", "${LOG_LEVEL}": "LOG_LEVEL_DBG", "${FREQ}": 48000000,
}
BOOT_LINE = '#include "boot.h"\n' # line of the template, kept by `--boot`

@pytest.fixture()
def ws(tmp_path):
  """Synthetic workspace as file root, myapp behind the bootloader, with an empty boot.h."""
  build_workspace(tmp_path)
  pro = tmp_path / "projects" / "myapp"
  (pro / "main.h").write_text(render(load_template("main.h"), MAIN_H))
  (pro / "boot.h").write_text(render(load_template("boot.h"), MAIN_H))
  with file_context(root_path=str(tmp_path)):
    yield tmp_path

def existing_project_reads_main_h(ws):
  cfg = load_project(ws)
  assert cfg.board.name == "uno"
  assert cfg.chip.name == "STM32G0C1"
  assert cfg.pro_ver == "1.0.0"
  assert cfg.flash_kB == 480
  assert cfg.ram_kB == 140
  assert cfg.opt_level == "O1"
  assert cfg.log_level == "LOG_LEVEL_DBG"
  assert cfg.freq_Hz == 48000000
  assert cfg.boot is True and cfg.boot_keys == ""

def comments_of_main_h_read_as_c_reads_them(ws):
  """A block comment is a space, wherever it stands."""
  edit_main_h(ws, "PRO_FLASH_kB 480", "PRO_FLASH_kB 480 /* kB */")
  edit_main_h(ws, 'PRO_OPT_LEVEL "O1"', 'PRO_OPT_LEVEL "O1" /* fast */')
  cfg = load_project(ws)
  assert (cfg.flash_kB, cfg.opt_level) == (480, "O1")

def a_main_h_without_the_include_runs_from_the_start_of_flash(ws):
  """boot.h left without its `#include` puts nothing behind the bootloader."""
  edit_main_h(ws, BOOT_LINE, "")
  add_boot_define(ws, f'#define BOOT_KEYS "{KEY}"')
  cfg = load_project(ws)
  assert cfg.boot is False and cfg.boot_keys == ""

def main_h_without_pro_framework_exits(ws):
  """No Core version stands in for the one a project names."""
  main_h = ws / "projects" / "myapp" / "main.h"
  lines = main_h.read_text().splitlines()
  main_h.write_text("\n".join(line for line in lines if "PRO_FRAMEWORK" not in line))
  with pytest.raises(SystemExit):
    load_project(ws)

def include_of_a_missing_boot_h_exits(ws):
  (ws / "projects" / "myapp" / "boot.h").unlink()
  with pytest.raises(SystemExit):
    load_project(ws)

def boot_keys_come_from_boot_h_joined_as_c_joins_them(ws):
  add_boot_define(ws, f'#define BOOT_KEYS \\\n  "{KEY}" \\\n  "{KEY.upper()}" // product')
  add_define(ws, "#define PRO_SIGNING_KEY 1")
  cfg = load_project(ws)
  assert cfg.boot_keys == KEY + KEY.upper() and cfg.signing_key == 1

def boot_keys_other_than_whole_keys_of_64_hex_digits_exit(ws):
  boot_h = ws / "projects" / "myapp" / "boot.h"
  empty = boot_h.read_text()
  for keys in ("8a1fe3c0", KEY + "8a", "zz" * 32, ""):
    add_boot_define(ws, f'#define BOOT_KEYS "{keys}"')
    with pytest.raises(SystemExit):
      load_project(ws)
    boot_h.write_text(empty)

def a_boot_h_that_is_not_utf8_exits_rather_than_lose_its_keys(ws):
  """Read as empty, it would build a `plain` bootloader, which checks no signature."""
  add_boot_define(ws, f'#define BOOT_KEYS "{KEY}"')
  boot_h = ws / "projects" / "myapp" / "boot.h"
  boot_h.write_bytes(boot_h.read_bytes() + "// wyjście\n".encode("cp1250"))
  with pytest.raises(SystemExit):
    load_project(ws)

def settings_out_of_their_layer_exit(ws):
  """`PRO_` settings stay in main.h, `BOOT_` ones in boot.h, never the other way round."""
  for line in (f'#define BOOT_KEYS "{KEY}"', "#define BOOT_HOLD { .port = GPIOB, .pin = 5 }"):
    add_define(ws, line)
    with pytest.raises(SystemExit):
      load_project(ws)
    edit_main_h(ws, f"{line}\n", "")
  add_boot_define(ws, "#define PRO_SIGNING_KEY 1")
  with pytest.raises(SystemExit):
    load_project(ws)

def bootloader_on_the_host_exits(ws):
  pro = ws / "projects" / "desk"
  pro.mkdir()
  (pro / "main.h").write_text('#define PRO_CHIP_HOST\n#define PRO_FRAMEWORK "1.0.0"\n'
    f"{BOOT_LINE}")
  (pro / "boot.h").write_text("")
  with pytest.raises(SystemExit):
    load_project(ws, "desk")

def signing_key_takes_a_key_of_boot_keys(ws):
  """A `plain` bootloader checks no signature, a `key` one knows only its own keys."""
  add_define(ws, "#define PRO_SIGNING_KEY 1")
  with pytest.raises(SystemExit):
    load_project(ws)
  add_boot_define(ws, f'#define BOOT_KEYS "{KEY}"')
  with pytest.raises(SystemExit):
    load_project(ws)

def numbers_of_main_h_take_digits_below_65536():
  """A key number fills 16 bits of the image header."""
  assert main_h_number({"PRO_SIGNING_KEY": "65535"}, "PRO_SIGNING_KEY") == 65535
  for value in ("65536", "-1", "0x10", "x"):
    with pytest.raises(SystemExit):
      main_h_number({"PRO_SIGNING_KEY": value}, "PRO_SIGNING_KEY")

def settings_flags_load_as_main_h_would_hold_them(ws):
  """The load builds with them, while main.h waits until the project resolves."""
  main_h = (ws / "projects" / "myapp" / "main.h").read_text()
  cfg = load_project(ws, opt_level="o2", memory=[256, 64, 16], drv="shtc3")
  assert (cfg.opt_level, cfg.flash_kB, cfg.ram_kB) == ("O2", 240, 64)
  assert cfg.project_drivers == ["shtc3"]
  assert cfg.settings == {"PRO_OPT_LEVEL": '"O2"', "PRO_FLASH_kB": "240", "PRO_RAM_kB": "64",
    "PRO_DRIVERS": '"shtc3"'}
  assert (ws / "projects" / "myapp" / "main.h").read_text() == main_h

def driver_flag_adds_to_the_drivers_main_h_names(ws):
  edit_main_h(ws, 'PRO_DRIVERS ""', 'PRO_DRIVERS "max31865"')
  assert load_project(ws, drv="shtc3, MAX31865").project_drivers == ["max31865", "shtc3"]

def memory_flag_takes_two_or_three_values(ws):
  for memory in ([256], [256, 64, 16, 8]):
    with pytest.raises(SystemExit):
      load_project(ws, memory=memory)

def memory_takes_from_1kB_up_to_what_the_chip_has(ws):
  """Uno runs STM32G0C1 of 512kB flash and 144kB RAM, which bounds flags and main.h alike."""
  for memory in ([600, 64], [256, 200], [8, 16, 20], [0, 0]):
    with pytest.raises(SystemExit):
      load_project(ws, memory=memory)
  edit_main_h(ws, "PRO_FLASH_kB 480", "PRO_FLASH_kB 1000")
  with pytest.raises(SystemExit):
    load_project(ws)

def wb55_main_h_may_claim_the_whole_flash_of_the_part(ws):
  """A new project gets 832kB below the radio stack, while main.h may claim all 1024kB."""
  pro = ws / "projects" / "radio"
  pro.mkdir()
  (pro / "main.h").write_text('#define PRO_CHIP_STM32WB55\n#define PRO_FRAMEWORK "1.0.0"\n'
    "#define PRO_FLASH_kB 1024\n#define PRO_RAM_kB 192\n")
  assert load_project(ws, "radio").flash_kB == 1024
  with pytest.raises(SystemExit):
    load_project(ws, "radio", memory=[1028, 192])

def boot_flag_loads_behind_the_bootloader_before_any_file_changes(ws):
  """A boot.h the project lacks reads as the template --boot writes, without a setting."""
  edit_main_h(ws, BOOT_LINE, "")
  (ws / "projects" / "myapp" / "boot.h").unlink()
  cfg = load_project(ws, boot=True)
  assert cfg.boot is True and cfg.boot_keys == ""
  assert not (ws / "projects" / "myapp" / "boot.h").exists()

def boot_flag_on_the_host_exits(ws):
  pro = ws / "projects" / "desk"
  pro.mkdir()
  (pro / "main.h").write_text('#define PRO_CHIP_HOST\n#define PRO_FRAMEWORK "1.0.0"\n')
  with pytest.raises(SystemExit):
    load_project(ws, "desk", boot=True)

def chip_flag_builds_an_existing_project_on_another_chip(ws):
  """-c alone is the bare chip as at creation, memory follows it, and main.h stays as it is."""
  main_h = (ws / "projects" / "myapp" / "main.h").read_text()
  cfg = load_project(ws, chip="STM32G081")
  assert cfg.chip.name == "STM32G081" and cfg.board is None
  assert cfg.plc # `PRO_PLC true` of main.h stands for --plc
  assert (cfg.flash_kB, cfg.ram_kB) == (128, 36) # not the 480kB and 140kB of main.h
  assert cfg.load_flags == "-c STM32G081"
  assert (ws / "projects" / "myapp" / "main.h").read_text() == main_h

def board_flag_puts_a_bare_project_on_a_board(ws):
  pro = ws / "projects" / "bare"
  pro.mkdir()
  (pro / "main.h").write_text('#define PRO_CHIP_STM32G081\n#define PRO_FRAMEWORK "1.0.0"\n')
  cfg = load_project(ws, "bare", board="uno")
  assert (cfg.board.name, cfg.chip.name) == ("uno", "STM32G0C1") and cfg.plc
  assert cfg.load_flags == "-b uno"

def main_h_without_hardware_takes_it_from_each_load(ws):
  """One test of flash for every chip: main.h names no board, chip or memory."""
  pro = ws / "projects" / "any"
  pro.mkdir()
  (pro / "main.h").write_text('#define PRO_FRAMEWORK "1.0.0"\n')
  with pytest.raises(SystemExit):
    load_project(ws, "any")
  g081 = load_project(ws, "any", chip="STM32G081")
  wb55 = load_project(ws, "any", chip="STM32WB55")
  assert (g081.flash_kB, g081.ram_kB, g081.load_flags) == (128, 36, "-c STM32G081")
  assert (wb55.flash_kB, wb55.ram_kB) == (832, 192)
  assert load_project(ws, "any", board="uno").chip.name == "STM32G0C1"

def main_h_without_hardware_takes_settings_flags_but_memory(ws):
  """-c names hardware main.h leaves open, and memory belongs to the hardware of each load."""
  pro = ws / "projects" / "any"
  pro.mkdir()
  (pro / "main.h").write_text('#define PRO_FRAMEWORK "1.0.0"\n')
  cfg = load_project(ws, "any", chip="STM32G081", opt_level="O2", drv="shtc3")
  assert cfg.settings == {"PRO_OPT_LEVEL": '"O2"', "PRO_DRIVERS": '"shtc3"'}
  with pytest.raises(SystemExit):
    load_project(ws, "any", chip="STM32G081", memory=[64, 18])

def flags_writing_main_h_refuse_a_load_that_overrides_it(ws):
  """Checked against the hardware or Core of the load, they would land in main.h of another."""
  for flags in ({"memory": [64, 18]}, {"plc": True}, {"boot": True}, {"opt_level": "O2"}):
    with pytest.raises(SystemExit):
      load_project(ws, chip="STM32G081", **flags)
  build_workspace(ws, core="2.0.0", project="other")
  refs = refs_cfg() | {"available-versions": ["2.0.0", "1.0.0"]}
  with pytest.raises(SystemExit):
    config_load(Args(name="myapp", framework="2.0.0", drv="shtc3"), pro_map(ws), "2.0.0", refs)
  assert load_project(ws, board="uno", opt_level="O2").settings == {"PRO_OPT_LEVEL": '"O2"'}

def forced_chip_needs_no_board_of_main_h(ws):
  """A board main.h names and this Core lacks stays unlooked-for under -c."""
  main_h = ws / "projects" / "myapp" / "main.h"
  main_h.write_text(main_h.read_text().replace("PRO_BOARD_Uno", "PRO_BOARD_Gone"))
  cfg = load_project(ws, chip="STM32G081")
  assert cfg.chip.name == "STM32G081" and cfg.load_flags == "-c STM32G081"

def hardware_of_main_h_forced_again_is_a_plain_load(ws):
  cfg = load_project(ws, board="uno")
  assert cfg.load_flags == "" and cfg.flash_kB == 480
  main_h = ws / "projects" / "myapp" / "main.h"
  main_h.write_text(main_h.read_text().replace("PRO_PLC true", "PRO_PLC false"))
  for flags in ({}, {"board": "uno"}): # `uno` runs on the PLC layer, both refuse alike
    with pytest.raises(SystemExit):
      load_project(ws, **flags)

def board_of_main_h_spelled_otherwise_than_core_exits(ws):
  """C includes the board by `PRO_BOARD_Uno` alone, so `PRO_BOARD_UNO` would build without it."""
  edit_main_h(ws, "PRO_BOARD_Uno", "PRO_BOARD_UNO")
  for flags in ({}, {"board": "uno"}):
    with pytest.raises(SystemExit):
      load_project(ws, **flags)

def unknown_project_exits(ws):
  with pytest.raises(SystemExit):
    config_load(Args(name="ghost"), pro_map(ws), "1.0.0", refs_cfg())

def opt_normalize_clamps_unknown():
  cfg = replace(host_cfg("app"), opt_level="O9")
  opt_normalize(cfg)
  assert cfg.opt_level == "Og"

def opt_normalize_fixes_case():
  cfg = replace(host_cfg("app"), opt_level="og")
  opt_normalize(cfg)
  assert cfg.opt_level == "Og"

def opt_o2_builds_as_written_on_stm32():
  cfg = replace(host_cfg("app"), chip=parse_chip("STM32G081"), opt_level="O2")
  opt_normalize(cfg)
  assert cfg.opt_level == "O2"

def framework_flag_builds_an_existing_project_on_another_core(ws):
  build_workspace(ws, core="2.0.0", project="other")
  refs = refs_cfg() | {"available-versions": ["2.0.0", "1.0.0"]}
  cfg = config_load(Args(name="myapp", framework="2.0.0"), pro_map(ws), "2.0.0", refs)
  assert (cfg.pro_ver, cfg.fw_ver) == ("1.0.0", "2.0.0")
  assert cfg.load_flags == "-f 2.0.0"
  cfg = config_load(Args(name="myapp", framework="2.0.0", chip="STM32G081"), pro_map(ws),
    "2.0.0", refs)
  assert cfg.load_flags == "-f 2.0.0 -c STM32G081"
