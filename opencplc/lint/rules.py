# opencplc/lint/rules.py

"""
Rules of Forge: VRTS on the call graph, the stack of each thread, and the shape of the files.

What a rule looks for in the API of Core comes from `lint.yaml` of that Core,
with what the `lint.yaml` of a project adds for its own drivers,
so a Core that renames a function changes that file, not Forge.
A check takes data and gives findings back: nothing here runs a tool or prints.
"""

import re
from collections import Counter, deque
from dataclasses import dataclass
from fnmatch import fnmatchcase
from xaeian import DIR, FILE, PATH
from ..utils import glob_match
from .finding import Finding
from .lintfile import LISTS, read, flat
from .graph import Graph, Function, INDIRECT, place
from . import sources

@dataclass(frozen=True)
class Rule:
  """A rule of Forge: its family, the norms behind it, and whether a project turns it on itself."""
  family: str # orders the wiki and this table, never shown in a finding
  refs: str
  opt_in: bool = False

# The rules under the names a finding and an exception give, family by family
RULES = {
  "irq-yield": Rule("vrts", "CWE-479, CERT SIG30-C"),
  "irq-heap": Rule("vrts", "CWE-364, CERT SIG30-C"),
  "irq-log": Rule("vrts", "CWE-479, CERT SIG30-C"),
  "irq-volatile": Rule("vrts", "BARR-C 1.8, CERT DCL22-C, CWE-362"),
  "thread-hold": Rule("vrts", "CWE-1322"),
  "heap-owner": Rule("vrts", "CWE-416, CERT MEM30-C"),
  "heap-cleared": Rule("vrts", "CWE-401, CERT MEM31-C"),
  "no-heap": Rule("vrts", "MISRA 21.3", opt_in=True),
  "recursion": Rule("stack", "MISRA 17.2, CWE-674"),
  "stack-fit": Rule("stack", "CWE-787"),
  "stack-margin": Rule("stack", "CWE-787", opt_in=True),
  "header-object": Rule("files", "MISRA 8.6, BARR-C 4.2"),
  "header-guard": Rule("files", "MISRA Dir 4.10, CERT PRE06-C"),
  "extern-in-c": Rule("files", "MISRA 8.5, CERT DCL40-C"),
  "own-header-first": Rule("files", "MISRA 8.4, BARR-C 4.3"),
  "include-form": Rule("files", ""), # a form of OpenCPLC, which no norm asks
  "config-order": Rule("files", "CERT DCL40-C"),
  "config-unread": Rule("files", "MISRA 2.5"),
  "switch-enum": Rule("values", "CWE-478"),
  "switch-enum-default": Rule("values", "", opt_in=True),
  "switch-default": Rule("values", "MISRA 16.4", opt_in=True),
  "status-used": Rule("values", "MISRA 17.7, CERT ERR33-C, CWE-252", opt_in=True),
  "conversion": Rule("gcc", "MISRA 10.3, CWE-197", opt_in=True),
  "double-promotion": Rule("gcc", "", opt_in=True),
  "static-scope": Rule("gcc", "MISRA 8.7, MISRA 8.8, CERT DCL15-C"),
  "cppcheck-style": Rule("tools", "", opt_in=True),
}
GRAPH_RULES = (
  "irq-yield", "irq-heap", "irq-log", "thread-hold", "heap-owner", "heap-cleared",
  "recursion", "stack-fit",
)
FILE_RULES = ("header-object", "header-guard", "extern-in-c", "own-header-first")
# Rules of files telling code of others from Core, which only `vendor` of `lint.yaml` does
TREE_RULES = ("include-form", "config-order", "config-unread")
VALUE_RULES = ("switch-enum", "irq-volatile")
OPT_INS = tuple(name for name, rule in RULES.items() if rule.opt_in)
START = "Reset_Handler" # the start of the program, in the vector table but no interrupt
STACK_MARGIN = 25 # % of a stack `stack-margin` keeps free
HEAP_C = ("malloc", "calloc", "realloc", "free")
CONFIG_HEADERS = ("main.h", "boot.h") # configure the build, every tree takes them in quotes
FORGE_SETTINGS = ("PRO_", "BOOT_") # names of `main.h` Forge reads itself, no file of the build
# Where a finding of `include-form` says a file lies
PLACES = {
  "Core": "lies in Core", "project": "lies in the project",
  "vendor": "is code of others", "toolchain": "comes with the toolchain",
}

