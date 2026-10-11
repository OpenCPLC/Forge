# tests/test_runner.py

"""`--test`: programs run one by one, each in a clean folder and under a time limit."""

import shutil
import pytest
from xaeian import file_context
from opencplc import runner
from opencplc.project import ANSI
from conftest import build_program as build

HAVE_GCC = shutil.which("gcc") is not None

@pytest.fixture()
def build_dir(tmp_path):
  with file_context(root_path=str(tmp_path)):
    yield tmp_path

@pytest.mark.skipif(not HAVE_GCC, reason="gcc required")
def counts_decide_and_a_failure_shows_its_output(build_dir, capsys):
  build(build_dir, "good", '#include <stdio.h>\nint main(void)\n'
    '{ puts("noise"); puts("3 OK"); return 0; }\n')
  build(build_dir, "bad", '#include <stdio.h>\nint main(void)\n'
    '{ puts("detail"); puts("2 OK, 1 ERR"); return 1; }\n')
  assert runner.run_tests(str(build_dir), ["good", "bad"]) == 1
  out = ANSI.sub("", capsys.readouterr().out)
  assert "detail" in out and "noise" not in out
  assert "INF good 3/3 OK" in out and "ERR bad 2/3" in out
  assert "ERR Test programs 1/2, checks 5/6 in" in out

@pytest.mark.skipif(not HAVE_GCC, reason="gcc required")
def one_program_asked_for_shows_everything(build_dir, capsys):
  build(build_dir, "good", '#include <stdio.h>\nint main(void)\n'
    '{ puts("noise"); puts("3 OK"); return 0; }\n')
  assert runner.run_tests(str(build_dir), ["good"]) == 0
  out = ANSI.sub("", capsys.readouterr().out)
  assert "noise" in out and "INF Test programs 1/1, checks 3/3 in" in out

@pytest.mark.skipif(not HAVE_GCC, reason="gcc required")
def an_exit_without_counts_fails(build_dir, capsys):
  """A reset of the firmware is `exit(0)` on the computer, and it is no result."""
  build(build_dir, "quiet", "int main(void) { return 0; }\n")
  assert runner.run_tests(str(build_dir), ["quiet"]) == 1
  assert "ended with code 0" in capsys.readouterr().out

@pytest.mark.skipif(not HAVE_GCC, reason="gcc required")
def any_byte_in_the_output_keeps_the_run(build_dir):
  build(build_dir, "raw", '#include <stdio.h>\nint main(void)\n'
    '{ putchar(255); puts(""); puts("1 OK"); return 0; }\n')
  assert runner.run_tests(str(build_dir), ["raw"]) == 0

@pytest.mark.skipif(not HAVE_GCC, reason="gcc required")
def a_hang_is_cut(build_dir, monkeypatch, capsys):
  monkeypatch.setattr(runner, "TEST_TIMEOUT_s", 1)
  build(build_dir, "stuck", "int main(void) { for(;;); }\n")
  assert runner.run_tests(str(build_dir), ["stuck"]) == 1
  assert "hangs" in capsys.readouterr().out

@pytest.mark.skipif(not HAVE_GCC, reason="gcc required")
def each_run_starts_in_a_clean_folder(build_dir):
  build(build_dir, "once", '#include <stdio.h>\nint main(void) {\n'
    '  if(fopen("state", "r")) return 1;\n'
    '  fclose(fopen("state", "w"));\n'
    '  puts("1 OK");\n  return 0;\n}\n')
  assert runner.run_tests(str(build_dir), ["once"]) == 0
  assert runner.run_tests(str(build_dir), ["once"]) == 0 # the file of the last run is gone
