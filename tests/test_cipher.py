# tests/test_cipher.py

"""`--cipher`: cipher keys made and shown, update images encrypted, their trailers left plain."""

import pytest
from conftest import write_app_image, write_boot_image
from opencplc.cipher import cipher_command, encrypt, encrypted, nonce
from opencplc.pack import pack
from opencplc.project import ANSI
from opencplc.utils import keys, xchacha

ORIGIN = 0x08004000  # application slot behind a 16kB bootloader
SIZE = 0x400         # image bytes before the trailer

BOOT = bytes.fromhex("00100020" "81000008") + bytes(0xF8) # stack, reset vector 0x08000081
KEY = bytes(range(32))

@pytest.fixture()
def image(tmp_path):
  """Update image `make dist` leaves under the `key` bootloader, signed by the development key."""
  write_app_image(tmp_path / "app.hex", ORIGIN, SIZE)
  write_boot_image(tmp_path / "boot.hex", BOOT)
  pack(str(tmp_path / "app.hex"), str(tmp_path / "app-1.2.0.hex"), str(tmp_path / "boot.hex"),
    keys.dev_public().hex(), 0)
  return tmp_path / "app-1.2.0.bin"

def encrypted_image_keeps_its_trailer_and_takes_its_signature_as_nonce(image):
  plain = image.read_bytes()
  sealed = encrypt(plain, KEY)
  assert sealed[SIZE:] == plain[SIZE:]
  assert sealed[:SIZE] == xchacha.xchacha20(plain[:SIZE], KEY, plain[SIZE + 8:SIZE + 32])
  assert encrypted(sealed) and not encrypted(plain)

def image_encrypted_once_is_never_encrypted_again(image):
  """No device would decrypt two passes in one."""
  with pytest.raises(ValueError, match="encrypted already"):
    encrypt(encrypt(image.read_bytes(), KEY), KEY)

def command_makes_a_key_then_shows_its_fingerprint_and_the_key_once_confirmed(monkeypatch, capsys):
  """With no console to confirm, as under CI, the key never lands in a log."""
  monkeypatch.setenv(keys.PASSWORD_ENV, "correct horse")
  cipher_command(["acme-enc"], False)
  key_id = keys.cipher_record("acme-enc")["id"]
  assert key_id in ANSI.sub("", capsys.readouterr().out)
  key = keys.cipher_key("acme-enc").hex()
  def no_console():
    raise EOFError # what `input` meets with nobody to answer
  monkeypatch.setattr("builtins.input", no_console)
  cipher_command(["acme-enc"], False)
  shown = ANSI.sub("", capsys.readouterr().out)
  assert key_id in shown and key not in shown
  cipher_command(["acme-enc"], True)
  assert key in ANSI.sub("", capsys.readouterr().out)

def command_encrypts_the_image_beside_and_removes_the_plain_one(image, monkeypatch):
  """A release never ships the plain image by mistake."""
  keys.cipher_make("acme-enc", "correct horse")
  monkeypatch.setenv(keys.PASSWORD_ENV, "correct horse")
  plain = image.read_bytes()
  cipher_command(["acme-enc", str(image)], False)
  sealed = image.with_name("app-1.2.0-acme-enc.bin").read_bytes()
  assert not image.exists() and sealed == encrypt(plain, keys.cipher_key("acme-enc"))

def a_failed_encryption_leaves_no_plain_image_either(image, monkeypatch, capsys):
  """
  No key of the name or a wrong password: `make dist CIPHER=` never leaves a plain image,
  and says it took it away, after the reason.
  """
  keys.cipher_make("acme-enc", "correct horse")
  monkeypatch.setenv(keys.PASSWORD_ENV, "wrong horse")
  plain = image.read_bytes()
  for name, reason in (("other", "No cipher key other"), ("acme-enc", "Cipher failed")):
    image.write_bytes(plain)
    with pytest.raises(SystemExit):
      cipher_command([name, str(image)], False)
    assert not image.exists() and not list(image.parent.glob(f"*-{name}.bin"))
    shown = ANSI.sub("", capsys.readouterr().out)
    assert shown.index(reason) < shown.index("Plain image app-1.2.0.bin removed")

def unsigned_image_stops_before_any_password(tmp_path, image, monkeypatch, capsys):
  """A `plain` bootloader leaves the signature erased: no nonce, so the refusal points at `key`."""
  keys.cipher_make("acme-enc", "correct horse")
  monkeypatch.delenv(keys.PASSWORD_ENV, raising=False)
  monkeypatch.setattr(keys.getpass, "getpass", lambda prompt: pytest.fail("password asked"))
  pack(str(tmp_path / "app.hex"), str(tmp_path / "unsigned.hex"), str(tmp_path / "boot.hex"))
  with pytest.raises(ValueError, match="without a signature"):
    nonce((tmp_path / "unsigned.bin").read_bytes())
  with pytest.raises(SystemExit):
    cipher_command(["acme-enc", str(tmp_path / "unsigned.bin")], False)
  shown = ANSI.sub("", capsys.readouterr().out)
  assert shown.index("key bootloader") < shown.index("Plain image unsigned.bin removed")

def command_refusals_before_the_image_leave_it_and_ask_nothing(tmp_path, image, monkeypatch):
  """
  No image, a `.hex`, a name with a space, arguments past FILE, or one encrypted already,
  which stays as it is.
  """
  keys.cipher_make("acme-enc", "correct horse")
  monkeypatch.delenv(keys.PASSWORD_ENV, raising=False)
  monkeypatch.setattr(keys.getpass, "getpass", lambda prompt: pytest.fail("password asked"))
  sealed = tmp_path / "app-1.2.0-old.bin"
  sealed.write_bytes(encrypt(image.read_bytes(), KEY))
  for args in (["acme-enc", str(tmp_path / "none.bin")], ["acme-enc", str(tmp_path / "app.hex")],
    ["acme enc", str(image)], ["acme-enc", str(image), "x"], ["acme-enc", str(sealed)]):
    with pytest.raises(SystemExit):
      cipher_command(args, False)
  assert image.exists() and sealed.exists() and not list(tmp_path.glob("*-acme-enc.bin"))
