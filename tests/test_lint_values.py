# tests/test_lint_values.py

"""Rules on types and proven values: a `switch` judged by its enum across the program."""

from dataclasses import replace
from xaeian import file_context
import pytest
from opencplc.lint.dump import Unit, Values, Argument, Ignored, Access, Literal
from opencplc.lint.values import merge, check_status, check_literals, check_volatile
from conftest import value_switch as switch, value_entry as entry, value_found as found

MODE = frozenset({0, 1, 5}) # `MODE_Idle`, `MODE_Run`, `MODE_Stop = 5`

@pytest.fixture(autouse=True)
def workspace(tmp_path):
  """Paths of a test count from its own folder, as the paths of a build from the workspace."""
  with file_context(root_path=str(tmp_path)):
    yield

def a_closed_enum_named_in_full_needs_no_default():
  assert found(Unit({"MODE_t": MODE}, [switch(cases=MODE)], [entry(Values(frozenset({1})))])) == []

def a_closed_enum_missing_a_case_needs_default():
  missing = switch(cases=frozenset({0, 1}))
  assert found(Unit({"MODE_t": MODE}, [missing], [])) == [("switch-default",
    "`switch` over `MODE_t` has no `case` for 1 of its values and no `default`")]
  assert found(Unit({"MODE_t": MODE}, [replace(missing, has_default=True)], [])) == []

def an_unchecked_entry_opens_the_enum_and_every_switch_over_it_needs_default():
  wide = entry(Values(frozenset(), 0, 255))
  assert found(Unit({"MODE_t": MODE}, [switch(cases=MODE)], [wide])) == [("switch-default",
    "`switch` over `MODE_t` has no `default`, while `MODE_t` takes `uint8_t` unchecked "
    "at frame.c:7")]
  assert found(Unit({"MODE_t": MODE}, [switch(default=True)], [wide])) == []

def an_empty_range_proves_nothing():
  # Crossed bounds say the flow lost its way, never that no value comes
  assert not Values(frozenset(), 5, 2).within(MODE)

def a_range_check_is_no_proof_when_the_enum_has_gaps():
  # `raw <= MODE_Stop` lets 2, 3 and 4 through, which no enumerator has
  checked = entry(Values(frozenset(), 0, 5))
  assert len(found(Unit({"MODE_t": MODE}, [switch(cases=MODE)], [checked]))) == 1
  every = frozenset(range(6))
  assert found(Unit({"MODE_t": every}, [switch(cases=every)], [checked])) == []

def every_caller_proving_a_parameter_closes_the_enum():
  passed = entry(Values(frozenset(), 0, 255), param=("frame.c:parse", 0))
  callers = [
    Argument("frame.c:parse", 0, Values(frozenset({0}))),
    Argument("frame.c:parse", 0, Values(frozenset({5}))),
  ]
  assert found(Unit({"MODE_t": MODE}, [switch(cases=MODE)], [passed], callers)) == []
  callers.append(Argument("frame.c:parse", 0, Values(frozenset(), 0, 9)))
  assert len(found(Unit({"MODE_t": MODE}, [switch(cases=MODE)], [passed], callers))) == 1

def raw_bytes_need_a_comparison_of_the_field_afterwards():
  copied = Unit({"MODE_t": MODE}, [switch(cases=MODE)], [entry(Values(), "memory")])
  assert "takes raw bytes into `uint8_t.mode`" in found(copied)[0][1]
  checked = Unit({"MODE_t": MODE}, [switch(cases=MODE)], [entry(Values(), "memory", checked=True)])
  assert found(checked) == []

def a_union_member_beside_the_enum_brings_its_value_in():
  written = Unit({"MODE_t": MODE}, [switch(cases=MODE)],
    [entry(Values(frozenset(), 0, 255), "union")])
  assert "takes `uint8_t` written beside `mode` in a union at frame.c:7" in found(written)[0][1]
  one = entry(Values(frozenset({1})), "union")
  assert found(Unit({"MODE_t": MODE}, [switch(cases=MODE)], [one])) == []

def raw_zeros_are_a_value_the_enum_has():
  zeroed = entry(Values(frozenset({0})), "memory")
  assert found(Unit({"MODE_t": MODE}, [switch(cases=MODE)], [zeroed])) == []
  gapped = frozenset({1, 5})
  assert len(found(Unit({"MODE_t": gapped}, [switch(cases=gapped)], [zeroed]))) == 1

def a_zero_of_static_storage_opens_an_enum_without_a_zero_enumerator():
  zero = replace(entry(Values(frozenset({0})), "initial"), source="mode")
  assert found(Unit({"MODE_t": MODE}, [switch(cases=MODE)], [zero])) == []
  gapped = frozenset({1, 5})
  opened = found(Unit({"MODE_t": gapped}, [switch(cases=gapped)], [zero]))
  assert "`MODE_t` starts as `0` in `mode` at frame.c:7" in opened[0][1]

