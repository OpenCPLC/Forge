# opencplc/headers.py

"""
main.h and boot.h of a project, as Forge reads and writes them.

main.h holds the `PRO_` settings of the application, boot.h the `BOOT_` ones it shares
with the bootloader, and each layer stays in its own file.
A project put behind the bootloader starts its boot.h from the template.
Forge writes single lines into them, and the rest of each file stays as it is.
"""

import re, sys
from datetime import datetime
from xaeian import Print, FILE, PATH, fmt_path, replace_map
from xaeian.xstring import scan
from .config import BOOT_H, BOOT_LINE
from .args import flag
from .templates import load_templates
from . import utils

p = Print()

# Settings of main.h Forge reads: the application and how Forge builds and signs it
MAIN_H_DEFINES = [
  "PRO_FRAMEWORK", "PRO_FLASH_kB", "PRO_RAM_kB", "PRO_OPT_LEVEL", "PRO_PLC", "PRO_DRIVERS",
  "PRO_SIGNING_KEY",
  "LOG_LEVEL", "SYS_CLOCK_FREQ",
]
DEFINE = re.compile(r"\s*#define\s+(\w+)")
PRO_DEFINE = re.compile(r"\s*#define\s+PRO_")
INCLUDE = re.compile(r"\s*#include\b")
BOOT_INCLUDE = re.compile(rf'\s*#include\s+"{re.escape(BOOT_H)}"')
BLANK = re.compile(r"[^\n]")

def code_lines(lines:list[str]) -> list[str]:
  """`lines` as C sees them: every comment blanked, so each line stays where it was."""
  parts = scan("\n".join(lines), quotes='"', esc="\\", line="//", block=("/*", "*/"))
  text = "".join(BLANK.sub(" ", chunk) if kind == "comment" else chunk for kind, chunk in parts)
  return text.split("\n")

def header_lines(lines:list[str]) -> list[str]:
  """Lines of main.h or boot.h as C reads them: no comment, continued lines joined, no indent."""
  return [ln.lstrip() for ln in utils.lines_clear(code_lines(lines), "//")]

def main_h_defines(lines:list[str]) -> dict:
  """`#define` entries Forge reads from main.h, its comments cleared already."""
  # Board and chip are flags without a value
  flags = [ln for ln in lines if re.fullmatch(r"\s*#define\s+PRO_(BOARD|CHIP)_\w+\s*", ln)]
  info = utils.get_vars(flags, ["PRO_BOARD", "PRO_CHIP"], "_", "#define", required=False)
  info |= utils.get_vars(lines, MAIN_H_DEFINES, " ", "#define", required=False)
  return info

def boot_included(lines:list[str]) -> bool:
  """`True` when main.h includes `boot.h`: the project runs behind the bootloader."""
  return any(BOOT_INCLUDE.match(ln) for ln in lines)

def read_boot_h(name:str, pro_dir:str, made:bool=False) -> list[str]:
  """
  Lines of `boot.h` of project `name`, as C reads them.

  A missing file exits, unless `made`: --boot writes it from the template then.
  """
  path = PATH.resolve(f"{pro_dir}/{BOOT_H}", read=False)
  if not FILE.exists(path):
    if made: return header_lines(boot_h_text(name).split("\n"))
    p.err(f"File {utils.color_main_h(name)} includes {utils.color_file(BOOT_H)}, "
      "which the project lacks")
    p.tip(f"Restore it, start a {utils.color_symbol('plain')} one with {flag.boot}, "
      f"or remove the {utils.color_include('#include')}")
    sys.exit(1)
  return header_lines(text_load(path).split("\n"))

def layer_reject(lines:list[str], prefix:str, shown:str, home:str, paint):
  """
  A `#define` of `prefix` in the file `shown` exits, as it belongs in `home`.

  `paint` gives its name the color of its layer.
  """
  for ln in lines:
    match = DEFINE.match(ln)
    if not match or not match.group(1).startswith(prefix): continue
    p.err(f"Definition {paint(match.group(1))} in {shown} "
      f"belongs in {utils.color_file(home)}")
    p.tip(f"Move it to {utils.color_file(home)} of the project")
    sys.exit(1)

