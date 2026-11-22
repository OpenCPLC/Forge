# opencplc/lint/forms.py

"""
Rules of form over the code a project writes, each from a norm.

Rules of MISRA C go by number, as `misra-15.5`, and their reports come from the MISRA addon
of cppcheck; what the addon lacks, rules of BARR-C, Power of Ten and directives of MISRA C,
Forge reads from the same dump.
Core is the framework, tested on its own, and writes some of these forms on purpose,
as logs taking a format with arguments, so only what the project writes counts:
a macro of Core or of a header of others stays theirs where a file of the project expands it.
"""

import html, re
import xml.etree.ElementTree as ET
from typing import Callable
from xaeian import FILE
from .finding import Finding
from .dump import Tokens
from .rules import RULES

FUNCTION_LINES = 60 # lines of code in a function at most, one printed page of Power of Ten
# Integer types naming no width, which MISRA C wants behind a typedef that does:
# `int` has 16 bits on some chips.
# IEEE 754 fixes `float` and `double` on every target, so a typedef would only rename them,
# and plain `char` holds text.
BASIC = {"int", "short", "long", "signed", "unsigned"}
# Text of each rule the wiki names: the addon prints none without the MISRA document
MISRA_TEXTS = {
  "11.4": "cast between a pointer and an integer",
  "12.1": "operators of different precedence without parentheses",
  "14.4": "condition that is not Boolean",
  "15.1": "`goto`",
  "15.5": "`return` before the end of the function",
  "15.6": "body of `if`, `else` or a loop without braces",
  "15.7": "`else if` without a closing `else`",
  "16.4": "`switch` without `default`",
  "17.1": "feature of `<stdarg.h>`",
  "17.7": "returned value nobody reads",
  "18.4": "`+` or `-` on a pointer",
  "19.2": "`union`",
  "20.10": "`#` or `##` in a macro",
}

#--------------------------------------------------------------------------------------------- Dump

def trim_directives(dump:str, keep:Callable[[str], bool]):
  """
  `dump` without the directives of the files `keep` refuses, half of it when Core comes along.

  cppcheck writes each element on a line of its own, the tokens of a directive below it.
  """
  kept, dropping = [], False
  for line in FILE.load(dump, binary=True).splitlines(keepends=True):
    text = line.strip()
    if dropping:
      dropping = text != b"</directive>"
      continue
    if text.startswith(b"<directive "):
      file = re.search(rb'file="([^"]*)"', text)
      if not keep(html.unescape(file[1].decode()) if file else ""):
        dropping = not text.endswith(b"/>")
        continue
    kept.append(line)
  FILE.save(dump, b"".join(kept))

class Written:
  """
  A dump read for the code a project writes, its directives trimmed to those of the project.

  `place` gives the workspace path a file of the dump stands for, a copy its source,
  and `owns` whether that path is code of the project.
  """
  def __init__(self, dump:str, place:Callable[[str], str], owns:Callable[[str], bool]):
    data = FILE.load(dump, binary=True)
    # Raw tokens and values are a third of a dump and no rule of form reads them
    for tag in (b"rawtokens", b"valueflow"):
      start, end = data.find(b"<" + tag), data.find(b"</" + tag + b">")
      if start >= 0 and end > start: data = data[:start] + data[end + len(tag) + 3:]
    root = ET.fromstring(data)
    self.place, self.owns = place, owns
    self.directives = [(place(d.get("file", "")), int(d.get("linenr", "0")), d.get("str", ""))
      for d in root.iter("directive")]
    # Macros of the project: one it defines nowhere comes from Core or a header of others
    self.macros = {found[1] for _, _, text in self.directives
      if (found := re.match(r"#\s*define\s+(\w+)", text))}
    config = root.find("dump")
    self.tokens = Tokens(config) if config is not None else None
    # Places holding a token of their macro: a report of the addon there is theirs as well
    order = self.tokens.order if self.tokens else []
    self.shared = {self.at(t) for t in order if self.theirs(t)}

  def theirs(self, token:ET.Element) -> bool:
    """`token` comes from a macro the project does not define."""
    macro = token.get("macroName")
    return bool(macro) and macro not in self.macros

  def at(self, token:ET.Element) -> tuple[str, int, int]:
    """Workspace path, line and column of `token`."""
    return self.place(token.get("file", "")), int(token.get("linenr")), int(token.get("column"))

  def ours(self, token:ET.Element|None) -> bool:
    """`token` is written by the project: in a file of it and from no macro of others."""
    if token is None or not self.owns(self.place(token.get("file", ""))): return False
    return not self.theirs(token)

  def finding(self, rule:str, token:ET.Element, message:str, function:str="") -> Finding:
    """Finding of `rule` at `token`."""
    return Finding(rule, *self.at(token), message, function, RULES[rule].refs)

