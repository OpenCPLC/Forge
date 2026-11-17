# opencplc/lint/command.py

"""
Runs of the analysis: `make lint` in full, and the lines every chip build prints after its link.

`run_lint` checks a resolved project and answers with an exit code.
`build_report` is quick enough for every build:
the stack of each thread and the rules of Forge, findings as warnings that stop nothing.
Both read the objects the linker took, named in the map beside the image,
so an object left behind by a removed source never counts.
"""

import re, time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from xaeian import Print, Color as c, FILE, PATH, fmt_list, fmt_path, grey
from xaeian.cmd import run
from ..model import Project
from ..runner import fraction
from .. import utils
from .finding import Finding
from .graph import load_graph, settle_weak, drop_unlinked
from .rules import (
  Bodies, Trees, Stack, GRAPH_RULES, FILE_RULES, TREE_RULES, VALUE_RULES, OPT_INS,
  load_roles, split_opt_ins, vendor_code, find_threads, hidden_calls, contexts, check_graph,
  check_stacks, check_files, check_includes, check_config,
)
from .values import merge, local_key, check_switches, check_status, check_volatile
from .lintfile import LINT, LintFileError, Waiver, read, exceptions, keep
from .checkers import (
  Unit, GCC_RULES, CPPCHECK_MIN, GCC_MIN, too_old, run_cppcheck, run_analyzer,
)
from .dump import Unit as Facts
from . import sources

p = Print()

LOAD = re.compile(r"^LOAD (.+\.o)$", re.M)
SYMBOL = re.compile(r"^[0-9a-fA-F]+ ([WV]) (\S+)$")
GRAPH_OPT_INS = ("no-heap", "stack-margin")
VALUE_OPT_INS = ("switch-enum-default", "switch-default", "status-used")

@dataclass
class Check:
  """What the rules of Forge give over one build."""
  found: list[Finding]
  stacks: list[Stack]
  # Rules that ran, a Core without `lint.yaml` keeps those of files only
  ran: tuple[str, ...]
  texts: dict[str, str]                            # sources and headers checked, as gcc wrote them
  irq: set[str] = field(default_factory=set)       # keys of the functions an interrupt runs
  thread: set[str] = field(default_factory=set)    # and of those a thread or `main` runs
  graphed: set[str] = field(default_factory=set)   # and of every function the call graph holds
  hidden: list[str] = field(default_factory=list)  # thread and interrupt starts a macro hides

def linked_objects(elf:str) -> list[str]:
  """Objects of the application the map beside `elf` names, no bootloader and no library."""
  build = PATH.dirname(PATH.local(elf))
  trees = [f"{build}/opencplc", f"{build}/project"]
  objects = LOAD.findall(FILE.load(PATH.with_suffix(elf, ".map")))
  return [o for o in objects if any(PATH.is_under(PATH.local(o), tree) for tree in trees)]

def beside(objects:list[str], suffix:str) -> list[str]:
  """Files gcc wrote next to `objects` under `suffix`, those that exist."""
  return [path for path in (PATH.with_suffix(o, suffix) for o in objects) if FILE.exists(path)]

def weak_titles(objects:list[str], sources_of:dict[str, str]) -> set[str]:
  """Graph titles of the `weak` definitions in `objects`, read from their symbols."""
  if not objects: return set()
  found = set()
  # A list of one object comes without the heading line `nm` gives each of several
  source = sources_of.get(PATH.normalize(objects[0]), "") if len(objects) == 1 else ""
  for line in run(["arm-none-eabi-nm", "--defined-only", *objects]).stdout.splitlines():
    if line.endswith(":") and not line.startswith(" "):
      source = sources_of.get(PATH.normalize(line[:-1]), "")
    elif (symbol := SYMBOL.match(line)) and source:
      found.add(f"{source}:{symbol[2]}")
  return found

def stack_sizes(elf:str) -> dict[str, int|None]:
  """Bytes of every symbol of the image; a name two files give two sizes stays unknown."""
  sizes = {}
  for line in run(["arm-none-eabi-nm", "-S", "--defined-only", elf]).stdout.splitlines():
    parts = line.split()
    if len(parts) != 4: continue
    name, size = parts[3], int(parts[1], 16)
    sizes[name] = size if sizes.get(name, size) == size else None
  return sizes