def an_integer_switch_needs_a_default_unless_its_cases_cover_every_value():
  byte = Values(frozenset(), 0, 255) # a `uint8_t`, as its type bounds it
  assert found(Unit({}, [switch("", values=byte)], [])) == [("switch-default",
    "`switch` over `uint8_t` has no `default`, while its cases leave values out")]
  assert found(Unit({}, [switch("", cases=frozenset(range(256)), values=byte)], [])) == []
  masked = switch("", cases=frozenset({0, 1, 2, 3}), values=Values(frozenset(), 0, 3))
  assert found(Unit({}, [masked], [])) == []

def an_ignored_status_is_reported_and_other_values_are_not():
  unit = Unit(ignored=[
    Ignored("send", "status_t", "app.c", 3, "loop"),
    Ignored("memcpy", "void *", "app.c", 4, "loop"),
  ])
  assert [(f.rule, f.line, f.function) for f in check_status(merge([unit]), "status_t")] == [
    ("status-used", 3, "loop")]

def a_double_constant_in_float_math_is_reported_once_however_many_units_see_it():
  # A header seen by two units gives its place once
  literal = Literal("0.5", "ctl.h", 7, 18, "limit")
  reported = check_literals(merge([Unit(literals=[literal]), Unit(literals=[literal])]))
  assert [(f.rule, f.line, f.col, f.function) for f in reported] == [
    ("float-literal", 7, 18, "limit")]
  assert "`0.5` without `f`" in reported[0].message and "MISRA 10.7" in reported[0].refs

def a_variable_an_interrupt_writes_and_a_thread_polls_is_volatile():
  irq, thread = {"TIM2_IRQHandler"}, {"app.c:elapsed", "app.c:setup", "main"}
  reads = Access("app.c:ticks", "ticks", "app.c", 5, "app.c:elapsed", False, True, False,
    polled=True)
  writes = Access("app.c:ticks", "ticks", "app.c", 5, "TIM2_IRQHandler", True, False, False)
  found_here = check_volatile(merge([Unit(accesses=[writes, reads])]), irq, thread)
  assert [(f.rule, f.path, f.line, f.function) for f in found_here] == [
    ("irq-volatile", "app.c", 5, "ticks")]
  volatile = [replace(a, volatile=True) for a in (writes, reads)]
  assert check_volatile(merge([Unit(accesses=volatile)]), irq, thread) == []
  # A write from a thread read by an interrupt is mostly a setting made before it starts
  setup = Access("app.c:ticks", "ticks", "app.c", 5, "app.c:setup", True, False, False)
  assert check_volatile(merge([Unit(accesses=[setup, reads])]), irq, thread) == []

def only_polling_asks_for_volatile():
  irq, thread = {"TIM2_IRQHandler"}, {"app.c:reset", "app.c:harvest", "app.c:once"}
  writes = Access("app.c:ticks", "ticks", "app.c", 5, "TIM2_IRQHandler", True, False, False)
  # A value handed over by a flag is read once a call, and a call reloads it anyway
  once = Access("app.c:ticks", "ticks", "app.c", 5, "app.c:once", False, True, False)
  # Zeroing wants exclusion rather than `volatile`, and a read with interrupts masked is fresh
  reset = Access("app.c:ticks", "ticks", "app.c", 5, "app.c:reset", True, False, False)
  harvest = replace(once, function="app.c:harvest", guarded=True, polled=True)
  assert check_volatile(merge([Unit(accesses=[writes, once, reset, harvest])]), irq, thread) == []
  # `+=` in a loop with no barrier polls as well
  added = replace(reset, read=True, polled=True)
  assert len(check_volatile(merge([Unit(accesses=[writes, added])]), irq, thread)) == 1

def a_helper_gcc_inlined_into_an_interrupt_writes_for_it():
  irq, thread = {"TIM2_IRQHandler"}, {"app.c:elapsed", "main"}
  writes = Access("app.c:ticks", "ticks", "app.c", 5, "app.c:count", True, False, False)
  reads = Access("app.c:ticks", "ticks", "app.c", 5, "app.c:elapsed", False, True, False,
    polled=True)
  unit = Unit(accesses=[writes, reads], calls=[("TIM2_IRQHandler", "app.c:count")])
  inlined = check_volatile(merge([unit]), irq, thread, irq | thread)
  assert [(f.rule, f.function) for f in inlined] == [("irq-volatile", "ticks")]
  # A helper the call graph holds runs where the graph says, here nowhere
  assert check_volatile(merge([unit]), irq, thread, irq | thread | {"app.c:count"}) == []
