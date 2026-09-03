# tests/test_cli.py

"""End-to-end CLI flow in-process: network and toolchain installation stubbed out."""

import pytest
from xaeian import file_context
import opencplc.__main__ as forge
import opencplc.workspace as ws_mod
from opencplc import actions
from opencplc.args import Args
from conftest import build_workspace, write_forge_config, run_cli, refs_cfg
from conftest import frozen_forge, _raise_disk_full

@pytest.fixture()
def ws(tmp_path, monkeypatch):
  build_workspace(tmp_path)
  write_forge_config(tmp_path)
  monkeypatch.chdir(tmp_path)
  monkeypatch.setattr(ws_mod, "REFS_FRESH", False)
  monkeypatch.setattr(ws_mod.utils, "install_git", lambda yes: None)
  monkeypatch.setattr(ws_mod.utils, "git_get_refs", lambda url, opt="--ref": ["1.0.0"])
  monkeypatch.setattr(forge, "ensure_toolchains", lambda is_embedded, yes: None)
  with file_context(root_path=str(tmp_path)):
    yield tmp_path

def new_project_generates_everything(ws, monkeypatch):
  assert run_cli(monkeypatch, "-n", "app", "-b", "Uno", "-y") == 0
  pro = ws / "projects" / "app"
  assert (pro / "main.c").exists() and (pro / "main.h").exists()
  assert (pro / "makefile").exists() and (pro / "flash.ld").exists()
  assert "ACTIVE := projects/app" in (ws / "makefile").read_text()
  assert 'PRO_BOARD_Uno' in (pro / "main.h").read_text()

def load_existing_project_by_name(ws, monkeypatch):
  assert run_cli(monkeypatch, "-n", "app", "-b", "Uno", "-y") == 0
  assert run_cli(monkeypatch, "app") == 0
  assert "ACTIVE := projects/app" in (ws / "makefile").read_text()

def project_without_pro_chip_is_rejected(ws, monkeypatch):
  broken = ws / "projects" / "broken"
  broken.mkdir()
  (broken / "main.h").write_text("// no PRO_CHIP here")
  assert run_cli(monkeypatch, "broken") == 1

def switching_projects_moves_the_dispatcher(ws, monkeypatch):
  run_cli(monkeypatch, "-n", "a", "-b", "Uno", "-y")
  run_cli(monkeypatch, "-n", "b", "-c", "STM32G081", "-y")
  assert "ACTIVE := projects/b" in (ws / "makefile").read_text()
  run_cli(monkeypatch, "a")
  assert "ACTIVE := projects/a" in (ws / "makefile").read_text()
  assert (ws / "projects" / "b" / "makefile").exists()  # other project keeps its files

def reload_from_inside_project_dir_targets_that_project(ws, monkeypatch):
  run_cli(monkeypatch, "-n", "deep/app", "-b", "Uno", "-y")
  run_cli(monkeypatch, "-n", "other", "-b", "Uno", "-y")
  (ws / "projects" / "deep" / "app" / "makefile").unlink()
  monkeypatch.chdir(ws / "projects" / "deep" / "app")
  assert run_cli(monkeypatch, "-r") == 0
  assert (ws / "projects" / "deep" / "app" / "makefile").exists()     # this project regenerated
  assert "ACTIVE := projects/other" in (ws / "makefile").read_text()  # workspace untouched

def info_prints_resolved_config(ws, monkeypatch, capsys):
  run_cli(monkeypatch, "-n", "app", "-b", "Uno", "-y")
  assert run_cli(monkeypatch, "app", "-i") == 0
  out = capsys.readouterr().out
  assert "STM32G0C1" in out and "Uno" in out and "492" in out

def config_flags_on_existing_project_fail(ws, monkeypatch):
  run_cli(monkeypatch, "-n", "app", "-b", "Uno", "-y")
  assert run_cli(monkeypatch, "app", "-o", "O2") == 1
  assert run_cli(monkeypatch, "app", "-b", "Eco") == 1

def listing_and_numeric_pick(ws, monkeypatch, capsys):
  run_cli(monkeypatch, "-n", "alpha", "-b", "Uno", "-y")
  run_cli(monkeypatch, "-n", "beta", "-b", "Uno", "-y")
  assert run_cli(monkeypatch, "-l") == 0
  out = capsys.readouterr().out
  assert "alpha" in out and "beta" in out

def delete_active_project_empties_dispatcher(ws, monkeypatch):
  run_cli(monkeypatch, "-n", "gone", "-b", "Uno", "-y")
  assert run_cli(monkeypatch, "-d", "gone") == 0
  assert not (ws / "projects" / "gone").exists()
  assert "ACTIVE :=" in (ws / "makefile").read_text()
  assert "projects/gone" not in (ws / "makefile").read_text()

