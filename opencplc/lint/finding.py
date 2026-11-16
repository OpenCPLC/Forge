# opencplc/lint/finding.py

"""A place breaking a rule: what every check gives back and an exception of `lint.yaml` matches."""

from dataclasses import dataclass

@dataclass(frozen=True)
class Finding:
  """One place, workspace-relative, so the console opens it in the editor."""
  rule: str
  path: str
  line: int
  col: int
  message: str
  function: str = ""  # thread, handler or caller a `path:function` exception names
  refs: str = ""      # norms behind the rule, `CWE-416, CERT MEM30-C`

  def text(self) -> str:
    """The finding as a compiler prints a warning."""
    refs = f" [{self.refs}]" if self.refs else ""
    return f"{self.path}:{self.line}:{self.col}: {self.rule}: {self.message}{refs}"
