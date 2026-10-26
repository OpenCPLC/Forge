# tests/test_keygen.py

"""`--keygen NAME [COUNT]`: product keys made or taken, held by `BOOT_KEYS` of boot.h."""

import os, pytest
from opencplc.keygen import keygen, key_names, with_keys, with_include, KEYS_NOTE
from opencplc.utils import keys, ed25519

MAIN_H = ("#ifndef MAIN_H_\r\n#define MAIN_H_\r\n\r\n#include <xdef.h>\r\n\r\n"
  "#define PRO_CHIP_STM32G081\r\n\r\n#endif\r\n")
BOOT_H = "#ifndef BOOT_H_\r\n#define BOOT_H_\r\n\r\n#endif\r\n"
KEY, NEXT = bytes(range(32)), bytes(range(32, 64))

def first_key_goes_into_boot_h_before_its_guard_closes():
  """The line endings of the file stay."""
  text, numbers = with_keys(BOOT_H, [KEY])
  assert numbers == [0]
  assert text == ("#ifndef BOOT_H_\r\n#define BOOT_H_\r\n\r\n"
    f'{KEYS_NOTE}\r\n#define BOOT_KEYS "{KEY.hex()}"\r\n\r\n#endif\r\n')

def next_keys_go_at_the_end_one_a_line():
  """A key keeps its number: devices in the field trust keys by number."""
  text, numbers = with_keys(with_keys(BOOT_H, [KEY])[0], [KEY, NEXT])
  assert numbers == [0, 1] and text.count(KEYS_NOTE) == 1
  assert f'#define BOOT_KEYS \\\r\n  "{KEY.hex()}" \\\r\n  "{NEXT.hex()}"\r\n' in text
  text, numbers = with_keys(text, [bytes(32)])
  assert numbers == [2] and f'  "{NEXT.hex()}" \\\r\n  "{bytes(32).hex()}"\r\n' in text

def a_boot_h_holding_every_key_comes_back_unchanged():
  """Whatever the case of its digits: `--keygen acme 3` run again writes nothing."""
  once = with_keys(BOOT_H, [KEY, NEXT])[0]
  assert with_keys(once, [KEY, NEXT]) == (once, [0, 1])
  upper = f'#define BOOT_KEYS "{KEY.hex().upper()}"\r\n'
  assert with_keys(upper, [KEY]) == (upper, [0])

def keys_written_by_hand_keep_their_place_and_what_follows():
  hold = "#define BOOT_HOLD { .port = GPIOB, .pin = 5 }"
  boot_h = f'#define BOOT_KEYS "{KEY.hex().upper()}"\r\n{hold}\r\n'
  text, numbers = with_keys(boot_h, [NEXT])
  assert numbers == [1]
  assert text == (f'#define BOOT_KEYS \\\r\n  "{KEY.hex().upper()}" \\\r\n'
    f'  "{NEXT.hex()}"\r\n{hold}\r\n')

def keys_ending_the_file_in_a_backslash_take_the_next_key():
  """A continuation with no line behind it, the file without its final newline."""
  text, numbers = with_keys(f'#define BOOT_KEYS "{KEY.hex()}" \\', [NEXT])
  assert numbers == [1] and text.endswith(f'  "{KEY.hex()}" \\\n  "{NEXT.hex()}"')

def include_goes_behind_the_last_include_once():
  """A commented one includes nothing, so the real one goes in beside it."""
  text = with_include(MAIN_H)
  assert '#include <xdef.h>\r\n#include "boot.h"\r\n' in text
  assert with_include(text) == text
  commented = MAIN_H.replace("#include <xdef.h>", '#include <xdef.h>\r\n// #include "boot.h"')
  assert with_include(commented).count('\r\n#include "boot.h"') == 1

def a_boot_h_a_load_refuses_exits():
  with pytest.raises(SystemExit):
    with_keys(BOOT_H + '#define BOOT_KEYS "8a1fe3c0"\r\n', [KEY])

def count_names_the_spare_keys():
  assert key_names(["acme"]) == ["acme"]
  assert key_names(["acme", "3"]) == ["acme", "acme-1", "acme-2"]
  for args in (["acme", "0"], ["acme", "17"], ["acme", "x"], ["acme", "2", "3"]):
    with pytest.raises(SystemExit):
      key_names(args)

def development_key_name_and_odd_names_are_refused():
  for name in ("dev", "DEV", "my key", "../x"): # Windows file names ignore case
    with pytest.raises(SystemExit):
      key_names([name])

@pytest.fixture()
def pro(tmp_path):
  """Project folder with a main.h, no boot.h yet."""
  folder = tmp_path / "app"
  folder.mkdir()
  (folder / "main.h").write_bytes(MAIN_H.encode())
  return folder

