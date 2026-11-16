# tests/test_lint_values.py

"""Rules on types and proven values: a `switch` judged by its enum across the program."""

from dataclasses import replace
from xaeian import file_context
import pytest
from opencplc.lint.dump import Unit, Values, Argument, Ignored, Access
from opencplc.lint.values import merge, check_status, check_volatile
from conftest import value_switch as switch, value_entry as entry, value_found as found

MODE = frozenset({0, 1, 5}) # `MODE_Idle`, `MODE_Run`, `MODE_Stop = 5`

@pytest.fixture(autouse=True)
def workspace(tmp_path):
  """Paths of a test count from its own folder, as the paths of a build from the workspace."""
  with file_context(root_path=str(tmp_path)):
    yield

def a_closed_enum_needs_no_default():
  assert found(Unit({"MODE_t": MODE}, [switch()], [entry(Values(frozenset({1})))])) == []

def an_unchecked_entry_opens_the_enum_and_the_switch_reports_it():
  unit = Unit({"MODE_t": MODE}, [switch()], [entry(Values(frozenset(), 0, 255))])
  assert found(unit) == [("switch-enum", "`switch` over `MODE_t` has no `default`, "
    "and `MODE_t` takes `uint8_t` unchecked at frame.c:7")]

def an_empty_range_proves_nothing():
  # Crossed bounds say the flow lost its way, never that no value comes
  assert not Values(frozenset(), 5, 2).within(MODE)

def a_range_check_is_no_proof_when_the_enum_has_gaps():
  # `raw <= MODE_Stop` lets 2, 3 and 4 through, which no enumerator has
  checked = entry(Values(frozenset(), 0, 5))
  assert len(found(Unit({"MODE_t": MODE}, [switch()], [checked]))) == 1
  assert found(Unit({"MODE_t": frozenset(range(6))}, [switch()], [checked])) == []

def every_caller_proving_a_parameter_closes_the_enum():
  passed = entry(Values(frozenset(), 0, 255), param=("frame.c:parse", 0))
  callers = [
    Argument("frame.c:parse", 0, Values(frozenset({0}))),
    Argument("frame.c:parse", 0, Values(frozenset({5}))),
  ]
  assert found(Unit({"MODE_t": MODE}, [switch()], [passed], callers)) == []
  callers.append(Argument("frame.c:parse", 0, Values(frozenset(), 0, 9)))
  assert len(found(Unit({"MODE_t": MODE}, [switch()], [passed], callers))) == 1

def raw_bytes_need_a_comparison_of_the_field_afterwards():
  copied = Unit({"MODE_t": MODE}, [switch()], [entry(Values(), "memory")])
  assert "takes raw bytes into `uint8_t.mode`" in found(copied)[0][1]
  checked = Unit({"MODE_t": MODE}, [switch()], [entry(Values(), "memory", checked=True)])
  assert found(checked) == []

def a_union_member_beside_the_enum_brings_its_value_in():
  written = Unit({"MODE_t": MODE}, [switch()], [entry(Values(frozenset(), 0, 255), "union")])
  assert found(written) == [("switch-enum", "`switch` over `MODE_t` has no `default`, "
    "and `MODE_t` takes `uint8_t` written beside `mode` in a union at frame.c:7")]
  assert found(Unit({"MODE_t": MODE}, [switch()], [entry(Values(frozenset({1})), "union")])) == []

def raw_zeros_are_a_value_the_enum_has():
  zeroed = entry(Values(frozenset({0})), "memory")
  assert found(Unit({"MODE_t": MODE}, [switch()], [zeroed])) == []
  assert len(found(Unit({"MODE_t": frozenset({1, 5})}, [switch()], [zeroed]))) == 1

def a_zero_of_static_storage_opens_an_enum_without_a_zero_enumerator():
  zero = replace(entry(Values(frozenset({0})), "initial"), source="mode")
  assert found(Unit({"MODE_t": MODE}, [switch()], [zero])) == []
  assert found(Unit({"MODE_t": frozenset({1, 5})}, [switch()], [zero])) == [("switch-enum",
    "`switch` over `MODE_t` has no `default`, and `MODE_t` starts as `0` in `mode` at frame.c:7")]

def an_integer_switch_needs_a_default_only_when_turned_on():
  # A value without a label skips the `switch`, as C defines
  assert found(Unit({}, [switch("")], [])) == []
  assert found(Unit({}, [switch("")], []), opt_ins={"switch-default"}) == [
    ("switch-default", "`switch` over `uint8_t` has no `default`")]
  covered = switch("", cases=frozenset({0, 1, 2, 3}), values=Values(frozenset(), 0, 3))
  assert found(Unit({}, [covered], []), opt_ins={"switch-default"}) == []

def default_over_a_closed_enum_is_reported_only_when_turned_on():
  closed = Unit({"MODE_t": MODE}, [switch(default=True)], [])
  assert found(closed) == []
  assert [rule for rule, _ in found(closed, opt_ins={"switch-enum-default"})] == [
    "switch-enum-default"]
  opened = Unit({"MODE_t": MODE}, [switch(default=True)], [entry(Values(frozenset(), 0, 255))])
  assert found(opened, opt_ins={"switch-enum-default"}) == []

def an_ignored_status_is_reported_and_other_values_are_not():
  unit = Unit(ignored=[
    Ignored("send", "status_t", "app.c", 3, "loop"),
    Ignored("memcpy", "void *", "app.c", 4, "loop"),
  ])
  assert [(f.rule, f.line, f.function) for f in check_status(merge([unit]), "status_t")] == [
    ("status-used", 3, "loop")]

def a_variable_an_interrupt_writes_and_a_thread_reads_is_volatile():
  irq, thread = {"TIM2_IRQHandler"}, {"app.c:elapsed", "app.c:setup", "main"}
  reads = Access("app.c:ticks", "ticks", "app.c", 5, "app.c:elapsed", False, False)
  writes = Access("app.c:ticks", "ticks", "app.c", 5, "TIM2_IRQHandler", True, False)
  found_here = check_volatile(merge([Unit(accesses=[writes, reads])]), irq, thread)
  assert [(f.rule, f.path, f.line, f.function) for f in found_here] == [
    ("irq-volatile", "app.c", 5, "ticks")]
  volatile = [replace(a, volatile=True) for a in (writes, reads)]
  assert check_volatile(merge([Unit(accesses=volatile)]), irq, thread) == []
  # A write from a thread read by an interrupt is mostly a setting made before it starts
  setup = Access("app.c:ticks", "ticks", "app.c", 5, "app.c:setup", True, False)
  assert check_volatile(merge([Unit(accesses=[setup, reads])]), irq, thread) == []

def a_helper_gcc_inlined_into_an_interrupt_writes_for_it():
  irq, thread = {"TIM2_IRQHandler"}, {"app.c:elapsed", "main"}
  writes = Access("app.c:ticks", "ticks", "app.c", 5, "app.c:count", True, False)
  reads = Access("app.c:ticks", "ticks", "app.c", 5, "app.c:elapsed", False, False)
  unit = Unit(accesses=[writes, reads], calls=[("TIM2_IRQHandler", "app.c:count")])
  inlined = check_volatile(merge([unit]), irq, thread, irq | thread)
  assert [(f.rule, f.function) for f in inlined] == [("irq-volatile", "ticks")]
  # A helper the call graph holds runs where the graph says, here nowhere
  assert check_volatile(merge([unit]), irq, thread, irq | thread | {"app.c:count"}) == []
