# opencplc/lint/__init__.py

"""
Static analysis of a chip project: `make lint`, kept apart from the build.

Rules of Forge read what gcc writes while it builds, never the C itself:
the call graph and frames of `-fcallgraph-info=su`, and the dependency files of `-MMD`.
cppcheck and `-fanalyzer` add the common bugs of C.
`lint.yaml` of a Core and of a project holds the roles of the API, rules turned on and exceptions.

Example:
  >>> code = run_lint(project) # stacks and findings printed, `1` while any finding is left
"""

from .command import run_lint

__all__ = ["run_lint"]
