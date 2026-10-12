# tests/test_configure.py

"""Flag policy and reading an existing project through the production path."""

import pytest
from xaeian import file_context
from opencplc.args import Args
from opencplc.configure import config_load, flags_reject, opt_normalize
from conftest import build_workspace, load_template, render, ws_paths, refs_cfg, pro_map
from conftest import KEY, add_define, load_project

MAIN_H = {
  "${NAME}": "myapp", "${DATE}": "2026-01-01", "${BOARD}": "Uno", "${PLC}": "true",
  "${DRIVERS}": "", "${CHIP}": "STM32G0C1", "${PRO_FRAMEWORK}": "1.0.0", "${FLASH}": 480,
  "${RAM}": 140, "${BOOT}": "true", "${OPT_LEVEL}": "O1", "${LOG_LEVEL}": "LOG_LEVEL_DBG",
  "${FREQ}": 48000000,
}

@pytest.fixture()
def ws(tmp_path):
  """Synthetic workspace as file root, myapp with a main.h rendered from `MAIN_H`."""
  build_workspace(tmp_path)
  (tmp_path / "projects" / "myapp" / "main.h").write_text(render(load_template("main.h"), MAIN_H))
  with file_context(root_path=str(tmp_path)):
    yield tmp_path

def existing_project_reads_main_h(ws):
  cfg = load_project(ws)
  assert cfg["board"] == "uno"
  assert cfg["chip"] == "STM32G0C1"
  assert cfg["pro_ver"] == "1.0.0"
  assert cfg["flash_kB"] == 480
  assert cfg["ram_kB"] == 140
  assert cfg["opt_level"] == "O1"
  assert cfg["log_level"] == "LOG_LEVEL_DBG"
  assert cfg["freq_Hz"] == 48000000
  assert cfg["boot"] is True

def a_main_h_without_pro_boot_runs_from_the_start_of_flash(ws):
  main_h = (ws / "projects" / "myapp" / "main.h")
  main_h.write_text("\n".join(l for l in main_h.read_text().splitlines() if "PRO_BOOT" not in l))
  cfg = load_project(ws)
  assert cfg["boot"] is False

def main_h_without_pro_framework_exits(ws):
  """No Core version stands in for the one a project names."""
  main_h = ws / "projects" / "myapp" / "main.h"
  lines = main_h.read_text().splitlines()
  main_h.write_text("\n".join(line for line in lines if "PRO_FRAMEWORK" not in line))
  with pytest.raises(SystemExit):
    load_project(ws)

def pro_boot_key_puts_the_image_under_the_key_bootloader(ws):
  add_define(ws, f'#define PRO_BOOT_KEY "{KEY.upper()}"')
  cfg = load_project(ws)
  assert cfg["boot_key"] == KEY and cfg["boot_key_build"] is False

def pro_boot_key_short_of_64_hex_digits_exits(ws):
  add_define(ws, '#define PRO_BOOT_KEY "8a1fe3c0"')
  with pytest.raises(SystemExit):
    load_project(ws)

def boot_key_on_marks_the_key_bootloader_build(ws):
  add_define(ws, "#define BOOT_KEY ON")
  cfg = load_project(ws)
  assert cfg["boot_key_build"] is True and cfg["boot_key"] == ""

def config_flags_are_rejected_for_existing_project(ws):
  for kwargs in ({"memory": [128, 36]}, {"opt_level": "O2"}, {"plc": True}, {"boot": True}):
    with pytest.raises(SystemExit):
      load_project(ws, **kwargs)

def chip_flag_builds_an_existing_project_on_another_chip(ws):
  """-c alone is the bare chip as at creation, memory follows it, and main.h stays as it is."""
  main_h = (ws / "projects" / "myapp" / "main.h").read_text()
  cfg = load_project(ws, chip="STM32G081")
  assert cfg["chip"] == "STM32G081" and cfg["board"] is None
  assert cfg["plc"] # `PRO_PLC true` of main.h stands for -P
  assert (cfg["flash_kB"], cfg["ram_kB"]) == (128, 36) # not the 480kB and 140kB of main.h
  assert cfg["load_flags"] == "-c STM32G081"
  assert (ws / "projects" / "myapp" / "main.h").read_text() == main_h

