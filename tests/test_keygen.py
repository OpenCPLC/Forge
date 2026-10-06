# tests/test_keygen.py

"""`--keygen`: product key made or taken, written under `PRO_BOOT` in main.h."""

import pytest
from opencplc.keygen import keygen, with_key
from opencplc.utils import keys

MAIN_H = "#define PRO_CHIP_STM32G081\r\n#define PRO_BOOT false\r\n#define PRO_OPT_LEVEL \"Og\"\r\n"
KEY = bytes(range(32))

def key_lands_under_pro_boot_which_turns_true_crlf_kept():
  text = with_key(MAIN_H, KEY)
  assert text == ("#define PRO_CHIP_STM32G081\r\n"
    f'#define PRO_BOOT true\r\n#define PRO_BOOT_KEY "{KEY.hex()}"\r\n#define PRO_BOOT_EPOCH 0\r\n'
    '#define PRO_OPT_LEVEL "Og"\r\n')

def commented_key_of_earlier_tries_gives_way():
  old = MAIN_H.replace("\r\n#define PRO_OPT",
    '\r\n// #define PRO_BOOT_KEY "ab"\r\n// #define PRO_BOOT_EPOCH 0\r\n#define PRO_OPT')
  text = with_key(old, KEY)
  assert "// #define" not in text and text.count("PRO_BOOT_KEY") == 1

def project_with_a_key_keeps_it():
  with pytest.raises(SystemExit):
    with_key(with_key(MAIN_H, KEY), bytes(32))

def second_project_takes_the_key_without_a_password(tmp_path, keys_dir, monkeypatch):
  first, second = tmp_path / "a.h", tmp_path / "b.h"
  first.write_bytes(MAIN_H.encode())
  second.write_bytes(MAIN_H.encode())
  monkeypatch.setenv(keys.PASSWORD_ENV, "correct horse")
  keygen("acme", str(first))
  monkeypatch.delenv(keys.PASSWORD_ENV)
  keygen("acme", str(second)) # a password prompt would fail here, nothing answers it
  public = keys.product_public("acme").hex()
  assert public in first.read_text() and public in second.read_text()

def development_key_name_and_odd_names_are_refused(tmp_path):
  (tmp_path / "main.h").write_bytes(MAIN_H.encode())
  for name in ("dev", "DEV", "my key", "../x"): # Windows file names ignore case
    with pytest.raises(SystemExit):
      keygen(name, str(tmp_path / "main.h"))

def lost_pub_stops_the_key_before_its_password(tmp_path, keys_dir, monkeypatch):
  """`acme.key` without `acme.pub` would fail only after the password was typed twice."""
  (tmp_path / "main.h").write_bytes(MAIN_H.encode())
  keys_dir.mkdir()
  (keys_dir / "acme.key").write_text("{}\n")
  monkeypatch.setattr("opencplc.keygen.new_password", lambda name: pytest.fail("password asked"))
  with pytest.raises(SystemExit):
    keygen("acme", str(tmp_path / "main.h"))