@dataclass
class Roles:
  """What a Core says of its own API in `lint.yaml`, with what a project adds."""
  yields: set[str]         # hand the core over, never from an interrupt
  holds: set[str]          # keep the core, never in a thread
  heap: set[str]           # the whole heap, which an interrupt never touches
  heap_new: str            # takes a block the calling thread owns
  heap_clear: str          # gives back every block of the calling thread
  thread: str              # starts a thread on a function and a stack array
  irq_handlers: list[str]  # name endings of what the vector table points at
  irq_starts: list[str]    # globs of calls that register an interrupt handler
  irq_fields: list[str]    # fields a driver calls from its interrupt
  frame: dict[str, int]    # words a thread switch leaves on its stack, by `-mcpu`
  # Code of others, outside the checks: the folder of the file naming it, and a glob from there
  vendor: list[tuple[str, str]]
  log: list[str]           # globs of what writes the console buffer, never from an interrupt
  panic: set[str]          # end the program, so an interrupt may reach the log through them
  status: str              # type of an error code a caller has to read
  load: list[str]          # globs of what writes raw bytes into a buffer of its caller

@dataclass
class Thread:
  """A function given to `thread()`, with the array it runs on."""
  title: str  # in the graph
  stack: str  # symbol of the array
  path: str
  line: int   # of the call

@dataclass
class Stack:
  """Stack of one thread: the deepest path the graph shows, what a switch adds, and its array."""
  thread: str
  deepest: int     # bytes
  frame: int       # bytes a switch leaves on top
  size: int|None   # bytes of the array, `None` when the image does not say
  holes: set[str]  # why the depth is a floor: `pointer`, `dynamic` or `library` calls

def load_roles(core_dir:str, pro_dir:str = "") -> Roles|None:
  """
  Roles of the Core in `core_dir`, with what the project in `pro_dir` adds to their lists.

  `None` for a Core without `lint.yaml`; a file Forge cannot take raises `LintFileError`.
  """
  core = read(core_dir, core=True)
  if core is None: return None
  project = (read(pro_dir, core=False) if pro_dir else None) or {}
  roles, more = flat(core["roles"]), flat(project.get("roles", {}))
  lists = {key: list(dict.fromkeys(roles[key] + more.get(key, []))) for key in LISTS}
  vendor = [(core_dir, glob) for glob in core["vendor"]]
  vendor += [(pro_dir, glob) for glob in project.get("vendor", [])]
  return Roles(set(lists["yield"]), set(lists["hold"]), set(lists["heap.any"]), roles["heap.new"],
    roles["heap.clear"], roles["thread"], lists["irq.handler"], lists["irq.start"],
    lists["irq.field"], roles["frame"], vendor, lists["log"], set(lists["panic"]),
    roles["status"], lists["load"])

def split_opt_ins(names:list[str]) -> tuple[list[str], list[str]]:
  """Rules a project turns on, and the names among them that are no rule to turn on."""
  return [n for n in names if n in OPT_INS], [n for n in names if n not in OPT_INS]

def vendor_code(path:str, vendor:list[tuple[str, str]]) -> bool:
  """`path` lies in code Core or the project carries from others, a glob from the folder each."""
  return any(PATH.is_under(path, root) and glob_match(PATH.rel(path, root), pattern)
    for root, pattern in vendor)

#-------------------------------------------------------------------------------------------- Roots

