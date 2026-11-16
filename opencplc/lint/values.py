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
    accesses |= {(a.key, a.function, a.write): a for a in unit.accesses}
    for caller, callee in unit.calls:
      calls.setdefault(local_key(caller), set()).add(local_key(callee))
  return Program(enums, list(switches.values()), list(entries.values()), arguments,
    list(ignored.values()), list(accesses.values()), calls)

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

def openings(program:Program) -> dict[str, Entry]:
  """First place, in file order, where each open enum takes a value no proof covers."""
  found = {}
  for entry in sorted(program.entries, key=lambda e: (e.path, e.line)):
    if entry.enum not in found and not proven(entry, program): found[entry.enum] = entry
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

def check_switches(program:Program, opt_ins:set[str]) -> list[Finding]:
  """
  A `switch` without `default` over an enum that is open, or over an integer with `switch-default`.

  A value without a label skips a `switch` over an integer, as C defines,
  so its `default` is a form a project asks for, while an open enum hides a value nobody named.
  Proven values of the condition within the labels make `default` needless either way.
  `switch-enum-default` reports the other side: `default` over a closed enum.
  """
  opened, found = openings(program), []
  for switch in sorted(program.switches, key=lambda s: (s.path, s.line)):
    if switch.has_default:
      if switch.enum and switch.enum not in opened and "switch-enum-default" in opt_ins:
        found.append(at(switch, "switch-enum-default",
          f"`default` over `{switch.enum}` keeps `-Wswitch` from naming a new enumerator"))
      continue
    if switch.values.within(switch.cases): continue
    if switch.enum in opened:
      found.append(at(switch, "switch-enum", f"`switch` over `{switch.enum}` has no `default`, "
        f"and `{switch.enum}` {opening_text(opened[switch.enum])}"))
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
  A variable an interrupt writes and a thread reads or writes, declared without `volatile`.

  `irq` and `thread` are workspace-relative function keys of each context, from the call graph,
  and `graphed` every function it holds: one gcc inlined away joins the context of its caller.
  A function running in both counts for both.
  A write in a thread read by an interrupt is mostly a setting made before the interrupt starts,
  so only the interrupt writing counts.
  """
  irq, thread = inlined(irq, program.calls, graphed), inlined(thread, program.calls, graphed)
  by_key = {}
  for access in program.accesses: by_key.setdefault(access.key, []).append(access)
  found = []
  for accesses in by_key.values():
    if any(a.volatile for a in accesses): continue
    writer = next((a for a in accesses if a.write and local_key(a.function) in irq), None)
    reader = next((a for a in accesses if local_key(a.function) in thread), None)
    if writer is None or reader is None: continue
    first = min(accesses, key=lambda a: (a.path, a.line))
    found.append(Finding("irq-volatile", PATH.local(first.path), first.line, 1,
      f"`{first.name}` written by interrupt `{local_key(writer.function).rpartition(':')[2]}` "
      f"and used by thread `{local_key(reader.function).rpartition(':')[2]}` is not `volatile`",
      first.name, RULES["irq-volatile"].refs))
  return found
