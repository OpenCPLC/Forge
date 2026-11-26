# tests/test_release.py

"""Record of a release and a build checked against it: hashes, commits, keys by fingerprint."""

import os, shutil, hashlib, subprocess
import pytest
from xaeian import FILE, JSON
from opencplc import __version__
from opencplc.project import ANSI
from opencplc.release import record, verify, commit_of, keys_check
from opencplc.utils import keys

HAVE_GIT = shutil.which("git") is not None
IMAGE = b"\x01\x02\x03"
# Image behind the bootloader: header past the vectors, `board` at its byte 14 holding 0x0102
HEADED = bytes(0x200) + b"OPEN" + bytes(10) + b"\x02\x01"
WHEN = "2026-01-02T03:04:05Z"

@pytest.fixture()
def release(tmp_path):
  """What `make dist` leaves: the image of the build, the release in a project of one commit."""
  project = tmp_path / "app"
  project.mkdir()
  (project / "main.c").write_text("int main(void) { return 0; }\n")
  env = os.environ | {"GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_AUTHOR_DATE": WHEN, "GIT_COMMITTER_DATE": WHEN}
  commits = (["init", "-q"], ["add", "."], ["commit", "-q", "-m", "release"])
  for args in commits if HAVE_GIT else ():
    subprocess.run(["git", "-C", str(project), *args], check=True, env=env, capture_output=True)
  (tmp_path / "app.bin").write_bytes(IMAGE)
  (project / "app-1.2.0.hex").write_text(":00000001FF\n")
  (project / "app-1.2.0.bin").write_bytes(IMAGE + bytes(72))
  return tmp_path / "app.bin", project / "app-1.2.0", tmp_path / "core"

@pytest.mark.skipif(not HAVE_GIT, reason="git required")
def record_names_sources_tools_image_and_files(release):
  """Files the release itself leaves in the project are untracked, so the tree stays clean."""
  app, out, core = release
  record([str(app), str(out), str(core), "1.2.0"])
  data = JSON.parse(FILE.load(f"{out}.json"))
  assert data["tag"] == "1.2.0" and "release" not in data and data["forge"] == __version__
  assert len(data["commit"]) == 40 and data["epoch"] == 1767323045 and data["dirty"] is False
  assert data["image"] == {"sha256": hashlib.sha256(IMAGE).hexdigest(), "size": len(IMAGE)}
  assert set(data["files"]) == {"app-1.2.0.hex", "app-1.2.0.bin"}
  assert "sign" not in data and "cipher" not in data

@pytest.mark.skipif(not HAVE_GIT, reason="git required")
def a_tracked_change_marks_the_release_dirty_and_says_so(release, capsys):
  """The image carries the date of the last commit, and no commit gives it again."""
  app, out, core = release
  record([str(app), str(out), str(core), "1.2.0"])
  assert "uncommitted" not in capsys.readouterr().out
  (out.parent / "main.c").write_text("int main(void) { return 1; }\n")
  record([str(app), str(out), str(core), "1.2.0"])
  assert JSON.parse(FILE.load(f"{out}.json"))["dirty"] is True
  assert "Release from uncommitted changes" in ANSI.sub("", capsys.readouterr().out)

def record_opens_with_tag_version_and_variant(release):
  """`make dist TAG=hw-1.2` on a branch of 0.7.1; the variant as the compiler wrote it."""
  app, out, core = release
  app.write_bytes(HEADED)
  (out.parent / "main.h").write_text('#include "boot.h"\n#define FW_VERSION_MAJOR 0\n'
    "#define\tFW_VERSION_MINOR\t7\n#define FW_VERSION_PATCH 1u // patch\n")
  (out.parent / "boot.h").write_text("#define BOOT_BOARD_VARIANT (1 << 8 | 2)\n")
  record([str(app), str(out), str(core), "hw-1.2"])
  data = JSON.parse(FILE.load(f"{out}.json"))
  assert list(data)[:4] == ["tag", "version", "variant", "commit"]
  assert (data["tag"], data["version"], data["variant"]) == ("hw-1.2", "0.7.1", "0x0102")

def a_name_without_its_source_stays_out_of_the_record(release, capsys):
  """No tag, `PRO_VERSION` alone, an image header of a project without the bootloader."""
  app, out, core = release
  app.write_bytes(HEADED)
  (out.parent / "main.h").write_text('#define PRO_VERSION "0.5.0"\n')
  record([str(app), str(out), str(core), ""])
  assert not {"tag", "version", "variant", "release"} & set(JSON.parse(FILE.load(f"{out}.json")))
  assert "without version" not in capsys.readouterr().out

