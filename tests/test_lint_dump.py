# tests/test_lint_dump.py

"""What cppcheck proves of real C, read back from its dump: switches, entries, calls, accesses."""

import xml.etree.ElementTree as ET
import pytest
from xaeian import FILE, PATH, file_context
from xaeian.cmd import run, which
from opencplc.lint.dump import Tokens, read_dump
from opencplc.utils import tools

CPPCHECK = which("cppcheck", f"{tools.bin_dir('cppcheck')}/cppcheck")
SOURCE = """#include <stdint.h>
#include <string.h>
typedef enum { OK = 0, ERR, BUSY } status_t;
typedef enum { MODE_Idle, MODE_Run, MODE_Stop = 5 } MODE_t;
typedef enum { CH_A, CH_B, CH_C, CH_D } CH_t;
typedef struct { MODE_t mode; uint8_t level; } CONFIG_t;
status_t send(const uint8_t *data, uint16_t len);
static CONFIG_t config;
static uint32_t ticks;
static int act(MODE_t mode)
{
  switch(mode) {
    case MODE_Idle: return 1;
    case MODE_Run: return 2;
    case MODE_Stop: return 3;
  }
  return 0;
}
int implicit(uint8_t raw) { MODE_t mode = raw; return act(mode); }
int validated(uint8_t raw)
{
  if(raw > MODE_Stop) return -1;
  return act((MODE_t)raw);
}
int copied(const uint8_t *data)
{
  memcpy(&config, data, sizeof(config));
  return act(config.mode);
}
void channels(void) { for(CH_t ch = CH_A; ch <= CH_C; ch++) send((const uint8_t *)"x", 1); }
int level(uint8_t raw)
{
  switch(raw & 3) {
    case 0: case 1: case 2: case 3: return 1;
  }
  return 0;
}
void TIM2_IRQHandler(void) { ticks++; }
uint32_t elapsed(void) { return ticks; }
typedef union { MODE_t mode; uint8_t raw; } BOTH_t;
typedef struct { uint16_t *output; uint8_t count; } MEASURE_t;
uint16_t PAGE_Load(const uint8_t *key, uint8_t *data);
uint16_t CONFIG_Load(CONFIG_t *loaded);
static BOTH_t both;
static MEASURE_t measure;
MODE_t give(uint8_t raw) { return raw; }
void loaded(void)
{
  PAGE_Load((const uint8_t *)&config, (uint8_t *)&config);
  CONFIG_Load(&config);
}
int compared(void)
{
  PAGE_Load(0, (uint8_t *)&config);
  if(config.mode > MODE_Stop) return -1;
  return act(config.mode);
}
void zeroed(void) { memset(&config, 0, sizeof(config)); }
void bytes(uint8_t value) { uint8_t *p = (uint8_t *)&config; p[0] = value; }
void united(uint8_t value) { both.raw = value; }
void named(void) { both.raw = MODE_Run; }
static void counted(uint8_t count) { measure.count = count; }
void element(uint16_t value) { measure.output[0] = value; counted(1); }
typedef enum { STEP_A, STEP_B, STEP_C } STEP_t;
void typed(const CONFIG_t *src) { memcpy(&config, src, sizeof(config)); }
STEP_t guarded(STEP_t e) { if(e < STEP_C) e++; return e; }
STEP_t wrapped(STEP_t e) { e = (e == STEP_C) ? STEP_A : (STEP_t)(e + 1); return e; }
STEP_t cycled(STEP_t e) { e = (STEP_t)((e + 1) % 3); return e; }
typedef enum { NZ_ONE = 1, NZ_TWO = 2 } NZ_t;
typedef struct { NZ_t kind; uint8_t level; } NZBOX_t;
static NZ_t bare;
static NZ_t given = NZ_TWO;
static NZ_t counted = 7;
static NZBOX_t box;
static NZBOX_t named = { .level = 3 };
static NZBOX_t listed = { NZ_TWO, 1 };
static NZ_t pair[3] = { NZ_ONE, NZ_TWO };
int started(void) { static NZ_t inner; return inner + bare + given + counted; }
void raw_enum(const uint8_t *bytes, uint8_t raw)
{
  memcpy(&bare, bytes, sizeof(bare));
  *(uint8_t *)&given = raw;
  memcpy(&counted, &given, sizeof(given));
}
"""

@pytest.fixture()
def facts(tmp_path):
  """Facts of `SOURCE` as `app.c`, read from the dump cppcheck writes beside it."""
  root = PATH.normalize(str(tmp_path))
  FILE.save(f"{root}/app.c", SOURCE)
  run([CPPCHECK, "--quiet", "--dump", "--std=c11", "--library=gnu", f"{root}/app.c"])
  with file_context(root_path=root):
    yield read_dump(f"{root}/app.c.dump", {f"{root}/app.c": "app.c"}, ("*_Load",))

@pytest.mark.skipif(CPPCHECK is None, reason="cppcheck required")
def switches_carry_the_type_of_their_condition(facts):
  assert facts.enums["MODE_t"] == {0, 1, 5}
  switches = {s.function: s for s in facts.switches}
  assert (switches["act"].enum, switches["act"].has_default) == ("MODE_t", False)
  # `raw & 3` is proven within the labels 0 to 3, so its `switch` needs no `default`
  assert switches["level"].enum == "" and switches["level"].values.within(switches["level"].cases)

