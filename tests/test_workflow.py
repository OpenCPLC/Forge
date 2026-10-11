# tests/test_workflow.py

"""`project.yml`, the workflow a project repository calls by the tag of a Forge release."""

import re
import pytest
from xaeian import FILE
from opencplc import __version__
from conftest import REPO_ROOT

WORKFLOW = f"{REPO_ROOT}/.github/workflows/project.yml"
DOCS = [f"{REPO_ROOT}/tests.md", f"{REPO_ROOT}/tests.pl.md"]

def project_workflow_installs_its_own_release():
  # the wheel job tests a copy of `tests/` alone
  if not FILE.exists(WORKFLOW): pytest.skip("no source tree")
  # `@0.5.1` installing Forge 0.5.0 would build a project with the old one, quietly
  assert set(re.findall(r"\d+\.\d+\.\d+", FILE.load(WORKFLOW))) == {__version__}

def docs_pin_the_workflow_of_this_release():
  if not FILE.exists(DOCS[0]): pytest.skip("no source tree")
  # a project copies its `test.yml` from here, so an old tag would stay with it
  for path in DOCS:
    assert set(re.findall(r"project\.yml@(\S+)", FILE.load(path))) == {__version__}, path
