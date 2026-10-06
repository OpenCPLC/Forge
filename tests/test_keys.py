# tests/test_keys.py

"""Keys per machine: development key made once and kept, product keys under a password."""

import pytest
from xaeian import PATH
from opencplc.utils import keys, ed25519

def development_key_is_made_once_and_kept(keys_dir):
  seed = keys.dev_seed()
  assert len(seed) == 32 and (keys_dir / "dev.key").read_text().strip() == seed.hex()
  assert keys.dev_seed() == seed

def no_key_named_or_the_development_one_signs_with_it(keys_dir):
  seed = keys.dev_seed()
  assert keys.signing_seed() == seed
  assert keys.signing_seed(ed25519.public_key(seed)) == seed

def key_this_machine_lacks_raises_with_its_fingerprint(keys_dir):
  with pytest.raises(ValueError, match="no private key for 00000000"):
    keys.signing_seed(bytes(32))

def damaged_development_key_raises_and_stays(keys_dir):
  keys_dir.mkdir()
  (keys_dir / "dev.key").write_text("not a key\n")
  with pytest.raises(ValueError, match="damaged"):
    keys.dev_seed()
  assert (keys_dir / "dev.key").read_text() == "not a key\n"

def opencplc_keys_moves_the_directory(keys_dir):
  assert keys.keys_dir() == PATH.normalize(str(keys_dir))

def product_key_unmasks_with_its_password_alone(keys_dir):
  public = keys.product_make("acme", "correct horse")
  record = (keys_dir / "acme.key").read_text()
  seed = keys.product_seed("acme", "correct horse")
  assert ed25519.public_key(seed) == public and seed.hex() not in record
  assert (keys_dir / "acme.pub").read_text().strip() == public.hex()
  with pytest.raises(ValueError, match="wrong password"):
    keys.product_seed("acme", "wrong horse")

def product_key_is_never_replaced(keys_dir):
  keys.product_make("acme", "correct horse")
  before = (keys_dir / "acme.key").read_text()
  with pytest.raises(ValueError, match="already exists"):
    keys.product_make("acme", "other horse")
  assert (keys_dir / "acme.key").read_text() == before

def product_key_signs_beside_a_damaged_development_key(keys_dir, monkeypatch):
  """Signing with a product key in CI never reads the development key."""
  public = keys.product_make("acme", "correct horse")
  (keys_dir / "dev.key").write_text("not a key\n")
  monkeypatch.setenv(keys.PASSWORD_ENV, "correct horse")
  assert ed25519.public_key(keys.signing_seed(public)) == public

def signing_seed_finds_the_product_key_and_takes_the_password_from_ci(keys_dir, monkeypatch):
  public = keys.product_make("acme", "correct horse")
  monkeypatch.setenv(keys.PASSWORD_ENV, "correct horse")
  assert ed25519.public_key(keys.signing_seed(public)) == public
  monkeypatch.setenv(keys.PASSWORD_ENV, "wrong horse")
  with pytest.raises(ValueError, match="wrong password"):
    keys.signing_seed(public)
