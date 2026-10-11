# opencplc/runner.py

"""
Test programs of `make test`, run one after another, `--test`.

Each starts in a clean folder of its own and gets `TEST_TIMEOUT_s`,
so a hang fails the run instead of stopping it.
A program ends with a line counting its checks, `12 OK` or `8 OK, 2 ERR`.
Each program gets one line, a failed one its output below as it printed it, and the run a total.
A program asked for alone shows its output whatever the verdict.
"""

import os, re, subprocess, time
from xaeian import Print, Color as c, DIR, PATH

p = Print()

TEST_TIMEOUT_s = 60 # a hang, not a slow test: power cuts at every flash write take seconds
SUMMARY = re.compile(r"(\d+) OK(?:, (\d+) ERR)?")
EXE_EXT = ".exe" if os.name == "nt" else ""

def run_one(build:str, name:str) -> tuple[int|None, int, str, list[str]]:
  """
  One program in its own clean folder.

  Returns checks passed, `None` when it left no counts, checks failed,
  why it failed beyond its counts, and its output above them.
  """
  # beside the program, under a name that a program without `.exe` on Linux cannot take
  folder = PATH.resolve(f"{build}/{name}.run", read=False)
  if DIR.exists(folder): DIR.remove(folder, force=True)
  DIR.ensure(folder, is_file=False)
  exe = PATH.resolve(f"{build}/{name}{EXE_EXT}")
  # one stream keeps a `panic` on stderr in its place,
  # bytes decode leniently: a test may print any byte, and `xaeian.cmd.run` would refuse it
  try:
    res = subprocess.run([exe], cwd=folder, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
      timeout=TEST_TIMEOUT_s)
  except subprocess.TimeoutExpired as e:
    out = (e.stdout or b"").decode(errors="replace")
    return None, 0, f"hangs, cut after {TEST_TIMEOUT_s}s", out.splitlines()
  lines = res.stdout.decode(errors="replace").splitlines()
  counts = SUMMARY.fullmatch(lines[-1].strip()) if lines else None
  if not counts: return None, 0, f"ended with code {res.returncode}", lines
  ok, err = int(counts[1]), int(counts[2] or 0)
  # misses explain their own exit code, an exit without them is the failure itself
  why = f"ended with code {res.returncode}" if res.returncode and not err else ""
  return ok, err, why, lines[:-1]

def fraction(passed:int, total:int) -> str:
  """`passed/total`: what passed in cream, magenta when short of the whole, the whole in grey."""
  return f"{c.CREAM if passed == total else c.MAGNTA}{passed}{c.END}{c.GREY}/{total}{c.END}"

def shown(name:str) -> str:
  """Program name with `test_` greyed, so the modules stand out down the list."""
  if not name.startswith("test_"): return name
  return f"{c.GREY}test_{c.END}{name.removeprefix('test_')}"

def run_tests(build:str, names:list[str]) -> int:
  """Programs `names` built in `build`: a line each and a total; `1` when any of them failed."""
  if not names: return 0
  start = time.perf_counter()
  passed_checks = all_checks = failed = 0
  for name in names:
    ok, err, why, output = run_one(build, name)
    passed = ok is not None and not err and not why
    line = shown(name)
    if ok is not None: line += f" {fraction(ok, ok + err)}"
    if why: line += f" {c.GREY}({why}){c.END}"
    if passed: p.ok(line)
    else: p.err(line)
    if len(names) == 1 or not passed:
      for text in output: p(text)
    passed_checks += ok or 0
    all_checks += (ok or 0) + err
    failed += not passed
  # a hang leaves no counts, so the programs stand beside the checks
  total = (f"Test programs {fraction(len(names) - failed, len(names))}, "
    f"checks {fraction(passed_checks, all_checks)} in {time.perf_counter() - start:.1f}s")
  if failed:
    p.err(total)
    return 1
  p.ok(total)
  return 0