def version_string_counts_written_in_literals_alone(release):
  """`FW_VERSION` glued from macros gives way to the numbers beside it."""
  app, out, core = release
  numbers = ("#define FW_VERSION_MAJOR 1\n#define FW_VERSION_MINOR (9)\n"
    "#define FW_VERSION_PATCH 9\n")
  glued = 'STR(FW_VERSION_MAJOR) "." STR(FW_VERSION_MINOR) "." STR(FW_VERSION_PATCH)'
  for version, want in (('"2.0.0" "-rc1"', "2.0.0-rc1"), (glued, "1.9.9")):
    (out.parent / "main.h").write_text(f"#define FW_VERSION {version}\n{numbers}")
    record([str(app), str(out), str(core), ""])
    assert JSON.parse(FILE.load(f"{out}.json"))["version"] == want

def a_version_forge_cannot_read_leaves_the_record_without_it(release, capsys):
  """The release goes on, its record says nothing wrong, and the warning says why."""
  app, out, core = release
  (out.parent / "main.h").write_text("#define FW_VERSION_MAJOR 1\n"
    "#define FW_VERSION_MINOR (1 << 2)\n#define FW_VERSION_PATCH 0\n")
  record([str(app), str(out), str(core), ""])
  assert "version" not in JSON.parse(FILE.load(f"{out}.json"))
  assert "Release record without version" in ANSI.sub("", capsys.readouterr().out)

def outside_a_repository_the_commit_is_empty(tmp_path):
  assert commit_of(str(tmp_path)) == {"commit": "", "epoch": 0, "dirty": False}

def record_holds_keys_by_fingerprint_alone(release):
  """Anyone may read a record: no seed of a sign key and no cipher key lands in it."""
  app, out, core = release
  public = keys.sign_make("acme", "")
  key_id = keys.cipher_make("acme-enc", "")
  (out.parent / "app-1.2.0.acme-enc.bin").write_bytes(bytes(75))
  record([str(app), str(out), str(core), "1.2.0", public.hex(), "0", "acme-enc"])
  data, text = JSON.parse(FILE.load(f"{out}.json")), FILE.load(f"{out}.json")
  assert data["sign"] == {"key": 0, "fingerprint": public.hex()[:8]}
  assert data["cipher"] == {"name": "acme-enc", "id": key_id}
  assert "app-1.2.0.acme-enc.bin" in data["files"]
  assert keys.cipher_key("acme-enc").hex() not in text
  assert keys.sign_seed("acme", "").hex() not in text

def verify_passes_the_same_image_and_names_the_release_when_it_differs(release, capsys):
  app, out, core = release
  record([str(app), str(out), str(core), "1.2.0"])
  verify([str(app), f"{out}.json"])
  assert "is the one of release app-1.2.0" in ANSI.sub("", capsys.readouterr().out)
  app.write_bytes(IMAGE + b"\x04")
  with pytest.raises(SystemExit):
    verify([str(app), f"{out}.json"])
  shown = ANSI.sub("", capsys.readouterr().out)
  assert "differs from release app-1.2.0" in shown and f"Forge {__version__}" in shown

def verify_without_a_record_says_how_to_name_one(release, capsys):
  app, out, _ = release
  with pytest.raises(SystemExit):
    verify([str(app), f"{out}.json"])
  shown = ANSI.sub("", capsys.readouterr().out)
  assert "No release record app-1.2.0.json" in shown and "RECORD=" in shown

def keys_of_a_release_stop_it_before_any_password(monkeypatch, capsys, keys_dir):
  """A key missing here, or encryption without the key bootloader, exits before its build."""
  monkeypatch.setattr(keys.getpass, "getpass", lambda prompt, **_: pytest.fail("password asked"))
  sign = keys.sign_make("acme", "").hex()
  for args in (["acme-enc"], [sign, "0", "acme-enc"], [bytes(32).hex(), "0"]):
    with pytest.raises(SystemExit):
      keys_check(args)
  shown = ANSI.sub("", capsys.readouterr().out)
  assert "No cipher key acme-enc" in shown and "No sign key 00000000" in shown
  keys.cipher_make("acme-enc", "")
  keys_check([sign, "0", "acme-enc"])

def a_release_signs_as_packing_does(capsys, keys_dir):
  """`.pub` alone, as a team holds it, signs nothing; the development key signs as in a build."""
  sign = keys.sign_make("acme", "").hex()
  (keys_dir / "acme.key").unlink()
  with pytest.raises(SystemExit):
    keys_check([sign, "0"])
  assert "acme has no .key" in ANSI.sub("", capsys.readouterr().out)
  keys_check([keys.dev_public().hex(), "0"])