def build_texts(deps:list[str], core_dir:str, pro_dir:str) -> dict[str, str]:
  """Sources and headers of Core and the project the build compiled, code of others among them."""
  texts = {}
  for path in sources.build_files(deps):
    local = PATH.local(path)
    if PATH.is_under(local, core_dir) or PATH.is_under(local, pro_dir):
      texts[path] = FILE.load(path)
  return texts

def lint_opt_ins(pro_dir:str) -> tuple[set[str], list[str]]:
  """Rules `rules` of the `lint.yaml` of the project turns on, and its names no such rule has."""
  turned, unknown = split_opt_ins((read(pro_dir, core=False) or {}).get("rules", []))
  return set(turned), unknown

def forge_check(
  elf:str, core_dir:str, pro_dir:str, cpu:str,
  opt_ins:set[str]|None = None,
) -> Check:
  """
  Rules of Forge over a finished build, those of `opt_ins` the project turned on among them.

  A Core without `lint.yaml` leaves out `TREE_RULES`, VRTS and the stack,
  and a build without a call graph the last two.
  """
  opt_ins = opt_ins or set()
  roles = load_roles(core_dir, pro_dir)
  vendor = roles.vendor if roles else []
  objects = linked_objects(elf)
  every = build_texts(beside(objects, ".d"), core_dir, pro_dir)
  texts = {path: text for path, text in every.items() if not vendor_code(PATH.local(path), vendor)}
  found = check_files(texts)
  if roles is None: return Check(found, [], FILE_RULES, texts)
  found += check_includes(texts, Trees(core_dir, pro_dir, vendor))
  found += check_config(texts, every, f"{pro_dir}/main.h")
  files = FILE_RULES + TREE_RULES
  cis = beside(objects, ".ci")
  if not cis: return Check(found, [], files, texts)
  graph, described = load_graph(cis)
  graphed = [o for o in objects if FILE.exists(PATH.with_suffix(o, ".ci"))]
  sources_of = {PATH.normalize(o): source for o, source in zip(graphed, described)}
  settle_weak(graph, weak_titles(graphed, sources_of))
  sizes = stack_sizes(elf)
  drop_unlinked(graph, set(sizes))
  threads = find_threads(graph, texts, roles)
  stacks, misfits = check_stacks(graph, threads, sizes, 4 * roles.frame.get(cpu, 0),
    "stack-margin" in opt_ins)
  found += check_graph(graph, texts, threads, roles, opt_ins, pro_dir) + misfits
  irq, thread = contexts(graph, texts, threads, roles)
  ran = files + GRAPH_RULES + tuple(rule for rule in GRAPH_OPT_INS if rule in opt_ins)
  return Check(found, stacks, ran, texts, {local_key(t) for t in irq},
    {local_key(t) for t in thread}, {local_key(t) for t in graph.functions},
    hidden_calls(graph, texts, roles))

def load_all_waivers(core_dir:str, pro_dir:str) -> tuple[list[Waiver], list[str]]:
  """Exceptions of the Core and of the project, each for its own code."""
  waivers, refused = exceptions(read(core_dir, core=True), core_dir)
  more, bad = exceptions(read(pro_dir, core=False), pro_dir)
  return waivers + more, refused + bad

def stack_line(stack:Stack) -> str:
  """`STACK loop 556B / 2048B (27%)`: the deepest path with its switch frame, against the array."""
  used = stack.deepest + stack.frame
  notes = f"{used * 100 // stack.size}%" if stack.size else "array not found"
  if stack.holes: notes += ", at least"
  size = f" / {stack.size}B" if stack.size else ""
  return f"STACK {stack.thread} {c.GOLD}{used}B{c.END}{size} {grey(f'({notes})')}"

def hidden_text(where:str) -> str:
  """Warning for a thread or an interrupt started inside a macro, which the rules cannot read."""
  return f"Rules of threads and interrupts skip the call at {where}, a macro hides its arguments"