def version_and_hash_need_no_workspace(tmp_path, monkeypatch, capsys):
  monkeypatch.chdir(tmp_path)
  with file_context(root_path=str(tmp_path)):
    assert run_cli(monkeypatch, "-v") == 0
    assert run_cli(monkeypatch, "-hl", "start", "stop") == 0
  assert not (tmp_path / "opencplc.json").exists()
  assert "Forge" in capsys.readouterr().out

def scoped_reload_keeps_the_active_project(ws, monkeypatch):
  run_cli(monkeypatch, "-n", "a", "-b", "Uno", "-y")
  run_cli(monkeypatch, "-n", "b", "-b", "Uno", "-y")
  launch = (ws / ".vscode" / "launch.json").read_text()
  monkeypatch.chdir(ws / "projects" / "a")
  assert run_cli(monkeypatch, "-r") == 0
  assert "ACTIVE := projects/b" in (ws / "makefile").read_text()
  assert (ws / ".vscode" / "launch.json").read_text() == launch

def stlink_binding_flows_into_makefile_and_config(ws, monkeypatch):
  run_cli(monkeypatch, "-n", "app", "-b", "Uno", "-y")
  assert run_cli(monkeypatch, "app", "-s", "066AFF49") == 0
  assert "STLINK := 066AFF49" in (ws / "projects" / "app" / "makefile").read_text()
  assert '"projects/app": "066AFF49"' in (ws / "opencplc.json").read_text()
  assert "066AFF49" in (ws / ".vscode" / "launch.json").read_text()
  assert run_cli(monkeypatch, "app", "-s") == 0
  assert "STLINK := \n" in (ws / "projects" / "app" / "makefile").read_text()
  assert "066AFF49" not in (ws / "opencplc.json").read_text()

def deleting_a_project_drops_its_stlink(ws, monkeypatch):
  run_cli(monkeypatch, "-n", "app", "-b", "Uno", "-y")
  run_cli(monkeypatch, "app", "-s", "SER1")
  assert run_cli(monkeypatch, "-d", "app") == 0
  assert "SER1" not in (ws / "opencplc.json").read_text()

def pinned_project_loads_without_the_workspace_default_core(ws, monkeypatch):
  # main.h pins 1.0.0 (present); the workspace default 2.0.0 is not on disk and must not be needed
  run_cli(monkeypatch, "-n", "app", "-b", "Uno", "-y")
  cfg = (ws / "opencplc.json").read_text().replace('"version": "1.0.0"', '"version": "2.0.0"')
  (ws / "opencplc.json").write_text(cfg.replace('["1.0.0"]', '["2.0.0", "1.0.0"]'))
  monkeypatch.setattr(ws_mod.utils, "git_get_refs", lambda url, opt="--ref": ["2.0.0", "1.0.0"])
  assert run_cli(monkeypatch, "app") == 0
  assert not (ws / "opencplc" / "2.0.0").exists()

def new_project_without_board_or_chip_fails_with_a_list(ws, monkeypatch, capsys):
  assert run_cli(monkeypatch, "-n", "app") == 1
  assert "Uno" in capsys.readouterr().out

def reload_by_name_keeps_the_active_project(ws, monkeypatch):
  run_cli(monkeypatch, "-n", "a", "-b", "Uno", "-y")
  run_cli(monkeypatch, "-n", "b", "-b", "Uno", "-y")
  assert run_cli(monkeypatch, "-r", "a") == 0
  assert "ACTIVE := projects/b" in (ws / "makefile").read_text()

def listing_creates_no_workspace_marker(tmp_path, monkeypatch):
  monkeypatch.chdir(tmp_path)
  with file_context(root_path=str(tmp_path)):
    run_cli(monkeypatch, "-l")
  assert not (tmp_path / "opencplc.json").exists()

def size_report_shows_kilobytes_and_percent(monkeypatch, capsys):
  import opencplc.actions as actions
  monkeypatch.setattr(actions, "memory_usage", lambda elf: (70 * 1024 + 512, 35 * 1024))
  actions.size_report("x.elf", 72, 36)
  out = capsys.readouterr().out
  assert "70.5kB" in out and "72kB" in out and "(97%)" in out
  assert "35.0kB" in out and "36kB" in out

def memory_usage_reads_the_size_table(monkeypatch):
  import subprocess
  import opencplc.actions as actions
  header = "   text   data    bss    dec    hex filename"
  table = header + "\n" + "  68208   4144  30960 103312  19390 x.elf" + "\n"
  monkeypatch.setattr(subprocess, "run",
    lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=table, stderr=""))
  assert actions.memory_usage("x.elf") == (68208 + 4144, 4144 + 30960)

def plc_layer_without_a_board(ws, monkeypatch):
  assert run_cli(monkeypatch, "-n", "app", "-c", "STM32G081", "-P", "-y") == 0
  main_h = (ws / "projects" / "app" / "main.h").read_text()
  assert "PRO_BOARD_None" in main_h
  assert "PRO_PLC true" in main_h
  make = (ws / "projects" / "app" / "makefile").read_text()
  assert "plc/plc.c" in make and "brd/uno" not in make

