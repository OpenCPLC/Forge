# tests/test_files.py

"""Project discovery: a project is a folder holding main.h."""

from opencplc.utils.files import get_project_list

def projects_found_by_main_h(tmp_path):
  (tmp_path / "app").mkdir()
  (tmp_path / "app" / "main.h").write_text("")
  (tmp_path / "firm" / "sub").mkdir(parents=True)
  (tmp_path / "firm" / "sub" / "main.h").write_text("")
  (tmp_path / "empty").mkdir()
  names = set(get_project_list(str(tmp_path)))
  assert names == {"app", "firm/sub"}

def folder_without_main_h_is_not_a_project(tmp_path):
  (tmp_path / "misc").mkdir()
  (tmp_path / "misc" / "other.h").write_text("")
  assert get_project_list(str(tmp_path)) == {}

def missing_root_returns_empty(tmp_path):
  assert get_project_list(str(tmp_path / "nope")) == {}
