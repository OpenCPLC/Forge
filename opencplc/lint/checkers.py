# opencplc/lint/checkers.py

"""
The outside checks of `make lint`: cppcheck with its dump of types and values, gcc `-fanalyzer`.

Each sees a unit of the build, the application or the bootloader, with its own defines and paths,
and what they report becomes findings, with their ids and CWE numbers kept.
"""

import os, re, sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable
from xaeian import DIR, FILE, JSON, PATH
from xaeian.cmd import run, version, which
from ..config import WARNINGS
from ..utils import tree_path
from .finding import Finding
from .dump import Unit as Facts, configured, read_dump
from .forms import check_forms, trim_directives
from .rules import MISRA_NAME

CPPCHECK = re.compile(r"^(.+?):(\d+):(\d+): (\w+): (.*) \[(\w+)\] \[(\d+)\]$")
GCC = re.compile(r"^(.+?):(\d+):(\d+): warning: (.*?)(?: \[(CWE-\d+)\])? \[-W([\w=-]+)\]$")
ERROR = re.compile(r"^(.+?):(\d+):(\d+): (?:fatal )?error: (.*)$")
CPPCHECK_MIN = (2, 17) # the oldest whose dump the rules on values are tested against
GCC_MIN = (14,) # the oldest with `-Wmissing-variable-declarations` of `static-scope`
# The symbol a warning of `static-scope` names, in the quotes of the locale gcc runs in
SYMBOL = re.compile(r"for [‘'](\w+)[’']")
SEVERITIES = ("error", "warning", "style", "performance", "portability") # `information` is none
# Noise in firmware: every thread loop is a `while(1)`, and `print` parses its own format
ANALYZER = ["-fanalyzer", "-Wno-analyzer-infinite-loop", "-Wno-analyzer-va-arg-type-mismatch"]
# Checks of cppcheck left out, each one wrong for this code
CPPCHECK_OFF = (
  "shiftNegativeLHS", # gcc, the only compiler of a build, defines it: the sign extends
  # It takes `x = (int16_t)x` of a `uint16_t x` for the value `x` had,
  # though from `0x8000` the cast changes it:
  # every finding of it in projects was of that kind, and a fix breaks code.
  "redundantAssignment",
)
# Flags of the rules gcc checks, compiled into the sources of the project only
GCC_RULES = {
  "static-scope": ("-Wmissing-prototypes", "-Wmissing-variable-declarations"),
  "conversion": ("-Wconversion",),
}
# Rule of each warning those flags raise: `-Wconversion` names its sign and float cases apart
OPTION_RULES = {
  "conversion": "conversion",
  "sign-conversion": "conversion",
  "float-conversion": "conversion",
  "missing-prototypes": "static-scope",
  "missing-variable-declarations": "static-scope",
}
WORKERS = 8 # processes of the MISRA addon at once, each holding a whole dump in memory

@dataclass
class Unit:
  """C sources compiled under one set of defines and paths: the application or its bootloader."""
  name: str
  mcu_flags: str
  sources: list[str]
  defines: list[str]
  include_dirs: list[str]
  project: str = "" # folder of the project, the only code rules of form look at

  def flags(self) -> list[str]:
    """
    Flags its build compiles a source with, the optimization pinned to `-Og`.

    What the analyzer finds depends on it: `-O1` and above hide a leak and a double free.
    """
    return [*self.mcu_flags.split(), *(f"-D{d}" for d in self.defines),
      *(f"-I{d}" for d in self.include_dirs), "-Og", *WARNINGS]

  def owns(self, path:str) -> bool:
    """`path` is code of the project rather than of Core."""
    return bool(self.project) and PATH.is_under(path, self.project)

def predefined(unit:Unit, folder:str) -> str:
  """Macros gcc defines on its own for the chip, without which cppcheck stops at `#error`."""
  empty = f"{folder}/empty.c"
  FILE.save(empty, "")
  macros = run(["arm-none-eabi-gcc", *unit.mcu_flags.split(), "-dM", "-E", empty]).stdout
  FILE.save(f"{folder}/gcc.h", macros)
  return f"{folder}/gcc.h"

def cppcheck(unit:Unit, folder:str, sources:list[str], *options:str) -> str:
  """Output of cppcheck over `sources` with the defines and paths of `unit`."""
  listed = f"{folder}/sources.txt"
  FILE.save(listed, "\n".join(sources))
  macros = predefined(unit, folder)
  res = run([
    "cppcheck", "--std=c11", "--platform=arm32-wchar_t4", "--library=gnu", "--quiet",
    f"-j{os.cpu_count() or 1}", *options, *(f"--suppress={check}" for check in CPPCHECK_OFF),
    f"--include={macros}", f"--file-list={listed}",
    *(f"-D{d}" for d in unit.defines), *(f"-I{d}" for d in unit.include_dirs),
  ])
  return res.stderr + res.stdout

