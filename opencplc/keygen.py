# opencplc/keygen.py

"""
`--sign NAME [COUNT]`: sign keys of an application, made or taken, added to its `boot.h`.

`COUNT` keys go in, `NAME` and its spare ones `NAME-1`, `NAME-2`...,
so the same command in another application of the product writes the same list.
Keys are numbered from `0` in the order of `BOOT_KEYS`, so a new one always goes at the end:
a key changed or taken out would cut off the devices in the field that trust it.
A project without the bootloader gets its `boot.h` and the `#include` of it in main.h.
"""

import re, sys
from xaeian import Print, FILE, fmt_id, fmt_list
from .args import flag
from .config import BOOT_H
from .headers import boot_keys, layers_check, boot_h_text, header_lines, code_lines
from .headers import main_h_defines, define_end, line_end
from .headers import text_load, text_save, main_h_with
from .platforms import parse_chip
from .utils import keys
from .utils.palette import KEY_COLOR
from . import utils

p = Print()

DEV_NAME = keys.DEV_KEY.removesuffix(".key") # `dev`, the development key file
COUNT_MAX = 16 # past a handful, spare keys only add text to the bootloader
KEYS_NOTE = "// Sign keys, numbered from `0`: `--sign` adds the next one at the end"
KEYS_DEFINE = re.compile(r"\s*#define\s+BOOT_KEYS\b")

#--------------------------------------------------------------------------------------------- Keys

def key_names(args:list[str]) -> list[str]:
  """Names of `--sign NAME [COUNT]`: `NAME`, then `NAME-1` up to `NAME-<COUNT-1>`."""
  if len(args) > 2:
    p.err(f"Flag {flag.sign} takes NAME and optional COUNT")
    sys.exit(1)
  name, count = args[0], args[1] if len(args) > 1 else "1"
  # Windows file names ignore case, so `DEV` would land on the development key
  if not keys.NAME.fullmatch(name) or name.lower() == DEV_NAME:
    p.err(f"Sign key name {utils.color_wrong(name)} takes letters, digits, `-` and `_`, "
      f"`{DEV_NAME}` is reserved")
    sys.exit(1)
  if not count.isdigit() or not 1 <= int(count) <= COUNT_MAX:
    p.err(f"Sign key count {utils.color_wrong(count)} is not a number from 1 to {COUNT_MAX}")
    sys.exit(1)
  return [name] + [f"{name}-{i}" for i in range(1, int(count))]

def lost_pub_reject(name:str):
  """A `.key` left without its `.pub` exits: a new key of that name would replace it."""
  if not FILE.exists(f"{keys.keys_dir()}/{name}.key"): return
  pub, key = utils.color_key_file(f"{name}.pub"), utils.color_key_file(f"{name}.key")
  p.err(f"No {pub} beside {key} in {keys.keys_shown()}")
  p.tip(f"Recreate {pub}: its key from {utils.color_boot('BOOT_KEYS')} on one line")
  sys.exit(1)

def keys_ready(names:list[str]) -> dict[str, bytes]:
  """Public key of every name: taken from this computer, the missing ones made, one password."""
  publics = {name: keys.sign_public(name) for name in names}
  new = [name for name, public in publics.items() if public is None]
  for name in new: lost_pub_reject(name)
  taken = [name for name in names if name not in new]
  if taken: p.inf(f"Sign keys {fmt_list(taken, KEY_COLOR)} taken from {keys.keys_shown()}")
  if not new: return publics
  password = keys.new_password(keys.SIGN_PASSWORD)
  for name in new: publics[name] = keys.sign_make(name, password)
  p.ok(f"Sign keys {fmt_list(new, KEY_COLOR)} made in {keys.keys_shown()}")
  files = utils.color_key_file(".key")
  if password:
    p.tip(f"Keep two offline copies of {files} files and password, spare keys apart from main one")
  else:
    p.wrn(f"Sign keys without password: {files} file alone signs, "
      "keep it and its copy offline on encrypted drives")
  return publics

#-------------------------------------------------------------------------------------------- Files

def files_check(name:str, main_h:str, boot_h:str):
  """main.h and boot.h a load would refuse stop here, before any password is asked."""
  main_lines = header_lines(main_h.split("\n"))
  boot_lines = header_lines(boot_h.split("\n"))
  layers_check(name, main_lines, boot_lines)
  boot_keys(boot_lines)
  # Only a chip main.h names can refuse: without one, the board or each load names it
  chip = main_h_defines(main_lines).get("PRO_CHIP")
  if chip and parse_chip(chip).platform != "STM32":
    p.err(f"Chip {utils.color_chip(chip)} runs no bootloader, so it takes no sign keys")
    sys.exit(1)

def keys_put(lines:list[str], block:list[str]):
  """`block` in place of `BOOT_KEYS` in `lines` of boot.h, without one before its guard closes."""
  cr = line_end(lines)
  block = [ln + cr for ln in block]
  code = code_lines(lines)
  start = next((i for i, ln in enumerate(code) if KEYS_DEFINE.match(ln)), None)
  if start is not None:
    lines[start:define_end(lines, start) + 1] = block
    return
  endif = [i for i, ln in enumerate(code) if ln.strip().startswith("#endif")]
  at = endif[-1] if endif else len(lines)
  lines[at:at] = [KEYS_NOTE + cr] + block + [cr]

def with_keys(boot_h:str, publics:list[bytes]) -> tuple[str, list[int]]:
  """
  boot.h with the keys of `publics` it lacks at the end of `BOOT_KEYS`,
  and the number of every key of `publics`.

  Keys boot.h holds stay as written, so a boot.h that has them all comes back unchanged.
  """
  lines = boot_h.split("\n")
  pieces = keys.keys_split(boot_keys(header_lines(lines)))
  known = [piece.lower() for piece in pieces]
  new = [k for k in dict.fromkeys(pub.hex() for pub in publics) if k not in known]
  if new: keys_put(lines, keys.keys_block(pieces + new))
  return "\n".join(lines), [(known + new).index(pub.hex()) for pub in publics]

#------------------------------------------------------------------------------------------ Command

def keygen(args:list[str], name:str, pro_dir:str):
  """`--sign NAME [COUNT]` on project `name`: keys made or taken, held by its boot.h."""
  names = key_names(args)
  main_path, boot_path = f"{pro_dir}/main.h", f"{pro_dir}/{BOOT_H}"
  main_h = text_load(main_path)
  boot_h = text_load(boot_path) if FILE.exists(boot_path) else boot_h_text(name)
  files_check(name, main_h, boot_h)
  publics = keys_ready(names)
  boot_h, numbers = with_keys(boot_h, list(publics.values()))
  text_save(boot_path, boot_h)
  text_save(main_path, main_h_with(main_h, {}, boot=True))
  held = ", ".join(f"{utils.color_key(key)} {fmt_id(n)}" for key, n in zip(names, numbers))
  p.ok(f"{utils.color_boot('BOOT_KEYS')} of {utils.color_pro_file(name, BOOT_H)} holds {held}")
