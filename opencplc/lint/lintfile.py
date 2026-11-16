# opencplc/lint/lintfile.py

"""
The `lint.yaml` of a Core or of a project: roles of its API, code of others, rules, exceptions.

A Core gives the roles of VRTS in full, a project adds to their lists for its own drivers,
turns rules on and keeps exceptions for its own code.
A key the file has no place for is an error, so a misspelled one never passes in silence.
An exception is a place, a `.gitignore` pattern from the folder of the file with `:function`
for a rule of the graph, and a reason; one without a reason is refused,
and one that silences nothing is reported, so no exception outlives its code.

Example:
  rules: [no-heap, stack-margin]
  roles:
    irq:
      field: [OnFrame]
  vendor: [lib/thirdparty/*]
  except:
    thread-hold:
      main.c:calibrate: Measure needs 50ms of quiet bus, other threads wait
"""

from dataclasses import dataclass
from typing import Any
from xaeian import FILE, PATH, YAML
from ..utils import glob_match
from .finding import Finding

LINT = "lint.yaml" # in the root of a Core, and of a project that needs one
SECTIONS = ("roles", "vendor", "rules", "except")
NESTED = ("heap", "irq") # roles grouping others, `heap.any` and `irq.field` among them
# Roles a list of names gives, which a project extends for its own code
LISTS = (
  "yield", "hold", "log", "panic", "load",
  "heap.any", "irq.handler", "irq.start", "irq.field",
)
SINGLE = ("thread", "status", "heap.new", "heap.clear", "frame") # a Core sets each alone

class LintFileError(ValueError):
  """A `lint.yaml` Forge cannot take: its path and what is wrong with it."""

@dataclass
class Waiver:
  """One exception, from the `lint.yaml` of the folder `root`."""
  rule: str
  place: str     # `.gitignore` pattern from `root`
  function: str  # "" for every function of the place
  reason: str
  root: str      # workspace-relative
  used: bool = False

  def explains(self, finding:Finding) -> bool:
    """`finding` is the rule at the place this exception names."""
    if finding.rule != self.rule or not PATH.is_under(finding.path, self.root): return False
    if not glob_match(PATH.rel(finding.path, self.root), self.place): return False
    return not self.function or self.function == finding.function

  def text(self) -> str:
    """The exception as its file names it: rule and place."""
    return f"{self.rule} {self.place}" + (f":{self.function}" if self.function else "")

def flat(roles:dict) -> dict[str, Any]:
  """Roles under one level of keys, `irq.field` for `field` inside `irq`."""
  found = {}
  for key, value in roles.items():
    if key in NESTED and isinstance(value, dict):
      found |= {f"{key}.{inner}": item for inner, item in value.items()}
    else: found[key] = value
  return found

def names(path:str, key:str, value:Any) -> list[str]:
  """`value` as the list of names `key` holds, an error naming both when it is none."""
  if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
    raise LintFileError(f"{path}: `{key}` is a list of names")
  return value

def read(root:str, core:bool) -> dict|None:
  """
  `root/lint.yaml` checked against what it may hold, `None` when there is none.

  `core` lets the file set the roles a Core sets alone, and keeps `rules` out:
  rules are turned on by a project.
  """
  path = f"{root}/{LINT}"
  if not FILE.exists(path): return None
  try:
    data = YAML.load(path, {})
  except Exception as error:
    raise LintFileError(f"{path}: {error}") from error
  if not isinstance(data, dict): raise LintFileError(f"{path}: keys at the top, as `roles:`")
  for key in data:
    if key not in SECTIONS: raise LintFileError(f"{path}: no place for `{key}`")
  if core and "rules" in data: raise LintFileError(f"{path}: `rules` are turned on by a project")
  names(path, "vendor", data.setdefault("vendor", []))
  names(path, "rules", data.setdefault("rules", []))
  roles = data.setdefault("roles", {})
  if not isinstance(roles, dict): raise LintFileError(f"{path}: `roles` holds keys")
  for key, value in flat(roles).items():
    if key in LISTS: names(path, f"roles.{key}", value)
    elif key not in SINGLE: raise LintFileError(f"{path}: no role `{key}`")
    elif not core: raise LintFileError(f"{path}: role `{key}` is set by Core")
  if core and (missing := [key for key in LISTS + SINGLE if key not in flat(roles)]):
    raise LintFileError(f"{path}: no role `{missing[0]}`")
  exceptions = data.setdefault("except", {})
  if not isinstance(exceptions, dict) or not all(isinstance(v, dict) for v in exceptions.values()):
    raise LintFileError(f"{path}: `except` holds a rule, and under it a place with its reason")
  return data

def exceptions(data:dict|None, root:str) -> tuple[list[Waiver], list[str]]:
  """Exceptions of the `lint.yaml` of `root`, and the ones refused for a missing reason."""
  found, refused = [], []
  for rule, places in (data or {}).get("except", {}).items():
    for place, reason in places.items():
      pattern, _, function = str(place).partition(":")
      waiver = Waiver(str(rule), pattern, function, str(reason or "").strip(), root)
      if waiver.reason: found.append(waiver)
      else: refused.append(f"{root}/{LINT}: {waiver.text()}")
  return found, refused

def keep(findings:list[Finding], waivers:list[Waiver]) -> list[Finding]:
  """Findings no exception explains; an exception that explains one is marked used."""
  left = []
  for finding in findings:
    explained = [w for w in waivers if w.explains(finding)]
    for waiver in explained: waiver.used = True
    if not explained: left.append(finding)
  return left
