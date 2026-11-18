# opencplc/lint/dump.py

"""
What cppcheck knows of one translation unit, read from its `--dump`: types and proven values.

gcc drops a conversion from an integer to a short enum before any dump of its own shows it,
and cppcheck keeps the type of every expression with the values its flow analysis proved.
Only the facts the rules need leave this module, so a dump of megabytes ends as a few lists.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, replace
from fnmatch import fnmatchcase
from xaeian import FILE

# Value range a type of `valueType-type` holds by itself, by sign
TYPE_RANGE = {
  ("bool", ""): (0, 1),
  ("char", "unsigned"): (0, 0xFF), ("char", "signed"): (-0x80, 0x7F),
  ("short", "unsigned"): (0, 0xFFFF), ("short", "signed"): (-0x8000, 0x7FFF),
}
RAW_COPIES = {"memcpy": 0, "memmove": 0, "memset": 0} # destination of each by argument index
# CMSIS calls that mask interrupts, and those that end it, a restored `PRIMASK` among them
MASKING = {
  "__disable_irq": True, "__disable_fault_irq": True,
  "__enable_irq": False, "__enable_fault_irq": False, "__set_PRIMASK": False,
}
KEYWORDS = {"if", "while", "for", "switch", "return", "sizeof", "do"} # a `(` after them is no call
ASM = {"asm", "__asm", "__asm__"} # a barrier the compiler keeps, whatever it holds
SHARED = ("Global", "Namespace", "Public") # a variable of the file, or a field of a struct
NESTING = 4 # levels of structs in a struct whose enum fields raw bytes reach

@dataclass(frozen=True)
class Values:
  """What cppcheck proved of an expression: exact values, or bounds, or nothing."""
  known: frozenset[int] = frozenset()
  low: int|None = None
  high: int|None = None

  def within(self, allowed:frozenset[int]) -> bool:
    """
    Every value it may take is in `allowed`.

    A range wider than 4096 counts as unproven, and so does an empty one:
    bounds that cross say the flow analysis lost its way, not that no value comes.
    """
    if self.known: return self.known <= allowed
    if self.low is None or self.high is None: return False
    if self.high < self.low or self.high - self.low > 4096: return False
    return all(value in allowed for value in range(self.low, self.high + 1))

@dataclass(frozen=True)
class Switch:
  """A `switch` of a function: the type steering it and whether it has `default`."""
  path: str
  line: int
  function: str
  enum: str              # enum type of the condition, "" for an integer
  source: str            # type of the condition as written, for a message
  has_default: bool
  cases: frozenset[int]  # labels with a proven value
  values: Values         # of the condition, its type bounding an integer

@dataclass(frozen=True)
class Entry:
  """A place where a value of another type becomes a value of an enum."""
  enum: str
  path: str
  line: int
  function: str
  # `assignment`, `arithmetic`, `cast`, `argument`, `return`,
  # `initial` for a zero of static storage, `memory` for raw bytes over an object,
  # `union` for another member of a union
  kind: str
  source: str                         # type it came from
  values: Values
  param: tuple[str, int]|None = None  # callee key and argument of a parameter passed on
  member: str = ""                    # enum field the bytes land in, `memory` and `union` only
  checked: bool = False               # that field compared afterwards in the same function

@dataclass(frozen=True)
class Argument:
  """Value one call passes as one argument, for a check made by the caller."""
  callee: str # function key: `path:name` for a static one, `name` otherwise
  index: int
  values: Values

@dataclass(frozen=True)
class Ignored:
  """A call whose returned value nobody reads, with the type of that value."""
  callee: str
  returns: str
  path: str
  line: int
  function: str

@dataclass(frozen=True)
class Access:
  """One function reading or writing one variable that outlives a call."""
  key: str        # `name`, `path:name` for a static one, `Struct.field` for a field
  name: str
  path: str       # of the declaration
  line: int
  function: str   # key of the function, as for `Argument`
  write: bool     # by an assignment, `++` or `--`
  read: bool      # by anything but a plain `=`, which only writes
  volatile: bool  # as declared
  # Read with interrupts masked or through a pointer to `volatile`, fresh either way
  guarded: bool = False
  # Read again and again by a loop with no barrier, where a value kept in a register would do
  polled: bool = False

@dataclass(frozen=True)
class Literal:
  """A `double` constant a `float` operand meets, which takes their math to `double`."""
  text: str # its first literal, as written
  path: str
  line: int
  column: int
  function: str

@dataclass
class Unit:
  """Facts of one translation unit."""
  enums: dict[str, frozenset[int]] = field(default_factory=dict)
  switches: list[Switch] = field(default_factory=list)
  entries: list[Entry] = field(default_factory=list)
  arguments: list[Argument] = field(default_factory=list)
  ignored: list[Ignored] = field(default_factory=list)
  accesses: list[Access] = field(default_factory=list)
  literals: list[Literal] = field(default_factory=list)
  # Caller and callee key of each call the source makes, one gcc inlines included
  calls: list[tuple[str, str]] = field(default_factory=list)

#--------------------------------------------------------------------------------------------- Read

class Tokens:
  """The token list of a dump, with scopes, functions, variables and values by id."""
  def __init__(self, config:ET.Element):
    self.order = list(config.iter("token"))
    self.by_id = {t.get("id"): t for t in self.order}
    self.index = {t.get("id"): i for i, t in enumerate(self.order)}
    self.scopes = {s.get("id"): s for s in config.iter("scope")}
    self.functions = {f.get("id"): f for f in config.iter("function")}
    self.variables = {v.get("id"): v for v in config.iter("var") if v.get("nameToken")}
    self.values = {v.get("id"): list(v) for v in config.iter("values")}
    self.enums:dict[str, frozenset[int]] = {} # enumerators by enum, once `collect_enums` ran
    self.members = {} # variables of each scope, the fields of a struct among them
    for variable in self.variables.values():
      self.members.setdefault(variable.get("scope"), []).append(variable)
    # Function scope each scope lies in, found once rather than for every token
    self.owner = {}
    for scope_id in self.scopes:
      scope = self.scopes[scope_id]
      while scope is not None and scope.get("type") != "Function":
        scope = self.scopes.get(scope.get("nestedIn"))
      self.owner[scope_id] = scope
    # Body of each function this unit defines, by function id; one only declared has none
    self.bodies = {s.get("function"): s for s in self.scopes.values()
      if s.get("type") == "Function" and s.get("function")}
    self.barriers:dict[str, bool] = {} # by function scope, once `barrier` looked inside it

  def get(self, token:ET.Element|None, name:str) -> ET.Element|None:
    """Token an attribute of `token` points at."""
    return self.by_id.get(token.get(name)) if token is not None else None

  def next(self, token:ET.Element, step:int=1) -> ET.Element|None:
    """Token `step` places on in the list."""
    position = self.index[token.get("id")] + step
    return self.order[position] if 0 <= position < len(self.order) else None

  def enum_of(self, token:ET.Element|None) -> str:
    """Enum type of an expression, "" for any other type, a pointer to an enum included."""
    if token is None or token.get("valueType-pointer", "0") != "0": return ""
    scope = self.scopes.get(token.get("valueType-typeScope") or "")
    return scope.get("className") if scope is not None and scope.get("type") == "Enum" else ""

  def record_of(self, token:ET.Element|None) -> ET.Element|None:
    """Struct scope of an expression whose type is a struct or a pointer to one."""
    scope = self.type_scope(token)
    return scope if scope is not None and scope.get("type") in ("Struct", "Union") else None

  def type_scope(self, token:ET.Element|None) -> ET.Element|None:
    """Struct, union or enum scope of the type of an expression, a pointer to one included."""
    scope = self.scopes.get(token.get("valueType-typeScope") or "") if token is not None else None
    if scope is None or scope.get("type") not in ("Struct", "Union", "Enum"): return None
    return scope

  def function_of(self, token:ET.Element) -> ET.Element|None:
    """Function scope a token stands in."""
    return self.owner.get(token.get("scope"))

  def values_of(self, token:ET.Element, assume:str="") -> Values:
    """
    Proven values of an expression, its type bounding them when the flow says nothing.

    `assume` is the enum the value enters, and an expression of that enum holds one of its
    enumerators: the hypothesis a closed enum is proven by, entry by entry.
    A step by a constant and a remainder by one are followed from there.
    """
    known, low, high, excluded = set(), None, None, set()
    for value in self.values.get(token.get("values") or "", []):
      if value.get("intvalue") is None: continue
      number = signed(int(value.get("intvalue")))
      if value.get("impossible") == "true":
        # An impossible upper bound `x` leaves values above it, a lower one values below it
        bound = value.get("bound")
        if bound == "Upper": low = number + 1 if low is None else max(low, number + 1)
        elif bound == "Lower": high = number - 1 if high is None else min(high, number - 1)
        else: excluded.add(number)
      elif value.get("known") == "true":
        known.add(number)
    if known: return Values(frozenset(known))
    if assume and self.enum_of(token) == assume:
      return narrowed(Values(self.enums.get(assume, frozenset())), low, high, excluded)
    if (stepped := self.arithmetic(token, assume)) is not None:
      return narrowed(stepped, low, high, excluded)
    if token.get("str") == "&":
      # A mask keeps the value between zero and itself
      for side in (self.get(token, "astOperand1"), self.get(token, "astOperand2")):
        mask = self.values_of(side).known if side is not None else frozenset()
        if len(mask) == 1 and min(mask) >= 0:
          low = 0 if low is None else max(low, 0)
          high = min(mask) if high is None else min(high, min(mask))
    bounds = TYPE_RANGE.get((token.get("valueType-type"), token.get("valueType-sign") or ""))
    if bounds:
      low = bounds[0] if low is None else max(low, bounds[0])
      high = bounds[1] if high is None else min(high, bounds[1])
    return Values(frozenset(), low, high)

  def arithmetic(self, token:ET.Element, assume:str) -> Values|None:
    """Values of `x + c`, `x - c` or `x % c` with a constant `c`, `None` for anything else."""
    text = token.get("str")
    left, right = self.get(token, "astOperand1"), self.get(token, "astOperand2")
    if text not in ("+", "-", "%") or left is None or right is None: return None
    constant = self.values_of(right).known
    if text == "+" and len(constant) != 1:
      left, right = right, left
      constant = self.values_of(right).known
    if len(constant) != 1: return None
    step, base = min(constant), self.values_of(left, assume)
    if text != "%": return shifted(base, step if text == "+" else -step)
    if step <= 0: return None
    if base.known: return Values(frozenset(remainder(v, step) for v in base.known))
    if base.low is not None and base.low >= 0: return Values(frozenset(), 0, step - 1)
    return Values(frozenset(), 1 - step, step - 1)

def signed(number:int) -> int:
  """A value cppcheck wrote as an unsigned 64-bit word, as cppcheck 2.17 writes `-1`."""
  return number - (1 << 64) if number >= 1 << 63 else number

def remainder(value:int, divisor:int) -> int:
  """`value % divisor` as C takes it, the sign of the remainder following `value`."""
  return abs(value) % divisor * (1 if value >= 0 else -1)

def narrowed(values:Values, low:int|None, high:int|None, excluded:set[int]) -> Values:
  """`values` without what the bounds and the excluded points of the flow rule out."""
  if values.known:
    kept = {v for v in values.known if v not in excluded
      and (low is None or v >= low) and (high is None or v <= high)}
    return Values(frozenset(kept)) if kept else Values()
  low = values.low if low is None else low if values.low is None else max(low, values.low)
  high = values.high if high is None else high if values.high is None else min(high, values.high)
  while low is not None and low in excluded: low += 1
  while high is not None and high in excluded: high -= 1
  return Values(frozenset(), low, high)

def loop_bounded(
  tokens:Tokens, step:ET.Element, counter:ET.Element|None,
  assume:str = "",
) -> Values|None:
  """
  Values of the counter of a `for` before its step, held by the condition of that loop.

  The step of `for(ch = CH_A; ch <= CH_C; ch++)` starts from `CH_C` at most;
  `None` for a step outside a `for`, or a condition other than the counter against a constant.
  """
  inner = tokens.get(step, "astParent")
  outer = tokens.get(inner, "astParent") if inner is not None else None
  opener = tokens.get(outer, "astParent") if outer is not None else None
  keyword = tokens.get(opener, "astOperand1") if opener is not None else None
  if counter is None or keyword is None or keyword.get("str") != "for": return None
  condition = tokens.get(inner, "astOperand1")
  if condition is None or condition.get("isComparisonOp") != "true": return None
  left, right = tokens.get(condition, "astOperand1"), tokens.get(condition, "astOperand2")
  if left is None or right is None or left.get("varId") != counter.get("varId"): return None
  limit = tokens.values_of(right).known
  if len(limit) != 1: return None
  edge, base = min(limit), tokens.values_of(counter, assume)
  low = min(base.known) if base.known else base.low
  high = max(base.known) if base.known else base.high
  bounds = {"<": (low, edge - 1), "<=": (low, edge),
    ">": (edge + 1, high), ">=": (edge, high)}.get(condition.get("str"))
  return Values(frozenset(), *bounds) if bounds else None

def shifted(values:Values, step:int) -> Values:
  """`values` moved by `step`, what `++` or `--` leaves of them."""
  move = lambda bound: None if bound is None else bound + step
  return Values(frozenset(v + step for v in values.known), move(values.low), move(values.high))

def type_text(token:ET.Element|None) -> str:
  """Type of an expression as a message names it: `uint8_t` over `unsigned char`."""
  if token is None: return "?"
  if token.get("valueType-originalTypeName"): return token.get("valueType-originalTypeName")
  sign = token.get("valueType-sign")
  return f"{sign} {token.get('valueType-type')}" if sign else token.get("valueType-type") or "?"

def function_key(tokens:Tokens, function:ET.Element|None, path:str) -> str:
  """Key of a function across units: `path:name` for a static one, where it is defined."""
  if function is None: return ""
  name = function.get("name")
  if function.get("isStatic") != "true": return name
  where = tokens.by_id.get(function.get("token") or function.get("tokenDef"))
  return f"{where.get('file') if where is not None else path}:{name}"

def owner_key(tokens:Tokens, token:ET.Element) -> str:
  """Key of the function `token` stands in, "" outside any."""
  scope = tokens.function_of(token)
  owner = tokens.functions.get(scope.get("function") or "") if scope is not None else None
  return function_key(tokens, owner, token.get("file"))

def listed(tokens:Tokens, top:ET.Element|None) -> list[ET.Element]:
  """Expressions of a comma list whose topmost `,` is `top`, in order."""
  found = []
  while top is not None and top.get("str") == ",":
    found.append(tokens.get(top, "astOperand2"))
    top = tokens.get(top, "astOperand1")
  if top is not None: found.append(top)
  return found[::-1]

def arguments(tokens:Tokens, call:ET.Element) -> list[ET.Element]:
  """Argument expressions of the call opened by the `(` token `call`, in order."""
  return listed(tokens, tokens.get(call, "astOperand2"))

def unwrap(tokens:Tokens, token:ET.Element|None) -> ET.Element|None:
  """Expression under casts, so `(uint8_t *)&config` reads as `&config`."""
  while token is not None and token.get("isCast") == "true":
    token = tokens.get(token, "astOperand1")
  return token

def path_of(tokens:Tokens, token:ET.Element|None) -> str:
  """An object named through its fields, `<variable id>.inner`, "" for any other expression."""
  if token is None: return ""
  if token.get("variable"): return token.get("variable")
  if token.get("str") not in (".", "->"): return ""
  owner, name = path_of(tokens, tokens.get(token, "astOperand1")), tokens.get(token, "astOperand2")
  return f"{owner}.{name.get('str')}" if owner and name is not None else ""

def enum_fields(tokens:Tokens, record:ET.Element, depth:int=NESTING) -> list[tuple[str, str]]:
  """Enum of each field of `record` with its path, `inner.mode`, nested structs included."""
  found = []
  for variable in tokens.members.get(record.get("id"), []):
    name_token = tokens.by_id.get(variable.get("nameToken"))
    if name_token is None or variable.get("isPointer") == "true": continue
    name = name_token.get("str")
    inner = tokens.record_of(name_token)
    if enum := tokens.enum_of(name_token): found.append((enum, name))
    elif inner is not None and depth:
      found += [(enum, f"{name}.{path}") for enum, path in enum_fields(tokens, inner, depth - 1)]
  return found

#------------------------------------------------------------------------------------------ Collect

def collect_enums(tokens:Tokens, unit:Unit):
  """Enumerators of every enum the unit sees, by the type name, from their proven values."""
  enums = {i: s.get("className") for i, s in tokens.scopes.items()
    if s.get("type") == "Enum" and s.get("className")}
  members = {name: set() for name in enums.values()}
  for token in tokens.order:
    name = enums.get(token.get("scope"))
    if name is None or not token.get("str", "").isidentifier(): continue
    values = tokens.values_of(token)
    if len(values.known) == 1: members[name] |= values.known
  unit.enums |= {name: frozenset(values) for name, values in members.items()}
  tokens.enums = unit.enums

def collect_switches(tokens:Tokens, unit:Unit):
  """Each `switch`, its condition typed, its `default` looked up in its own scope."""
  defaults, cases = set(), {}
  for token in tokens.order:
    text = token.get("str")
    if text == "default": defaults.add(token.get("scope"))
    elif text == "case":
      label = tokens.get(token, "astOperand1")
      known = tokens.values_of(label).known if label is not None else frozenset()
      cases.setdefault(token.get("scope"), set()).update(known)
  for scope_id, scope in tokens.scopes.items():
    if scope.get("type") != "Switch": continue
    brace = tokens.by_id.get(scope.get("bodyStart"))
    close = tokens.next(brace, -1) if brace is not None else None
    opener = tokens.get(close, "link")
    keyword = tokens.next(opener, -1) if opener is not None else None
    if keyword is None or keyword.get("str") != "switch": continue
    # An element without children is false, so every test of one compares with `None`
    condition = tokens.get(opener, "astOperand2")
    function = tokens.function_of(keyword)
    unit.switches.append(Switch(keyword.get("file"), int(keyword.get("linenr")),
      function.get("className") if function is not None else "", tokens.enum_of(condition),
      type_text(condition), scope_id in defaults, frozenset(cases.get(scope_id, ())),
      tokens.values_of(condition) if condition is not None else Values()))

def collect_entries(tokens:Tokens, unit:Unit, loads:tuple[str, ...]=()):
  """
  Every place a value of another type becomes a value of an enum, and the calls.

  `loads` are globs of functions writing raw bytes into the buffer a caller gives them.
  """
  aliases = {} # byte pointers holding the address of a struct, by variable
  for token in tokens.order:
    function = tokens.function_of(token)
    if function is None: continue
    where = (token.get("file"), int(token.get("linenr")), function.get("className"))
    text, operand = token.get("str"), tokens.get(token, "astOperand1")
    assigns = token.get("isAssignmentOp") == "true"
    if assigns or text in ("++", "--"): collect_store(tokens, unit, token, where, aliases)
    if assigns and text == "=":
      target, source = tokens.enum_of(operand), tokens.get(token, "astOperand2")
      if target and source is not None and tokens.enum_of(source) != target:
        unit.entries.append(clamped(tokens, entry(tokens, target, where, "assignment", source),
          token, source))
    elif text in ("++", "--"):
      # A step stays inside when the value it starts from is proven one short of the edge
      target = tokens.enum_of(operand)
      before = loop_bounded(tokens, token, operand, target) or tokens.values_of(operand, target)
      if target: unit.entries.append(Entry(target, *where, "arithmetic", target,
        shifted(before, 1 if text == "++" else -1)))
    elif assigns:
      # Compound arithmetic on an enum may step past its last enumerator
      target = tokens.enum_of(operand)
      if target: unit.entries.append(Entry(target, *where, "arithmetic", target, Values()))
    elif token.get("isCast") == "true":
      target = tokens.enum_of(token)
      if target and operand is not None and tokens.enum_of(operand) != target:
        unit.entries.append(clamped(tokens, entry(tokens, target, where, "cast", operand),
          tokens.get(token, "astParent"), operand))
    elif text == "return":
      # `return` carries the type of its function, which takes the value without a cast
      target = tokens.enum_of(token)
      if target and operand is not None and tokens.enum_of(operand) != target:
        unit.entries.append(entry(tokens, target, where, "return", operand))
    elif text == "(" and operand is not None:
      collect_call(tokens, unit, token, where, loads, aliases)

def entry(tokens:Tokens, enum:str, where:tuple, kind:str, source:ET.Element) -> Entry:
  """Entry of `source` into `enum`, a parameter passed straight on kept for its callers."""
  param = None
  variable = tokens.variables.get(source.get("variable") or "")
  if variable is not None and variable.get("access") == "Argument":
    scope = tokens.scopes.get(variable.get("scope"))
    function = tokens.functions.get(scope.get("function")) if scope is not None else None
    for arg in function if function is not None else []:
      if arg.get("variable") == variable.get("id"):
        param = (function_key(tokens, function, where[0]), int(arg.get("nr")) - 1)
  return Entry(enum, *where, kind, type_text(source), tokens.values_of(source, enum), param)

def collect_call(
  tokens:Tokens, unit:Unit, call:ET.Element, where:tuple,
  loads:tuple[str, ...], aliases:dict,
):
  """Arguments a call passes, what it ignores, and the raw bytes it writes over a struct."""
  name_token = tokens.get(call, "astOperand1")
  name = name_token.get("str") if name_token is not None else ""
  if not name.isidentifier() or name in KEYWORDS: return
  callee = tokens.functions.get(name_token.get("function") or "")
  key = function_key(tokens, callee, where[0]) or name
  if caller := owner_key(tokens, call): unit.calls.append((caller, key))
  args = list(callee) if callee is not None else []
  params = {int(a.get("nr")) - 1: tokens.variables.get(a.get("variable")) for a in args}
  loader = any(fnmatchcase(name, glob) for glob in loads)
  passed = arguments(tokens, call)
  for index, arg in enumerate(passed):
    if arg is None: continue
    unit.arguments.append(Argument(key, index, tokens.values_of(arg)))
    param = params.get(index)
    target = tokens.enum_of(tokens.by_id.get(param.get("nameToken"))) if param is not None else ""
    if target and tokens.enum_of(arg) != target:
      unit.entries.append(entry(tokens, target, where, "argument", arg))
    if RAW_COPIES.get(name) != index and not (loader and raw_param(tokens, param)): continue
    raw = raw_target(tokens, arg, aliases)
    if raw and not typed_copy(tokens, name, passed, raw[1]):
      collect_raw(tokens, unit, call, raw, where, filled(tokens, name, passed))
  returns = call.get("valueType-originalTypeName") or tokens.enum_of(call)
  if call.get("astParent") is None and returns: unit.ignored.append(Ignored(key, returns, *where))

def raw_param(tokens:Tokens, param:ET.Element|None) -> bool:
  """A parameter taking bytes to write: a pointer to anything but a struct, and not to `const`."""
  name_token = tokens.by_id.get(param.get("nameToken")) if param is not None else None
  if name_token is None or name_token.get("valueType-pointer", "0") == "0": return False
  if name_token.get("valueType-type") == "record": return False
  return not int(name_token.get("valueType-constness") or 0) & 1

def raw_target(tokens:Tokens, expression:ET.Element|None, aliases:dict) -> tuple|None:
  """
  Object whose bytes `expression` points at, with the scope of its type: struct, union or enum.

  `&config` under casts, a pointer to such an object, or a byte pointer that took its address.
  """
  target = unwrap(tokens, expression)
  if target is None: return None
  if target.get("variable") in aliases: return aliases[target.get("variable")]
  if target.get("str") == "&" and not target.get("astOperand2"):
    target = tokens.get(target, "astOperand1")
    if target is None or target.get("valueType-pointer", "0") != "0": return None
  elif target.get("valueType-pointer") != "1": return None
  scope = tokens.type_scope(target)
  return (target, scope) if scope is not None else None

def typed_copy(tokens:Tokens, name:str, passed:list, scope:ET.Element) -> bool:
  """A `memcpy` or `memmove` from an object of the same type, its enum values as they were."""
  if name not in ("memcpy", "memmove") or len(passed) < 2: return False
  source = unwrap(tokens, passed[1])
  if source is not None and source.get("str") == "&" and not source.get("astOperand2"):
    source = tokens.get(source, "astOperand1")
  return source is not None and source.get("valueType-typeScope") == scope.get("id")

def filled(tokens:Tokens, name:str, passed:list) -> Values:
  """What a raw write leaves in an enum: zero from `memset` of zero, anything otherwise."""
  if name != "memset" or len(passed) < 2 or passed[1] is None: return Values()
  return Values(frozenset({0})) if tokens.values_of(passed[1]).known == {0} else Values()

def collect_raw(
  tokens:Tokens, unit:Unit, after:ET.Element, raw:tuple, where:tuple,
  values:Values = Values(),
):
  """Raw bytes over an object: the enum it is, or each enum field of it, `after` the write."""
  object_token, scope = raw
  path = path_of(tokens, object_token)
  if scope.get("type") == "Enum":
    unit.entries.append(Entry(scope.get("className"), *where, "memory", object_token.get("str"),
      values, checked=compared_after(tokens, after, path)))
    return
  for enum, member in enum_fields(tokens, scope):
    unit.entries.append(Entry(enum, *where, "memory", scope.get("className") or "struct",
      values, member=member, checked=compared_after(tokens, after, path and f"{path}.{member}")))

def collect_store(tokens:Tokens, unit:Unit, op:ET.Element, where:tuple, aliases:dict):
  """
  A write whose bytes land in an enum the target does not name.

  Bytes stored through a pointer to a struct, `((uint8_t *)&config)[1] = raw`,
  or a member of a union written beside an enum member.
  A byte pointer taking the address of a struct stands for that struct from then on.
  """
  target = tokens.get(op, "astOperand1")
  if target is None: return
  if op.get("str") == "=" and target.get("variable") \
    and target.get("valueType-pointer", "0") != "0" and target.get("valueType-type") != "record":
    raw = raw_target(tokens, tokens.get(op, "astOperand2"), aliases)
    if raw: aliases[target.get("variable")] = raw
    else: aliases.pop(target.get("variable"), None)
    return
  base = None
  if target.get("str") == "[" or (target.get("str") == "*" and not target.get("astOperand2")):
    base = tokens.get(target, "astOperand1")
    if base is not None and base.get("str") in ("+", "-"): base = tokens.get(base, "astOperand1")
  raw = raw_target(tokens, base, aliases) if base is not None else None
  # A store of the type of the object is a typed one, its value checked where it is assigned
  if raw and target.get("valueType-typeScope") != raw[1].get("id"):
    collect_raw(tokens, unit, op, raw, where)
  access = target if target.get("str") in (".", "->") else base
  if access is not None and access.get("str") in (".", "->"):
    collect_union(tokens, unit, op, access, where, access is target)

def collect_union(
  tokens:Tokens, unit:Unit, op:ET.Element, access:ET.Element, where:tuple,
  whole:bool,
):
  """
  A member of a union written: every enum member beside it takes the bytes too.

  `whole` is a member assigned itself, which gives its value to them,
  while a part of it written leaves their values to a comparison afterwards.
  """
  owner = tokens.get(access, "astOperand1")
  record = tokens.record_of(owner)
  if record is None or record.get("type") != "Union": return
  written = tokens.get(access, "astOperand2")
  name = written.get("str") if written is not None else ""
  value = tokens.get(op, "astOperand2") if whole and op.get("str") == "=" else None
  values = tokens.values_of(value) if value is not None else Values()
  path = path_of(tokens, owner)
  for enum, member in enum_fields(tokens, record):
    if member.split(".")[0] == name: continue
    unit.entries.append(Entry(enum, *where, "union", type_text(written), values, member=member,
      checked=compared_after(tokens, op, path and f"{path}.{member}")))

def clamped(tokens:Tokens, found:Entry, assign:ET.Element|None, source:ET.Element) -> Entry:
  """
  `found` with the values its target keeps once the very next statement clamps it,
  `if(x > LAST) x = FIRST;`: what the condition lets through and what the clamp gives.

  An upper clamp holds only a value that cannot go below zero, so the source has to be unsigned.
  """
  if assign is None or assign.get("str") != "=": return found
  path = path_of(tokens, tokens.get(assign, "astOperand1"))
  end = assign
  while end is not None and end.get("str") != ";": end = tokens.next(end)
  keyword = tokens.next(end) if end is not None else None
  if not path or keyword is None or keyword.get("str") != "if": return found
  opener = tokens.next(keyword)
  condition = tokens.get(opener, "astOperand2")
  if condition is None: return found
  left, right = tokens.get(condition, "astOperand1"), tokens.get(condition, "astOperand2")
  text = condition.get("str")
  # A strict `x > C` or `C < x` lets through up to `C`, and `>=` or `<=` one less
  if path_of(tokens, left) == path and text in (">", ">="): edge, step = right, text == ">="
  elif path_of(tokens, right) == path and text in ("<", "<="): edge, step = left, text == "<="
  else: return found
  limit = tokens.values_of(edge).known if edge is not None else frozenset()
  base = tokens.values_of(source)
  low = 0 if source.get("valueType-sign") == "unsigned" else base.low
  if len(limit) != 1 or low is None or low < 0: return found
  high = min(limit) - step
  if base.high is not None: high = min(high, base.high)
  given = frozenset()
  start = tokens.next(tokens.get(opener, "link"))
  if start is not None and start.get("str") == "{": start = tokens.next(start)
  while start is not None and start.get("str") != ";":
    if start.get("str") == "=" and path_of(tokens, tokens.get(start, "astOperand1")) == path:
      given = tokens.values_of(tokens.get(start, "astOperand2")).known
    start = tokens.next(start)
  if not given or high - low > 4096: return found
  return replace(found, values=Values(frozenset(range(low, high + 1)) | given))

def compared_after(tokens:Tokens, after:ET.Element, target:str) -> bool:
  """The function of `after` compares the object at `target`, a variable or a field, later on."""
  function = tokens.function_of(after)
  if not target or function is None: return False
  end = tokens.index.get(function.get("bodyEnd"), len(tokens.order))
  for token in tokens.order[tokens.index[after.get("id")]:end]:
    if token.get("isComparisonOp") != "true": continue
    for side in (tokens.get(token, "astOperand1"), tokens.get(token, "astOperand2")):
      if path_of(tokens, side) == target: return True
  return False

#-------------------------------------------------------------------------------------------- Start

def initializer(tokens:Tokens, name_token:ET.Element) -> ET.Element|None:
  """Value the declaration at `name_token` gives its variable, `None` when it gives none."""
  node, parent = name_token, tokens.get(name_token, "astParent")
  if parent is not None and parent.get("str") == "[" and tokens.get(parent, "astOperand1") is node:
    node, parent = parent, tokens.get(parent, "astParent")
  if parent is None or parent.get("str") != "=" or tokens.get(parent, "astOperand1") is not node:
    return None
  return tokens.get(parent, "astOperand2")

def dimension(tokens:Tokens, name_token:ET.Element) -> int|None:
  """Elements of the array declared at `name_token`, `None` when the size is no constant."""
  bracket = tokens.get(name_token, "astParent")
  if bracket is None or bracket.get("str") != "[": return None
  size = tokens.get(bracket, "astOperand2")
  known = tokens.values_of(size).known if size is not None else frozenset()
  return min(known) if len(known) == 1 else None

def braced(tokens:Tokens, value:ET.Element|None) -> list[tuple[str, ET.Element|None]]:
  """Items of a brace initializer: the field a designator names, "" in order, and the value."""
  if value is None or value.get("str") != "{": return []
  found = []
  for item in listed(tokens, tokens.get(value, "astOperand1")):
    designator = tokens.get(item, "astOperand1") if item is not None else None
    if designator is not None and item.get("str") == "=" and designator.get("str") == ".":
      field_token = tokens.get(designator, "astOperand1")
      found.append((field_token.get("str") if field_token is not None else "",
        tokens.get(item, "astOperand2")))
    else: found.append(("", item))
  return found

def into(tokens:Tokens, unit:Unit, enum:str, value:ET.Element, where:tuple):
  """`value` an initializer gives to an object of `enum`: an entry unless it is of the enum."""
  kind = "assignment"
  while value is not None and value.get("isCast") == "true" and tokens.enum_of(value) == enum:
    value, kind = tokens.get(value, "astOperand1"), "cast"
  if value is not None and tokens.enum_of(value) != enum:
    unit.entries.append(entry(tokens, enum, where, kind, value))

def started(
  tokens:Tokens, unit:Unit, variable:ET.Element, value:ET.Element|None, where:tuple,
  label:str, depth:int = NESTING,
):
  """
  The object `variable` declares, given `value` by an initializer or `None`, element by element.

  What no initializer reaches starts as zero, so an enum there takes `0`.
  """
  name_token = tokens.by_id.get(variable.get("nameToken"))
  scope = tokens.type_scope(name_token)
  if scope is None or variable.get("isPointer") == "true": return
  if variable.get("isArray") != "true":
    return started_one(tokens, unit, scope, value, where, label, depth)
  items = [item for _, item in braced(tokens, value)]
  for item in items: started_one(tokens, unit, scope, item, where, f"{label}[]", depth)
  size = dimension(tokens, name_token)
  if value is None or (size is not None and len(items) < size):
    started_one(tokens, unit, scope, None, where, f"{label}[]", depth)

def started_one(
  tokens:Tokens, unit:Unit, scope:ET.Element, value:ET.Element|None, where:tuple,
  label:str, depth:int,
):
  """One object of the type `scope`, given `value`: a brace list reaches its fields one by one."""
  if scope.get("type") == "Enum":
    if value is None:
      unit.entries.append(Entry(scope.get("className"), *where, "initial", label,
        Values(frozenset({0}))))
    else: into(tokens, unit, scope.get("className"), value, where)
    return
  # A union is given one member, and another value than a brace list is a typed copy
  if depth <= 0: return
  if value is not None and (value.get("str") != "{" or scope.get("type") == "Union"): return
  fields = sorted((v for v in tokens.members.get(scope.get("id"), [])
    if v.get("nameToken") in tokens.by_id), key=lambda v: tokens.index[v.get("nameToken")])
  names = [tokens.by_id[v.get("nameToken")].get("str") for v in fields]
  given, position = {}, 0
  for field, item in braced(tokens, value):
    if field: position = names.index(field) if field in names else len(names)
    if position < len(names): given[position] = item
    position += 1
  for index, variable in enumerate(fields):
    started(tokens, unit, variable, given.get(index), where, f"{label}.{names[index]}", depth - 1)

def collect_statics(tokens:Tokens, unit:Unit):
  """
  Objects of static storage, of the file or `static` in a function, as their declarations start.

  Zero fills what no initializer reaches, an entry of `0` into each enum there,
  and a value of another type an initializer gives enters its enum as an assignment does.
  """
  for variable in tokens.variables.values():
    if variable.get("isExtern") == "true": continue
    access, static = variable.get("access"), variable.get("isStatic") == "true"
    if access != "Global" and not (access == "Local" and static): continue
    name_token = tokens.by_id.get(variable.get("nameToken"))
    if name_token is None: continue
    function = tokens.function_of(name_token)
    where = (name_token.get("file"), int(name_token.get("linenr")),
      function.get("className") if function is not None else "")
    started(tokens, unit, variable, initializer(tokens, name_token), where, name_token.get("str"))

# Operators of the usual arithmetic conversions, where a `double` operand takes a `float` one along
WIDENING = {"+", "-", "*", "/", "<", ">", "<=", ">=", "==", "!=", "+=", "-=", "*=", "/="}

def constant(tokens:Tokens, node:ET.Element|None) -> bool:
  """`node` a number, or arithmetic of numbers alone, which the compiler folds."""
  if node is None: return False
  if node.get("type") == "number": return True
  if node.get("isArithmeticalOp") != "true": return False
  left, right = tokens.get(node, "astOperand1"), tokens.get(node, "astOperand2")
  return constant(tokens, left) and (right is None or constant(tokens, right))

def first_double(tokens:Tokens, node:ET.Element|None) -> ET.Element|None:
  """First literal of type `double` within constant `node`, left to right."""
  if node is None: return None
  if node.get("type") == "number": return node if node.get("valueType-type") == "double" else None
  # An element without children is false, so `or` would skip a literal found on the left
  left = first_double(tokens, tokens.get(node, "astOperand1"))
  return left if left is not None else first_double(tokens, tokens.get(node, "astOperand2"))

def collect_literals(tokens:Tokens, unit:Unit):
  """
  Each `double` constant a `float` operand meets: `x > 0.5`, `x * (1.0 / 3.0)`.

  The constant is the slip, a literal without `f`, while a variable of type `double` is a choice.
  A constant assigned or passed on converts once, at compile time, and costs nothing.
  """
  for token in tokens.order:
    if token.get("str") not in WIDENING: continue
    function = tokens.function_of(token)
    sides = (tokens.get(token, "astOperand1"), tokens.get(token, "astOperand2"))
    if function is None or None in sides: continue
    for mine, other in (sides, sides[::-1]):
      if mine.get("valueType-type") != "float" or other.get("valueType-type") != "double": continue
      literal = first_double(tokens, other) if constant(tokens, other) else None
      if literal is None: continue
      unit.literals.append(Literal(literal.get("str"), literal.get("file"),
        int(literal.get("linenr")), int(literal.get("column")), function.get("className")))
      break

def collect_accesses(tokens:Tokens, unit:Unit):
  """
  Reads and writes of file-scope variables and of struct fields, function by function.

  A field of a local copy is no shared data.
  Masking follows the token order of a function, each CMSIS call of `MASKING` setting it,
  and the `memory` clobber of those calls keeps the compiler from moving a read across them.
  A read is polled when a loop with no barrier runs it again and again on the same object,
  in its own function or through a function of the unit that loop calls.
  """
  loops = polling_loops(tokens)
  helpers = run_by(tokens, loops)
  masked = {} # by function scope, whether its last masking call so far masked interrupts
  for token in tokens.order:
    function = tokens.function_of(token)
    if function is None: continue
    if token.get("str") in MASKING and (after := tokens.next(token)) is not None \
      and after.get("str") == "(":
      masked[function.get("id")] = MASKING[token.get("str")]
      continue
    variable = tokens.variables.get(token.get("variable") or "")
    if variable is None or variable.get("access") not in SHARED: continue
    if token.get("id") == variable.get("nameToken"): continue
    declared = tokens.by_id.get(variable.get("nameToken"))
    path = declared.get("file") if declared is not None else token.get("file")
    name = token.get("str")
    line = int((declared if declared is not None else token).get("linenr"))
    if variable.get("access") == "Public":
      scope = tokens.scopes.get(variable.get("scope"))
      record = scope.get("className") if scope is not None else "?"
      # Unnamed structs are numbered unit by unit, so their fields go by their declaration
      key = f"{path}:{line}:{name}" if record.startswith("Anonymous") else f"{record}.{name}"
      expression = tokens.get(token, "astParent") if token.get("astParent") else token
      if local_copy(tokens, expression): continue
    else:
      key = f"{path}:{name}" if variable.get("isStatic") == "true" else name
      expression = token
    reached = element(tokens, expression, variable.get("isArray") == "true")
    write, read = used(tokens, reached)
    if not (write or read): continue
    guarded = masked.get(function.get("id"), False) or fresh(reached)
    index = tokens.index[token.get("id")]
    polled = read and (any(start <= index <= end and not names_in(tokens, reached) & assigned
      for start, end, assigned in loops)
      or (function.get("id") in helpers and fixed(tokens, reached)))
    unit.accesses.append(Access(key, name, path, line, owner_key(tokens, token),
      write, read, variable.get("isVolatile") == "true", guarded, polled))

#-------------------------------------------------------------------------------------------- Loops

def is_call(tokens:Tokens, token:ET.Element) -> bool:
  """`token` is the `(` of a call, never of a cast or of `if`, `while` and their kin."""
  if token.get("str") != "(" or token.get("isCast") == "true": return False
  callee = tokens.get(token, "astOperand1")
  return callee is not None and callee.get("str") not in KEYWORDS

def body_of(tokens:Tokens, call:ET.Element) -> ET.Element|None:
  """Function scope the call reaches in this unit, `None` for another unit or a pointer."""
  name = tokens.get(call, "astOperand1")
  return tokens.bodies.get(name.get("function") or "") if name is not None else None

def span_of(tokens:Tokens, scope:ET.Element) -> tuple[int, int]:
  """Token indexes from the opening to the closing token of a function body or a loop scope."""
  return tokens.index[scope.get("bodyStart")], tokens.index[scope.get("bodyEnd")]

def barrier(tokens:Tokens, start:int, end:int) -> bool:
  """
  Something between the token indexes `start` and `end` the compiler cannot see through,
  so it reloads every variable past it: `asm`, a call through a pointer or into another unit.
  A call to a function of this unit counts by what that function holds.
  """
  for token in tokens.order[start:end + 1]:
    if token.get("str") in ASM: return True
    if not is_call(tokens, token): continue
    body = body_of(tokens, token)
    if body is None: return True
    scope = body.get("id")
    if scope not in tokens.barriers:
      tokens.barriers[scope] = False # a recursion brings no barrier of its own
      tokens.barriers[scope] = barrier(tokens, *span_of(tokens, body))
    if tokens.barriers[scope]: return True
  return False

def loop_span(tokens:Tokens, scope:ET.Element) -> tuple[int, int]|None:
  """
  Token indexes of what a loop runs on every turn: its condition, its step and its body.

  The start of a `for` runs once, so the turns begin past its first `;`,
  and the condition of a `do` follows the body.
  """
  # Found from the body, since cppcheck 2.17 names no keyword of a loop scope
  brace = tokens.by_id.get(scope.get("bodyStart"))
  close = tokens.by_id.get(scope.get("bodyEnd"))
  before = tokens.next(brace, -1) if brace is not None else None
  if scope.get("type") == "Do": keyword = before
  else:
    closing = before is not None and before.get("str") == ")"
    opener = tokens.get(before, "link") if closing else None
    keyword = tokens.next(opener, -1) if opener is not None else None
  if keyword is None or close is None: return None
  start, end = tokens.index[keyword.get("id")], tokens.index[close.get("id")]
  if scope.get("type") == "For":
    while start < end and tokens.order[start].get("str") != ";": start += 1
  elif scope.get("type") == "Do":
    after = tokens.next(close)
    opener = tokens.next(after) if after is not None and after.get("str") == "while" else None
    shut = tokens.get(opener, "link") if opener is not None else None
    if shut is not None: end = tokens.index[shut.get("id")]
  return start, end

def polling_loops(tokens:Tokens) -> list[tuple[int, int, set[str]]]:
  """
  Loops with no barrier, by the token indexes of their turns, each with the variables it assigns.

  Such a loop may keep a variable it only reads in a register, all its turns long.
  """
  found = []
  for scope in tokens.scopes.values():
    if scope.get("type") not in ("While", "For", "Do"): continue
    span = loop_span(tokens, scope)
    if span is None or barrier(tokens, *span): continue
    assigned = set()
    for token in tokens.order[span[0]:span[1] + 1]:
      if token.get("isAssignmentOp") == "true" or token.get("str") in ("++", "--"):
        target = tokens.get(token, "astOperand1")
        if target is not None and target.get("varId", "0") != "0":
          assigned.add(target.get("varId"))
    found.append((*span, assigned))
  return found

def run_by(tokens:Tokens, loops:list[tuple[int, int, set[str]]]) -> set[str]:
  """Function scopes of this unit the loops call, at any depth: each runs on their every turn."""
  found, spans = set(), [(start, end) for start, end, _ in loops]
  while spans:
    start, end = spans.pop()
    for token in tokens.order[start:end + 1]:
      body = body_of(tokens, token) if is_call(tokens, token) else None
      if body is None or body.get("id") in found: continue
      found.add(body.get("id"))
      spans.append(span_of(tokens, body))
  return found

def names_in(tokens:Tokens, node:ET.Element) -> set[str]:
  """Variables an expression names, by `varId`: the object, its bases and indexes."""
  found, seen, stack = set(), set(), [node]
  while stack:
    item = stack.pop()
    # A few trees link back into themselves in cppcheck, `uart.c` of Core among them
    if item is None or item.get("id") in seen: continue
    seen.add(item.get("id"))
    if item.get("varId", "0") != "0": found.add(item.get("varId"))
    stack += [tokens.get(item, "astOperand1"), tokens.get(item, "astOperand2")]
  return found

def fixed(tokens:Tokens, reached:ET.Element) -> bool:
  """
  `reached` is one object on every call: a variable of static storage,
  a field of one or its element at a constant index, never what a pointer leads to.
  """
  node, seen = reached, set()
  while node is not None and node.get("str") in (".", "[") and node.get("id") not in seen:
    seen.add(node.get("id"))
    if node.get("originalName") == "->": return False
    index = tokens.get(node, "astOperand2") if node.get("str") == "[" else None
    if index is not None and len(tokens.values_of(index).known) != 1: return False
    node = tokens.get(node, "astOperand1")
  variable = tokens.variables.get(node.get("variable") or "") if node is not None else None
  if variable is None: return False
  return variable.get("access") == "Global" or variable.get("isStatic") == "true"

def element(tokens:Tokens, expression:ET.Element, array:bool) -> ET.Element:
  """
  What an access reaches: the element of an `array` it indexes, else `expression` itself.

  An element of an array is part of it, while the element a pointer leads to is another object.
  """
  parent = tokens.get(expression, "astParent")
  if array and parent is not None and parent.get("str") == "[" \
    and tokens.get(parent, "astOperand1") is expression:
    return parent
  return expression

def used(tokens:Tokens, reached:ET.Element) -> tuple[bool, bool]:
  """
  Whether `reached` is written and whether it is read: `=` only writes it,
  `+=` or `++` does both, `&` takes its address without either, anything else reads it.
  """
  parent = tokens.get(reached, "astParent")
  if parent is None: return False, True
  if parent.get("str") in ("++", "--"): return True, True
  if parent.get("str") == "&" and parent.get("astOperand2") is None: return False, False
  if parent.get("isAssignmentOp") == "true" and tokens.get(parent, "astOperand1") is reached:
    return True, parent.get("str") != "="
  return False, True

def fresh(expression:ET.Element) -> bool:
  """The value `expression` reaches is `volatile` there, through a pointer to `volatile` too."""
  bits = int(expression.get("valueType-volatileness") or 0)
  return bool(bits >> int(expression.get("valueType-pointer") or 0) & 1)

def local_copy(tokens:Tokens, member:ET.Element) -> bool:
  """
  The field access `member` lands in an object of its own function, a copy rather than shared data.

  A pointer may lead anywhere, so a path through `->`, `*` or a pointer counts as shared.
  """
  node, seen = member, set()
  while node is not None and node.get("str") in (".", "[") and node.get("id") not in seen:
    seen.add(node.get("id"))
    if node.get("originalName") == "->": return False
    node = tokens.get(node, "astOperand1")
  variable = tokens.variables.get(node.get("variable") or "") if node is not None else None
  if variable is None or variable.get("isPointer") == "true" or variable.get("isStatic") == "true":
    return False
  # An array parameter is a pointer in C
  return variable.get("access") == "Local" \
    or (variable.get("access") == "Argument" and variable.get("isArray") != "true")

def configured(path:str) -> bool:
  """Dump `path` holds a configuration, so cppcheck read its source through."""
  return b'<dump cfg="' in FILE.load(path, binary=True)

def read_dump(path:str, rename:dict[str, str]|None=None, loads:tuple[str, ...]=()) -> Unit|None:
  """
  Facts of the dump `path`, its first configuration: the one the defines of the build pick.

  `rename` gives the path a file read under another name had, a copy its source.
  `loads` are globs of functions writing raw bytes into the buffer a caller gives them.
  `None` comes back for a dump without a configuration, as an `#error` leaves it.
  """
  data = FILE.load(path, binary=True)
  # Raw tokens and directives are a third of a dump and no rule reads them
  for tag in (b"rawtokens", b"directivelist"):
    start, end = data.find(b"<" + tag), data.find(b"</" + tag + b">")
    if start >= 0 and end > start: data = data[:start] + data[end + len(tag) + 3:]
  config = ET.fromstring(data).find("dump")
  if config is None: return None
  unit = Unit()
  for token in config.iter("token"):
    if (name := token.get("file")) in (rename or {}): token.set("file", rename[name])
  tokens = Tokens(config)
  collect_enums(tokens, unit)
  collect_statics(tokens, unit)
  collect_switches(tokens, unit)
  collect_entries(tokens, unit, loads)
  collect_accesses(tokens, unit)
  collect_literals(tokens, unit)
  return unit