def board_flag_puts_a_bare_project_on_a_board(ws):
  pro = ws / "projects" / "bare"
  pro.mkdir()
  (pro / "main.h").write_text('#define PRO_CHIP_STM32G081\n#define PRO_FRAMEWORK "1.0.0"\n')
  cfg = load_project(ws, "bare", board="uno")
  assert (cfg["board"], cfg["chip"]) == ("uno", "STM32G0C1") and cfg["plc"]
  assert cfg["load_flags"] == "-b uno"

def main_h_without_hardware_takes_it_from_each_load(ws):
  """One test of flash for every chip: main.h names no board, chip or memory."""
  pro = ws / "projects" / "any"
  pro.mkdir()
  (pro / "main.h").write_text('#define PRO_FRAMEWORK "1.0.0"\n')
  with pytest.raises(SystemExit):
    load_project(ws, "any")
  g081 = load_project(ws, "any", chip="STM32G081")
  wb55 = load_project(ws, "any", chip="STM32WB55")
  assert (g081["flash_kB"], g081["ram_kB"], g081["load_flags"]) == (128, 36, "-c STM32G081")
  assert (wb55["flash_kB"], wb55["ram_kB"]) == (832, 192)
  assert load_project(ws, "any", board="uno")["chip"] == "STM32G0C1"

def forced_chip_needs_no_board_of_main_h(ws):
  """A board main.h names and this Core lacks stays unlooked-for under -c."""
  main_h = ws / "projects" / "myapp" / "main.h"
  main_h.write_text(main_h.read_text().replace("PRO_BOARD_Uno", "PRO_BOARD_Gone"))
  cfg = load_project(ws, chip="STM32G081")
  assert cfg["chip"] == "STM32G081" and cfg["load_flags"] == "-c STM32G081"

def hardware_of_main_h_forced_again_is_a_plain_load(ws):
  cfg = load_project(ws, board="uno")
  assert cfg["load_flags"] == "" and cfg["flash_kB"] == 480
  main_h = ws / "projects" / "myapp" / "main.h"
  main_h.write_text(main_h.read_text().replace("PRO_PLC true", "PRO_PLC false"))
  for flags in ({}, {"board": "uno"}): # Uno runs on the PLC layer, both refuse alike
    with pytest.raises(SystemExit):
      load_project(ws, **flags)

def no_flags_pass_the_policy():
  flags_reject(Args(name="x"))

def unknown_project_exits(ws):
  with pytest.raises(SystemExit):
    config_load(Args(name="ghost"), pro_map(ws), ws_paths(), "1.0.0", refs_cfg())

def opt_normalize_clamps_unknown():
  cfg = {"opt_level": "O9", "platform": "Host"}
  opt_normalize(cfg)
  assert cfg["opt_level"] == "Og"

def opt_normalize_fixes_case():
  cfg = {"opt_level": "og", "platform": "Host"}
  opt_normalize(cfg)
  assert cfg["opt_level"] == "Og"

def opt_o2_builds_as_written_on_stm32():
  cfg = {"opt_level": "O2", "platform": "STM32"}
  opt_normalize(cfg)
  assert cfg["opt_level"] == "O2"

def framework_flag_builds_an_existing_project_on_another_core(ws):
  build_workspace(ws, core="2.0.0", project="other")
  paths = ws_paths(core="2.0.0")
  cfg = config_load(Args(name="myapp", framework="2.0.0"), pro_map(ws), paths, "2.0.0",
    refs_cfg() | {"available-versions": ["2.0.0", "1.0.0"]})
  assert cfg["pro_ver"] == "1.0.0"
  assert cfg["fw_ver"] == "2.0.0"
  assert paths["fw"].endswith("opencplc/2.0.0")
  assert cfg["load_flags"] == "-f 2.0.0"
  cfg = config_load(Args(name="myapp", framework="2.0.0", chip="STM32G081"), pro_map(ws),
    ws_paths(core="2.0.0"), "2.0.0", refs_cfg() | {"available-versions": ["2.0.0", "1.0.0"]})
  assert cfg["load_flags"] == "-f 2.0.0 -c STM32G081"