class Bodies:
  """Function bodies of the sources, read once a file: which function a line stands in."""
  def __init__(self, texts:dict[str, str]):
    self.texts = texts
    self.cache:dict[str, list[tuple[str, int, int]]] = {}

  def around(self, path:str, line:int) -> str:
    """Name of the function whose body holds `line` of `path`, "" outside any."""
    if path not in self.cache:
      self.cache[path] = sources.top_level(sources.code(self.texts.get(path, "")))[1]
    return next((name for name, first, last in self.cache[path] if first <= line <= last), "")

def calls_to(graph:Graph, match) -> list[tuple[str, str]]:
  """Every call whose callee `match` takes: callee and the place of the call."""
  return [(callee, site) for calls in graph.calls.values()
    for callee, site in calls if match(callee)]

def args_at(texts:dict[str, str], site:str) -> list[str]:
  """Arguments of the call at `site`, read from its source, none when the source is not read."""
  path, line, col = place(site)
  text = texts.get(path)
  return sources.call_args(sources.code(text), line, col) if text else []

def last_word(arg:str) -> str:
  """The name an argument ends with: `&loop` gives `loop`, `(uint32_t *)stack` gives `stack`."""
  words = sources.WORD.findall(arg)
  return words[-1] if words else ""

def find_threads(graph:Graph, texts:dict[str, str], roles:Roles) -> list[Thread]:
  """
  Threads of the build: the calls to `thread` gcc compiled, a function and a stack each.

  Names come from the source at the place of the call, so a thread an `#if` leaves out is none.
  """
  found = []
  for _, site in calls_to(graph, lambda callee: callee == roles.thread):
    args = args_at(texts, site)
    if len(args) < 2: continue
    path, line, _ = place(site)
    found.append(Thread(graph.title(last_word(args[0]), path), last_word(args[1]), path, line))
  return found

def hidden_calls(graph:Graph, texts:dict[str, str], roles:Roles) -> list[str]:
  """
  Places of calls starting a thread or an interrupt whose arguments no source read shows.

  A macro around such a call hides its function and stack, so the rules of threads
  and interrupts pass it by.
  """
  def starts(callee:str) -> bool:
    return callee == roles.thread or any(fnmatchcase(callee, g) for g in roles.irq_starts)
  found = set()
  for _, site in calls_to(graph, starts):
    path, line, _ = place(site)
    if path in texts and not args_at(texts, site): found.add(f"{PATH.local(path)}:{line}")
  return sorted(found)

def irq_roots(graph:Graph, texts:dict[str, str], roles:Roles) -> list[str]:
  """
  Titles of what runs in an interrupt.

  A handler of the vector table, and each function a driver gets for its interrupt:
  as an argument of a registering call, or in one of its callback fields.
  """
  roots = {title for title, fn in graph.functions.items()
    if fn.name.endswith(tuple(roles.irq_handlers)) and fn.name != START}
  starts = calls_to(graph, lambda callee: any(fnmatchcase(callee, g) for g in roles.irq_starts))
  for _, site in starts:
    path = place(site)[0]
    roots |= {graph.title(last_word(arg), path) for arg in args_at(texts, site)}
  for path, text in texts.items():
    given = sources.assigned(sources.code(text), roles.irq_fields)
    roots |= {graph.title(name, path) for name in given}
  return sorted(root for root in roots if root in graph.functions)

#-------------------------------------------------------------------------------------------- Graph

def at(rule:str, fn:Function, message:str) -> Finding:
  """Finding at the start of `fn`, the function an exception names."""
  return Finding(rule, PATH.local(fn.path), fn.line, 1, message, fn.name, RULES[rule].refs)

def named(graph:Graph, title:str) -> str:
  """Name of a function by its title, a library one as gcc called it."""
  fn = graph.functions.get(title)
  return fn.name if fn else title

def chain_text(graph:Graph, chain:list[tuple[str, str]]) -> str:
  """`a` (where) → `b` (where): each callee with the place it is called from."""
  steps = []
  for callee, site in chain:
    path, line, _ = place(site)
    steps.append(f"`{named(graph, callee)}` ({PATH.local(path)}:{line})")
  return " → ".join(steps)