@pytest.mark.skipif(CPPCHECK is None, reason="cppcheck required")
def integers_entering_an_enum_carry_what_cppcheck_proved(facts):
  entries = {(e.function, e.kind): e for e in facts.entries}
  assert entries[("implicit", "assignment")].values.high == 255
  assert entries[("implicit", "assignment")].param == ("implicit", 0)
  checked = entries[("validated", "cast")].values
  assert (checked.low, checked.high) == (0, 5)
  copy = entries[("copied", "memory")]
  assert (copy.enum, copy.source, copy.member) == ("MODE_t", "CONFIG_t", "mode")
  assert not copy.checked
  # The step of a loop bounded by `CH_C` stays inside `CH_t`
  assert entries[("channels", "arithmetic")].values.within(facts.enums["CH_t"])

@pytest.mark.skipif(CPPCHECK is None, reason="cppcheck required")
def statuses_left_unread_and_variables_shared_come_out(facts):
  # Every call left unread comes out with what it returns, the rule picks the status
  ignored = [(i.callee, i.returns, i.function) for i in facts.ignored]
  assert ("send", "status_t", "channels") in ignored and ("memcpy", "void *", "copied") in ignored
  ticks = {(a.function, a.write) for a in facts.accesses if a.name == "ticks"}
  assert {("TIM2_IRQHandler", True), ("elapsed", False)} <= ticks
  assert all(a.path == "app.c" for a in facts.accesses if a.name == "ticks")

@pytest.mark.skipif(CPPCHECK is None, reason="cppcheck required")
def returns_loads_raw_bytes_and_unions_enter_an_enum(facts):
  entries = {}
  for e in facts.entries: entries.setdefault((e.function, e.kind), []).append(e)
  given = entries[("give", "return")][0]
  assert (given.values.high, given.param) == (255, ("give", 0))
  # A loader writes through its byte parameter, never through a `const` one or a struct pointer
  assert [e.line for e in entries[("loaded", "memory")]] == [49]
  assert [e.checked for e in entries[("compared", "memory")]] == [True]
  assert entries[("zeroed", "memory")][0].values.known == {0}
  assert [(e.member, e.checked) for e in entries[("bytes", "memory")]] == [("mode", False)]
  united = entries[("united", "union")][0]
  assert (united.member, united.values.high) == ("mode", 255)
  assert entries[("named", "union")][0].values.known == {1}

@pytest.mark.skipif(CPPCHECK is None, reason="cppcheck required")
def an_element_behind_a_pointer_field_is_no_write_of_it_and_calls_come_out(facts):
  output = {(a.function, a.write) for a in facts.accesses if a.key == "MEASURE_t.output"}
  assert output == {("element", False)}
  assert ("app.c:counted", True) in {(a.function, a.write) for a in facts.accesses
    if a.key == "MEASURE_t.count"}
  assert ("element", "app.c:counted") in facts.calls

@pytest.mark.skipif(CPPCHECK is None, reason="cppcheck required")
def a_state_machine_stepping_its_own_enum_stays_closed(facts):
  # An expression of the enum entering holds one of its enumerators, the hypothesis of the proof
  steps = [e for e in facts.entries if e.enum == "STEP_t"]
  assert {e.function for e in steps} == {"guarded", "wrapped", "cycled"}
  assert all(e.values.within(facts.enums["STEP_t"]) for e in steps)
  # A copy from a struct of the same type brings typed values, no raw bytes
  assert not [e for e in facts.entries if e.function == "typed"]

def a_bound_written_as_an_unsigned_word_reads_signed():
  # Version 2.17 of cppcheck writes the impossible `-1` below an unsigned byte as `2**64 - 1`
  dump = ET.fromstring('''<dump>
    <token id="1" str="raw" values="2" valueType-type="char" valueType-sign="unsigned"/>
    <values id="2">
      <value intvalue="18446744073709551615" impossible="true" bound="Upper"/>
      <value intvalue="6" impossible="true" bound="Lower"/>
    </values>
  </dump>''')
  tokens = Tokens(dump)
  values = tokens.values_of(tokens.by_id["1"])
  assert (values.low, values.high) == (0, 5)

@pytest.mark.skipif(CPPCHECK is None, reason="cppcheck required")
def static_storage_starts_as_zero_where_no_initializer_reaches(facts):
  # An object of static storage holds zeros, a value an enum without a zero enumerator lacks
  zeros = sorted(e.source for e in facts.entries if e.kind == "initial" and e.enum == "NZ_t")
  assert zeros == ["bare", "box.kind", "inner", "named.kind", "pair[]"]
  assert all(e.values.known == {0} for e in facts.entries if e.kind == "initial")
  # A value of another type an initializer gives enters like an assignment
  assert [e.values.known for e in facts.entries
    if e.enum == "NZ_t" and e.kind == "assignment"] == [{7}]

@pytest.mark.skipif(CPPCHECK is None, reason="cppcheck required")
def raw_bytes_reach_an_enum_variable_as_they_reach_a_field(facts):
  raw = [(e.source, e.member) for e in facts.entries if e.function == "raw_enum"]
  # A copy from a variable of the same enum is a typed one
  assert sorted(raw) == [("bare", ""), ("given", "")]

