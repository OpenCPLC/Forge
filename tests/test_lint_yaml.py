# tests/test_lint_yaml.py

"""`lint.yaml` of Core and of a project: roles and what a project adds, rules, exceptions."""

from xaeian import FILE, YAML, file_context
import pytest
from dataclasses import replace
from opencplc.lint.lintfile import LintFileError, read, exceptions, keep
from opencplc.lint.rules import load_roles
from opencplc.lint.dump import Entry, Values
from opencplc.lint.command import lint_opt_ins, load_all_waivers, vouching
from conftest import lint_finding as finding

ROLES = {
  "yield": ["let", "delay"], "hold": ["sleep"],
  "heap": {"any": ["heap_new", "heap_clear"], "new": "heap_new", "clear": "heap_clear"},
  "thread": "vrts_thread",
  "irq": {"handler": ["IRQHandler", "_Handler"], "start": ["IRQ_Enable*"], "field": ["Callback"]},
  "frame": {"cortex-m4": 17},
  "log": ["_LOG_*"], "panic": ["panic"], "status": "status_t", "load": ["*_Load"],
}

@pytest.fixture(autouse=True)
def workspace(tmp_path):
  """Paths of a test count from its own folder, as the paths of a build from the workspace."""
  with file_context(root_path=str(tmp_path)):
    YAML.save("core/lint.yaml", {"roles": ROLES, "vendor": ["lib/ext/*"]})
    yield

def a_project_adds_to_the_lists_of_core():
  FILE.save("app/lint.yaml", "roles:\n  irq:\n    field: [OnFrame]\n  load: [SENSOR_Read]\n"
    "vendor: [lib/third/*]\n")
  roles = load_roles("core", "app")
  assert roles.irq_fields == ["Callback", "OnFrame"]
  assert roles.load == ["*_Load", "SENSOR_Read"]
  assert roles.vendor == [("core", "lib/ext/*"), ("app", "lib/third/*")]
  assert load_roles("core", "elsewhere").irq_fields == ["Callback"]
  assert load_roles("nowhere", "app") is None

def a_key_out_of_place_is_an_error_naming_it():
  FILE.save("app/lint.yaml", "roles:\n  thread: my_thread\n")
  with pytest.raises(LintFileError, match="role `thread` is set by Core"):
    load_roles("core", "app")
  FILE.save("app/lint.yaml", "exept: {}\n")
  with pytest.raises(LintFileError, match="no place for `exept`"): read("app", core=False)
  FILE.save("app/lint.yaml", "roles:\n  irq:\n    feild: [OnFrame]\n")
  with pytest.raises(LintFileError, match="no role `irq.feild`"): read("app", core=False)
  YAML.save("core/lint.yaml", {"roles": ROLES, "rules": ["no-heap"]})
  with pytest.raises(LintFileError, match="turned on by a project"): read("core", core=True)

def a_project_turns_rules_on():
  FILE.save("app/lint.yaml", "rules: [no-heap, nope]\n")
  assert lint_opt_ins("app") == ({"no-heap"}, ["nope"])
  assert lint_opt_ins("plain") == (set(), [])

def stack_margin_is_a_quarter_unless_the_project_gives_another_for_all_or_by_thread():
  FILE.save("app/lint.yaml", "rules: [no-heap]\n")
  assert read("app", core=False)["stack-margin"].of("loop") == 25
  FILE.save("app/lint.yaml", "stack-margin: 10\n")
  assert read("app", core=False)["stack-margin"].of("loop") == 10
  FILE.save("app/lint.yaml", "stack-margin: {DBG_Loop: 0, loop: 40}\n")
  margins = read("app", core=False)["stack-margin"]
  assert (margins.of("DBG_Loop"), margins.of("loop"), margins.of("PLC_Main")) == (0, 40, 25)

def stack_margin_takes_whole_percents_from_a_project_alone():
  for value in ("100", "-1", "12.5", "25%", "true", "{loop: 75%}"):
    FILE.save("app/lint.yaml", f"stack-margin: {value}\n")
    with pytest.raises(LintFileError, match="whole percents from 0 to 99"): read("app", core=False)
  YAML.save("core/lint.yaml", {"roles": ROLES, "stack-margin": 10})
  with pytest.raises(LintFileError, match="set by a project"): read("core", core=True)

def an_exception_without_a_reason_is_refused():
  FILE.save("app/lint.yaml", "except:\n  recursion:\n    lib/*:\n  irq-yield:\n"
    "    '*': checked by hand\n")
  waivers, refused = exceptions(read("app", core=False), "app")
  assert [w.text() for w in waivers] == ["irq-yield *"]
  assert refused == ["app/lint.yaml: recursion lib/*"]

def an_exception_explains_its_rule_at_its_place():
  FILE.save("app/lint.yaml", "except:\n"
    "  thread-hold:\n    main.c:calibrate: a quiet bus for 50ms\n"
    "  recursion:\n    lib/ext/: messages nest three levels at most\n")
  waivers, _ = load_all_waivers("core", "app")
  left = keep([
    finding("thread-hold", "app/main.c", "calibrate"),
    finding("thread-hold", "app/main.c", "loop"),
    finding("recursion", "app/lib/ext/pb/decode.c", "decode"),
    finding("recursion", "app/lib/mine.c", "walk"),
  ], waivers)
  assert [(f.path, f.function) for f in left] == [
    ("app/main.c", "loop"), ("app/lib/mine.c", "walk")]
  assert all(w.used for w in waivers)

def a_project_vouches_for_its_own_entry_into_an_enum_of_core():
  # The `switch` lies in Core, while the value enters it in the project, checked out of reach
  FILE.save("app/lint.yaml", "except:\n  switch-default:\n"
    "    state.c:apply: Register map refuses other values before apply\n")
  waivers, _ = load_all_waivers("core", "app")
  vouched = vouching(waivers)
  own = Entry("UART_Parity_t", "app/state.c", 376, "apply", "cast", "unsigned int", Values())
  assert vouched(own) and all(w.used for w in waivers)
  assert not vouched(replace(own, path="core/hal/uart.c"))

def a_project_cannot_silence_core():
  FILE.save("app/lint.yaml", "except:\n  heap-owner:\n    '*': modbus is not ours\n")
  waivers, _ = load_all_waivers("core", "app")
  assert len(keep([finding("heap-owner", "core/plc/com/modbus_master.c")], waivers)) == 1
