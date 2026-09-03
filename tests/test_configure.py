# tests/test_configure.py

"""Flag policy and reading an existing project through the production path."""

import pytest
from xaeian import file_context
from opencplc.args import Args
from opencplc.configure import config_load, flags_reject, opt_normalize
from conftest import build_workspace, load_template, render, ws_paths, refs_cfg, pro_map

MAIN_H = {
  "${NAME}": "myapp", "${DATE}": "2026-01-01", "${BOARD}": "Uno", "${PLC}": "true",
  "${DRIVERS}": "", "${CHIP}": "STM32G0C1", "${PRO_VERSION}": "1.0.0", "${FLASH}": 480,
  "${RAM}": 140, "${OPT_LEVEL}": "O1", "${LOG_LEVEL}": "LOG_LEVEL_DBG",
  "${FREQ}": 48000000,
}

@pytest.fixture()
def ws(tmp_path):
  build_workspace(tmp_path)
  (tmp_path / "projects" / "myapp" / "main.h").write_text(render(load_template("main.h"), MAIN_H))
  with file_context(root_path=str(tmp_path)):
    yield tmp_path

def existing_project_reads_main_h(ws):
  cfg = config_load(Args(name="myapp"), pro_map(ws), ws_paths(), "1.0.0", refs_cfg())
  assert cfg["board"] == "uno"
  assert cfg["chip"] == "STM32G0C1"
  assert cfg["pro_ver"] == "1.0.0"
  assert cfg["flash_kB"] == 480
  assert cfg["ram_kB"] == 140
  assert cfg["opt_level"] == "O1"
  assert cfg["log_level"] == "LOG_LEVEL_DBG"
  assert cfg["freq_Hz"] == 48000000

def config_flags_are_rejected_for_existing_project(ws):
  for kwargs in ({"board": "uno"}, {"chip": "STM32G081"}, {"memory": [128, 36]},
      {"opt_level": "O2"}):
    with pytest.raises(SystemExit):
      config_load(Args(name="myapp", **kwargs), pro_map(ws), ws_paths(),
        "1.0.0", refs_cfg())

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
  from conftest import build_workspace
  build_workspace(ws, core="2.0.0", project="other")
  paths = ws_paths(core="2.0.0")
  cfg = config_load(Args(name="myapp", framework="2.0.0"), pro_map(ws), paths, "2.0.0",
    refs_cfg() | {"available-versions": ["2.0.0", "1.0.0"]})
  assert cfg["pro_ver"] == "1.0.0"
  assert cfg["fw_ver"] == "2.0.0"
  assert paths["fw"].endswith("opencplc/2.0.0")
