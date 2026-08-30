# tests/test_version.py

"""Framework version aliases, ordering and validation."""

import pytest
from opencplc.utils.version import (
  version_real, version_is_release, version_key, version_older_than, version_check,
)

def latest_resolves_names_pass_through():
  assert version_real("latest", "1.2.0") == "1.2.0"
  assert version_real("develop", "1.2.0") == "develop"
  assert version_real("main", "1.2.0") == "main"

def concrete_version_passes_through():
  assert version_real("1.0.2", "1.2.0") == "1.0.2"
  assert version_real("feature-x", "1.2.0") == "feature-x"

def release_vs_branch():
  assert version_is_release("1.0.0")
  assert version_is_release("0.5.0")
  assert not version_is_release("develop")
  assert not version_is_release("main")

def sort_releases_newest_first_branches_after():
  refs = ["develop", "0.5.0", "1.0.0", "0.10.0", "main"]
  ordered = sorted(refs, key=version_key, reverse=True)
  assert ordered[:3] == ["1.0.0", "0.10.0", "0.5.0"]
  assert set(ordered[3:]) == {"develop", "main"}

def older_than_is_semver_aware():
  assert version_older_than("0.9.0", "0.10.0")
  assert not version_older_than("1.0.0", "0.9.9")

def version_check_accepts_known():
  version_check("1.0.0", ["1.0.0", "develop"], "err")

def version_check_exits_on_unknown():
  with pytest.raises(SystemExit):
    version_check("9.9.9", ["1.0.0", "develop"], "err")

def active_version_resolves_flag_and_default():
  from opencplc.utils.version import version_active
  cfg = {"version": "latest", "available-versions": ["1.2.0", "develop"]}
  assert version_active("", cfg) == "1.2.0"
  assert version_active("1.0.0", cfg) == "1.0.0"
  cfg["version"] = "develop"
  assert version_active("", cfg) == "develop"
