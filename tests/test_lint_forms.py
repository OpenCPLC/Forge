# tests/test_lint_forms.py

"""Rules of form over the code a project writes, macros of Core expanded in it left out."""

import os, stat, sys
import pytest
from xaeian import FILE, PATH, file_context
from xaeian.cmd import run, which
from opencplc.lint.checkers import (
  CPPCHECK_MIN, Unit as Build, run_cppcheck, too_old, misra_addon, misra_rules, python_command,
)
from opencplc.lint.forms import trim_directives
from opencplc.utils import tools

CPPCHECK = which(f"{tools.bin_dir('cppcheck')}/cppcheck" if tools.WINDOWS else "cppcheck")
USABLE = bool(CPPCHECK) and not too_old(CPPCHECK, CPPCHECK_MIN)
ARM_BIN = tools.bin_dir("arm-gcc")
GCC = which("arm-none-eabi-gcc", f"{ARM_BIN}/arm-none-eabi-gcc")
REPO = PATH.dirname(PATH.dirname(PATH.resolve(__file__)))
CORE = """#ifndef CORE_H_
#define CORE_H_
#define CORE_SKIP(n) for(int k = 0; k < (n); k++) { if(k == 1) continue; }
#define CORE_LEAVE(label) goto label
typedef void (*CORE_Fn_t)(void);
typedef enum { CORE_Off, CORE_On } CORE_State_t;
void CORE_Run(CORE_Fn_t fn);
int CORE_Status(void);
CORE_State_t CORE_State(void);
#endif
"""
APP = """#include "core.h"
#define TWICE(x) ((x) * 2)
static int count;
static void (*hook)(void);
static void tick(void) { count++; }
static unsigned char flags;
float ratio(void) { return 0.5f; }
int main(void)
{
  for(unsigned char i = 0; i < 3; i++) { if(i == 1) continue; }
  if(count == 3) count = TWICE(count);
  if(3 == count) goto done;
  CORE_SKIP(4);
  CORE_LEAVE(done);
  CORE_Run(tick);
  hook = tick;
  flags = (unsigned char)CORE_Status();
  if(CORE_State() == CORE_On) count++;
  if(count == LIMIT_FROM_NOWHERE) count = 0;
done:
  return count;
}
void long_one(void)
{
""" + "  count++;\n" * 61 + "}\n"
FORMS = frozenset({
  "no-continue", "constant-left", "function-length", "fixed-width",
  "no-function-macro", "no-function-pointer", "misra-15.1",
})
# Line of `APP` holding each text
AT = {text: next(n for n, line in enumerate(APP.splitlines(), 1) if text in line) for text in (
  "if(i == 1) continue", "if(count == 3)", "if(3 == count)", "#define TWICE", "(*hook)",
  "void long_one", "int count", "char flags", "float ratio", "char i", "int main", "CORE_SKIP(4)",
  "goto done", "== CORE_On", "LIMIT_FROM_NOWHERE",
)}

@pytest.fixture()
def found(tmp_path, monkeypatch):
  """Findings of every rule of form over `APP`, a project including the `core.h` of a Core."""
  if not USABLE or GCC is None: pytest.skip("cppcheck and arm-none-eabi-gcc required")
  root = PATH.normalize(str(tmp_path))
  paths = [os.path.dirname(CPPCHECK), ARM_BIN, os.environ.get("PATH", "")]
  monkeypatch.setenv("PATH", os.pathsep.join(paths))
  FILE.save(f"{root}/core/core.h", CORE)
  FILE.save(f"{root}/pro/app.c", APP)
  unit = Build("app", "-mcpu=cortex-m0plus -mthumb", [f"{root}/pro/app.c"], [],
    [f"{root}/core", f"{root}/pro"], "pro")
  with file_context(root_path=root):
    yield [(f.rule, f.line) for f in run_cppcheck(unit, f"{root}/lint", forms=FORMS)[0]
      if f.rule in FORMS]

def each_form_finds_what_the_project_writes(found):
  assert ("no-continue", AT["if(i == 1) continue"]) in found
  assert ("constant-left", AT["if(i == 1) continue"]) in found
  assert ("constant-left", AT["if(count == 3)"]) in found
  assert ("constant-left", AT["== CORE_On"]) in found
  assert ("no-function-macro", AT["#define TWICE"]) in found
  assert ("no-function-pointer", AT["(*hook)"]) in found
  assert ("function-length", AT["void long_one"]) in found
  widths = {line for rule, line in found if rule == "fixed-width"}
  assert widths == {AT[text] for text in ("int count", "char flags", "char i")}