def spelled(token:ET.Element|None) -> str:
  """What `token` reads, "" for no token."""
  return token.get("str", "") if token is not None else ""

#-------------------------------------------------------------------------------------------- Rules

def check_continue(written:Written) -> list[Finding]:
  """`continue`, which BARR-C asks to avoid."""
  return [written.finding("no-continue", token, "`continue` skips the rest of the loop")
    for token in written.tokens.order if spelled(token) == "continue" and written.ours(token)]

def constant(tokens:Tokens, node:ET.Element|None) -> bool:
  """An expression of no variable and no call: a literal, an enumerator, or math of them."""
  if node is None or node.get("variable") or node.get("function"): return False
  if node.get("type") in ("number", "char", "string") or spelled(node) == "sizeof": return True
  # An enumerator, whose value cppcheck knows: a name it cannot resolve proves nothing
  if node.get("type") == "name": return bool(node.get("values"))
  left, right = tokens.get(node, "astOperand1"), tokens.get(node, "astOperand2")
  if spelled(node) == "(" and spelled(left) == "sizeof": return True
  if spelled(node) == "(" and node.get("isCast") != "true": return False # a call
  if left is None and right is None: return False
  return all(constant(tokens, side) for side in (left, right) if side is not None)

def check_constant_left(written:Written) -> list[Finding]:
  """`==` and `!=` with the constant right of them, where `=` typed for them would assign."""
  found, tokens = [], written.tokens
  for token in tokens.order:
    if spelled(token) not in ("==", "!=") or not written.ours(token): continue
    left, right = tokens.get(token, "astOperand1"), tokens.get(token, "astOperand2")
    if not constant(tokens, right) or constant(tokens, left): continue
    found.append(written.finding("constant-left", token,
      f"`{spelled(token)}` has its constant on the right"))
  return found

def check_length(written:Written) -> list[Finding]:
  """Functions over `FUNCTION_LINES` lines holding code, braces of blocks inside included."""
  found, tokens = [], written.tokens
  for scope in tokens.scopes.values():
    if scope.get("type") != "Function": continue
    start, end = tokens.by_id.get(scope.get("bodyStart")), tokens.by_id.get(scope.get("bodyEnd"))
    if start is None or end is None or not written.ours(start): continue
    inside = tokens.order[tokens.index[start.get("id")] + 1:tokens.index[end.get("id")]]
    lines = {t.get("linenr") for t in inside if t.get("file") == start.get("file")}
    if len(lines) <= FUNCTION_LINES: continue
    function = tokens.functions.get(scope.get("function") or "")
    head = tokens.by_id.get(function.get("token")) if function is not None else None
    name = scope.get("className", "")
    found.append(written.finding("function-length", head if head is not None else start,
      f"`{name}` holds {len(lines)} lines of code, over {FUNCTION_LINES}", name))
  return found

def plain(token:ET.Element) -> str:
  """
  Type `token` names without a width, "" for any other.

  cppcheck folds a sign into the word after it, so `unsigned char` reads as a `char` with a sign,
  and a typedef it spells out keeps its name aside, which passes.
  """
  word = spelled(token)
  if token.get("originalName") or (word not in BASIC and word != "char"): return ""
  sign = {"isUnsigned": "unsigned ", "isSigned": "signed "}
  signed = next((text for flag, text in sign.items() if token.get(flag) == "true"), "")
  return signed + word if word in BASIC or signed else ""

def widthless(tokens:Tokens, first:ET.Element|None, last:ET.Element|None) -> list[str]:
  """Types naming no width from `first` to `last`."""
  if first is None or last is None: return []
  span = tokens.order[tokens.index[first.get("id")]:tokens.index[last.get("id")] + 1]
  return [word for word in map(plain, span) if word]

def declared_by_project(written:Written, function:ET.Element|None) -> bool:
  """`function` is declared by the project, so its types are the project's to choose."""
  if function is None: return True
  head = written.tokens.by_id.get(function.get("tokenDef") or function.get("token"))
  return written.ours(head)

def typed_by_project(written:Written, variable:ET.Element) -> bool:
  """The type of `variable` is the project's choice: no parameter of `main` or of a Core API."""
  if variable.get("access") != "Argument": return True
  scope = written.tokens.scopes.get(variable.get("scope") or "")
  owner = written.tokens.functions.get(scope.get("function") or "") if scope is not None else None
  if owner is not None and owner.get("name") == "main": return False
  return declared_by_project(written, owner)

