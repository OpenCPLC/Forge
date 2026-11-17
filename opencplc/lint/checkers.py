# opencplc/lint/checkers.py

"""
The outside checks of `make lint`: cppcheck with its dump of types and values, gcc `-fanalyzer`.

Each sees a unit of the build, the application or the bootloader, with its own defines and paths,
and what they report becomes findings, with their ids and CWE numbers kept.
"""

import os, re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from xaeian import DIR, FILE, PATH
from xaeian.cmd import run, version
from ..config import WARNINGS
from .finding import Finding
from .dump import Unit as Facts, read_dump

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
# What gcc, the only compiler of a build, defines: a shift of a negative value extends its sign
CPPCHECK_OFF = ("shiftNegativeLHS",)
# Flags of the rules gcc checks, compiled into the sources of the project only:
# `static-scope` always, the others when `rules` of its `lint.yaml` turns them on
GCC_RULES = {
  "static-scope": ("-Wmissing-prototypes", "-Wmissing-variable-declarations"),
  "conversion": ("-Wconversion",),
  "double-promotion": ("-Wdouble-promotion",),
}
# Rule of each warning those flags raise: `-Wconversion` names its sign and float cases apart
OPTION_RULES = {
  "conversion": "conversion",
  "sign-conversion": "conversion",
  "float-conversion": "conversion",
  "double-promotion": "double-promotion",
  "missing-prototypes": "static-scope",
  "missing-variable-declarations": "static-scope",
}

@dataclass
class Unit:
  """C sources compiled under one set of defines and paths: the application or its bootloader."""
  name: str
  mcu_flags: str
  sources: list[str]
  defines: list[str]
  include_dirs: list[str]
  project: str = "" # folder of the project, the only code rules a project turns on look at

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

def run_cppcheck(
  unit:Unit, folder:str,
  style:bool = False,
  dump:bool = False,
  loads:tuple[str, ...] = (),
) -> tuple[list[Finding], list[Finding], list[Facts]]:
  """
  cppcheck over copies of the sources of `unit`: its checks of warnings, performance, portability.

  With `style` its checks of style run too, on the code of the project alone,
  and their findings come back apart from the rest.
  With `dump` the facts it proves of each source come back as well, `loads` naming the functions
  that write raw bytes into a buffer of their caller.
  cppcheck writes a dump beside the source it reads, so it reads copies under `folder`,
  and the trees of Core and of the project stay clean.
  """
  folder = f"{folder}/{unit.name}"
  copies = {}
  for source in unit.sources:
    copy = PATH.resolve(f"{folder}/src/{PATH.local(source)}")
    FILE.save(copy, FILE.load(source, binary=True))
    copies[copy] = PATH.local(source)
  enable = "warning,performance,portability" + (",style" if style else "")
  output = cppcheck(unit, folder, list(copies), f"--enable={enable}",
    "--template={file}:{line}:{column}: {severity}: {message} [{id}] [{cwe}]",
    *(["--dump"] if dump else []))
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
  facts = [read_dump(f"{copy}.dump", copies, loads) for copy in copies
    if dump and FILE.exists(f"{copy}.dump")]
  # What cppcheck wrote beside each copy goes, `.ctu-info` of an addon too. The copies stay
  # for the next run: Windows keeps a fresh `.c` open a moment for whoever indexes or scans it.
  FILE.remove([f"{copy}{suffix}" for copy in copies for suffix in (".dump", ".ctu-info")])
  return found, styled, facts

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
    target = f"{folder}/{PATH.local(source).replace('/', '_')}.o"
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
