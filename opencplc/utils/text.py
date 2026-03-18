# opencplc/utils/text.py

import re
from xaeian import Print, Color as c, Ico, replace_start

p = Print()

def last_line_len(text:str) -> int:
  """Length of last line in multiline string."""
  return len(text.split('\n')[-1].strip())

def line_remove(text:str, phrase:str, limit:int=1) -> str:
  """Remove lines containing phrase."""
  lines = text.splitlines()
  out, count = [], 0
  for ln in lines:
    if phrase in ln and count < limit:
      count += 1
    else:
      out.append(ln)
  return "\n".join(out)

def line_replace(text:str, phrase:str, new:str, limit:int=1) -> str:
  """Replace lines containing phrase, preserving indent."""
  lines = text.splitlines()
  out, count = [], 0
  for ln in lines:
    if phrase in ln and count < limit:
      indent = len(ln) - len(ln.lstrip())
      out.append(" " * indent + new)
      count += 1
    else:
      out.append(ln)
  return "\n".join(out)

def line_add_before(text:str, phrase:str, new_line:str, limit:int=1) -> str:
  """Add line before lines containing phrase."""
  lines = text.splitlines()
  out, count = [], 0
  for ln in lines:
    if phrase in ln and count < limit:
      out.append(new_line)
      count += 1
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

def swap_comment_lines(text:str, comment:str="#", next_line:bool=False) -> str:
  """Swap commented/uncommented state of lines."""
  lines = text.splitlines()
  i = 0
  while i < len(lines):
    find, repl = None, ""
    if lines[i].startswith(f"{comment} "):
      find = f"{comment} "
    elif lines[i].startswith(f"{comment}\t"):
      find, repl = f"{comment}\t", "\t"
    if find is not None:
      lines[i] = replace_start(lines[i], find, repl)
      if next_line:
        if i + 1 < len(lines):
          lines[i + 1] = find + lines[i + 1].lstrip()
          i += 1
      elif i:
        lines[i - 1] = find + lines[i - 1].lstrip()
    i += 1
  return "\n".join(lines)

def get_vars(
  lines: list[str],
  prefixes: list[str],
  sep: str = "=",
  trim_start: str = "",
  required: bool = True,
) -> dict[str, str]:
  """Extract variables from lines matching prefixes."""
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
        p.wrn(f"Variable {c.MAGENTA}{pf}{c.END} not found")
        return {}
  return result

def get_var(lines:list[str], name:str, sep:str="=", trim:str="") -> str|None:
  """Get single variable value."""
  v = get_vars(lines, [name], sep, trim, required=False)
  return v.get(name)

def find_missing_keys(template:dict, subject:dict, prefix:str="") -> list[str]:
  """Find keys present in template but missing in subject (recursive)."""
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