# tests/test_common.py

"""Project name validation and name/flag assignment."""

import pytest
from opencplc.utils.common import validate_project_name, assign_name

def valid_names_pass():
  for name in ("myapp", "firm/app", "ok/nested/deep", "app.v2", "a_b-c"):
    assert validate_project_name(name) == (True, "")

def invalid_names_fail():
  bad = (
    "", "..", "../x", "a/../b", "foo//bar", "foo/.", "foo/name.",
    "foo/CON", "CON", "COM1.c", "/abs", "C:/abs", "a\\b", "a\x08b", "a<b", "a|b",
    "foo/name /b", " lead", "x" * 101,
  )
  for name in bad:
    valid, reason = validate_project_name(name)
    assert not valid, name
    assert reason, name

def assign_name_moves_flag_value():
  assert assign_name("", "myapp", "-n") == ("myapp", True)

def assign_name_keeps_matching_pair():
  assert assign_name("myapp", "myapp", "-n") == ("myapp", True)

def assign_name_passes_booleans_through():
  assert assign_name("myapp", True, "-n") == ("myapp", True)
  assert assign_name("myapp", False, "-n") == ("myapp", False)

def assign_name_conflict_exits():
  with pytest.raises(SystemExit):
    assign_name("one", "two", "-n")
