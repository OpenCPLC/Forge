# tests/test_tools.py

"""Tool packages: installed when missing or at another version, first on PATH, one question."""

import io, os, json, shutil, subprocess, time, zipfile
import pytest
from xaeian import file_context
from opencplc.utils import tools
from opencplc.project import generate
from conftest import build_workspace, resolve_uno

@pytest.fixture()
def home(tmp_path, monkeypatch):
  """A private tools directory on a Windows Forge, with the download and the registry stubbed."""
  root = tmp_path / "tools"
  monkeypatch.setenv("OPENCPLC_TOOLS", str(root))
  # `ensure_tools` prepends to PATH by assignment, so the fixture owns the restore
  monkeypatch.setenv("PATH", os.environ.get("PATH", ""))
  monkeypatch.setattr(tools, "WINDOWS", True)
  monkeypatch.setattr(tools, "ensure_git", lambda yes: None)
  monkeypatch.setattr(tools, "user_path_add", lambda path: pytest.fail("touched the user PATH"))
  fetched = []
  def fetch(url, path):
    fetched.append(url.rsplit("/", 1)[1])
    inside = "make.exe" if "make" in url else "bin/tool.exe" # make ships flat, the rest a bin/
    with zipfile.ZipFile(path, "w") as z: z.writestr(inside, "")
  monkeypatch.setattr(tools, "fetch", fetch)
  return root, fetched

def missing_packages_are_installed_once(home, monkeypatch):
  root, fetched = home
  monkeypatch.setenv("PATH", "C:/elsewhere")
  tools.ensure_tools(is_embedded=True, yes=True)
  assert fetched == ["make-4.4.zip", "arm-gcc-15.3.zip", "openocd-0.12.zip"]
  assert (root / "make" / "make.exe").exists() and (root / "arm-gcc" / "bin" / "tool.exe").exists()
  assert json.loads((root / "tools.json").read_text())["arm-gcc"] == "arm-gcc-15.3.zip"
  where = str(root).replace("\\", "/")
  first = [f"{where}/make", f"{where}/arm-gcc/bin", f"{where}/openocd/bin"]
  assert os.environ["PATH"].split(";")[:3] == first
  tools.ensure_tools(is_embedded=True, yes=True)
  assert len(fetched) == 3 # everything present, nothing fetched again

def another_version_in_forge_replaces_the_package(home, monkeypatch):
  root, fetched = home
  tools.ensure_tools(is_embedded=False, yes=True)
  (root / "mingw" / "old.txt").write_text("stale")
  monkeypatch.setitem(tools.PACKAGES, "mingw", "mingw-17.0.zip")
  tools.ensure_tools(is_embedded=False, yes=True)
  assert fetched.count("mingw-16.1.zip") == 1 and fetched.count("mingw-17.0.zip") == 1
  assert not (root / "mingw" / "old.txt").exists()

def a_package_gone_from_disk_comes_back(home):
  root, fetched = home
  tools.ensure_tools(is_embedded=False, yes=True)
  (root / "make" / "make.exe").unlink()
  (root / "make").rmdir()
  tools.ensure_tools(is_embedded=False, yes=True)
  assert fetched.count("make-4.4.zip") == 2

def a_broken_zip_exits_and_leaves_no_half_package(home, monkeypatch):
  root, fetched = home
  monkeypatch.setattr(tools, "fetch", lambda url, path: io.open(path, "wb").write(b"junk"))
  with pytest.raises(SystemExit):
    tools.install("openocd")
  assert not (root / "openocd").exists() and not (root / "openocd-0.12.zip").exists()

def linux_takes_the_tools_from_path(home, monkeypatch, capsys):
  root, fetched = home
  monkeypatch.setattr(tools, "WINDOWS", False)
  monkeypatch.setattr(tools.shutil, "which", lambda cmd: None if cmd == "openocd" else cmd)
  with pytest.raises(SystemExit):
    tools.ensure_tools(is_embedded=True, yes=True)
  assert "openocd" in capsys.readouterr().out and fetched == []

