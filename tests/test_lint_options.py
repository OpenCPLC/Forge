# tests/test_lint_options.py

"""Rules a project turns on in its `lint.yaml`, compiler rules reaching it alone."""

import os
import pytest
from xaeian import FILE, PATH, file_context
from xaeian.cmd import which
from opencplc.lint.rules import split_opt_ins
from opencplc.lint import checkers
from opencplc.lint.checkers import Unit, run_analyzer, cppcheck_too_old
from opencplc.utils import tools

ARM_BIN = tools.bin_dir("arm-gcc")
GCC = which("arm-none-eabi-gcc", f"{ARM_BIN}/arm-none-eabi-gcc")

@pytest.fixture()
def workspace(tmp_path):
  """Paths of a test count from its own folder, as the paths of a build from the workspace."""
  root = PATH.normalize(str(tmp_path))
  with file_context(root_path=root):
    yield root

def names_split_into_rules_to_turn_on_and_the_rest():
  assert split_opt_ins(["no-heap", "stack-margin", "conversion"]) == (
    ["no-heap", "stack-margin", "conversion"], [])
  # A rule of the default set is on already, so naming it is a mistake too
  assert split_opt_ins(["no-heap", "nope", "irq-yield"]) == (["no-heap"], ["nope", "irq-yield"])

@pytest.mark.skipif(GCC is None, reason="arm-none-eabi-gcc required")
def compiler_rules_turned_on_reach_the_project_alone(workspace, monkeypatch):
  monkeypatch.setenv("PATH", ARM_BIN + os.pathsep + os.environ.get("PATH", ""))
  narrowing = ("#include <stdint.h>\nuint8_t cut(uint32_t value);\n"
    "uint8_t cut(uint32_t value) { return value; }\n")
  FILE.save(f"{workspace}/core/lib.c", narrowing)
  FILE.save(f"{workspace}/project/main.c", narrowing)
  unit = Unit("app", "-mcpu=cortex-m4 -mthumb",
    [f"{workspace}/core/lib.c", f"{workspace}/project/main.c"], [], [], f"{workspace}/project")
  found = run_analyzer(unit, f"{workspace}/build", {"conversion"})
  assert [(f.rule, f.path, f.line) for f in found] == [("conversion", "project/main.c", 3)]
  assert run_analyzer(unit, f"{workspace}/build", set()) == []

@pytest.mark.skipif(GCC is None, reason="arm-none-eabi-gcc required")
def a_source_gcc_cannot_compile_is_a_finding_of_the_analyzer(workspace, monkeypatch):
  monkeypatch.setenv("PATH", ARM_BIN + os.pathsep + os.environ.get("PATH", ""))
  FILE.save(f"{workspace}/project/main.c", "int main(void) { return missing; }\n")
  unit = Unit("app", "-mcpu=cortex-m4 -mthumb", [f"{workspace}/project/main.c"], [], [],
    f"{workspace}/project")
  found = run_analyzer(unit, f"{workspace}/build", set())
  assert [(f.rule, f.path, f.line) for f in found] == [("analyzer", "project/main.c", 1)]
  assert found[0].message.startswith("`-fanalyzer` stops:") and "missing" in found[0].message

def a_cppcheck_older_than_the_rules_know_is_named(monkeypatch):
  monkeypatch.setattr(checkers, "version", lambda cmd: "2.13.0")
  assert cppcheck_too_old() == "2.13.0"
  monkeypatch.setattr(checkers, "version", lambda cmd: "2.22")
  assert cppcheck_too_old() is None
  monkeypatch.setattr(checkers, "version", lambda cmd: None)
  assert cppcheck_too_old() == "?"