def keygen_makes_boot_h_and_its_include(pro, keys_dir, monkeypatch):
  """One password for every new key, typed and repeated."""
  asked = []
  monkeypatch.delenv(keys.PASSWORD_ENV, raising=False)
  monkeypatch.setattr("opencplc.keygen.getpass.getpass",
    lambda prompt: asked.append(prompt) or "correct horse")
  keygen(["acme", "3"], "app", str(pro))
  assert len(asked) == 2
  boot_h = (pro / "boot.h").read_text()
  assert boot_h.startswith("// app/boot.h\n")
  assert all(keys.product_public(name).hex() in boot_h for name in ("acme", "acme-1", "acme-2"))
  assert '#include "boot.h"' in (pro / "main.h").read_text()

def keygen_run_again_touches_no_file(pro, keys_dir, monkeypatch):
  """A main.h written again would rebuild every object that includes it."""
  monkeypatch.setenv(keys.PASSWORD_ENV, "correct horse")
  keygen(["acme"], "app", str(pro))
  files = [pro / "main.h", pro / "boot.h"]
  for path in files: os.utime(path, ns=(0, 0))
  keygen(["acme"], "app", str(pro))
  assert all(path.stat().st_mtime_ns == 0 for path in files)

def another_application_of_the_product_takes_the_keys_without_a_password(tmp_path, keys_dir,
  monkeypatch):
  first, second = tmp_path / "a", tmp_path / "b"
  for folder in (first, second):
    folder.mkdir()
    (folder / "main.h").write_bytes(MAIN_H.encode())
  monkeypatch.setenv(keys.PASSWORD_ENV, "correct horse")
  keygen(["acme", "2"], "a", str(first))
  monkeypatch.delenv(keys.PASSWORD_ENV)
  keygen(["acme", "2"], "b", str(second)) # a password prompt would fail here, nothing answers it
  block = lambda folder: (folder / "boot.h").read_text().split("BOOT_KEYS")[1]
  assert block(first) == block(second)

def a_spare_key_added_later_keeps_the_numbers_of_the_others(pro, keys_dir, monkeypatch):
  monkeypatch.setenv(keys.PASSWORD_ENV, "correct horse")
  keygen(["acme"], "app", str(pro))
  keygen(["acme", "2"], "app", str(pro))
  boot_h = (pro / "boot.h").read_text()
  first, spare = keys.product_public("acme").hex(), keys.product_public("acme-1").hex()
  assert boot_h.index(first) < boot_h.index(spare)

def key_without_a_password_signs_without_asking(pro, keys_dir, monkeypatch):
  monkeypatch.delenv(keys.PASSWORD_ENV, raising=False)
  monkeypatch.setattr("opencplc.keygen.getpass.getpass", lambda prompt: "")
  keygen(["acme"], "app", str(pro))
  assert "salt" not in keys.product_record("acme")
  monkeypatch.setattr("opencplc.keygen.getpass.getpass", lambda prompt: pytest.fail("asked"))
  public = keys.product_public("acme")
  assert ed25519.public_key(keys.signing_seed(public)) == public

def short_password_stops_before_any_file(pro, keys_dir, monkeypatch):
  monkeypatch.delenv(keys.PASSWORD_ENV, raising=False)
  monkeypatch.setattr("opencplc.keygen.getpass.getpass", lambda prompt: "1234567")
  with pytest.raises(SystemExit):
    keygen(["acme"], "app", str(pro))
  assert keys.product_public("acme") is None and not (pro / "boot.h").exists()
  assert (pro / "main.h").read_bytes() == MAIN_H.encode()

def refused_files_and_lost_pub_stop_the_keys_before_their_password(pro, keys_dir, monkeypatch):
  """`acme.key` without `acme.pub` would fail only after the password was typed twice."""
  monkeypatch.setattr("opencplc.keygen.new_password", lambda names: pytest.fail("password asked"))
  (pro / "main.h").write_bytes((MAIN_H + f'#define BOOT_KEYS "{KEY.hex()}"\r\n').encode())
  with pytest.raises(SystemExit):
    keygen(["acme"], "app", str(pro))
  (pro / "main.h").write_bytes(MAIN_H.encode())
  (pro / "boot.h").write_bytes((BOOT_H + '#define BOOT_KEYS "8a1fe3c0"\r\n').encode())
  with pytest.raises(SystemExit):
    keygen(["acme"], "app", str(pro))
  (pro / "boot.h").unlink()
  keys_dir.mkdir()
  (keys_dir / "acme.key").write_text("{}\n")
  with pytest.raises(SystemExit):
    keygen(["acme"], "app", str(pro))
