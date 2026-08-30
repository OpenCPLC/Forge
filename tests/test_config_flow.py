# tests/test_config_flow.py

"""Config lifecycle: offline load, save only on change, refs fetched once."""

import time
import pytest
from xaeian import file_context
import opencplc.workspace as forge
from opencplc.templates import load_templates

@pytest.fixture()
def workspace(tmp_path, monkeypatch):
  monkeypatch.chdir(tmp_path)
  monkeypatch.setattr(forge, "REFS_FRESH", False)
  monkeypatch.setattr(forge.utils, "install_git", lambda yes: None)
  with file_context(root_path=str(tmp_path)):
    yield tmp_path

def load_does_not_create_the_file(workspace):
  cfg = forge.forge_config(load_templates())
  assert cfg["version"] == "latest"
  assert not (workspace / "opencplc.json").exists()

def persist_without_create_leaves_no_file(workspace):
  cfg = forge.forge_config(load_templates())
  forge.persist_config(cfg)
  assert not (workspace / "opencplc.json").exists()

def persist_create_writes_then_skips_unchanged(workspace):
  cfg = forge.forge_config(load_templates())
  forge.persist_config(cfg, create=True)
  marker = workspace / "opencplc.json"
  assert marker.exists()
  stamp = marker.stat().st_mtime_ns
  time.sleep(0.02)
  forge.persist_config(cfg, create=True)
  assert marker.stat().st_mtime_ns == stamp

def refs_fetched_once_and_cached(workspace, monkeypatch):
  calls = []
  monkeypatch.setattr(forge.utils, "git_get_refs",
    lambda url, opt="--ref": calls.append(url) or ["1.2.0", "1.0.0", "develop"])
  cfg = forge.forge_config(load_templates())
  forge.persist_config(cfg, create=True)
  assert forge.ensure_refs(cfg, yes=True) == ["1.2.0", "1.0.0", "develop"]
  assert forge.ensure_refs(cfg, yes=True) == ["1.2.0", "1.0.0", "develop"]
  assert len(calls) == 1
  saved = (workspace / "opencplc.json").read_text()
  assert "1.2.0" in saved

def offline_with_cache_keeps_cache(workspace, monkeypatch):
  monkeypatch.setattr(forge.utils, "git_get_refs", lambda url, opt="--ref": [])
  cfg = forge.forge_config(load_templates())
  cfg["available-versions"] = ["1.0.0"]
  assert forge.ensure_refs(cfg, yes=True) == ["1.0.0"]

def offline_without_cache_exits(workspace, monkeypatch):
  monkeypatch.setattr(forge.utils, "git_get_refs", lambda url, opt="--ref": [])
  cfg = forge.forge_config(load_templates())
  with pytest.raises(SystemExit):
    forge.ensure_refs(cfg, yes=True)

def saved_config_keeps_lists_inline_and_maps_open(workspace):
  cfg = forge.forge_config(load_templates())
  cfg["available-versions"] = ["1.2.0", "1.0.0", "develop"]
  cfg["stlink"] = {"projects/a": "AAA", "projects/b": "BBB"}
  forge.persist_config(cfg, create=True)
  text = (workspace / "opencplc.json").read_text()
  assert '"available-versions": ["1.2.0", "1.0.0", "develop"]' in text
  assert '\n    "projects/a": "AAA",\n    "projects/b": "BBB"\n' in text
  assert forge.forge_config(load_templates()) == cfg

def unknown_keys_are_dropped_on_load(workspace):
  (workspace / "opencplc.json").write_text(
    '{"version": "latest", "paths": {"projects": "./x"},'
    ' "default": {"chip": "X", "optLevel": "Og"}, "windows": true, "stlink": {}}')
  cfg = forge.forge_config(load_templates())
  assert "windows" not in cfg and "paths" not in cfg and "default" not in cfg