def git_comes_from_winget_without_a_question(monkeypatch):
  calls = []
  monkeypatch.setattr(tools, "WINDOWS", True)
  monkeypatch.setattr(tools.shutil, "which", lambda cmd: None)
  monkeypatch.setattr(tools.subprocess, "run",
    lambda cmd, **kw: calls.append(cmd) or type("R", (), {"returncode": 0})())
  # git appears in its user home only once winget ran
  monkeypatch.setattr(tools.FILE, "exists",
    lambda path: bool(calls) and path.endswith("Programs/Git/cmd/git.exe"))
  monkeypatch.setenv("LOCALAPPDATA", "C:/Users/me/AppData/Local")
  tools.ensure_git(yes=True)
  assert calls[0][:4] == ["winget", "install", "--id", "Git.Git"]
  quiet = {"--silent", "--accept-package-agreements", "--accept-source-agreements", "--scope"}
  assert quiet <= set(calls[0])
  assert os.environ["PATH"].startswith("C:/Users/me/AppData/Local/Programs/Git/cmd;")

def generated_files_carry_the_tool_paths_on_windows(home, tmp_path, monkeypatch):
  monkeypatch.setattr("opencplc.project.platform.system", lambda: "Windows")
  build_workspace(tmp_path)
  monkeypatch.chdir(tmp_path)
  with file_context(root_path=str(tmp_path)):
    generate(resolve_uno())
  make = (tmp_path / "projects" / "myapp" / "makefile").read_text()
  assert "export PATH := $(OPENCPLC_TOOLS)/make;$(OPENCPLC_TOOLS)/arm-gcc;" in make
  launch = json.loads((tmp_path / ".vscode" / "launch.json").read_text())
  cfg = launch["configurations"][0]
  assert cfg["armToolchainPath"] == "${env:OPENCPLC_TOOLS}/arm-gcc/bin"
  assert cfg["serverpath"] == "${env:OPENCPLC_TOOLS}/openocd/bin/openocd.exe"
  props = (tmp_path / ".vscode" / "c_cpp_properties.json").read_text()
  assert "${env:OPENCPLC_TOOLS}/arm-gcc/bin/arm-none-eabi-gcc.exe" in props

def the_default_home_is_spelled_through_the_environment(monkeypatch):
  """Make reads a makefile as ANSI, so a profile like `Łukasz` must never be written into it."""
  monkeypatch.setattr(tools, "WINDOWS", True)
  monkeypatch.delenv("OPENCPLC_TOOLS", raising=False)
  monkeypatch.setenv("LOCALAPPDATA", "C:/Users/Łukasz/AppData/Local")
  paths = tools.template_paths(is_embedded=True)
  assert "Łukasz" not in "".join(paths.values())
  assert paths["${TOOLS_PATH}"].startswith("$(LOCALAPPDATA)/OpenCPLC/make")
  assert paths["${TOOLS_ARM_GCC}"].startswith("${env:LOCALAPPDATA}/OpenCPLC/arm-gcc/bin/")

def generated_files_leave_the_tools_to_path_elsewhere(home, tmp_path, monkeypatch):
  monkeypatch.setattr(tools, "WINDOWS", False)
  monkeypatch.setattr("opencplc.project.platform.system", lambda: "Linux")
  build_workspace(tmp_path)
  monkeypatch.chdir(tmp_path)
  with file_context(root_path=str(tmp_path)):
    generate(resolve_uno())
  launch = (tmp_path / ".vscode" / "launch.json").read_text()
  assert "armToolchainPath" not in launch and "serverpath" not in launch
  json.loads(launch) # a dropped line must not leave a dangling comma behind
  props = json.loads((tmp_path / ".vscode" / "c_cpp_properties.json").read_text())
  assert props["configurations"][0]["compilerPath"] == "arm-none-eabi-gcc"
  assert "export PATH := ;$(PATH)" in (tmp_path / "projects" / "myapp" / "makefile").read_text()

@pytest.mark.skipif(os.name != "nt" or not shutil.which("make"), reason="Windows and make")
def a_running_make_is_renamed_aside_and_swept_later(tmp_path):
  """The reload that installs a new make runs inside the old one, which cannot be removed."""
  pkg = tmp_path / "make"
  pkg.mkdir()
  shutil.copy(shutil.which("make"), pkg / "make.exe")
  (tmp_path / "mk").write_text("sleepy:\n\t@ping -n 3 127.0.0.1\n")
  proc = subprocess.Popen([str(pkg / "make.exe"), "-f", str(tmp_path / "mk"), "sleepy"],
    stdout=subprocess.DEVNULL)
  time.sleep(0.5)
  tools.retire(str(pkg))
  assert [f.suffix for f in pkg.iterdir()] == [".old"] # the image aside, nothing else left
  proc.wait()
  tools.sweep(str(tmp_path))
  assert list(pkg.iterdir()) == []
