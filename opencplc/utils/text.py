# opencplc/utils/text.py

"""Line-level parsing of makefiles and main.h: comments, continuations, variables."""

import re
from xaeian import Print, Color as c

p = Print()

def last_line_len(text:str) -> int:
  """Length of last line in multiline string."""
  return len(text.split('\n')[-1].strip())

def line_remove(text:str, phrase:str, limit:int=1) -> str:
  """Drop up to limit lines containing phrase."""
  lines = text.splitlines()
  out, count = [], 0
  for ln in lines:
    if phrase in ln and count < limit:
      count += 1
    else:
      out.append(ln)
  return "\n".join(out)

def lines_clear(lines:list[str], comment:str="#") -> list[str]:
  """Strip comments and join continuation lines."""
  result = []
  current = ""
  for ln in lines:
    ln = ln.split(comment, 1)[0].rstrip()
    if ln.endswith("\\"):
      current += ln[:-1].rstrip()
    else:
      current += ln
      if current.strip():
        result.append(current.replace("\\\\", "\\"))
      current = ""
  if current.strip():
    result.append(current.replace("\\\\", "\\"))
  return result

def get_vars(
  lines: list[str],
  prefixes: list[str],
  sep: str = "=",
  trim_start: str = "",
  required: bool = True,
) -> dict[str, str]:
  """
  key → value for lines starting with one of prefixes, split on sep.

  trim_start strips a leading keyword such as #define, quotes around values are removed.
  With required every prefix must match, otherwise the result is empty.
  """
  if trim_start:
    lines = [re.sub(f"^{re.escape(trim_start)}+", "", ln).lstrip() for ln in lines]
  filtered = [ln for ln in lines if any(ln.startswith(pf) for pf in prefixes)]
  result = {}
  pattern = rf"^\s*(\w+)\s*{re.escape(sep)}\s*(.*)"
  for ln in filtered:
    m = re.match(pattern, ln)
    if m:
      key = m.group(1).strip()
      val = m.group(2).strip().strip('"')
      result[key] = val
  if required:
    for pf in prefixes:
      if pf not in result:
        p.wrn(f"Variable {c.SKY}{pf}{c.END} not found")
        return {}
  return result

def find_missing_keys(template:dict, subject:dict, prefix:str="") -> list[str]:
  """Dotted paths of keys present in template but missing in subject, nested dicts included."""
  missing = []
  for key in template:
    path = f"{prefix}.{key}" if prefix else key
    if key not in subject:
      missing.append(path)
    else:
      tval, sval = template[key], subject[key]
      if isinstance(tval, dict) and isinstance(sval, dict):
        missing += find_missing_keys(tval, sval, path)
  return missing