def return_type(tokens:Tokens, head:ET.Element) -> ET.Element|None:
  """First token of the words before the name `head` of a function, `None` when none are."""
  first = None
  before = tokens.next(head, -1)
  while before is not None and (before.get("type") == "name" or spelled(before) == "*"):
    first, before = before, tokens.next(before, -1)
  return first

def check_fixed_width(written:Written) -> list[Finding]:
  """
  Variables, fields, parameters and returns typed `int`, `short`, `long` or a `char` with a sign.

  `main` keeps its `int`, and a function Core declares keeps the types Core gave it.
  """
  found, tokens = [], written.tokens
  for variable in tokens.variables.values():
    name = tokens.by_id.get(variable.get("nameToken"))
    if not written.ours(name) or not typed_by_project(written, variable): continue
    first = tokens.by_id.get(variable.get("typeStartToken"))
    words = widthless(tokens, first, tokens.by_id.get(variable.get("typeEndToken")))
    if not words: continue
    found.append(written.finding("fixed-width", name,
      f"`{spelled(name)}` is `{' '.join(words)}`, which names no width"))
  for function in tokens.functions.values():
    head = tokens.by_id.get(function.get("token") or function.get("tokenDef"))
    if function.get("name") == "main" or not written.ours(head): continue
    if not declared_by_project(written, function): continue
    words = widthless(tokens, return_type(tokens, head), tokens.next(head, -1))
    if not words: continue
    found.append(written.finding("fixed-width", head,
      f"`{function.get('name')}` returns `{' '.join(words)}`, which names no width"))
  return found

def check_function_macro(written:Written) -> list[Finding]:
  """Macros with parameters, where a function would do."""
  found = []
  for path, line, text in written.directives:
    if not written.owns(path) or not (macro := re.match(r"#\s*define\s+(\w+)\(", text)): continue
    found.append(Finding("no-function-macro", path, line, 1,
      f"`{macro[1]}` is a macro with parameters", refs=RULES["no-function-macro"].refs))
  return found

def check_function_pointer(written:Written) -> list[Finding]:
  """Variables, fields and parameters pointing to a function, typedefs spelled out by cppcheck."""
  found, tokens = [], written.tokens
  for variable in tokens.variables.values():
    name = tokens.by_id.get(variable.get("nameToken"))
    if not written.ours(name): continue
    if spelled(tokens.next(name, -1)) != "*" or spelled(tokens.next(name, -2)) != "(": continue
    after = tokens.next(name)
    while spelled(after) == "[": # an array of them
      after = tokens.next(tokens.by_id.get(after.get("link"), after))
    if spelled(after) != ")" or spelled(tokens.next(after)) != "(": continue
    found.append(written.finding("no-function-pointer", name,
      f"`{spelled(name)}` points to a function"))
  return found

OWN_CHECKS = {
  "no-continue": check_continue,
  "constant-left": check_constant_left,
  "function-length": check_length,
  "fixed-width": check_fixed_width,
  "no-function-macro": check_function_macro,
  "no-function-pointer": check_function_pointer,
}

def misra_findings(written:Written, reports:list[dict]) -> list[Finding]:
  """Reports of the MISRA addon on code of the project, those at a macro of others left out."""
  found = []
  for report in reports:
    where = (written.place(report.get("file", "")), int(report["linenr"]), int(report["column"]))
    if not written.owns(where[0]) or where in written.shared: continue
    number = report["errorId"].removeprefix("c2012-")
    found.append(Finding(f"misra-{number}", *where,
      MISRA_TEXTS.get(number, "breaks the rule"), refs=f"MISRA {number}"))
  return found

def check_forms(
  dumps:list[str],
  place:Callable[[str], str], owns:Callable[[str], bool],
  rules:set[str],
  reports_of:Callable[[str], list[dict]],
) -> list[Finding]:
  """
  Findings of `rules` over the dumps of the sources of a project, their directives trimmed.

  `place` gives the workspace path a file of a dump stands for, `owns` whether it is the project's,
  and `reports_of` what the MISRA addon reported over a dump.
  """
  found = []
  for dump in dumps:
    written = Written(dump, place, owns)
    if written.tokens is None: continue
    for rule in sorted(rules & OWN_CHECKS.keys()): found += OWN_CHECKS[rule](written)
    found += misra_findings(written, reports_of(dump))
  return found
