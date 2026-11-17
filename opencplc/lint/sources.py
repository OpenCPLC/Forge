# opencplc/lint/sources.py

"""
What the rules read from the C text: files of a build, declarations, function bodies and calls.

Files come from the `.d` files of `-MMD`, the very list gcc followed.
Comments and literals, split off by `scan` of xaeian, turn into spaces before a search.
Every line keeps its place, so a match never comes from prose and its line number is the real one.
"""

import re
from functools import cache
from xaeian import FILE
from xaeian.xstring import scan

C_TOKENS = {"quotes": "\"'", "esc": "\\", "line": "//", "block": ("/*", "*/")}
DIRECTIVE = re.compile(r"^[ \t]*#(?:[^\n]*\\\n)*[^\n]*", re.M) # with its continued lines
INCLUDE = re.compile(r'^[ \t]*#[ \t]*include[ \t]*([<"])([^>"]+)[>"]', re.M)
DEFINE = re.compile(r"[ \t]*#[ \t]*define[ \t]+(\w+)")
CONDITION = re.compile(r"[ \t]*#[ \t]*(if|ifdef|ifndef|elif|else|endif)\b")
OPENER = re.compile(r"\s*#\s*(?:ifndef\s+(\w+)|if\s*!\s*defined\s*\(?\s*(\w+))") # one line
GUARD = re.compile(r"^[ \t]*#[ \t]*ifndef[ \t]+(\w+)[ \t]*\n[ \t]*#[ \t]*define[ \t]+\1\b", re.M)
BRACES = re.compile(r"\{[^{}]*\}")
BLOCK = "\x00" # stands for a brace block once its content is gone
NOT_STORAGE = re.compile(r"\s*(?:typedef|extern|_Static_assert|static_assert)\b")
TAGGED = re.compile(r"\s*(?:struct|union|enum)\b\s*\w*\s*\x00?")
WORD = re.compile(r"[A-Za-z_]\w*")
CALL = re.compile(r"[A-Za-z_]\w*\s*\(") # a name and the `(` of its call
ATTRIBUTE = re.compile(r"__attribute__\s*\(")

def blank(text:str) -> str:
  """`text` as spaces, its newlines kept."""
  return re.sub(r"[^\n]", " ", text)

@cache # includes, guards and defines each read the same file
def uncommented(text:str) -> str:
  """`text` without comments, literals left, so `#include "x.h"` still names its file."""
  return "".join(blank(chunk) if kind == "comment" else chunk
    for kind, chunk in scan(text, **C_TOKENS))

@cache # rules and call sites read one file 2 times on average, a third of `forge_check` saved
def code(text:str) -> str:
  """What the compiler parses of `text`, near enough: no comments, literals or directives."""
  text = "".join(chunk if kind == "text" else blank(chunk)
    for kind, chunk in scan(text, **C_TOKENS))
  return DIRECTIVE.sub(lambda directive: blank(directive.group()), text)

def line_of(text:str, offset:int) -> int:
  """Line of `offset`, counted from `1`."""
  return text.count("\n", 0, offset) + 1

def offset_of(text:str, line:int, col:int) -> int:
  """Offset of a line and a column, both counted from `1`."""
  start = 0
  for _ in range(line - 1): start = text.index("\n", start) + 1
  return start + col - 1

def build_files(paths:list[str]) -> list[str]:
  """Sources and headers named by the `.d` files `paths`, each once, in the order found."""
  found = {}
  for path in paths:
    if not FILE.exists(path): continue
    for word in FILE.load(path).replace("\\\n", " ").split():
      word = word.rstrip(":")
      if word.endswith((".c", ".h")): found[word] = None
  return list(found)

def closing(text:str, start:int) -> int:
  """Offset just past the `)` closing the `(` at `start`, the end of `text` when none does."""
  depth = 0
  for index in range(start, len(text)):
    if text[index] == "(": depth += 1
    elif text[index] == ")":
      depth -= 1
      if not depth: return index + 1
  return len(text)

def without_attributes(text:str) -> str:
  """`text` with every `__attribute__((...))` gone, nested parentheses and all."""
  while found := ATTRIBUTE.search(text):
    text = text[:found.start()] + " " + text[closing(text, found.end() - 1):]
  return text

def function_name(head:str) -> str:
  """Name a definition head gives its function, "" for the head of anything else."""
  head = without_attributes(head).rstrip()
  if not head.endswith(")"): return ""
  depth = 0
  for index in range(len(head) - 1, -1, -1):
    if head[index] == ")": depth += 1
    elif head[index] == "(":
      depth -= 1
      if not depth:
        name = re.search(r"(\w+)\s*$", head[:index])
        return name[1] if name else ""
  return ""

