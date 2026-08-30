# tests/test_make.py

"""
Generated makefiles driven by the real GNU Make.

HOST projects compile with the local gcc over a synthetic Core; embedded
makefiles are checked with a dry run. Skipped where make or gcc is missing.
"""

import shutil, subprocess
import pytest
from xaeian import file_context
from opencplc.project import generate
from conftest import (
  resolve_uno, build_workspace, host_model, make_run, write_file, forge_env, age,
)

HAVE_MAKE = shutil.which("make") is not None
HAVE_GCC = shutil.which("gcc") is not None

@pytest.fixture()
def ws(tmp_path):
  """Synthetic Core with real C: hal/host, lib and one host project calling into both."""
  core = tmp_path / "opencplc" / "1.0.0"
  write_file(core / "hal" / "host" / "sys.c", "int sys_tick(void) { return 42; }\n")
  write_file(core / "hal" / "host" / "sys.h", "int sys_tick(void);\n")
  write_file(core / "lib" / "util.c", "int lib_util(void) { return 1; }\n")
  write_file(core / "lib" / "util.h", "int lib_util(void);\n")
  pro = tmp_path / "projects" / "app"
  write_file(pro / "main.h", "#define PRO_CHIP_HOST\n")
  write_file(pro / "util.c", "int pro_util(void) { return 2; }\n")
  write_file(pro / "main.c",
    '#include "sys.h"\n#include "util.h"\nint pro_util(void);\n'
    "int main(void) { return sys_tick() + lib_util() + pro_util(); }\n")
  (tmp_path / "opencplc.json").write_text("{}")
  with file_context(root_path=str(tmp_path)):
    yield tmp_path

@pytest.mark.skipif(not (HAVE_MAKE and HAVE_GCC), reason="make and gcc required")
def host_project_builds_and_rebuild_is_a_noop(ws):
  generate(host_model())
  res = make_run(ws, "app", "build")
  assert res.returncode == 0, res.stdout + res.stderr
  out = ws / "build" / "projects" / "app"
  assert any(f.name.startswith("app") for f in out.iterdir())
  again = make_run(ws, "app", "build")
  assert "Nothing to be done" in again.stdout

@pytest.mark.skipif(not (HAVE_MAKE and HAVE_GCC), reason="make and gcc required")
def same_file_name_in_core_and_project_gives_two_objects(ws):
  generate(host_model())
  assert make_run(ws, "app", "build").returncode == 0
  obj = ws / "build" / "projects" / "app"
  assert (obj / "opencplc" / "lib" / "util.o").exists()
  assert (obj / "project" / "util.o").exists()

@pytest.mark.skipif(not (HAVE_MAKE and HAVE_GCC), reason="make and gcc required")
def clean_removes_only_this_project(ws):
  generate(host_model())
  assert make_run(ws, "app", "build").returncode == 0
  (ws / "build" / "projects" / "other").mkdir(parents=True)
  assert make_run(ws, "app", "clean").returncode == 0
  assert not (ws / "build" / "projects" / "app").exists()
  assert (ws / "build" / "projects" / "other").exists()

@pytest.mark.skipif(not (HAVE_MAKE and HAVE_GCC), reason="make and gcc required")
def switching_projects_keeps_the_other_build(ws):
  # project B shares the Core but compiles with its own flags
  pro_b = ws / "projects" / "b"
  write_file(pro_b / "main.h", "#define PRO_CHIP_HOST\n")
  write_file(pro_b / "main.c", "int main(void) { return 0; }\n")
  generate(host_model("app"))
  assert make_run(ws, "app", "build").returncode == 0
  stamp = {f: f.stat().st_mtime_ns
    for f in (ws / "build" / "projects" / "app").rglob("*.o")}
  generate(host_model("b"))
  assert make_run(ws, "b", "build").returncode == 0
  generate(host_model("app"))
  again = make_run(ws, "app", "build")
  assert "Nothing to be done" in again.stdout
  assert {f: f.stat().st_mtime_ns
    for f in (ws / "build" / "projects" / "app").rglob("*.o")} == stamp

@pytest.mark.skipif(not HAVE_MAKE, reason="make required")
def embedded_makefile_parses_in_dry_run(tmp_path):
  build_workspace(tmp_path)
  with file_context(root_path=str(tmp_path)):
    generate(resolve_uno())
  res = subprocess.run(["make", "-C", str(tmp_path / "projects" / "myapp"), "-n", "build"],
    capture_output=True, text=True)
  assert res.returncode == 0, res.stderr
  assert "arm-none-eabi-gcc -c" in res.stdout
  assert "myapp/opencplc/hal/arm/core.o" in res.stdout.replace("\\", "/")
  assert "myapp/project/main.o" in res.stdout.replace("\\", "/")

