# opencplc/lint/__init__.py

"""
Static analysis of a chip project: `make lint`, and the quick part of every build.

Rules of Forge read what gcc writes while it builds, never the C itself:
the call graph and frames of `-fcallgraph-info=su`, and the dependency files of `-MMD`.
cppcheck and `-fanalyzer` add the common bugs of C.
`lint.yaml` of a Core and of a project holds the roles of the API, rules turned on and exceptions.

Example:
  >>> code = run_lint(project) # findings printed, `1` while any is left
"""

from .command import run_lint, build_report

__all__ = ["run_lint", "build_report"]
