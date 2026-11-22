# tests/test_local.py

"""Local project: a path names it outside the workspace, its makefile names the workspace."""

import os, re, shutil
import pytest
from xaeian import PATH, file_context
import opencplc.__main__ as forge
import opencplc.workspace as ws_mod
from opencplc import utils
from opencplc.workspace import is_path
from conftest import build_workspace, write_forge_config, run_cli, local_copy

@pytest.fixture()
def ws(tmp_path, monkeypatch):
  """Synthetic workspace as cwd and file root, with `ext/` beside it for local projects."""
  root = tmp_path / "ws"
  root.mkdir()
  build_workspace(root)
  write_forge_config(root)
  monkeypatch.chdir(root)
  monkeypatch.setattr(ws_mod.utils, "ensure_git", lambda yes: None)
  monkeypatch.setattr(ws_mod.utils, "git_get_refs", lambda url, opt="--ref": ["1.0.0"])
  monkeypatch.setattr(forge.utils, "ensure_toolchain", lambda is_embedded, yes, tests: None)
  with file_context(root_path=str(root)):
    yield root

def path_starts_with_a_dot_or_stands_absolute(tmp_path):
  for path in (".", "..", "./app", "../app", ".\\app\\", "..\\ext\\app", str(tmp_path)):
    assert is_path(path), path
  for name in ("app", "firm/app", ".hidden/app", "..app", "opencplc/develop/.tests"):
    assert not is_path(name), name

def path_loads_a_local_project_without_touching_the_workspace(ws, monkeypatch):
  pro = local_copy(ws)
  assert run_cli(monkeypatch, "../ext/app") == 0
  make = (pro / "makefile").read_text()
  assert f"NAME := {PATH.resolve(str(pro))}\n" in make
  assert f"WORKSPACE := {PATH.resolve(str(ws))}\n" in make
  build = next(ln for ln in make.splitlines() if ln.startswith("BUILD := "))
  assert build.startswith("BUILD := $(WORKSPACE)/build/local/") and build.endswith("/app")
  assert ":" not in build.removeprefix("BUILD :=") # the path of the project stays out of it
  assert (pro / "flash.ld").exists()
  assert not (ws / "makefile").exists() and not (ws / ".vscode").exists()
  props = (pro / ".vscode" / "c_cpp_properties.json").read_text()
  assert f'"{PATH.resolve(str(ws))}/opencplc/1.0.0/lib/**"' in props
  assert '"${workspaceFolder}/**"' in props

def powershell_spelling_of_a_path_loads_the_same_project(ws, monkeypatch):
  pro = local_copy(ws)
  assert run_cli(monkeypatch, "..\\ext\\app\\") == 0
  assert f"NAME := {PATH.resolve(str(pro))}\n" in (pro / "makefile").read_text()

def path_into_the_workspace_is_the_name_of_its_project(ws, monkeypatch):
  assert run_cli(monkeypatch, "./projects/myapp") == 0
  assert "ACTIVE := projects/myapp" in (ws / "makefile").read_text()
  assert "NAME := myapp\n" in (ws / "projects" / "myapp" / "makefile").read_text()

def folder_of_the_workspace_beside_its_projects_is_refused(ws, monkeypatch):
  assert run_cli(monkeypatch, ".") == 1
  assert run_cli(monkeypatch, "./opencplc") == 1
  assert not (ws / "makefile").exists()

def folder_holding_the_workspace_is_refused(ws, monkeypatch):
  (ws.parent / "main.h").write_text((ws / "projects" / "myapp" / "main.h").read_text())
  assert run_cli(monkeypatch, "..") == 1
  assert not (ws.parent / "makefile").exists()

def path_make_or_the_console_misreads_is_refused(ws, monkeypatch):
  for folder in ("my app", "c#app", "r&d", "żaba"):
    pro = local_copy(ws, folder)
    assert run_cli(monkeypatch, f"../ext/{folder}") == 1, folder
    assert not (pro / "makefile").exists(), folder

@pytest.mark.skipif(os.name != "nt", reason="a drive root is a Windows path")
def root_of_a_drive_is_refused(ws, monkeypatch):
  assert run_cli(monkeypatch, "Q:/") == 1

@pytest.mark.skipif(os.name != "nt", reason="off Windows another case names another folder")
def path_in_another_case_names_the_same_project(ws, monkeypatch):
  """One spelling for a folder keeps the makefile, its target and its bound probe."""
  pro = local_copy(ws)
  assert run_cli(monkeypatch, "../ext/app", "--stlink", "066DFF51") == 0
  make = (pro / "makefile").read_text()
  assert run_cli(monkeypatch, "../EXT/APP") == 0
  assert (pro / "makefile").read_text() == make
  assert "TARGET := app\n" in make and "STLINK := 066DFF51\n" in make

def path_out_of_any_workspace_stops_before_making_one(ws, monkeypatch):
  pro = local_copy(ws)
  monkeypatch.chdir(pro)
  assert run_cli(monkeypatch, ".") == 1
  assert not (pro / "opencplc.json").exists() and not (pro / "makefile").exists()

def name_out_of_any_workspace_still_starts_one(ws, monkeypatch):
  """`-n` with a name in an empty folder makes a workspace there."""
  empty = ws.parent / "fresh"
  empty.mkdir()
  monkeypatch.chdir(empty)
  monkeypatch.setattr(forge, "ensure_framework", lambda fw_ver, forge_cfg, yes: None)
  run_cli(monkeypatch, "-n", "app", "-b", "Uno", "-y")
  assert (empty / "opencplc.json").exists()

