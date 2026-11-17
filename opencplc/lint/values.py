# opencplc/lint/values.py

"""
Rules on types and proven values: switches over enums, statuses nobody reads, shared variables.

Each reads the whole application at once.
An enum is closed when every place a value of another type enters it is proven inside its set,
so a `switch` over it needs no `default`, and `-Wswitch` keeps naming a new enumerator.
A variable an interrupt writes and a thread reads has to be `volatile`.
"""

from dataclasses import dataclass
from xaeian import PATH
from .finding import Finding
from .dump import Unit, Switch, Entry, Values, Ignored, Access
from .rules import RULES

@dataclass
class Program:
  """Facts of every unit of a build, each place once."""
  enums: dict[str, frozenset[int]]
  switches: list[Switch]
  entries: list[Entry]
  arguments: dict[tuple[str, int], list[Values]] # values each argument of a function gets
  ignored: list[Ignored]
  accesses: list[Access]
  calls: dict[str, set[str]] # workspace-relative keys of the functions each one calls

def merge(units:list[Unit]) -> Program:
  """One program of `units`; a header seen by many units gives its facts once."""
  enums, switches, entries, arguments, ignored, accesses = {}, {}, {}, {}, {}, {}
  calls = {}
  for unit in units:
    enums |= unit.enums
    switches |= {(s.path, s.line): s for s in unit.switches}
    entries |= {(e.path, e.line, e.enum, e.kind, e.member): e for e in unit.entries}
    for arg in unit.arguments: arguments.setdefault((arg.callee, arg.index), []).append(arg.values)
    ignored |= {(i.path, i.line): i for i in unit.ignored}
    accesses |= dict.fromkeys(unit.accesses)
    for caller, callee in unit.calls:
      calls.setdefault(local_key(caller), set()).add(local_key(callee))
  return Program(enums, list(switches.values()), list(entries.values()), arguments,
    list(ignored.values()), list(accesses), calls)

def local_key(key:str) -> str:
  """Function key with its path workspace-relative, so a dump and a call graph agree."""
  path, _, name = key.rpartition(":")
  return f"{PATH.local(path)}:{name}" if path else name

def where(path:str, line:int) -> str:
  return f"{PATH.local(path)}:{line}"

#-------------------------------------------------------------------------------------------- Enums

def proven(entry:Entry, program:Program) -> bool:
  """
  Every value `entry` lets in belongs to its enum.

  A parameter passed straight on is proven by every call passing a proven value, one level up.
  Raw bytes, or a union member beside the enum, are proven by a comparison of the field
  later in the same function, when the value they bring is not proven already.
  """
  allowed = program.enums.get(entry.enum, frozenset())
  if entry.checked or entry.values.within(allowed): return True
  passed = program.arguments.get(entry.param, []) if entry.param else []
  return bool(passed) and all(values.within(allowed) for values in passed)

def openings(program:Program, vouched=lambda entry: False) -> dict[str, Entry]:
  """
  First place, in file order, where each open enum takes a value no proof covers.

  `vouched` takes an entry an exception names, a check the code makes where no proof reaches,
  so a project answers for its own entry even when the `switch` lies in Core.
  """
  found = {}
  for entry in sorted(program.entries, key=lambda e: (e.path, e.line)):
    if entry.enum in found or proven(entry, program) or vouched(entry): continue
    found[entry.enum] = entry
  return found

def opening_text(entry:Entry) -> str:
  """How an enum opens, for a message."""
  place = where(entry.path, entry.line)
  if entry.kind == "memory":
    into = f"{entry.source}.{entry.member}" if entry.member else entry.source
    return f"takes raw bytes into `{into}` at {place}"
  if entry.kind == "initial": return f"starts as `0` in `{entry.source}` at {place}"
  if entry.kind == "union":
    return f"takes `{entry.source}` written beside `{entry.member}` in a union at {place}"
  if entry.kind == "arithmetic": return f"is counted on by arithmetic at {place}"
  return f"takes `{entry.source}` unchecked at {place}"

def at(switch:Switch, rule:str, message:str) -> Finding:
  """Finding at `switch`, named by the function it stands in for an exception."""
  return Finding(rule, PATH.local(switch.path), switch.line, 1, message, switch.function,
    RULES[rule].refs)