def a_constant_on_the_left_float_and_main_returning_int_pass(found):
  assert ("constant-left", AT["if(3 == count)"]) not in found
  # A name cppcheck cannot resolve may be a variable just as well
  assert ("constant-left", AT["LIMIT_FROM_NOWHERE"]) not in found
  # IEEE 754 gives `float` its width wherever OpenCPLC runs
  assert ("fixed-width", AT["float ratio"]) not in found
  assert ("fixed-width", AT["int main"]) not in found

def a_macro_of_core_stays_theirs_where_the_project_expands_it(found):
  # `CORE_SKIP` brings an `int`, a `continue` and a constant on the right, all Core's
  assert [rule for rule, line in found if line == AT["CORE_SKIP(4)"]] == []
  assert sum(rule == "no-continue" for rule, _ in found) == 1

def misra_rules_come_from_the_addon_of_cppcheck(found):
  if misra_addon() is None: pytest.skip("cppcheck without its MISRA addon")
  # The `goto` of `CORE_LEAVE` is a macro of Core
  assert [line for rule, line in found if rule == "misra-15.1"] == [AT["goto done"]]

def the_addon_names_its_rules_in_its_source(tmp_path):
  addon = f"{PATH.normalize(str(tmp_path))}/misra.py"
  FILE.save(addon, "self.executeCheck(1505, misra_15_5)\nself.executeCheck(2010, misra_20_10)\n")
  assert misra_rules(addon) == {"15.5", "20.10"}

def the_addon_lies_in_the_tree_of_cppcheck(tmp_path, monkeypatch):
  # Debian keeps it under the folder of its architecture
  root = PATH.normalize(str(tmp_path))
  for name in ("cppcheck", "cppcheck.exe"):
    FILE.save(f"{root}/bin/{name}", "")
    os.chmod(f"{root}/bin/{name}", stat.S_IRWXU)
  FILE.save(f"{root}/lib/x86_64-linux-gnu/cppcheck/addons/misra.py", "")
  monkeypatch.setenv("PATH", f"{root}/bin")
  assert misra_addon() == f"{root}/lib/x86_64-linux-gnu/cppcheck/addons/misra.py"

def directives_of_others_leave_the_dump(tmp_path):
  dump = f"{PATH.normalize(str(tmp_path))}/app.c.dump"
  FILE.save(dump, "<dumps>\n  <directivelist>\n"
    '    <directive file="core/core.h" linenr="1" str="#define A 1">\n'
    '      <token column="1" str="#"/>\n    </directive>\n'
    '    <directive file="pro/app.c" linenr="2" str="#define B(x) x">\n'
    '      <token column="1" str="#"/>\n    </directive>\n'
    '    <directive file="core/old.h" linenr="3" str="#define C 3"/>\n'
    "  </directivelist>\n</dumps>\n")
  trim_directives(dump, lambda file: file.startswith("pro/"))
  text = FILE.load(dump)
  assert 'str="#define B(x) x"' in text and "core/" not in text
  assert text.count("<directive ") == text.count("</directive>") == 1

def a_frozen_forge_runs_the_addon_through_itself(monkeypatch):
  monkeypatch.setattr(sys, "frozen", True, raising=False)
  assert python_command() == [sys.executable, "--python"]

def the_executable_runs_a_script_as_python_would(tmp_path):
  # `opencplc.exe --python` holds the only Python a machine may have, so the addon runs on it
  if not FILE.exists(f"{REPO}/.build.py"): pytest.skip("entry of the executable lies in the tree")
  root = PATH.normalize(str(tmp_path))
  FILE.save(f"{root}/helper.py", "WORD = 'beside'\n")
  FILE.save(f"{root}/script.py", "import sys, helper\nprint(helper.WORD, *sys.argv[1:])\n")
  done = run([sys.executable, f"{REPO}/.build.py", "--python", f"{root}/script.py", "a", "b"])
  assert done.stdout.split() == ["beside", "a", "b"], done.stderr