def top_level(text:str) -> tuple[list[tuple[int, str]], list[tuple[str, int, int]]]:
  """
  What stands at file scope of `text` cut to code.

  Declarations, each with the offset where it starts, and function definitions,
  each with its name and the first and last line of its body.
  Only `{`, `}` and `;` steer the walk, so nothing inside a body counts.
  """
  declarations, functions = [], []
  depth, start, name, opened = 0, 0, "", 0
  for mark in re.finditer(r"[{};]", text):
    if mark[0] == "{":
      if not depth: name, opened = function_name(text[start:mark.start()]), mark.start()
      depth += 1
    elif mark[0] == "}":
      depth = max(depth - 1, 0)
      if not depth and name:
        functions.append((name, line_of(text, opened), line_of(text, mark.start())))
        start, name = mark.end(), ""
    elif not depth:
      statement = text[start:mark.start()]
      declarations.append((start + len(statement) - len(statement.lstrip()), statement))
      start = mark.end()
  return declarations, functions

def call_args(text:str, line:int, col:int) -> list[str]:
  """
  Arguments of the call written at a line and column of `text`, split at its own commas.

  None when no call is written there: a macro without parentheses expands into one elsewhere.
  """
  if line > text.count("\n") + 1: return []
  call = CALL.match(text, offset_of(text, line, col))
  if not call: return []
  start = call.end() - 1
  inside = text[start + 1:closing(text, start) - 1]
  args, depth, last = [], 0, 0
  for index, char in enumerate(inside):
    if char in "([{": depth += 1
    elif char in ")]}": depth -= 1
    elif char == "," and not depth:
      args.append(inside[last:index].strip())
      last = index + 1
  return args + [inside[last:].strip()]

def assigned(text:str, fields:list[str]) -> list[str]:
  """
  Functions `text` cut to code gives to `fields`, by `.field = fn` or `->field = fn`.

  The name is the last word of the value, as for an argument: a cast or `&` before it changes none.
  """
  names = "|".join(re.escape(f) for f in fields)
  found = []
  for match in re.finditer(rf"(?:\.|->)\s*(?:{names})\s*=(?!=)", text):
    words = WORD.findall(text[match.end():value_end(text, match.end())])
    if words: found.append(words[-1])
  return found

def value_end(text:str, start:int) -> int:
  """Offset where the value starting at `start` ends: a `;`, `,` or bracket outside its own."""
  depth = 0
  for index in range(start, len(text)):
    if text[index] in "([{": depth += 1
    elif text[index] in ")]}":
      if not depth: return index
      depth -= 1
    elif text[index] in ";," and not depth: return index
  return len(text)

def flatten(statement:str) -> str:
  """Every brace block of `statement`, nested ones first, as one `BLOCK` character."""
  while (flat := BRACES.sub(BLOCK, statement)) != statement: statement = flat
  return statement

def defines_object(statement:str) -> bool:
  """A declaration that sets storage aside: no type, prototype or `extern`."""
  flat = flatten(without_attributes(statement)).strip()
  if not flat or NOT_STORAGE.match(flat): return False
  declarator = flat.split("=", 1)[0]
  # A body with nothing after it defines a type, whatever macro qualifies it
  if declarator.rstrip().endswith(BLOCK): return False
  if "(" in declarator: return False # a prototype, or a pointer to a function
  if tagged := TAGGED.match(declarator): return bool(WORD.search(declarator[tagged.end():]))
  return len(WORD.findall(declarator)) >= 2

def first_include(text:str) -> tuple[str, int]|None:
  """File and line of the first `#include` of `text`, `None` without one."""
  text = uncommented(text)
  found = INCLUDE.search(text)
  return (found[2], line_of(text, found.start())) if found else None

def includes(text:str) -> list[tuple[str, str, int]]:
  """Every `#include` of `text`: its mark, `<` or `"`, the file it names, and its line."""
  text = uncommented(text)
  return [(found[1], found[2], line_of(text, found.start())) for found in INCLUDE.finditer(text)]

def defines(text:str) -> list[tuple[str, int, bool]]:
  """
  Every `#define` of `text`: its name, its line, and whether it is open to a setting.

  Open stands inside `#ifndef` of its own name, or `#if !defined`, at any depth,
  so a name defined before keeps its value.
  `#else` of such a block is not open.
  """
  found, frames = [], [] # each frame the name its `#ifndef` leaves open, "" for any other
  for number, line in enumerate(uncommented(text).split("\n"), 1):
    if condition := CONDITION.match(line):
      if condition[1] in ("if", "ifdef", "ifndef"):
        opener = OPENER.match(line)
        frames.append((opener[1] or opener[2]) if opener else "")
      elif condition[1] == "endif":
        if frames: frames.pop()
      elif frames: frames[-1] = ""
    elif define := DEFINE.match(line):
      found.append((define[1], number, define[1] in frames))
  return found

def guarded(text:str) -> bool:
  """A header shut against a second inclusion by `#ifndef` and `#define`, never `#pragma once`."""
  return GUARD.search(uncommented(text)) is not None
