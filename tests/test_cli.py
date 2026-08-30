# tests/test_cli.py

"""End-to-end CLI flow in-process: network and toolchain installation stubbed out."""

import pytest
from xaeian import file_context
import opencplc.__main__ as forge
import opencplc.workspace as ws_mod
from conftest import build_workspace, write_forge_config, run_cli

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
  assert 'PRO_BOARD_UNO' in (pro / "main.h").read_text()

def load_existing_project_by_name(ws, monkeypatch):
  assert run_cli(monkeypatch, "-n", "app", "-b", "Uno", "-y") == 0
  assert run_cli(monkeypatch, "app") == 0
  assert "ACTIVE := projects/app" in (ws / "makefile").read_text()

def project_without_pro_chip_is_rejected(ws, monkeypatch):
  # the synthetic myapp carries a main.h with no PRO_CHIP definition
  assert run_cli(monkeypatch, "myapp") == 1

def switching_projects_moves_the_dispatcher(ws, monkeypatch):
  run_cli(monkeypatch, "-n", "a", "-b", "Uno", "-y")
  run_cli(monkeypatch, "-n", "b", "-c", "STM32G081", "-y")
  assert "ACTIVE := projects/b" in (ws / "makefile").read_text()
  run_cli(monkeypatch, "a")
  assert "ACTIVE := projects/a" in (ws / "makefile").read_text()
  assert (ws / "projects" / "b" / "makefile").exists()  # other project keeps its files

def reload_from_inside_project_dir_targets_that_project(ws, monkeypatch):
  import time
  run_cli(monkeypatch, "-n", "deep/app", "-b", "Uno", "-y")
  run_cli(monkeypatch, "-n", "other", "-b", "Uno", "-y")
  makefile = ws / "projects" / "deep" / "app" / "makefile"
  stamp = makefile.stat().st_mtime_ns
  time.sleep(0.02)
  monkeypatch.chdir(ws / "projects" / "deep" / "app")
  assert run_cli(monkeypatch, "-r") == 0
  assert makefile.stat().st_mtime_ns > stamp          # reloaded and marked current
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
  assert "uno" in capsys.readouterr().out

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
