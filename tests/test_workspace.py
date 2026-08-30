# tests/test_workspace.py

"""Workspace root discovery and project recognition from a working directory."""

from opencplc.workspace import find_workspace, project_from_path

def root_found_from_nested_dir(tmp_path):
  (tmp_path / "opencplc.json").write_text("{}")
  deep = tmp_path / "projects" / "firm" / "app"
  deep.mkdir(parents=True)
  assert find_workspace(str(deep)) == str(tmp_path)

def root_found_at_root(tmp_path):
  (tmp_path / "opencplc.json").write_text("{}")
  assert find_workspace(str(tmp_path)) == str(tmp_path)

def missing_marker_walks_past_tmp_tree(tmp_path):
  # the machine may hold a stray opencplc.json above tmp, so assert only
  # that nothing inside the marker-free tree was picked
  deep = tmp_path / "a" / "b"
  deep.mkdir(parents=True)
  found = find_workspace(str(deep))
  assert found is None or not found.startswith(str(tmp_path))

def project_recognized_from_its_dir(tmp_path):
  pro = tmp_path / "projects" / "firm" / "app"
  pro.mkdir(parents=True)
  (pro / "main.h").write_text("")
  assert project_from_path(str(pro), str(tmp_path / "projects")) == "firm/app"

def project_recognized_from_subdir(tmp_path):
  pro = tmp_path / "projects" / "app"
  sub = pro / "src" / "util"
  sub.mkdir(parents=True)
  (pro / "main.h").write_text("")
  assert project_from_path(str(sub), str(tmp_path / "projects")) == "app"

def path_outside_root_gives_none(tmp_path):
  other = tmp_path / "elsewhere"
  other.mkdir()
  assert project_from_path(str(other), str(tmp_path / "projects")) is None

def projects_root_itself_is_not_a_project(tmp_path):
  root = tmp_path / "projects"
  root.mkdir()
  (root / "main.h").write_text("")
  assert project_from_path(str(root), str(root)) is None
