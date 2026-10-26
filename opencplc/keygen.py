# opencplc/keygen.py

"""
`--keygen NAME [COUNT]`: product keys of an application, made or taken, added to its `boot.h`.

`COUNT` keys go in, `NAME` and its spare ones `NAME-1`, `NAME-2`...,
so the same command in another application of the product writes the same list.
Keys are numbered from `0` in the order of `BOOT_KEYS`, so a new one always goes at the end:
a key changed or taken out would cut off the devices in the field that trust it.
A project without the bootloader gets its `boot.h` and the `#include` of it in main.h.
"""

import os, re, sys, getpass
from xaeian import Print, Color as c, FILE
from .args import flag
from .config import BOOT_H, BOOT_LINE
from .configure import boot_included, boot_keys, layers_check
from .project import boot_h_text
from .utils import keys, lines_clear
from . import utils

p = Print()

NAME = re.compile(r"[A-Za-z0-9_-]+")
DEV_NAME = keys.DEV_KEY.removesuffix(".key") # `dev`, the development key file
PASSWORD_MIN = 8
COUNT_MAX = 16 # past a handful, spare keys only add text to the bootloader
KEYS_NOTE = "// Product keys, numbered from `0`: `--keygen` adds the next one at the end"
KEYS_DEFINE = re.compile(r"\s*#define\s+BOOT_KEYS\b")
INCLUDE = re.compile(r"\s*#include\b")

#--------------------------------------------------------------------------------------------- Keys

def key_names(args:list[str]) -> list[str]:
  """Names of `--keygen NAME [COUNT]`: `NAME`, then `NAME-1` up to `NAME-<COUNT-1>`."""
  if len(args) > 2:
    p.err(f"Flag {flag.keygen} takes NAME and an optional COUNT")
    sys.exit(1)
  name, count = args[0], args[1] if len(args) > 1 else "1"
  # Windows file names ignore case, so `DEV` would land on the development key
  if not NAME.fullmatch(name) or name.lower() == DEV_NAME:
    p.err(f"Key name {c.MAGNTA}{name}{c.END} takes letters, digits, `-` and `_`, "
      f"`{DEV_NAME}` is reserved")
    sys.exit(1)
  if not count.isdigit() or not 1 <= int(count) <= COUNT_MAX:
    p.err(f"Key count {c.MAGNTA}{count}{c.END} takes a number from 1 to {COUNT_MAX}")
    sys.exit(1)
  return [name] + [f"{name}-{i}" for i in range(1, int(count))]

def new_password(names:list[str]) -> str:
  """Password of new keys: `OPENCPLC_KEY_PASSWORD`, or typed twice; empty for none."""
  if os.environ.get(keys.PASSWORD_ENV): return os.environ[keys.PASSWORD_ENV]
  shown = ", ".join(names)
  password = getpass.getpass(f"Password of new keys {shown}, empty for none: ")
  if password and len(password) < PASSWORD_MIN:
    p.err(f"Password shorter than {PASSWORD_MIN} characters")
    sys.exit(1)
  if getpass.getpass("Repeat password: ") != password:
    p.err("Passwords differ")
    sys.exit(1)
  return password

def lost_pub_reject(name:str):
  """A `.key` left without its `.pub` exits: a new key of that name would replace it."""
  if not FILE.exists(f"{keys.keys_dir()}/{name}.key"): return
  p.err(f"Key {c.GOLD}{name}{c.END} lost {c.BLUE}{name}.pub{c.END} "
    f"beside {c.BLUE}{name}.key{c.END} in {c.CREAM}{keys.keys_dir()}{c.END}")
  p.run(f"Recreate {c.BLUE}{name}.pub{c.END} with one line: the key from "
    f"{c.SKY}BOOT_KEYS{c.END} of a bootloader that trusts it")
  sys.exit(1)

def keys_ready(names:list[str]) -> dict[str, bytes]:
  """Public key of every name: taken from this computer, the missing ones made, one password."""
  publics = {name: keys.product_public(name) for name in names}
  new = [name for name, public in publics.items() if public is None]
  for name in new: lost_pub_reject(name)
  taken = [name for name in names if name not in new]
  if taken:
    p.inf(f"Keys {c.GOLD}{', '.join(taken)}{c.END} taken from {c.CREAM}{keys.keys_dir()}{c.END}")
  if not new: return publics
  password = new_password(new)
  for name in new: publics[name] = keys.product_make(name, password)
  p.ok(f"Keys {c.GOLD}{', '.join(new)}{c.END} made in {c.CREAM}{keys.keys_dir()}{c.END}")
  if password:
    p.wrn("Keep two offline copies of the .key files and their password, "
      "the spare keys away from the first")
  else:
    p.wrn("Keys without a password: a .key file alone signs, "
      "keep it and its copy offline on encrypted drives")
  return publics

