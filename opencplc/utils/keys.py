# opencplc/utils/keys.py

"""
Keys that sign images for the `key` bootloader, kept per machine.

The development key has no password: Forge makes it on the first build that needs it
and never replaces it, so a board flashed from this machine keeps starting what it builds.
It never leaves the machine, every developer signs with their own.

A product key, `<name>.key`, holds its seed masked with `scrypt` of a password,
and `<name>.pub` beside it lets a second project take the key without the password.
A wrong password unmasks another seed, whose public key gives it away at once.
`OPENCPLC_KEYS` moves the directory, as `OPENCPLC_TOOLS` moves the packages.
"""

import os, json, getpass, hashlib, secrets
from xaeian import Print, Color as c, DIR, FILE, PATH
from . import ed25519

p = Print()

DEV_KEY = "dev.key"                     # seed of the development key, 64 hex digits
KEYS_ENV = "OPENCPLC_KEYS"              # directory of the keys, over the default one
PASSWORD_ENV = "OPENCPLC_KEY_PASSWORD"  # CI hands the password over as a secret
# 64MB per guess makes a stolen key file slow to try passwords on
SCRYPT = {"n": 2**16, "r": 8, "p": 1}

def keys_dir() -> str:
  """Windows `%LOCALAPPDATA%/OpenCPLC/keys`, elsewhere `~/.local/share/OpenCPLC/keys`."""
  if os.environ.get(KEYS_ENV): return PATH.normalize(os.environ[KEYS_ENV])
  if os.name == "nt": base = os.environ.get("LOCALAPPDATA", "")
  else: base = PATH.expand("~/.local/share")
  return PATH.normalize(f"{base}/OpenCPLC/keys")

def write_new(path:str, text:str) -> bool:
  """
  New file, `0o600` on POSIX; Windows leaves it to the rights of the folder.

  One that exists is never replaced, `False` then.
  """
  DIR.ensure(PATH.dirname(path))
  try:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
  except FileExistsError:
    return False
  with os.fdopen(fd, "w", encoding="utf-8") as f: f.write(text)
  return True

def dev_seed() -> bytes:
  """Seed of the development key, made on first use; a damaged file raises and stays."""
  path = f"{keys_dir()}/{DEV_KEY}"
  if write_new(path, secrets.token_hex(32) + "\n"):
    p.inf(f"Development key made in {c.BLUE}{path}{c.END}")
  try:
    seed = bytes.fromhex(FILE.load(path).strip())
  except ValueError:
    seed = b""
  if len(seed) != 32:
    raise ValueError(f"development key {path} damaged, move it away for a new one")
  return seed

def dev_public() -> bytes:
  """Public key of the development key, the one a build writes into the bootloader."""
  return ed25519.public_key(dev_seed())

def fingerprint(public:bytes|str) -> str:
  """First 8 hex digits of a public key, the way messages and `boot info` name it."""
  return (public.hex() if isinstance(public, bytes) else public)[:8]

def mask(seed:bytes, password:str, salt:bytes, params:dict) -> bytes:
  """`seed` XOR-ed with 32 bytes of `scrypt` of `password`; the same call unmasks it."""
  n, r, par = params["n"], params["r"], params["p"]
  pad = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=par,
    maxmem=256 * r * n, dklen=32)
  return bytes(a ^ b for a, b in zip(seed, pad))

def product_public(name:str) -> bytes|None:
  """Public key of product key `name`, `None` when this machine has no such key."""
  path = f"{keys_dir()}/{name}.pub"
  if not FILE.exists(path): return None
  return bytes.fromhex(FILE.load(path).strip())

def product_make(name:str, password:str) -> bytes:
  """New product key `name` under `password`; its public key. An existing name raises."""
  seed, salt = secrets.token_bytes(32), secrets.token_bytes(16)
  public = ed25519.public_key(seed)
  masked = mask(seed, password, salt, SCRYPT)
  record = SCRYPT | {"salt": salt.hex(), "seed": masked.hex()}
  if not write_new(f"{keys_dir()}/{name}.key", json.dumps(record) + "\n"):
    raise ValueError(f"key {name} already exists in {keys_dir()}")
  write_new(f"{keys_dir()}/{name}.pub", public.hex() + "\n")
  return public

def product_seed(name:str, password:str) -> bytes:
  """Seed of product key `name`; a wrong password raises."""
  record = json.loads(FILE.load(f"{keys_dir()}/{name}.key"))
  masked = bytes.fromhex(record["seed"])
  salt = bytes.fromhex(record["salt"])
  seed = mask(masked, password, salt, record)
  if ed25519.public_key(seed) != product_public(name):
    raise ValueError(f"wrong password for key {name}")
  return seed

def product_name(public:bytes) -> str|None:
  """Name of the product key with `public` on this machine, `None` without one."""
  if not DIR.exists(keys_dir()): return None
  for path in DIR.iter_files(keys_dir(), exts=[".pub"]):
    if FILE.load(path).strip() == public.hex(): return PATH.stem(path)
  return None

def password_for(name:str) -> str:
  """Password of key `name`: `OPENCPLC_KEY_PASSWORD` in CI, otherwise asked without echo."""
  return os.environ.get(PASSWORD_ENV) or getpass.getpass(f"Password of key {name}: ")

def signing_seed(public:bytes|None=None) -> bytes:
  """
  Seed that signs for `public`, without it the development one; a key not here raises.

  A product key goes first, so signing with it never reads the development key.
  """
  name = product_name(public) if public else None
  if name: return product_seed(name, password_for(name))
  seed = dev_seed()
  if public is None or ed25519.public_key(seed) == public: return seed
  raise ValueError(f"no private key for {fingerprint(public)} in {keys_dir()}")
