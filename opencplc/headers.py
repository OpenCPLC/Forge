# opencplc/headers.py

"""
main.h and boot.h of a project, as Forge reads them.

main.h holds the `PRO_` settings of the application, boot.h the `BOOT_` ones it shares
with the bootloader, and each layer stays in its own file.
A project put behind the bootloader starts its boot.h from the template.
"""

import re, sys
from datetime import datetime
from xaeian import Print, Color as c, FILE, PATH, replace_map
from .config import BOOT_H
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
BOOT_INCLUDE = re.compile(rf'\s*#include\s+"{re.escape(BOOT_H)}"')

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

def read_boot_h(name:str, pro_dir:str) -> list[str]:
  """Lines of `boot.h` of project `name`, comments cleared; a missing file exits."""
  path = PATH.resolve(f"{pro_dir}/{BOOT_H}", read=False)
  if not FILE.exists(path):
    p.err(f"File {utils.color_main_h(name)} includes {c.BLUE}{BOOT_H}{c.END}, "
      "which the project lacks")
    p.run(f"Create it beside main.h, empty for a {c.SKY}plain{c.END} bootloader, "
      f"or remove the {c.SKY}#include{c.END}")
    sys.exit(1)
  return utils.lines_clear(utils.load_lines(path) or [], "//")

def layer_reject(lines:list[str], prefix:str, shown:str, home:str):
  """A `#define` of `prefix` in the file `shown` exits, as it belongs in `home`."""
  for ln in lines:
    match = DEFINE.match(ln)
    if not match or not match.group(1).startswith(prefix): continue
    p.err(f"Definition {c.SKY}{match.group(1)}{c.END} in {shown} belongs in {c.BLUE}{home}{c.END}")
    p.run(f"Move it to {c.BLUE}{home}{c.END} of the project")
    sys.exit(1)

def layers_check(name:str, main_lines:list[str], boot_lines:list[str]):
  """`PRO_` settings stay in main.h for the application, `BOOT_` ones in boot.h for both."""
  layer_reject(main_lines, "BOOT_", utils.color_main_h(name), BOOT_H)
  layer_reject(boot_lines, "PRO_", utils.color_pro_file(name, BOOT_H), "main.h")

def boot_keys(lines:list[str]) -> str:
  """`BOOT_KEYS` of boot.h as C joins them, "" without; anything but whole keys exits."""
  written = utils.define_string(lines, "BOOT_KEYS")
  if written is None: return ""
  if not re.fullmatch(r"(?:[0-9a-fA-F]{64})+", written):
    p.err(f"Definition {c.SKY}BOOT_KEYS{c.END} in {c.BLUE}{BOOT_H}{c.END} "
      "needs public keys of 64 hex digits each")
    sys.exit(1)
  return written

def boot_h_text(name:str) -> str:
  """`boot.h` of a new project `name`: no setting yet, so a `plain` bootloader."""
  subs = {"${NAME}": utils.home_name(name), "${DATE}": datetime.now().strftime("%Y-%m-%d")}
  return replace_map(load_templates()["boot.h"].strip(), subs)
