# tests/test_layers.py

"""Imports inside the package point down its layers, so the graph of modules stays acyclic."""

import ast
from xaeian import DIR, FILE, PATH
import opencplc

ROOT = PATH.dirname(opencplc.__file__)
# Bottom up: a module imports only the ones before it, `utils` counts as one
ORDER = [
  "__init__", "config", "args", "templates", "utils",
  "platforms", "boards", "model", "headers", "workspace",
  "configure", "resolver", "project",
  "pack", "upload", "runner", "keygen", "lock", "actions",
  "__main__",
]
MODULES = {PATH.stem(f) for f in DIR.file_list(ROOT, exts=[".py"], deep=False)} | {"utils"}

def every_module_has_its_layer():
  assert MODULES <= set(ORDER), sorted(MODULES - set(ORDER))

def imports_point_down_the_layers():
  for path in DIR.iter_files(ROOT, exts=[".py"]):
    in_utils = PATH.basename(PATH.dirname(path)) == "utils"
    name = "utils" if in_utils else PATH.stem(path)
    for node in ast.walk(ast.parse(FILE.load(path))):
      # a helper importing a sibling helper stays inside `utils`
      if not isinstance(node, ast.ImportFrom) or node.level != (2 if in_utils else 1): continue
      # `from . import utils, __version__` names a module, or what the package itself holds
      names = [node.module] if node.module else [alias.name for alias in node.names]
      for target in (n.split(".")[0] for n in names):
        layer = target if target in MODULES else "__init__"
        assert ORDER.index(layer) < ORDER.index(name), f"{name} imports {layer}"