def reach(graph:Graph, root:str, targets:set[str], stop:set[str]) -> list[tuple[str, str]]|None:
  """Shortest chain of calls from `root` into `targets`, not through `stop`, `None` if none."""
  back = {root: None}
  queue = deque([root])
  while queue:
    caller = queue.popleft()
    for callee, site in graph.calls.get(caller, []):
      if callee in back: continue
      back[callee] = (caller, site)
      if callee in targets:
        chain = []
        while back[callee]:
          caller, site = back[callee]
          chain.append((callee, site))
          callee = caller
        return chain[::-1]
      if callee not in stop: queue.append(callee)
  return None

def reachable(graph:Graph, roots:list[str], stop:set[str]) -> set[str]:
  """Titles `roots` reach through any depth of calls, themselves included, not through `stop`."""
  seen, queue = set(roots), deque(roots)
  while queue:
    for callee, _ in graph.calls.get(queue.popleft(), []):
      if callee in seen or callee in stop: continue
      seen.add(callee)
      queue.append(callee)
  return seen

def contexts(
  graph:Graph, texts:dict[str, str],
  threads:list[Thread], roles:Roles,
) -> tuple[set[str], set[str]]:
  """Titles running in an interrupt, and those running in a thread or in `main` before them."""
  irq = reachable(graph, irq_roots(graph, texts, roles), roles.panic)
  thread = reachable(graph, [t.title for t in threads] + ["main"], roles.panic)
  return irq, thread

def check_graph(
  graph:Graph, texts:dict[str, str],
  threads:list[Thread], roles:Roles,
  opt_ins:frozenset[str]|set[str] = frozenset(),
  project_dir:str = "",
) -> list[Finding]:
  """
  VRTS: what interrupts and threads reach, who clears the arena of a thread, and recursion.

  The arena counts the function a call stands in by the source, so `-Os` inlining
  a helper into its caller changes no verdict.
  A panic ends the program, so an interrupt reaching the log through it logs nothing more.
  """
  found = []
  api = roles.yields | roles.holds # their insides are VRTS, not the code under check
  log = {title for callees in graph.calls.values() for title, _ in callees
    if any(fnmatchcase(named(graph, title), glob) for glob in roles.log)}
  for root in irq_roots(graph, texts, roles):
    if chain := reach(graph, root, roles.yields, api):
      found.append(at("irq-yield", graph.functions[root],
        f"interrupt hands the core over: {chain_text(graph, chain)}"))
    if chain := reach(graph, root, roles.heap, api | roles.heap):
      found.append(at("irq-heap", graph.functions[root],
        f"interrupt races a thread for the heap: {chain_text(graph, chain)}"))
    if chain := reach(graph, root, log, api | roles.panic):
      found.append(at("irq-log", graph.functions[root],
        f"interrupt writes the console buffer threads write: {chain_text(graph, chain)}"))
  if "no-heap" in opt_ins: found += check_no_heap(graph, roles, project_dir)
  bodies = Bodies(texts)
  clears = [(place(site), site) for _, site in calls_to(graph, lambda c: c == roles.heap_clear)]
  owners = {(graph.functions[t.title].path, graph.functions[t.title].name)
    for t in threads if t.title in graph.functions}
  for (path, line, col), _ in clears:
    owner = bodies.around(path, line)
    if (path, owner) in owners: continue
    found.append(Finding("heap-owner", PATH.local(path), line, col,
      f"`{owner or roles.heap_clear}` frees every block of the thread calling it", owner,
      RULES["heap-owner"].refs))
  for thread in threads:
    fn = graph.functions.get(thread.title)
    if not fn: continue
    if chain := reach(graph, thread.title, roles.holds, api):
      found.append(at("thread-hold", fn, f"thread keeps the core: {chain_text(graph, chain)}"))
    cleared = any(path == fn.path and bodies.around(path, line) == fn.name
      for (path, line, _), _ in clears)
    chain = reach(graph, thread.title, {roles.heap_new}, api)
    if chain and not cleared:
      found.append(at("heap-cleared", fn, f"thread never calls `{roles.heap_clear}` "
        f"for blocks of {chain_text(graph, chain)}"))
  return found + check_recursion(graph)