#-------------------------------------------------------------------------------------------- Files

def text_load(path:str) -> str:
  """Text of `path`, its line endings as they are."""
  return FILE.load(path, binary=True).decode("utf-8")

def text_save(path:str, text:str):
  """`text` into `path`, its line endings as they are; a file holding it keeps its mtime."""
  data = text.encode("utf-8")
  if not FILE.exists(path) or FILE.load(path, binary=True) != data: FILE.save(path, data)

def newline(text:str) -> str:
  """Line ending of `text`: CRLF when it has one, LF otherwise."""
  return "\r\n" if "\r\n" in text else "\n"

def files_check(name:str, main_h:str, boot_h:str):
  """main.h and boot.h a load would refuse stop here, before any password is asked."""
  main_lines = lines_clear(main_h.splitlines(), "//")
  boot_lines = lines_clear(boot_h.splitlines(), "//")
  layers_check(name, main_lines, boot_lines)
  boot_keys(boot_lines)

def keys_put(lines:list[str], block:list[str]):
  """`block` in place of `BOOT_KEYS` in `lines` of boot.h, without one before its guard closes."""
  start = next((i for i, ln in enumerate(lines) if KEYS_DEFINE.match(ln)), None)
  if start is not None:
    stop = start
    while stop + 1 < len(lines) and lines[stop].rstrip().endswith("\\"): stop += 1
    lines[start:stop + 1] = block
    return
  endif = [i for i, ln in enumerate(lines) if ln.strip().startswith("#endif")]
  at = endif[-1] if endif else len(lines)
  lines[at:at] = [KEYS_NOTE] + block + [""]

def include_put(lines:list[str]):
  """`#include "boot.h"` in `lines` of main.h, behind its last include; one there stays."""
  if boot_included(lines_clear(lines, "//")): return
  at = max((i for i, ln in enumerate(lines) if INCLUDE.match(ln)), default=-1)
  lines.insert(at + 1, BOOT_LINE)

def with_keys(boot_h:str, publics:list[bytes]) -> tuple[str, list[int]]:
  """
  boot.h with the keys of `publics` it lacks at the end of `BOOT_KEYS`,
  and the number of every key of `publics`.

  Keys boot.h holds stay as written, so a boot.h that has them all comes back unchanged.
  """
  nl = newline(boot_h)
  lines = boot_h.split(nl)
  pieces = keys.keys_split(boot_keys(lines_clear(lines, "//")))
  known = [piece.lower() for piece in pieces]
  new = [k for k in dict.fromkeys(pub.hex() for pub in publics) if k not in known]
  if new: keys_put(lines, keys.keys_block(pieces + new))
  return nl.join(lines), [(known + new).index(pub.hex()) for pub in publics]

def with_include(main_h:str) -> str:
  """main.h that includes `boot.h`; one that does comes back unchanged."""
  nl = newline(main_h)
  lines = main_h.split(nl)
  include_put(lines)
  return nl.join(lines)

#------------------------------------------------------------------------------------------ Command

def keygen(args:list[str], name:str, pro_dir:str):
  """`--keygen NAME [COUNT]` on project `name`: keys made or taken, held by its boot.h."""
  names = key_names(args)
  main_path, boot_path = f"{pro_dir}/main.h", f"{pro_dir}/{BOOT_H}"
  main_h = text_load(main_path)
  boot_h = text_load(boot_path) if FILE.exists(boot_path) else boot_h_text(name)
  files_check(name, main_h, boot_h)
  publics = keys_ready(names)
  boot_h, numbers = with_keys(boot_h, list(publics.values()))
  text_save(boot_path, boot_h)
  text_save(main_path, with_include(main_h))
  held = (f"{c.GOLD}{key}{c.END} as {c.GOLD}{n}{c.END}" for key, n in zip(names, numbers))
  p.ok(f"{c.SKY}BOOT_KEYS{c.END} of {utils.color_pro_file(name, BOOT_H)} holds {', '.join(held)}")