def build_report(elf:str, cpu:str, core:str, project:str):
  """
  After a link: the stack of each thread below FLASH and RAM, then the rules of Forge as warnings.

  Make passes `core` and `project` absolute, while Forge runs from the workspace.
  A rule name `lint.yaml` has no rule for, or a file Forge cannot take, waits for `make lint`.
  """
  core_dir, pro_dir = PATH.local(core), PATH.local(project)
  try:
    check = forge_check(elf, core_dir, pro_dir, cpu, lint_opt_ins(pro_dir)[0])
    waivers, _ = load_all_waivers(core_dir, pro_dir)
  except LintFileError as error:
    p.wrn(str(error))
    return
  for stack in check.stacks: p(stack_line(stack))
  for where in check.hidden: p.wrn(hidden_text(where))
  for finding in sorted(keep(check.found, waivers), key=lambda f: (f.path, f.line)):
    p.wrn(finding.text())

def units(pro:Project, vendor:list[tuple[str, str]]) -> list[Unit]:
  """
  The application and the bootloader behind it, the code Core carries from others left out.

  That code has its own project to check it, and the analyzer spends a minute on one such file.
  """
  def ours(paths:list[str]) -> list[str]:
    return [path for path in paths if not vendor_code(path, vendor)]
  found = [Unit("app", pro.mcu_flags, ours(pro.core_c_sources + pro.project_c_sources),
    pro.defines, pro.include_dirs, pro.pro_dir)]
  if pro.boot:
    found.append(Unit("boot", pro.mcu_flags, ours(pro.boot_c_sources), pro.boot_defines,
      pro.boot_include_dirs))
  return found

def stale(waiver:Waiver, files:list[str]) -> bool:
  """
  An exception silencing nothing at a place the build compiled.

  A place no file of the build matches stays quiet: Core serves many projects, each a part of it.
  """
  if waiver.used: return False
  return any(utils.glob_match(PATH.rel(path, waiver.root), waiver.place)
    for path in files if PATH.is_under(path, waiver.root))

def without_vendor(unit:Unit, vendor:list[tuple[str, str]]) -> Unit:
  """
  `unit` with the headers of others off its include path, as cppcheck reads it.

  cppcheck reports the same on Core without them in a third of the time,
  and the rules on values ask for the types of Core, while a chip header makes a dump tenfold.
  """
  ours = [d for d in unit.include_dirs if not vendor_code(f"{d}/_.h", vendor)]
  return replace(unit, include_dirs=ours)

def vector_entry(finding:Finding, handlers:tuple[str, ...]) -> bool:
  """`static-scope` at a handler of the vector table, which the startup code declares."""
  return finding.rule == "static-scope" and finding.function.endswith(handlers)

def vouching(waivers:list[Waiver]):
  """
  Whether an exception of `switch-enum` names the place an entry stands in,
  the check the code makes there out of reach of the proof; such an exception counts as used.
  """
  def vouched(entry) -> bool:
    stand = Finding("switch-enum", PATH.local(entry.path), entry.line, 1, "", entry.function)
    found = [waiver for waiver in waivers if waiver.explains(stand)]
    for waiver in found: waiver.used = True
    return bool(found)
  return vouched

def value_check(
  facts:list[Facts], check:Check, status:str,
  opt_ins:set[str], waivers:list[Waiver],
) -> dict[str, list[Finding]]:
  """Rules on types and proven values over the facts of every source of the application."""
  program = merge(facts)
  found = check_switches(program, opt_ins, vouching(waivers))
  found += check_volatile(program, check.irq, check.thread, check.graphed)
  if "status-used" in opt_ins: found += check_status(program, status)
  rules = VALUE_RULES + tuple(rule for rule in VALUE_OPT_INS if rule in opt_ins)
  return {rule: [f for f in found if f.rule == rule] for rule in rules}

def run_lint(pro:Project) -> int:
  """
  `make lint`: the rules of Forge, cppcheck and `-fanalyzer` over the build of `pro`.

  What no exception of `lint.yaml` explains prints the way a compiler prints a warning,
  and the last line counts the checks that found nothing, as `make test` counts its programs;
  `1` comes back while a finding is left or an exception lacks its reason.
  cppcheck installs without a question: `make lint` asks for it, at a console or under CI alike.
  """
  try:
    return lint(pro)
  except LintFileError as error:
    p.err(str(error))
    return 1

