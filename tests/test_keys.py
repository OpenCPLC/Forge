# tests/test_keys.py

"""Keys per machine: development key made once and kept, sign keys under a password."""

import pytest
from xaeian import PATH
from opencplc.project import ANSI
from opencplc.utils import keys, ed25519

def development_key_is_made_once_and_kept(machine_dir):
  seed = keys.dev_seed()
  assert len(seed) == 32 and (machine_dir / "dev.key").read_text().strip() == seed.hex()
  assert keys.dev_seed() == seed

def development_key_stays_on_the_machine_wherever_opencplc_keys_points(keys_dir, machine_dir):
  """A folder of sign keys, a stick or a read-only mount, never gets the development key."""
  keys.dev_seed()
  keys.sign_make("acme", "")
  assert (machine_dir / "dev.key").exists() and not (keys_dir / "dev.key").exists()
  assert (keys_dir / "acme.key").exists() and not (machine_dir / "acme.key").exists()

def no_key_named_or_the_development_one_signs_with_it(keys_dir):
  seed = keys.dev_seed()
  assert keys.seed_for() == seed
  assert keys.seed_for(ed25519.public_key(seed)) == seed

def key_this_machine_lacks_raises_with_its_fingerprint(keys_dir):
  with pytest.raises(ValueError, match="no sign key for 00000000"):
    keys.seed_for(bytes(32))

def damaged_development_key_raises_and_stays(machine_dir):
  machine_dir.mkdir()
  (machine_dir / "dev.key").write_text("not a key\n")
  with pytest.raises(ValueError, match="damaged"):
    keys.dev_seed()
  assert (machine_dir / "dev.key").read_text() == "not a key\n"

def opencplc_keys_moves_the_directory(keys_dir):
  assert keys.keys_dir() == PATH.normalize(str(keys_dir))

def keys_folder_is_shown_by_the_variable_a_person_finds_it_with(keys_dir, monkeypatch):
  elsewhere = str(keys_dir.parent / "elsewhere")
  monkeypatch.setenv("LOCALAPPDATA", str(keys_dir.parent))
  assert keys.keys_place() == "%LOCALAPPDATA%/keys"
  monkeypatch.delenv("LOCALAPPDATA")
  for var in ("HOME", "USERPROFILE"): monkeypatch.setenv(var, str(keys_dir.parent))
  assert keys.keys_place() == "~/keys"
  for var in ("HOME", "USERPROFILE"): monkeypatch.setenv(var, elsewhere)
  assert keys.keys_place() == PATH.normalize(str(keys_dir))

def sign_key_unmasks_with_its_password_alone(keys_dir):
  public = keys.sign_make("acme", "correct horse")
  record = (keys_dir / "acme.key").read_text()
  seed = keys.sign_seed("acme", "correct horse")
  assert ed25519.public_key(seed) == public and seed.hex() not in record
  assert (keys_dir / "acme.pub").read_text().strip() == public.hex()
  with pytest.raises(ValueError, match="wrong password"):
    keys.sign_seed("acme", "wrong horse")

def sign_key_is_never_replaced(keys_dir):
  keys.sign_make("acme", "correct horse")
  before = (keys_dir / "acme.key").read_text()
  with pytest.raises(ValueError, match="already exists"):
    keys.sign_make("acme", "other horse")
  assert (keys_dir / "acme.key").read_text() == before

def sign_key_signs_beside_a_damaged_development_key(machine_dir, monkeypatch):
  """Signing with a sign key in CI never reads the development key."""
  public = keys.sign_make("acme", "correct horse")
  machine_dir.mkdir()
  (machine_dir / "dev.key").write_text("not a key\n")
  monkeypatch.setenv(keys.SIGN_PASSWORD.env, "correct horse")
  assert ed25519.public_key(keys.seed_for(public)) == public

def seed_for_finds_the_sign_key_and_takes_the_password_from_ci(keys_dir, monkeypatch):
  public = keys.sign_make("acme", "correct horse")
  monkeypatch.setenv(keys.SIGN_PASSWORD.env, "correct horse")
  assert ed25519.public_key(keys.seed_for(public)) == public
  monkeypatch.setenv(keys.SIGN_PASSWORD.env, "wrong horse")
  with pytest.raises(ValueError, match="wrong password"):
    keys.seed_for(public)

