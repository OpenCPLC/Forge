# tests/test_files.py

"""Project discovery: a project is a folder holding main.h, in `projects/` or in a Core."""

from opencplc.utils.files import get_project_list, core_version, project_dir, project_name
from opencplc.utils.files import home_name

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

def name_in_core_starts_with_its_version_folder():
  name = "opencplc/develop/.tests/host"
  assert core_version(name) == "develop"
  assert project_dir(name) == name
  assert home_name(name) == ".tests/host" # the version would lie on another checkout

def any_other_name_lives_in_projects():
  for name in ("firm/app", "opencplc"):
    assert core_version(name) == ""
    assert project_dir(name) == f"projects/{name}"
    assert home_name(name) == name

def folder_maps_back_to_its_name():
  for name in ("firm/app", "opencplc/develop/.tests/host"):
    assert project_name(project_dir(name)) == name
  for folder in ("projects", "opencplc/develop", "build/projects/app"):
    assert project_name(folder) == ""