def bare_metal_writes_a_void_board(ws, monkeypatch):
  assert run_cli(monkeypatch, "-n", "app", "-c", "STM32G081", "-y") == 0
  main_h = (ws / "projects" / "app" / "main.h").read_text()
  assert "PRO_BOARD_None" in main_h
  assert "PRO_PLC false" in main_h
  assert "PRO_DRIVERS" not in main_h  # nothing to name, no line
  assert "plc/plc.c" not in (ws / "projects" / "app" / "makefile").read_text()

def drivers_flag_seeds_pro_drivers(ws, monkeypatch):
  assert run_cli(monkeypatch, "-n", "app", "-c", "STM32G081", "-D", "shtc3", "-y") == 0
  assert 'PRO_DRIVERS "shtc3"' in (ws / "projects" / "app" / "main.h").read_text()
  assert "dvr/shtc3.c" in (ws / "projects" / "app" / "makefile").read_text()

def board_brings_its_own_plc_layer(ws, monkeypatch):
  assert run_cli(monkeypatch, "-n", "app", "-b", "Uno", "-y") == 0
  main_h = (ws / "projects" / "app" / "main.h").read_text()
  assert "PRO_BOARD_Uno" in main_h and "PRO_PLC true" in main_h

def board_without_the_plc_layer_gets_the_plain_skeleton(ws, monkeypatch):
  from conftest import make_board, INI
  d = make_board(ws / "opencplc" / "1.0.0", "bare",
    INI.replace("plc = true", "plc = false"), title="Bare")
  (d / "opencplc_bare.c").write_text("// bare" + chr(10))
  assert run_cli(monkeypatch, "-n", "app", "-b", "bare", "-y") == 0
  main_h = (ws / "projects" / "app" / "main.h").read_text()
  assert "PRO_BOARD_Bare" in main_h and "PRO_PLC false" in main_h
  assert "PLC_Main" not in (ws / "projects" / "app" / "main.c").read_text()
  make = (ws / "projects" / "app" / "makefile").read_text()
  assert "brd/bare/" in make and "plc/plc.c" not in make

def board_without_the_plc_layer_takes_it_from_the_flag(ws, monkeypatch):
  from conftest import make_board, INI
  make_board(ws / "opencplc" / "1.0.0", "bare",
    INI.replace("plc = true", "plc = false"), title="Bare")
  assert run_cli(monkeypatch, "-n", "app", "-b", "bare", "-P", "-y") == 0
  assert "PRO_PLC true" in (ws / "projects" / "app" / "main.h").read_text()
  assert "plc/plc.c" in (ws / "projects" / "app" / "makefile").read_text()

def chip_flag_overrides_the_board_manifest(ws, monkeypatch):
  assert run_cli(monkeypatch, "-n", "app", "-b", "Uno", "-c", "STM32G081", "-y") == 0
  main_h = (ws / "projects" / "app" / "main.h").read_text()
  assert "PRO_BOARD_Uno" in main_h and "PRO_CHIP_STM32G081" in main_h
  assert "PRO_FLASH_kB 128" in main_h  # chip memory, not the 492kB of the board
  assert "SYS_CLOCK_FREQ 59904000" in main_h  # the clock still belongs to the board
  assert run_cli(monkeypatch, "app") == 0  # and it loads back the same way

def update_outside_a_frozen_build_points_at_pip(tmp_path, monkeypatch, capsys):
  monkeypatch.setattr(actions, "FROZEN", False)
  with pytest.raises(SystemExit):
    actions.update_forge(Args(update="latest", yes=True))
  assert "pip install -U opencplc" in capsys.readouterr().out

def frozen_update_lands_next_to_the_executable(tmp_path, monkeypatch):
  exe = frozen_forge(tmp_path, monkeypatch)
  actions.update_forge(Args(update="latest", yes=True))
  assert exe.read_bytes() == b"new"
  assert (tmp_path / "opencplc.exe.old").read_bytes() == b"old"

def a_failed_write_puts_the_old_executable_back(tmp_path, monkeypatch):
  exe = frozen_forge(tmp_path, monkeypatch)
  monkeypatch.setattr(actions.FILE, "save", _raise_disk_full)
  with pytest.raises(SystemExit):
    actions.update_forge(Args(update="latest", yes=True))
  assert exe.read_bytes() == b"old"

def the_replaced_executable_goes_on_the_next_run(tmp_path, monkeypatch):
  frozen_forge(tmp_path, monkeypatch)
  (tmp_path / "opencplc.exe.old").write_bytes(b"old")
  actions.info_actions(Args(), refs_cfg())
  assert not (tmp_path / "opencplc.exe.old").exists()