def lint(pro:Project) -> int:
  """`run_lint` on a project whose `lint.yaml` files Forge takes, `LintFileError` otherwise."""
  if pro.platform != "STM32":
    p.err(f"Lint checks a chip build, and {c.BLUE}{pro.name}{c.END} builds for this computer")
    return 1
  elf = f"{pro.build_dir}/{pro.target}.elf"
  if not FILE.exists(elf):
    p.err(f"No build of {c.BLUE}{pro.name}{c.END} to check")
    p.run(f"Build it with {utils.color_command('make')}")
    return 1
  opt_ins, unknown = lint_opt_ins(pro.pro_dir)
  if unknown:
    p.err(f"{fmt_path(f'{pro.pro_dir}/{LINT}')} turns on no rule named {fmt_list(unknown)}")
    p.run(f"Name rules under {c.SKY}rules{c.END} from {fmt_list(OPT_INS)}")
    return 1
  start = time.perf_counter()
  utils.ensure_packages(utils.LINT_TOOLS, True)
  for tool, least in (("cppcheck", CPPCHECK_MIN), ("arm-none-eabi-gcc", GCC_MIN)):
    if old := too_old(tool, least):
      p.err(f"Lint needs {tool} {'.'.join(map(str, least))} or newer, and finds {old}")
      p.run(f"Install a newer {tool} and run again")
      return 1
  folder = f"{pro.build_dir}/lint"
  check = forge_check(elf, pro.core_dir, pro.pro_dir, pro.cpu, opt_ins)
  roles = load_roles(pro.core_dir, pro.pro_dir)
  if "irq-yield" not in check.ran:
    p.wrn(f"VRTS and the stack need {fmt_path(f'{pro.core_dir}/{LINT}')} "
      "and a call graph in the build")
  for where in check.hidden: p.wrn(hidden_text(where))
  vendor = roles.vendor if roles else []
  loads = tuple(roles.load) if roles else ()
  handlers = tuple(roles.irq_handlers) if roles else ()
  local = {PATH.local(path): text for path, text in check.texts.items()}
  bodies = Bodies(local) # the function an exception names, for outside findings too
  checks = {rule: [f for f in check.found if f.rule == rule] for rule in check.ran}
  compiled = {rule for rule in GCC_RULES if rule in opt_ins or rule not in OPT_INS}
  groups = ["cppcheck", "analyzer", *sorted(compiled | (opt_ins & {"cppcheck-style"}))]
  outside = {name: {} for name in groups}
  def take(group:str, finding:Finding):
    # Headers of others reach every source, and both units share Core
    if vendor_code(finding.path, vendor): return
    function = finding.function or bodies.around(finding.path, finding.line)
    finding = replace(finding, function=function)
    if vector_entry(finding, handlers): return
    outside[group][(finding.rule, finding.path, finding.line, finding.col)] = finding
  every = units(pro, vendor)
  waivers, refused = load_all_waivers(pro.core_dir, pro.pro_dir)
  values = "irq-yield" in check.ran # VRTS and the stack ran, so the contexts are known
  # The analyzer only waits for its gcc processes, so it runs while the dumps are read
  with ThreadPoolExecutor(1) as background:
    analyzing = background.submit(
      lambda: [finding for unit in every for finding in run_analyzer(unit, folder, compiled)])
    for index, unit in enumerate(every):
      found, styled, facts = run_cppcheck(without_vendor(unit, vendor), folder,
        "cppcheck-style" in opt_ins, dump=values and not index, loads=loads)
      for finding in found: take("cppcheck", finding)
      for finding in styled: take("cppcheck-style", finding)
      if facts: checks |= value_check(facts, check, roles.status, opt_ins, waivers)
    for finding in analyzing.result():
      take(finding.rule if finding.rule in GCC_RULES else "analyzer", finding)
  checks |= {name: list(items.values()) for name, items in outside.items()}
  left = {name: keep(items, waivers) for name, items in checks.items()}
  shown = sorted((f for items in left.values() for f in items), key=lambda f: (f.path, f.line))
  for finding in shown: p(finding.text())
  for waiver in (w for w in waivers if stale(w, list(local))):
    p.wrn(f"Exception {waiver.text()} silences nothing {grey(f'({waiver.root}/{LINT})')}")
  for where in refused: p.err(f"Exception without a reason {grey(f'({where})')}")
  # Checks, as the summary of `make test` counts its programs: a check with findings fails once
  failed = sum(bool(items) for items in left.values())
  took = time.perf_counter() - start
  summary = f"Lint checks {fraction(len(left) - failed, len(left))} in {took:.1f}s"
  if failed or refused:
    p.err(summary)
    return 1
  p.ok(summary)
  return 0