def check_no_heap(graph:Graph, roles:Roles, project_dir:str) -> list[Finding]:
  """Each call from the code of the project into the heap, of VRTS or of the C library."""
  heap, found = roles.heap | set(HEAP_C), []
  for caller, callees in graph.calls.items():
    fn = graph.functions.get(caller)
    if fn is None or not PATH.is_under(PATH.local(fn.path), project_dir): continue
    for callee, site in callees:
      if named(graph, callee) not in heap: continue
      path, line, col = place(site)
      found.append(Finding("no-heap", PATH.local(path), line, col,
        f"project takes the heap: `{named(graph, callee)}`", fn.name, RULES["no-heap"].refs))
  return found

def calls(graph:Graph, title:str, callee:str) -> bool:
  """`title` calls `callee` itself, not through another function."""
  return any(name == callee for name, _ in graph.calls.get(title, []))

def cycles(graph:Graph) -> list[list[str]]:
  """Titles of compiled functions calling each other round, a function calling itself included."""
  index, low, stack, on, found = {}, {}, [], set(), []
  def enter(title:str):
    index[title] = low[title] = len(index)
    stack.append(title)
    on.add(title)
  for root in graph.functions:
    if root in index: continue
    enter(root)
    work = [(root, iter(graph.calls.get(root, [])))]
    while work:
      title, pending = work[-1]
      for callee, _ in pending:
        if callee not in graph.functions: continue
        if callee not in index:
          enter(callee)
          work.append((callee, iter(graph.calls.get(callee, []))))
          break
        if callee in on: low[title] = min(low[title], index[callee])
      else:
        work.pop()
        if work: low[work[-1][0]] = min(low[work[-1][0]], low[title])
        if low[title] != index[title]: continue
        group = []
        while not group or group[-1] != title:
          group.append(stack.pop())
          on.discard(group[-1])
        if len(group) > 1 or calls(graph, title, title): found.append(group)
  return found

def check_recursion(graph:Graph) -> list[Finding]:
  """A finding a cycle, at its first function in file order: its threads get no stack bound."""
  found = []
  for group in cycles(graph):
    members = sorted((graph.functions[title] for title in group),
      key=lambda fn: (fn.path, fn.line))
    names = " → ".join(f"`{fn.name}`" for fn in members)
    found.append(at("recursion", members[0], f"calls come back round: {names}"))
  return found

#-------------------------------------------------------------------------------------------- Stack

def deepest(graph:Graph, root:str) -> tuple[int, set[str]]:
  """Bytes on the deepest call path from `root`, and why the graph may hide a deeper one."""
  memo:dict[str, tuple[int, set[str]]] = {}
  def walk(title:str, seen:frozenset) -> tuple[int, set[str]]:
    if title in memo: return memo[title]
    if title == INDIRECT: return 0, {"pointer"}
    fn = graph.functions.get(title)
    if fn is None: return 0, {"library"}
    below = 0
    holes = {"dynamic"} if fn.frame is None else set()
    for callee, _ in graph.calls.get(title, []):
      if callee in seen: continue # a cycle, which `recursion` reports
      depth, more = walk(callee, seen | {title})
      below = max(below, depth)
      holes |= more
    memo[title] = ((fn.frame or 0) + below, holes)
    return memo[title]
  return walk(root, frozenset())

