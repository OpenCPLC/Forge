# tests/test_files.py

"""Project discovery: a project is a folder holding main.h, in `projects/` or in a Core."""

from opencplc.utils.files import get_project_list, core_version, project_dir, project_name
from opencplc.utils.files import home_name, is_core, ignored

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

def tests_folder_is_no_project_but_holds_some(tmp_path):
  for folder in ("app", "app/.tests", "app/.tests/g081"):
    (tmp_path / folder).mkdir(parents=True, exist_ok=True)
    (tmp_path / folder / "main.h").write_text("")
  assert set(get_project_list(str(tmp_path))) == {"app", "app/.tests/g081"}

def dot_folder_holds_no_project_but_tests_does(tmp_path):
  """A folder starting with a dot is other code's: a simulator, a cache, the bootloader of Core."""
  for folder in ("app", "app/.sim", "ectra/.sim/hal", ".boot", ".tests/g081"):
    (tmp_path / folder).mkdir(parents=True, exist_ok=True)
    (tmp_path / folder / "main.h").write_text("")
  assert set(get_project_list(str(tmp_path))) == {"app", ".tests/g081"}

def missing_root_returns_empty(tmp_path):
  assert get_project_list(str(tmp_path / "nope")) == {}

def name_in_core_starts_with_its_version_folder():
  name = "opencplc/develop/.tests/g081"
  assert core_version(name) == "develop"
  assert project_dir(name) == name
  assert home_name(name) == ".tests/g081" # the version would lie on another checkout

def any_other_name_lives_in_projects():
  for name in ("firm/app", "opencplc"):
    assert core_version(name) == ""
    assert project_dir(name) == f"projects/{name}"
    assert home_name(name) == name

def core_itself_is_its_tests():
  assert is_core("opencplc/develop") and not is_core("opencplc/develop/.tests/g081")
  assert project_dir("opencplc/develop") == "opencplc/develop/.tests"
  assert home_name("opencplc/develop") == ".tests"

def folder_maps_back_to_its_name():
  for name in ("firm/app", "opencplc/develop/.tests/g081", "opencplc/develop"):
    assert project_name(project_dir(name)) == name
  for folder in ("projects", "opencplc/develop", "build/projects/app"):
    assert project_name(folder) == ""

def ignored_folder_hides_all_below_it():
  assert ignored("demo/blink", ["demo/"]) and ignored("demo/ble/bridge", ["demo"])
  assert not ignored("demos/blink", ["demo/"]) and not ignored("app", ["demo/"])

def ignore_without_inner_slash_matches_at_any_depth():
  assert ignored("old", ["old"]) and ignored("umg/old/x", ["old"])
  assert not ignored("umg/older", ["old"])

def ignore_with_inner_slash_starts_at_projects():
  assert ignored("umg/old", ["umg/old"]) and ignored("app", ["/app"])
  assert not ignored("x/umg/old", ["umg/old"]) and not ignored("x/app", ["/app"])

def ignore_wildcards_read_as_in_gitignore():
  assert ignored("demo/ble/bridge", ["*/ble"]) and not ignored("demo/ble/bridge", ["*/bridge"])
  assert ignored("demo/ble/bridge", ["**/bridge"]) and ignored("bridge", ["**/bridge"])
  assert ignored("demo/x", ["demo/**"]) and not ignored("demo", ["demo/**"])
  assert ignored("app1", ["app?"]) and not ignored("app12", ["app?"])

def ignore_last_match_decides():
  patterns = ["demo/", "!demo/usb/serial"]
  assert not ignored("demo/usb/serial", patterns) and ignored("demo/usb/webusb", patterns)
  assert ignored("demo/usb/serial", ["!demo/usb/serial", "demo/"])

def ignore_takes_names_case_aside():
  assert ignored("Demo/Blink", ["demo/"]) and ignored("demo/blink", ["DEMO"])