def makefile_of_another_tool_leaves_a_new_workspace_alone(ws, monkeypatch):
  """A `WORKSPACE` of its own in a makefile above, one Forge did not write."""
  other = ws.parent / "other"
  (other / "src").mkdir(parents=True)
  (other / "makefile").write_text(f"WORKSPACE := {PATH.resolve(str(ws.parent / 'ros'))}\n")
  monkeypatch.chdir(other / "src")
  monkeypatch.setattr(forge, "ensure_framework", lambda fw_ver, forge_cfg, yes: None)
  run_cli(monkeypatch, "-n", "app", "-b", "Uno", "-y")
  assert (other / "src" / "opencplc.json").exists()

def local_project_finds_its_workspace_through_its_makefile(ws, monkeypatch):
  pro = local_copy(ws)
  run_cli(monkeypatch, "../ext/app")
  (pro / "flash.ld").unlink()
  shutil.rmtree(pro / ".vscode")
  monkeypatch.chdir(pro / "util")
  assert run_cli(monkeypatch, "-r") == 0
  assert (pro / "flash.ld").exists() # this project regenerated
  assert not (pro / ".vscode").exists() # a reload leaves the editor files, as in the workspace
  monkeypatch.chdir(pro)
  assert run_cli(monkeypatch, ".") == 0
  assert (pro / ".vscode" / "launch.json").exists()

def loaded_local_project_finds_its_workspace_from_a_folder_beside(ws, monkeypatch):
  pro = local_copy(ws)
  run_cli(monkeypatch, "../ext/app")
  (pro / "flash.ld").unlink()
  monkeypatch.chdir(pro.parent)
  assert run_cli(monkeypatch, "./app") == 0
  assert (pro / "flash.ld").exists()

def makefile_naming_a_workspace_gone_stops_the_run(ws, monkeypatch, capsys):
  pro = local_copy(ws)
  gone = PATH.resolve(str(ws.parent / "gone"))
  header = "# Generated by OpenCPLC Forge, reload with `opencplc -r`"
  name = PATH.resolve(str(pro))
  (pro / "makefile").write_text(f"{header}\nNAME := {name}\nWORKSPACE := {gone}\n")
  monkeypatch.chdir(pro)
  assert run_cli(monkeypatch, "-r") == 1
  assert "has no" in capsys.readouterr().out

def local_project_is_never_deleted(ws, monkeypatch):
  pro = local_copy(ws)
  assert run_cli(monkeypatch, "-d", "../ext/app") == 1
  assert (pro / "main.c").exists()

def new_local_project_lands_outside_but_not_inside_another(ws, monkeypatch):
  assert run_cli(monkeypatch, "-n", "../ext/fresh", "-b", "Uno", "-y") == 0
  pro = ws.parent / "ext" / "fresh"
  assert (pro / "main.c").exists() and (pro / "makefile").exists()
  assert run_cli(monkeypatch, "-n", "../ext/fresh/inner", "-b", "Uno", "-y") == 1
  assert not (pro / "inner").exists()

def tree_path_files_an_outside_path_short_under_local(ws):
  assert utils.tree_path("projects/myapp") == "projects/myapp"
  assert utils.tree_path(str(ws / "projects" / "myapp")) == "projects/myapp"
  deep = ws.parent / ("deep" * 30) / "app"
  outside = utils.tree_path(str(deep))
  assert re.fullmatch(r"local/[0-9a-f]{8}/app", outside), outside
  assert outside != utils.tree_path(str(ws.parent / "app")) # same name, another folder
  if os.name == "nt": # one folder whatever case the path is typed in
    assert utils.tree_path(str(deep).upper()).lower() == outside.lower()

def dot_folder_never_loads_as_a_local_project(ws, monkeypatch):
  """A simulator beside the projects keeps its own makefile, and no project starts there."""
  sim = local_copy(ws, ".sim")
  makefile = sim / "makefile"
  makefile.write_text("all:\n\tgcc sim.c\n")
  assert run_cli(monkeypatch, str(sim)) == 1
  assert makefile.read_text() == "all:\n\tgcc sim.c\n"
  made = ws.parent / "ext" / ".made"
  assert run_cli(monkeypatch, "-n", str(made), "-c", "HOST", "-y") == 1
  assert not made.exists()

def tests_folder_of_a_local_project_never_loads_as_one(ws, monkeypatch):
  """`.tests/main.h` sets up the tests of the project above, so Forge writes nothing into it."""
  tests = local_copy(ws) / ".tests"
  tests.mkdir()
  (tests / "main.h").write_text((ws / "projects" / "myapp" / "main.h").read_text())
  assert run_cli(monkeypatch, str(tests)) == 1
  assert [path.name for path in tests.iterdir()] == ["main.h"]

def dot_folder_of_a_local_project_is_no_project(tmp_path):
  app = tmp_path / "app"
  (app / ".sim" / "src").mkdir(parents=True)
  for folder in (app, app / ".sim"):
    (folder / "main.h").write_text("")
  assert ws_mod.local_project_at(str(app / ".sim" / "src")) == utils.full_path(str(app))

def local_name_goes_by_its_folder(tmp_path):
  name = PATH.resolve(str(tmp_path / "app"))
  assert utils.is_local(name) and not utils.is_local("firm/app")
  assert utils.project_dir(name) == name
  assert utils.home_name(name) == "app"
  assert utils.core_version(name) == ""