def check_stacks(
  graph:Graph, threads:list[Thread],
  sizes:dict[str, int|None],
  frame:int,
  margin:bool = False,
) -> tuple[list[Stack], list[Finding]]:
  """
  Stack of every thread against its array, `frame` bytes of a switch on top of each.

  With `margin` a thread also keeps `STACK_MARGIN` of its array free.
  """
  stacks, found = [], []
  for thread in threads:
    fn = graph.functions.get(thread.title)
    if not fn: continue
    depth, holes = deepest(graph, thread.title)
    size = sizes.get(thread.stack)
    stacks.append(Stack(fn.name, depth, frame, size, holes))
    if size is None: continue
    used = depth + frame
    if used > size:
      found.append(at("stack-fit", fn,
        f"needs at least {used}B, its stack `{thread.stack}` has {size}B"))
    elif margin and used * 100 > size * (100 - STACK_MARGIN):
      found.append(at("stack-margin", fn,
        f"needs at least {used}B of {size}B in `{thread.stack}`, under {STACK_MARGIN}% left"))
  return stacks, found

#-------------------------------------------------------------------------------------------- Files

def own_header(path:str, text:str) -> Finding|None:
  """
  A source with a header beside it includes that header first.

  A file of a family or a board implements the general header: `dma_g0.c` starts with `dma.h`.
  `main.h` of a project is its configuration, which every header includes, so `main.c` is free.
  """
  stem = PATH.stem(path)
  if stem == "main" or not FILE.exists(PATH.with_suffix(path, ".h")): return None
  first = sources.first_include(text)
  if first and PATH.basename(first[0]) in (f"{stem}.h", f"{stem.rsplit('_', 1)[0]}.h"): return None
  return Finding("own-header-first", PATH.local(path), first[1] if first else 1, 1,
    f"`{stem}.h` comes first, so gcc holds its declarations against this file",
    refs=RULES["own-header-first"].refs)

def check_files(texts:dict[str, str]) -> list[Finding]:
  """Rules of files over `texts`, path to content, the sources and headers of one build."""
  found = []
  for path, text in texts.items():
    local, body = PATH.local(path), sources.code(text)
    declarations = sources.top_level(body)[0]
    if path.endswith(".h"):
      if not sources.guarded(text):
        found.append(Finding("header-guard", local, 1, 1, "header has no `#ifndef` guard",
          refs=RULES["header-guard"].refs))
      for start, statement in declarations:
        if not sources.defines_object(statement): continue
        found.append(Finding("header-object", local, sources.line_of(body, start), 1,
          "header defines a variable, so every file including it gets its own",
          refs=RULES["header-object"].refs))
      continue
    for start, statement in declarations:
      if not re.match(r"\s*extern\b", statement): continue
      found.append(Finding("extern-in-c", local, sources.line_of(body, start), 1,
        "`extern` belongs to the header of the file that defines it",
        refs=RULES["extern-in-c"].refs))
    if missing := own_header(path, text): found.append(missing)
  return found

class Trees:
  """
  Tree each file name lies in: Core, the project, code of others, or else the toolchain.

  Names come from whole folders, not the include path of one build,
  so the header of another chip family behind its `#if` is known too.
  Hidden folders stay out: `.tests` holds fakes named as modules of Core,
  and a project inside Core is a tree of its own.
  """
  def __init__(self, core_dir:str, pro_dir:str, vendor:list[tuple[str, str]]):
    self.pro_dir = pro_dir
    self.names:dict[str, set[str]] = {}
    for root, tree in ((core_dir, "Core"), (pro_dir, "project")):
      for rel in DIR.file_list(root, exts=[".c", ".h"], blacklist=[".git"], shape="rel"):
        if any(part.startswith(".") for part in rel.split("/")): continue
        own = "vendor" if vendor_code(f"{root}/{rel}", vendor) else tree
        self.names.setdefault(PATH.basename(rel), set()).add(own)

  def of_file(self, path:str) -> str:
    """Tree of a file of the build: the project or Core."""
    return "project" if PATH.is_under(path, self.pro_dir) else "Core"

  def of_name(self, name:str, own:str) -> str:
    """Tree of the file an include in a file of `own` names, `own` first."""
    found = self.names.get(PATH.basename(name), set())
    if "vendor" in found: return "vendor" # a model keeps the name of what it stands in for
    if own in found: return own
    return next(iter(found), "toolchain")

