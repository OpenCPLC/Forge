# opencplc/lint/graph.py

"""
Call graph of a build, from the `.ci` files `-fcallgraph-info=su` leaves beside the objects.

gcc writes them after inlining, so the graph is the code that runs,
with the frame each function takes.
A function local to its file is titled `path:name`, so two of one name stay apart,
and gcc titles a `weak` function the same way: `settle_weak` gives it back its global name.
"""

import re
from dataclasses import dataclass, field
from xaeian import FILE

INDIRECT = "__indirect_call" # callee of every call through a pointer
TITLE = re.compile(r'graph: \{ title: "([^"]+)"')
NODE = re.compile(r'node: \{ title: "([^"]+)" label: "([^"]*)"')
EDGE = re.compile(r'edge: \{ sourcename: "([^"]+)" targetname: "([^"]+)" label: "([^"]*)"')
FRAME = re.compile(r"(\d+) bytes \(([\w,]+)\)")

@dataclass
class Function:
  """A function the build compiled: where it starts and the stack frame it takes."""
  name: str
  path: str
  line: int
  frame: int|None # bytes, `None` for a frame that grows at run time

@dataclass
class Graph:
  """Compiled functions by title, and the calls of each: callee and the place of the call."""
  functions: dict[str, Function] = field(default_factory=dict)
  calls: dict[str, list[tuple[str, str]]] = field(default_factory=dict)

  def title(self, name:str, path:str) -> str:
    """Title of `name` seen from the file `path`: its own static function, else the global one."""
    local = f"{path}:{name}"
    return local if local in self.functions else name

def place(text:str) -> tuple[str, int, int]:
  """Path, line and column of a `path:line:col`, the drive of a Windows path kept in the path."""
  path, line, col = text.rsplit(":", 2)
  return path, int(line), int(col)

def read(text:str, graph:Graph) -> str:
  """One `.ci` into `graph`, returning the source it describes; a declaration alone is skipped."""
  source = ""
  for line in text.splitlines():
    if node := NODE.match(line):
      parts = node[2].split("\\n")
      frame = FRAME.match(parts[2]) if len(parts) > 2 else None
      if not frame: continue
      path, number, _ = place(parts[1])
      # `dynamic,bounded` gives its upper bound, a plain `dynamic` none
      size = None if frame[2] == "dynamic" else int(frame[1])
      graph.functions[node[1]] = Function(parts[0], path, number, size)
    elif edge := EDGE.match(line):
      graph.calls.setdefault(edge[1], []).append((edge[2], edge[3]))
    elif title := TITLE.match(line):
      source = title[1]
  return source

def load_graph(paths:list[str]) -> tuple[Graph, list[str]]:
  """Graph of the `.ci` files `paths`, and the source each of them describes, in their order."""
  graph = Graph()
  return graph, [read(FILE.load(path), graph) for path in paths]

def settle_weak(graph:Graph, weak:set[str]):
  """
  Titles of `weak` definitions back under their global name.

  A strong definition elsewhere wins, so the weak one leaves the graph,
  and every call to either reaches the one the linker keeps.
  """
  for title in weak & graph.functions.keys():
    name = title.rsplit(":", 1)[1]
    calls = graph.calls.pop(title, [])
    if name in graph.functions:
      del graph.functions[title]
    else:
      graph.functions[name] = graph.functions.pop(title)
      graph.calls[name] = calls
    for callees in graph.calls.values():
      callees[:] = [(name if callee == title else callee, site) for callee, site in callees]