def misra_addon() -> str|None:
  """`misra.py` of the cppcheck on the path: beside it on Windows, in its tree elsewhere."""
  found = which("cppcheck")
  if not found: return None
  home = PATH.dirname(PATH.real(found))
  prefix = PATH.dirname(home)
  folders = [f"{home}/addons", f"{prefix}/share/cppcheck/addons", f"{prefix}/lib/cppcheck/addons"]
  # Debian keeps it in the folder of its architecture, as `lib/x86_64-linux-gnu`
  if DIR.exists(f"{prefix}/lib"):
    folders += [f"{lib}/cppcheck/addons" for lib in DIR.folder_list(f"{prefix}/lib")]
  return next((f"{f}/misra.py" for f in folders if FILE.exists(f"{f}/misra.py")), None)

def misra_rules(addon:str) -> set[str]:
  """Rules `addon` checks, as `15.5`, read from its source: each cppcheck brings its own."""
  numbers = {int(n) for n in re.findall(r"executeCheck\((\d+),", FILE.load(addon))}
  return {f"{n // 100}.{n % 100}" for n in numbers}

def python_command() -> list[str]:
  """How to run a script of Python: this interpreter, or `opencplc.exe`, which holds one."""
  return [sys.executable, "--python"] if getattr(sys, "frozen", False) else [sys.executable]

def misra_command(addon:str, rules:set[str]) -> list[str]:
  """`addon` over a dump with every rule but `rules` suppressed, which it then never runs."""
  quiet = ",".join(sorted(misra_rules(addon) - rules))
  return [*python_command(), addon, "--cli", *(["--suppress-rules", quiet] if quiet else [])]

def misra_reports(command:list[str], dump:str) -> list[dict]:
  """Reports `command` of the MISRA addon gives over `dump`, those naming a rule."""
  lines = run([*command, dump]).stdout.splitlines()
  reports = [JSON.parse(line) for line in lines if line.startswith("{")]
  # Lines of its log and of a configuration it misses carry no rule
  return [r for r in reports if str(r.get("errorId", "")).startswith("c2012-")]

def placer(copies:dict[str, str]) -> Callable[[str], str]:
  """Workspace path of a file a dump names, a copy giving its source, worked out once a name."""
  places:dict[str, str] = {}
  def place(file:str) -> str:
    if file not in places:
      path = PATH.normalize(file)
      places[file] = copies.get(path) or PATH.local(path)
    return places[file]
  return place

def form_findings(
  dumps:list[str], copies:dict[str, str],
  owns:Callable[[str], bool],
  forms:frozenset[str],
) -> list[Finding]:
  """
  Rules of form `forms` over the dumps of the sources of a project.

  Directives of files outside the project leave each dump first, which halves it.
  The MISRA addon runs a process a dump while Forge reads the same dumps for its own rules.
  """
  place = placer(copies)
  for dump in dumps: trim_directives(dump, lambda file: owns(place(file)))
  numbers = {name.removeprefix("misra-") for name in forms if MISRA_NAME.match(name)}
  addon = misra_addon() if numbers else None
  with ThreadPoolExecutor(min(os.cpu_count() or 1, WORKERS)) as pool:
    jobs = {}
    if addon:
      command = misra_command(addon, numbers)
      jobs = {dump: pool.submit(misra_reports, command, dump) for dump in dumps}
    reports_of = lambda dump: jobs[dump].result() if dump in jobs else []
    return check_forms(dumps, place, owns, set(forms), reports_of)