def layers_check(name:str, main_lines:list[str], boot_lines:list[str]):
  """`PRO_` settings stay in main.h for the application, `BOOT_` ones in boot.h for both."""
  layer_reject(main_lines, "BOOT_", utils.color_main_h(name), BOOT_H, utils.color_boot)
  boot_h = utils.color_pro_file(name, BOOT_H)
  layer_reject(boot_lines, "PRO_", boot_h, "main.h", utils.color_symbol)

def boot_keys(lines:list[str]) -> str:
  """`BOOT_KEYS` of boot.h as C joins them, "" without; anything but whole keys exits."""
  written = utils.define_string(lines, "BOOT_KEYS")
  if written is None: return ""
  if not re.fullmatch(r"(?:[0-9a-fA-F]{64})+", written):
    p.err(f"Definition {utils.color_boot('BOOT_KEYS')} in {utils.color_file(BOOT_H)} "
      "needs public keys of 64 hex digits each")
    sys.exit(1)
  return written

def boot_h_text(name:str) -> str:
  """`boot.h` of a new project `name`: no setting yet, so a `plain` bootloader."""
  subs = {"${NAME}": utils.home_name(name), "${DATE}": datetime.now().strftime("%Y-%m-%d")}
  return replace_map(load_templates()["boot.h"].strip(), subs)

def text_load(path:str) -> str:
  """
  Text of main.h or boot.h at `path`, its line endings as they are.

  A file that is not UTF-8 exits: read as empty, boot.h would give a bootloader without keys.
  """
  try:
    return FILE.load(path, binary=True).decode("utf-8")
  except UnicodeDecodeError:
    p.err(f"File {fmt_path(path)} is not UTF-8 text")
    p.tip("Save it as UTF-8")
    sys.exit(1)

def text_save(path:str, text:str):
  """`text` into `path`, its line endings as they are; a file holding it keeps its mtime."""
  data = text.encode("utf-8")
  if not FILE.exists(path) or FILE.load(path, binary=True) != data: FILE.save(path, data)

def line_end(lines:list[str]) -> str:
  """CR when most of `lines`, split at LF, end in it: a new line takes the ending most have."""
  ended = lines[:-1] # the piece past the last LF ends the file without an ending
  return "\r" if 2 * sum(ln.endswith("\r") for ln in ended) > len(ended) else ""

def define_end(lines:list[str], at:int) -> int:
  """Last line of the `#define` at line `at`: a line ending in a backslash goes on in the next."""
  while at + 1 < len(lines) and lines[at].rstrip().endswith("\\"): at += 1
  return at

def include_put(lines:list[str]):
  """`#include "boot.h"` in `lines` of main.h, behind its last include; one there stays."""
  if boot_included(header_lines(lines)): return
  code = code_lines(lines)
  at = max((i for i, ln in enumerate(code) if INCLUDE.match(ln)), default=-1)
  lines.insert(at + 1, BOOT_LINE + line_end(lines))

def define_put(lines:list[str], name:str, value:str):
  """
  `#define name value` in `lines` of main.h: every one C sees takes `value`, keeping its comment.

  A definition continued over lines takes them all, as one line.
  A missing one goes behind the last `PRO_` definition, or behind the last include.
  """
  defined = re.compile(rf"\s*#define\s+{re.escape(name)}\b")
  code = code_lines(lines)
  found = [i for i, ln in enumerate(code) if defined.match(ln)]
  # From the end: a definition made one line shifts only lines below it, all done already
  for i in reversed(found):
    end = define_end(lines, i)
    head = lines[i][:defined.match(code[i]).end()]
    tail = lines[end][len(code[end].rstrip()):] # its comment and line ending
    lines[i:end + 1] = [f"{head} {value}{tail}"]
  if found: return
  pro_ends = [define_end(lines, i) for i, ln in enumerate(code) if PRO_DEFINE.match(ln)]
  at = max(pro_ends, default=None)
  if at is None: at = max((i for i, ln in enumerate(code) if INCLUDE.match(ln)), default=-1)
  lines.insert(at + 1, f"#define {name} {value}{line_end(lines)}")

def main_h_with(text:str, settings:dict[str, str], boot:bool) -> str:
  """main.h `text` with `settings` defined and, with `boot`, the include of boot.h."""
  # Split at LF alone: a CRLF line keeps its CR, so every line left alone comes back as it was
  lines = text.split("\n")
  for name, value in settings.items(): define_put(lines, name, value)
  if boot: include_put(lines)
  return "\n".join(lines)