def cipher_key_unmasks_with_its_password_alone(keys_dir, monkeypatch):
  key_id = keys.cipher_make("acme-enc", "correct horse")
  record = (keys_dir / "acme-enc.cipher").read_text()
  monkeypatch.setenv(keys.CIPHER_PASSWORD.env, "correct horse")
  key = keys.cipher_key("acme-enc")
  assert keys.cipher_id(key) == key_id and key.hex() not in record
  monkeypatch.setenv(keys.CIPHER_PASSWORD.env, "wrong horse")
  with pytest.raises(ValueError, match="wrong password"):
    keys.cipher_key("acme-enc")

def cipher_key_without_a_password_asks_for_none(keys_dir, monkeypatch):
  monkeypatch.setattr(keys.getpass, "getpass", lambda prompt, **_: pytest.fail("password asked"))
  key_id = keys.cipher_make("acme-enc", "")
  assert keys.cipher_id(keys.cipher_key("acme-enc")) == key_id

def cipher_key_is_never_replaced(keys_dir):
  keys.cipher_make("acme-enc", "")
  before = (keys_dir / "acme-enc.cipher").read_text()
  with pytest.raises(ValueError, match="already exists"):
    keys.cipher_make("acme-enc", "")
  assert (keys_dir / "acme-enc.cipher").read_text() == before

def cipher_fingerprint_is_the_head_of_its_sha512():
  """A device computes the same 16 digits, so the key it holds is proven without showing it."""
  assert keys.cipher_id(bytes(32)) == "5046adc1dba83886"

def a_damaged_key_file_raises_with_its_path_and_never_as_a_wrong_password(keys_dir):
  keys.cipher_make("acme-enc", "")
  short, wide = '{"cipher": "00"}', '{"cipher": "' + "00" * 32 + '"}'
  for text in ("", "{nope", "[]", short, wide):
    (keys_dir / "acme-enc.cipher").write_text(text)
    with pytest.raises(ValueError, match="acme-enc.cipher damaged"): keys.cipher_key("acme-enc")
  keys.sign_make("acme", "")
  (keys_dir / "acme.key").write_text('{"seed": "zz"}')
  with pytest.raises(ValueError, match="acme.key damaged"): keys.sign_seed("acme", "")

def every_password_prompt_names_its_kind_and_new_keys_ask_twice(monkeypatch):
  asked = []
  monkeypatch.delenv(keys.SIGN_PASSWORD.env, raising=False)
  monkeypatch.delenv(keys.CIPHER_PASSWORD.env, raising=False)
  answer = lambda prompt, **_: asked.append(prompt) or "horse-123"
  monkeypatch.setattr(keys.getpass, "getpass", answer)
  keys.new_password(keys.SIGN_PASSWORD)
  keys.key_password(keys.CIPHER_PASSWORD)
  assert asked == ["Sign password: ", "Repeat: ", "Cipher password: "]

def signing_and_encryption_take_their_own_passwords(keys_dir, monkeypatch):
  public = keys.sign_make("acme", "signing horse")
  key_id = keys.cipher_make("acme-enc", "cipher horse")
  monkeypatch.setenv(keys.SIGN_PASSWORD.env, "signing horse")
  monkeypatch.setenv(keys.CIPHER_PASSWORD.env, "cipher horse")
  assert ed25519.public_key(keys.seed_for(public)) == public
  assert keys.cipher_id(keys.cipher_key("acme-enc")) == key_id

def without_a_console_only_the_variable_gives_the_password(monkeypatch, capsys):
  """CI has no console: the run stops and names the variable, never waits for a key."""
  monkeypatch.setattr(keys, "console", lambda: False)
  monkeypatch.setattr(keys.getpass, "getpass", lambda prompt, **_: pytest.fail("asked"))
  monkeypatch.delenv(keys.CIPHER_PASSWORD.env, raising=False)
  with pytest.raises(SystemExit): keys.key_password(keys.CIPHER_PASSWORD)
  assert "cipher password, set OPENCPLC_CIPHER_PASSWORD" in ANSI.sub("", capsys.readouterr().out)
  monkeypatch.setenv(keys.CIPHER_PASSWORD.env, "cipher horse")
  assert keys.key_password(keys.CIPHER_PASSWORD) == "cipher horse"

def a_password_holding_a_control_character_stops_the_run(monkeypatch):
  # Ctrl+V of an old console types `\x16` where the text should land, a password nobody types again
  monkeypatch.delenv(keys.SIGN_PASSWORD.env, raising=False)
  monkeypatch.setattr(keys.getpass, "getpass", lambda prompt, **_: "horse\x16123")
  with pytest.raises(SystemExit): keys.new_password(keys.SIGN_PASSWORD)
