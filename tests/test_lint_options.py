# tests/test_lint_options.py

"""Rules a project turns on in its `lint.yaml`, compiler rules reaching it alone."""

import os
from dataclasses import replace
from types import SimpleNamespace
import pytest
from xaeian import FILE, PATH, file_context
from xaeian.cmd import which
from opencplc.lint.rules import split_opt_ins
from opencplc.lint import checkers
from opencplc.lint.checkers import Unit, run_analyzer, too_old
from opencplc.lint.command import vector_entry
from opencplc.utils import tools
from conftest import lint_finding as finding

ARM_BIN = tools.bin_dir("arm-gcc")
GCC = which("arm-none-eabi-gcc", f"{ARM_BIN}/arm-none-eabi-gcc")

@pytest.fixture()
def workspace(tmp_path):
  """Paths of a test count from its own folder, as the paths of a build from the workspace."""
  root = PATH.normalize(str(tmp_path))
  with file_context(root_path=root):
    yield root

def names_split_into_rules_to_turn_on_and_the_rest():
  assert split_opt_ins(["no-heap"]) == (["no-heap"], [])
  # A rule of the default set is on already, so naming it is a mistake too
  named = ["nope", "irq-yield", "status-used", "float-literal", "conversion", "fixed-width",
    "cppcheck-style"]
  assert split_opt_ins(["no-heap", *named]) == (["no-heap"], named)
  # MISRA C goes by number, which the addon checks later: a number cut short or a directive is none
  forms = ["misra-15.5", "misra-20.10", "no-continue", "function-length"]
  wrong = ["misra-15", "misra-d4.6"]
  assert split_opt_ins([*forms, *wrong]) == (forms, wrong)

@pytest.mark.skipif(GCC is None, reason="arm-none-eabi-gcc required")
def compiler_rules_reach_the_project_alone(workspace, monkeypatch):
  monkeypatch.setenv("PATH", ARM_BIN + os.pathsep + os.environ.get("PATH", ""))
  # Narrowing asks for a cast, widening loses nothing and passes
  narrowing = ("#include <stdint.h>\nuint8_t cut(uint32_t value);\n"
    "uint8_t cut(uint32_t value) { return value; }\nuint32_t wide(uint8_t value);\n"
    "uint32_t wide(uint8_t value) { return value; }\n")
  FILE.save(f"{workspace}/core/lib.c", narrowing)
  FILE.save(f"{workspace}/project/main.c", narrowing)
  unit = Unit("app", "-mcpu=cortex-m4 -mthumb",
    [f"{workspace}/core/lib.c", f"{workspace}/project/main.c"], [], [], f"{workspace}/project")
  found = run_analyzer(unit, f"{workspace}/build", {"conversion"})
  assert [(f.rule, f.path, f.line) for f in found] == [("conversion", "project/main.c", 3)]
  assert run_analyzer(unit, f"{workspace}/build", set()) == []

@pytest.mark.skipif(GCC is None, reason="arm-none-eabi-gcc required")
def what_no_header_declares_is_static(workspace, monkeypatch):
  monkeypatch.setenv("PATH", ARM_BIN + os.pathsep + os.environ.get("PATH", ""))
  FILE.save(f"{workspace}/project/main.c", "int count;\nstatic int kept;\n"
    "void loop(void) { count = kept++; }\nint main(void) { loop(); return count; }\n")
  unit = Unit("app", "-mcpu=cortex-m4 -mthumb", [f"{workspace}/project/main.c"], [], [],
    f"{workspace}/project")
  found = run_analyzer(unit, f"{workspace}/build", {"static-scope"})
  # Each named, so an exception reaches one symbol, a variable too
  assert sorted((f.rule, f.line, f.function) for f in found) == [
    ("static-scope", 1, "count"),
    ("static-scope", 3, "loop"),
  ]

def a_handler_of_the_vector_table_stays_global():
  # The startup code declares it, and `static` would leave its weak default in the table
  handlers = ("IRQHandler", "_Handler")
  handler = finding("static-scope", "project/main.c", "TIM2_IRQHandler")
  assert vector_entry(handler, handlers)
  assert not vector_entry(replace(handler, function="loop"), handlers)
  assert not vector_entry(replace(handler, rule="analyzer"), handlers)

@pytest.mark.skipif(GCC is None, reason="arm-none-eabi-gcc required")
def a_source_gcc_cannot_compile_is_a_finding_of_the_analyzer(workspace, monkeypatch):
  monkeypatch.setenv("PATH", ARM_BIN + os.pathsep + os.environ.get("PATH", ""))
  FILE.save(f"{workspace}/project/main.c", "int main(void) { return missing; }\n")
  unit = Unit("app", "-mcpu=cortex-m4 -mthumb", [f"{workspace}/project/main.c"], [], [],
    f"{workspace}/project")
  found = run_analyzer(unit, f"{workspace}/build", set())
  assert [(f.rule, f.path, f.line) for f in found] == [("analyzer", "project/main.c", 1)]
  assert found[0].message.startswith("`-fanalyzer` stops:") and "missing" in found[0].message

def a_tool_older_than_the_rules_know_is_named(monkeypatch):
  monkeypatch.setattr(checkers, "version", lambda cmd: "2.13.0")
  assert too_old("cppcheck", (2, 17)) == "2.13.0"
  monkeypatch.setattr(checkers, "version", lambda cmd: "2.22")
  assert too_old("cppcheck", (2, 17)) is None
  monkeypatch.setattr(checkers, "version", lambda cmd: None)
  assert too_old("cppcheck", (2, 17)) == "?"
  monkeypatch.setattr(checkers, "version", lambda cmd: "13.2")
  assert too_old("arm-none-eabi-gcc", (14,)) == "13.2"

def what_gcc_defines_never_comes_from_cppcheck(monkeypatch, tmp_path):
  """A shift of a negative value is defined by gcc, `>>` extending the sign."""
  commands = []
  monkeypatch.setattr(checkers, "run",
    lambda command: commands.append(command) or SimpleNamespace(stdout="", stderr=""))
  unit = Unit("app", "-mcpu=cortex-m0plus", [], [], [])
  checkers.cppcheck(unit, PATH.normalize(str(tmp_path)), [])
  assert "--suppress=shiftNegativeLHS" in commands[-1]