def check_includes(texts:dict[str, str], trees:Trees) -> list[Finding]:
  """
  The mark of each `#include` names a tree: quotes the tree of the file, angle brackets another.

  `main.h` and `boot.h` configure the build, so every tree takes them in quotes.
  """
  found = []
  for path, text in texts.items():
    local = PATH.local(path)
    own = trees.of_file(local)
    for mark, name, line in sources.includes(text):
      tree, base = trees.of_name(name, own), PATH.basename(name)
      quoted = base in CONFIG_HEADERS or tree == own
      if (mark == '"') == quoted: continue
      if base in CONFIG_HEADERS: where = "configures the build of every tree"
      elif tree == own: where = f"{PLACES[tree]}, as this file does"
      else: where = PLACES[tree]
      form = f'"{name}"' if quoted else f"<{name}>"
      found.append(Finding("include-form", local, line, 1, f"`{base}` {where}, so `{form}`",
        refs=RULES["include-form"].refs))
  return found

def check_config(texts:dict[str, str], every:dict[str, str], main_h:str) -> list[Finding]:
  """
  Knobs of headers, and the settings of `main.h` a project gives them.

  A knob is a `#define` open to a setting, and an include above it reaches `main.h`,
  directly or through another header: a file without it keeps the default alone.
  `texts` are the files checked, `every` all of the build, code of others among them.
  """
  local = {PATH.local(path): text for path, text in every.items()}
  headers:dict[str, list[str]] = {}
  for path, text in local.items(): headers.setdefault(PATH.basename(path), []).append(text)
  def reaches(names:list[str]) -> bool:
    seen, queue = set(names), deque(names)
    while queue:
      name = queue.popleft()
      if name == "main.h": return True
      for text in headers.get(name, []):
        for _, include, _ in sources.includes(text):
          if (base := PATH.basename(include)) in seen: continue
          seen.add(base)
          queue.append(base)
    return False
  found = []
  for path, text in ((PATH.local(path), text) for path, text in texts.items()):
    if not path.endswith(".h") or path == main_h: continue
    guard = sources.GUARD.search(sources.uncommented(text))
    above = sources.includes(text)
    for name, line, opened in sources.defines(text):
      if not opened or (guard and name == guard[1]): continue
      if reaches([PATH.basename(include) for _, include, at in above if at < line]): continue
      found.append(Finding("config-order", path, line, 1,
        f"no include above `{name}` reaches `main.h`, so a project cannot set it", name,
        RULES["config-order"].refs))
  return found + (unread_settings(local, main_h) if main_h in local else [])

def unread_settings(local:dict[str, str], main_h:str) -> list[Finding]:
  """
  Settings of `main.h` no file of the build reads, or one shuts out with a plain `#define`.

  A setting building on another reads it in `main.h` itself.
  """
  text = local[main_h]
  guard = sources.GUARD.search(sources.uncommented(text))
  settings:dict[str, int] = {}
  for name, line, _ in sources.defines(text):
    if name.startswith(FORGE_SETTINGS) or (guard and name == guard[1]): continue
    settings.setdefault(name, line)
  own = Counter(sources.WORD.findall(sources.uncommented(text)))
  defined = Counter(name for name, _, _ in sources.defines(text))
  read = {name for name in settings if own[name] > defined[name]}
  shut:dict[str, str] = {}
  for path, body in local.items():
    if path == main_h: continue
    hits = settings.keys() & set(sources.WORD.findall(sources.uncommented(body)))
    read |= hits
    for name, line, opened in (sources.defines(body) if hits else []):
      if name in hits and not opened: shut.setdefault(name, f"{path}:{line}")
  found = []
  for name, line in settings.items():
    if name in shut: why = f"`{shut[name]}` defines `{name}` without `#ifndef`"
    elif name not in read: why = f"no file of the build reads `{name}`"
    else: continue
    found.append(Finding("config-unread", main_h, line, 1, f"{why}, so setting it changes nothing",
      name, RULES["config-unread"].refs))
  return found
