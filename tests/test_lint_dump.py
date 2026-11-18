# tests/test_lint_dump.py

"""What cppcheck proves of real C, read back from its dump: switches, entries, calls, accesses."""

import os
import xml.etree.ElementTree as ET
import pytest
from xaeian import FILE, PATH, file_context
from xaeian.cmd import run, which
from opencplc.lint.dump import Tokens, read_dump
from opencplc.lint.checkers import CPPCHECK_MIN, Unit as Build, run_cppcheck, too_old
from opencplc.lint.command import read_unit, without_vendor
from opencplc.utils import tools

# Found as `make lint` finds it: the Forge package on Windows, where PATH plays no part
CPPCHECK = which(f"{tools.bin_dir('cppcheck')}/cppcheck" if tools.WINDOWS else "cppcheck")
USABLE = bool(CPPCHECK) and not too_old(CPPCHECK, CPPCHECK_MIN)
ARM_BIN = tools.bin_dir("arm-gcc")
GCC = which("arm-none-eabi-gcc", f"{ARM_BIN}/arm-none-eabi-gcc")
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
void __disable_irq(void);
void __enable_irq(void);
uint32_t harvest(void)
{
  __disable_irq();
  uint32_t taken = ticks;
  ticks = 0;
  __enable_irq();
  return taken + ticks;
}
typedef struct { uint32_t seq; int16_t id; } SNAP_t;
static SNAP_t *snap_at;
int16_t snapped(void)
{
  volatile SNAP_t *src = snap_at;
  SNAP_t copy;
  do { copy = *src; } while(copy.seq != src->seq);
  return copy.id;
}
typedef volatile struct { uint8_t arr[4]; uint16_t level; } VS_t;
static VS_t vs;
uint16_t vs_read(void) { return vs.level + vs.arr[1]; }
static struct { uint8_t n; } one;
uint8_t one_n(void) { return one.n; }
void one_point(uint8_t **at) { *at = &one.n; }
typedef enum { PAR_None = 0, PAR_Odd = 1, PAR_Even = 2 } PAR_t;
typedef struct { PAR_t parity; } LINE_t;
static LINE_t wire;
uint32_t stored(void);
void framing(void)
{
  wire.parity = (PAR_t)stored();
  if(wire.parity > PAR_Even) wire.parity = PAR_None;
}
PAR_t unclamped(void) { PAR_t p = (PAR_t)stored(); return p; }
void let(void);
static uint8_t done;
static uint8_t ready(void) { return done; }
void waits(void) { while(!done) {} }
void yields(void) { while(!done) let(); }
void asks(void) { while(!ready()) {} }
uint8_t once(void) { return done; }
void later(void) { do {} while(!done); }
static MODE_t machine;
void stepper(void)
{
  switch(machine) {
    case MODE_Idle: machine = MODE_Run; break;
    case MODE_Run: machine = MODE_Stop; break;
    case MODE_Stop: break;
  }
}
void dropped(void) { (void)send((const uint8_t *)"x", 1); }
int half_over(float x) { return x > 0.5; }
float third_of(float x) { return x * (1.0 / 3.0); }
int below_half(float x) { return x < -0.5; }
float scaled_f(float x) { return x * 2.0f; }
double doubled(double d) { return d * 2.0; }
void halved(float *x) { *x *= 0.5; }
float initial(void) { float y = 2.0; return y; }
"""

@pytest.fixture()
def facts(tmp_path):
  """Facts of `SOURCE` as `app.c`, read from the dump cppcheck writes beside it."""
  if not USABLE: pytest.skip(f"cppcheck {'.'.join(map(str, CPPCHECK_MIN))} or newer required")
  root = PATH.normalize(str(tmp_path))
  FILE.save(f"{root}/app.c", SOURCE)
  done = run([CPPCHECK, "--quiet", "--dump", "--std=c11", "--library=gnu", f"{root}/app.c"])
  assert FILE.exists(f"{root}/app.c.dump"), done.stderr + done.stdout
  with file_context(root_path=root):
    yield read_dump(f"{root}/app.c.dump", {f"{root}/app.c": "app.c"}, ("*_Load",))

def switches_carry_the_type_of_their_condition(facts):
  assert facts.enums["MODE_t"] == {0, 1, 5}
  switches = {s.function: s for s in facts.switches}
  assert (switches["act"].enum, switches["act"].has_default) == ("MODE_t", False)
  # `raw & 3` is proven within the labels 0 to 3, so its `switch` needs no `default`
  assert switches["level"].enum == "" and switches["level"].values.within(switches["level"].cases)

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

def statuses_left_unread_and_variables_shared_come_out(facts):
  # Every call left unread comes out with what it returns, the rule picks the status
  ignored = [(i.callee, i.returns, i.function) for i in facts.ignored]
  assert ("send", "status_t", "channels") in ignored and ("memcpy", "void *", "copied") in ignored
  # A cast to `void` drops the value on purpose
  assert not [call for call in ignored if call[2] == "dropped"]
  ticks = {(a.function, a.write) for a in facts.accesses if a.name == "ticks"}
  assert {("TIM2_IRQHandler", True), ("elapsed", False)} <= ticks
  assert all(a.path == "app.c" for a in facts.accesses if a.name == "ticks")

def a_float_meeting_a_double_constant_comes_out(facts):
  # The constant is the slip: a `double` variable, a literal with `f` or one assigned pass
  assert {(l.text, l.function) for l in facts.literals} == {
    ("0.5", "half_over"), ("1.0", "third_of"), ("-0.5", "below_half"), ("0.5", "halved"),
  }

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

def a_read_masked_or_through_volatile_is_guarded_and_a_local_copy_shares_nothing(facts):
  harvest = {(a.write, a.read, a.guarded) for a in facts.accesses
    if a.name == "ticks" and a.function == "harvest"}
  # Between `__disable_irq()` and `__enable_irq()` guarded, past them bare; `=` only writes
  assert harvest == {(False, True, True), (True, False, True), (False, True, False)}
  # `src->seq` reads through a pointer to `volatile`, while `copy` is a local copy
  assert {(a.function, a.read, a.guarded) for a in facts.accesses
    if a.key in ("SNAP_t.seq", "SNAP_t.id")} == {("snapped", True, True)}

def a_volatile_type_guards_its_fields_and_the_elements_of_their_arrays(facts):
  # A `typedef volatile struct` makes every field `volatile` where it is read, an array one too
  assert {(a.name, a.read, a.guarded) for a in facts.accesses
    if a.function == "vs_read" and a.name in ("level", "arr")} == {
    ("level", True, True), ("arr", True, True)}

def a_field_of_an_unnamed_struct_goes_by_its_declaration_and_an_address_reads_nothing(facts):
  # Unnamed structs are numbered unit by unit, so `Anonymous0` would gather other files
  line = SOURCE.splitlines().index("static struct { uint8_t n; } one;") + 1
  assert {(a.function, a.key) for a in facts.accesses if a.name == "n"
    and a.function in ("one_n", "one_point")} == {("one_n", f"app.c:{line}:n")}

def a_loop_with_no_barrier_polls_what_it_reads(facts):
  # A call into another unit reloads every variable, and one read a call is fresh anyway
  polled = {(a.function, a.polled) for a in facts.accesses if a.name == "done" and a.read}
  assert polled == {("waits", True), ("yields", False), ("app.c:ready", True), ("once", False),
    ("later", True)}

def a_clamp_right_after_the_conversion_closes_the_enum(facts):
  parity = {e.function: e for e in facts.entries if e.enum == "PAR_t"}
  assert parity["framing"].values.within(facts.enums["PAR_t"])
  assert not parity["unclamped"].values.within(facts.enums["PAR_t"])

def an_element_behind_a_pointer_field_is_no_write_of_it_and_calls_come_out(facts):
  output = {(a.function, a.write) for a in facts.accesses if a.key == "MEASURE_t.output"}
  assert output == {("element", False)}
  assert ("app.c:counted", True) in {(a.function, a.write) for a in facts.accesses
    if a.key == "MEASURE_t.count"}
  assert ("element", "app.c:counted") in facts.calls

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

def static_storage_starts_as_zero_where_no_initializer_reaches(facts):
  # An object of static storage holds zeros, a value an enum without a zero enumerator lacks
  zeros = sorted(e.source for e in facts.entries if e.kind == "initial" and e.enum == "NZ_t")
  assert zeros == ["bare", "box.kind", "inner", "named.kind", "pair[]"]
  assert all(e.values.known == {0} for e in facts.entries if e.kind == "initial")
  # A value of another type an initializer gives enters like an assignment
  assert [e.values.known for e in facts.entries
    if e.enum == "NZ_t" and e.kind == "assignment"] == [{7}]

def raw_bytes_reach_an_enum_variable_as_they_reach_a_field(facts):
  raw = [(e.source, e.member) for e in facts.entries if e.function == "raw_enum"]
  # A copy from a variable of the same enum is a typed one
  assert sorted(raw) == [("bare", ""), ("given", "")]

def a_dump_without_a_configuration_reads_as_none(tmp_path):
  # All cppcheck leaves of a source an `#error` or an unknown macro stopped: its raw tokens
  path = f"{PATH.normalize(str(tmp_path))}/app.c.dump"
  FILE.save(path, '<dumps><rawtokens><tok str="send"/></rawtokens></dumps>')
  assert read_dump(path) is None

@pytest.mark.skipif(not USABLE or GCC is None, reason="cppcheck and arm-none-eabi-gcc required")
def a_source_cppcheck_stops_on_goes_again_with_every_path(tmp_path, monkeypatch):
  root = PATH.normalize(str(tmp_path))
  paths = [os.path.dirname(CPPCHECK), ARM_BIN, os.environ.get("PATH", "")]
  monkeypatch.setenv("PATH", os.pathsep.join(paths))
  # A nanopb message checks the version `pb.h` gives, which the path without `lib` lacks
  FILE.save(f"{root}/lib/pb.h", "#define PB_PROTO_HEADER_VERSION 40\n")
  FILE.save(f"{root}/app/msg.h", "#include <pb.h>\n#if PB_PROTO_HEADER_VERSION != 40\n"
    "#error Regenerate this file\n#endif\ntypedef enum { OK = 0, ERR } status_t;\n"
    "status_t send(void);\n")
  FILE.save(f"{root}/app/main.c", '#include "msg.h"\nvoid loop(void) { send(); }\n')
  FILE.save(f"{root}/app/broken.c", "#error Every path stops here\n")
  sources = [f"{root}/app/main.c", f"{root}/app/broken.c"]
  unit = Build("app", "-mcpu=cortex-m0plus -mthumb", sources, [], [f"{root}/app", f"{root}/lib"])
  vendor = [(root, "lib/")]
  with file_context(root_path=root):
    # Facts asked or not, as for a bootloader: the dump tells what cppcheck left unread
    narrow = run_cppcheck(without_vendor(unit, vendor), f"{root}/lint")
    found, _, facts, unread = read_unit(unit, vendor, f"{root}/lint", True, ())
  assert narrow[3] == sources # without `lib` neither source is read
  assert [(i.callee, i.function) for f in facts for i in f.ignored] == [("send", "loop")]
  assert unread == [f"{root}/app/broken.c"]
  # The stop of the narrow path goes, the one every path gives stays
  assert [(f.rule, f.path) for f in found] == [("preprocessorErrorDirective", "app/broken.c")]

