# tests/test_layers.py

"""Imports inside the package point down its layers, so the graph of modules stays acyclic."""

import ast
from xaeian import DIR, FILE, PATH
import opencplc

ROOT = PATH.dirname(opencplc.__file__)
# Bottom up: a module imports only the ones before it, a subpackage counts as one
ORDER = [
  "__init__", "config", "args", "templates", "utils",
  "platforms", "boards", "model", "headers", "workspace",
  "configure", "resolver", "project",
  "pack", "upload", "runner", "lint", "keygen", "lock", "actions",
  "__main__",
]
PACKAGES = {"utils", "lint"}
MODULES = {PATH.stem(f) for f in DIR.file_list(ROOT, exts=[".py"], deep=False)} | PACKAGES

def every_module_has_its_layer():
  assert MODULES <= set(ORDER), sorted(MODULES - set(ORDER))

def imports_point_down_the_layers():
  for path in DIR.iter_files(ROOT, exts=[".py"]):
    package = PATH.basename(PATH.dirname(path))
    inside = package in PACKAGES
    name = package if inside else PATH.stem(path)
    for node in ast.walk(ast.parse(FILE.load(path))):
      # A file of a subpackage importing a sibling stays inside its layer
      if not isinstance(node, ast.ImportFrom) or node.level != (2 if inside else 1): continue
      # `from . import utils, __version__` names a module, or what the package itself holds
      names = [node.module] if node.module else [alias.name for alias in node.names]
      for target in (n.split(".")[0] for n in names):
        layer = target if target in MODULES else "__init__"
        assert ORDER.index(layer) < ORDER.index(name), f"{name} imports {layer}"

def lint_keeps_its_own_order():
  """Inside `lint` the files that only take and give data import nothing that runs a tool."""
  pure = {"finding", "graph", "sources", "rules", "lintfile", "dump", "values"}
  for stem in pure:
    tree = ast.parse(FILE.load(f"{ROOT}/lint/{stem}.py"))
    for node in ast.walk(tree):
      if isinstance(node, ast.ImportFrom) and node.level == 1:
        assert node.module in pure | {None}, f"lint.{stem} imports {node.module}"
      if isinstance(node, ast.ImportFrom) and node.module == "xaeian.cmd":
        raise AssertionError(f"lint.{stem} runs a tool")