def check_switches(
  program:Program, opt_ins:set[str],
  vouched = lambda entry: False,
) -> list[Finding]:
  """
  A state machine without `default` over an enum that is open: a stray value stalls it for good.

  A value without a label skips a `switch`, as C defines, which harms no dispatch:
  a variable its cases set is caught unset by `-Wmaybe-uninitialized`, a missing `return`
  by `-Wreturn-type`, and a safe value set before it stays.
  A `switch` whose cases set the very variable it switches on is another matter:
  a value no case names keeps it where it is.
  `switch-default` asks for `default` over an integer, as a form a project turns on,
  and `switch-enum-default` reports the other side: `default` over a closed enum.
  Proven values of the condition within the labels make `default` needless either way.
  """
  opened, found = openings(program, vouched), []
  for switch in sorted(program.switches, key=lambda s: (s.path, s.line)):
    if switch.has_default:
      if switch.enum and switch.enum not in opened and "switch-enum-default" in opt_ins:
        found.append(at(switch, "switch-enum-default",
          f"`default` over `{switch.enum}` keeps `-Wswitch` from naming a new enumerator"))
      continue
    if switch.values.within(switch.cases): continue
    if switch.enum in opened and switch.steps:
      found.append(at(switch, "switch-enum", f"`switch` over `{switch.enum}` steps the value "
        f"it switches on and has no `default`, while `{switch.enum}` "
        f"{opening_text(opened[switch.enum])}: a stray value would stall it"))
    elif not switch.enum and "switch-default" in opt_ins:
      found.append(at(switch, "switch-default",
        f"`switch` over `{switch.source}` has no `default`"))
  return found

#------------------------------------------------------------------------------------------- Status

def check_status(program:Program, status:str) -> list[Finding]:
  """Each call whose `status` nobody reads: a failure there goes unnoticed."""
  return [Finding("status-used", PATH.local(i.path), i.line, 1,
    f"`{status}` of `{local_key(i.callee).rpartition(':')[2]}` is never read", i.function,
    RULES["status-used"].refs) for i in program.ignored if i.returns == status]

#----------------------------------------------------------------------------------------- Volatile

def inlined(context:set[str], calls:dict[str, set[str]], graphed:set[str]) -> set[str]:
  """
  `context` with the functions gcc inlined into its own, which the call graph never shows.

  The source still calls them, so a callee missing from `graphed` runs where its caller runs.
  """
  found, queue = set(context), list(context)
  while queue:
    for callee in calls.get(queue.pop(), ()):
      if callee in found or callee in graphed: continue
      found.add(callee)
      queue.append(callee)
  return found

def check_volatile(
  program:Program, irq:set[str], thread:set[str],
  graphed:set[str] = frozenset(),
) -> list[Finding]:
  """
  A variable an interrupt writes and a thread polls, declared without `volatile`.

  `irq` and `thread` are workspace-relative function keys of each context, from the call graph,
  and `graphed` every function it holds: one gcc inlined away joins the context of its caller.
  A function running in both counts for both.
  Polling is the one read `volatile` saves: a loop with no barrier may keep the value
  in a register and never see the interrupt change it.
  A read once per call, or with a call into another unit between turns, reloads anyway,
  so a value handed over by a flag or a ring index needs no `volatile` of its own.
  A write in a thread wants exclusion, which `volatile` does not give, and a read guarded
  by masked interrupts or a pointer to `volatile` is fresh.
  """
  irq, thread = inlined(irq, program.calls, graphed), inlined(thread, program.calls, graphed)
  by_key = {}
  for access in program.accesses: by_key.setdefault(access.key, []).append(access)
  found = []
  for accesses in by_key.values():
    if any(a.volatile for a in accesses): continue
    writer = next((a for a in accesses if a.write and local_key(a.function) in irq), None)
    reader = next((a for a in accesses
      if a.read and a.polled and not a.guarded and local_key(a.function) in thread), None)
    if writer is None or reader is None: continue
    first = min(accesses, key=lambda a: (a.path, a.line))
    found.append(Finding("irq-volatile", PATH.local(first.path), first.line, 1,
      f"`{first.name}` written by interrupt `{local_key(writer.function).rpartition(':')[2]}` "
      f"is polled by thread `{local_key(reader.function).rpartition(':')[2]}` "
      "in a loop with no barrier, and is not `volatile`", first.name, RULES["irq-volatile"].refs))
  return found
