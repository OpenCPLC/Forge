# opencplc/utils/hash.py

"""DJB2 hashes and the C code generated from them (-hl)."""

import re
from xaeian import Color as c

def hash_string(s:str) -> int:
  """32-bit DJB2 hash of s."""
  h = 5381
  for ch in s:
    h = ((h << 5) + h) + ord(ch)
  return h & 0xFFFFFFFF

def c_code_enum(hash_list:list[str], title:str="", define:bool=False) -> str:
  """C enum (or #define lines) mapping names to DJB2 hashes of their lowercase form, colored."""
  prefix = (
    "".join(ch for ch in title.upper() if ch.isalpha()) + ("_HASH_" if define else "_Hash_")
    if title else "HASH_"
  )
  lines = ["\n"] if define else [f"\n{c.MAGNTA}typedef enum{c.END} " + "{\n"]
  for name in hash_list:
    val = hash_string(name.lower())
    if define:
      cname = re.sub(r'[^a-zA-Z0-9]', '_', name.upper())
      lines.append(f"{c.MAGNTA}#define {c.BLUE}{prefix}{cname}{c.END} {c.GREEN}{val}{c.END}\n")
    else:
      cname = "".join(ch for ch in name.title() if ch.isalpha())
      lines.append(f"  {c.CYAN}{prefix}{cname}{c.END} = {c.GREEN}{val}{c.END},\n")
  if not define:
    lines.append("} " + f"{c.TEAL}{prefix}t{c.END};\n")
  return "".join(lines)