def run_cppcheck(
  unit:Unit, folder:str,
  facts:bool = False,
  loads:tuple[str, ...] = (),
  forms:frozenset[str] = frozenset(),
) -> tuple[list[Finding], list[Finding], list[Facts], list[str]]:
  """
  cppcheck over copies of the sources of `unit`: its checks of warnings, performance, portability
  and style, findings of the last on the code of the project alone and apart from the rest.

  With `facts` the facts it proves of each source come back as well, `loads` naming the functions
  that write raw bytes into a buffer of their caller.
  Rules of form, `forms`, read the dumps of the sources of the project before they go,
  their findings among the first list under their own names.
  Sources whose dump holds nothing come back last, stopped by an `#error` or an unknown macro.
  cppcheck writes a dump beside the source it reads, so it reads copies under `folder`,
  and the trees of Core and of the project stay clean.
  """
  folder = f"{folder}/{unit.name}"
  copies, origins = {}, {}
  for source in unit.sources:
    copy = PATH.resolve(f"{folder}/src/{tree_path(source)}")
    FILE.save(copy, FILE.load(source, binary=True))
    copies[copy] = PATH.local(source)
    origins[copy] = source
  output = cppcheck(unit, folder, list(copies), "--enable=warning,performance,portability,style",
    "--template={file}:{line}:{column}: {severity}: {message} [{id}] [{cwe}]", "--dump")
  found, styled = [], []
  for line in output.splitlines():
    report = CPPCHECK.match(line)
    if not report or report[4] not in SEVERITIES: continue
    path = PATH.normalize(report[1])
    refs = f"CWE-{report[7]}" if report[7] != "0" else ""
    finding = Finding(report[6], copies.get(path) or PATH.local(path), int(report[2]),
      int(report[3]), report[5], refs=refs)
    if report[4] != "style": found.append(finding)
    elif unit.owns(finding.path): styled.append(finding)
  proved, unread = [], []
  for copy in copies:
    dump = f"{copy}.dump"
    if not FILE.exists(dump) or not configured(dump): unread.append(origins[copy])
    elif facts: proved.append(read_dump(dump, copies, loads))
  if forms and unit.project:
    owned = [f"{copy}.dump" for copy in copies
      if unit.owns(copies[copy]) and origins[copy] not in unread]
    found += form_findings(owned, copies, unit.owns, forms)
  # What cppcheck wrote beside each copy goes, `.ctu-info` of an addon too.
  # The copies stay for the next run:
  # Windows keeps a fresh `.c` open a moment for whoever indexes or scans it.
  FILE.remove([f"{copy}{suffix}" for copy in copies for suffix in (".dump", ".ctu-info")])
  return found, styled, proved, unread

def too_old(command:str, least:tuple[int, ...]) -> str|None:
  """Version of the tool run as `command` when below `least`, `None` when new enough."""
  found = version(command) or "?"
  parts = tuple(int(part) for part in re.findall(r"\d+", found)[:2])
  return found if parts < least else None

def run_analyzer(unit:Unit, folder:str, rules:set[str]) -> list[Finding]:
  """
  Every source of `unit` compiled again with `-fanalyzer`, every warning of gcc a finding.

  All of them each time, so the verdict never hangs on what the last build happened to rebuild.
  The flags of `rules` reach the sources of the project only, and so do their findings.
  """
  folder = f"{folder}/{unit.name}"
  DIR.ensure(folder, is_file=False)
  flags = unit.flags() + ANALYZER + ["-fdiagnostics-plain-output"]
  extra = [flag for rule in sorted(rules & GCC_RULES.keys()) for flag in GCC_RULES[rule]]
  def compile_one(source:str) -> tuple[str, int, str]:
    target = f"{folder}/{tree_path(source).replace('/', '_')}.o"
    own = extra if unit.owns(source) else []
    res = run(["arm-none-eabi-gcc", "-c", *flags, *own, source, "-o", target])
    return source, res.returncode, res.stderr
  with ThreadPoolExecutor(os.cpu_count()) as pool:
    outputs = list(pool.map(compile_one, unit.sources))
  found = {}
  for source, code, out in outputs:
    # A source gcc could not compile was never analyzed, which no warning would tell
    if not code: continue
    error = next(filter(None, map(ERROR.match, out.splitlines())), None)
    if error: where = (PATH.local(PATH.normalize(error[1])), int(error[2]), int(error[3]))
    else: where = (PATH.local(source), 1, 1)
    stop = error[4] if error else f"gcc ends with code {code}"
    found[("analyzer", *where)] = Finding("analyzer", *where, f"`-fanalyzer` stops: {stop}")
  for line in (line for _, _, out in outputs for line in out.splitlines()):
    if not (warning := GCC.match(line)): continue
    option = warning[6]
    rule = OPTION_RULES.get(option, f"W{option}")
    path = PATH.local(PATH.normalize(warning[1]))
    if option in OPTION_RULES and not unit.owns(path): continue
    # Named for an exception, a variable too, which no function body holds
    symbol = SYMBOL.search(warning[4]) if rule == "static-scope" else None
    finding = Finding(rule, path, int(warning[2]), int(warning[3]), warning[4],
      symbol[1] if symbol else "", warning[5] or "")
    # A header warns once for every source including it
    found[(finding.rule, finding.path, finding.line, finding.col)] = finding
  return list(found.values())