# The reload rule runs Forge itself, so these tests drive the real CLI through Make.
# FORGE points Make at this interpreter and PYTHONPATH at the repo, no install needed.

@pytest.mark.skipif(not (HAVE_MAKE and HAVE_GCC), reason="make and gcc required")
def stale_main_h_triggers_exactly_one_reload(ws):
  import os, time
  from conftest import write_forge_config
  write_forge_config(ws)
  generate(host_model())
  assert make_run(ws, "app", "build").returncode == 0
  makefile = ws / "projects" / "app" / "makefile"
  age(makefile, *(ws / "build").rglob("*.o"))
  before = makefile.stat().st_mtime_ns
  os.utime(ws / "projects" / "app" / "main.h", None)
  env, forge = forge_env()
  res = subprocess.run(["make", "-C", str(ws / "projects" / "app"), "build", forge],
    capture_output=True, text=True, env=env)
  assert res.returncode == 0, res.stdout + res.stderr
  assert res.stdout.count("using framework version") == 1
  assert makefile.stat().st_mtime_ns > before
  again = subprocess.run(["make", "-C", str(ws / "projects" / "app"), "build", forge],
    capture_output=True, text=True, env=env)
  assert "using framework version" not in again.stdout
  assert "Nothing to be done" in again.stdout

@pytest.mark.skipif(not (HAVE_MAKE and HAVE_GCC), reason="make and gcc required")
def new_source_is_built_in_the_same_make_run(ws):
  import time
  from conftest import write_forge_config
  write_forge_config(ws)
  generate(host_model())
  assert make_run(ws, "app", "build").returncode == 0
  age(ws / "projects" / "app" / "makefile", *(ws / "build").rglob("*.o"))
  write_file(ws / "projects" / "app" / "more.c", "int more(void) { return 3; }\n")
  env, forge = forge_env()
  res = subprocess.run(["make", "-C", str(ws / "projects" / "app"), "build", forge],
    capture_output=True, text=True, env=env)
  assert res.returncode == 0, res.stdout + res.stderr
  assert res.stdout.count("using framework version") == 1
  assert (ws / "build" / "projects" / "app" / "project" / "more.o").exists()

@pytest.mark.skipif(not (HAVE_MAKE and HAVE_GCC), reason="make and gcc required")
def missing_forge_fails_the_reload(ws):
  import os, time
  generate(host_model())
  assert make_run(ws, "app", "build").returncode == 0
  age(ws / "projects" / "app" / "makefile")
  os.utime(ws / "projects" / "app" / "main.h", None)
  res = subprocess.run(["make", "-C", str(ws / "projects" / "app"), "build",
    "FORGE=no_such_forge_cmd"], capture_output=True, text=True)
  assert res.returncode != 0
  assert "no_such_forge_cmd" in res.stdout + res.stderr

@pytest.mark.skipif(not (HAVE_MAKE and HAVE_GCC), reason="make and gcc required")
def dist_copies_one_tagged_file_into_the_project(ws):
  generate(host_model())
  res = make_run(ws, "app", "dist", "TAG=1.2.0")
  assert res.returncode == 0, res.stdout + res.stderr
  copies = sorted(f.name for f in (ws / "projects" / "app").iterdir() if f.name.startswith("app-"))
  assert len(copies) == 1 and copies[0].startswith("app-1.2.0")
  assert "Copied" in res.stdout

@pytest.mark.skipif(not (HAVE_MAKE and HAVE_GCC), reason="make and gcc required")
def root_make_reports_idle_and_failure(ws):
  generate(host_model())
  first = subprocess.run(["make"], cwd=ws, capture_output=True, text=True)
  assert first.returncode == 0, first.stdout + first.stderr
  again = subprocess.run(["make"], cwd=ws, capture_output=True, text=True)
  assert "Nothing to be done for" in again.stdout and "Entering directory" in again.stdout
  age(*(ws / "build").rglob("*.o"), *(ws / "build").glob("app*")) # edit lands in the same second
  write_file(ws / "projects" / "app" / "main.c", "int main(void) { return }" + "\n")
  broken = subprocess.run(["make"], cwd=ws, capture_output=True, text=True)
  assert broken.returncode != 0
  assert "Build failed in" in broken.stdout
