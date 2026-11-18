# opencplc/utils/keys.py

"""
Keys that sign images for the `key` bootloader, and keys that encrypt update images, per machine.

The development key has no password: Forge makes it on the first build that needs it
and never replaces it, so a board flashed from this machine keeps starting what it builds.
It never leaves the machine, every developer signs with their own.

A product key, `<name>.key`, holds its seed masked with `scrypt` of a password,
or bare when it has none, and `<name>.pub` beside it lets a second project take the key
without the password.
A wrong password unmasks another seed, whose public key gives it away.
A cipher key, `<name>.cipher`, holds 32 random bytes masked the same way, with its fingerprint:
it has no public half, so the fingerprint gives a wrong password away.
`OPENCPLC_KEYS` moves the directory, as `OPENCPLC_TOOLS` moves the packages.
"""

import os, re, sys, getpass, hashlib, secrets
from xaeian import Print, Color as c, DIR, FILE, JSON, PATH
from . import ed25519

p = Print()

DEV_KEY = "dev.key"                     # seed of the development key, 64 hex digits
KEYS_ENV = "OPENCPLC_KEYS"              # directory of the keys, over the default one
PASSWORD_ENV = "OPENCPLC_KEY_PASSWORD"  # CI hands the password over as a secret
PASSWORD_MIN = 8                        # characters of a password, when a key has one
KEY_DIGITS = 64                         # hex digits of one public key in `BOOT_KEYS`
NAME = re.compile(r"[A-Za-z0-9_-]+")    # name of a key and of its files
# 64MB per guess makes a stolen key file slow to try passwords on
SCRYPT = {"n": 2**16, "r": 8, "p": 1}

def keys_split(keys_hex:str) -> list[str]:
  """Public keys of `BOOT_KEYS`, written as one string, apart: 64 hex digits each."""
  return [keys_hex[i:i + KEY_DIGITS] for i in range(0, len(keys_hex), KEY_DIGITS)]

def keys_block(pieces:list[str]) -> list[str]:
  """`BOOT_KEYS` definition of these public keys in hex: one beside the name, more one a line."""
  if len(pieces) == 1: return [f'#define BOOT_KEYS "{pieces[0]}"']
  lines = [f'  "{key}" \\' for key in pieces]
  lines[-1] = lines[-1].removesuffix(" \\")
  return ["#define BOOT_KEYS \\"] + lines

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
    p.inf(f"Development key made in {c.CREAM}{path}{c.END}")
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
  """
  New product key `name`, under `password` or bare without one; its public key.

  An existing name raises.
  """
  seed = secrets.token_bytes(32)
  public = ed25519.public_key(seed)
  record = {"seed": seed.hex()}
  if password:
    salt = secrets.token_bytes(16)
    record = SCRYPT | {"salt": salt.hex(), "seed": mask(seed, password, salt, SCRYPT).hex()}
  if not write_new(f"{keys_dir()}/{name}.key", JSON.smart(record) + "\n"):
    raise ValueError(f"key {name} already exists in {keys_dir()}")
  write_new(f"{keys_dir()}/{name}.pub", public.hex() + "\n")
  return public

def key_record(path:str, sizes:dict[str, int]) -> dict:
  """
  Key file `path`: each field of `sizes` hex of that many bytes,
  with `salt` and the costs of `scrypt` when a password masks it.

  A damaged file raises with its path, so it never passes for a wrong password.
  """
  try:
    record = JSON.parse(FILE.load(path))
    if "salt" in record: sizes = sizes | {"salt": 16}
    whole = all(len(bytes.fromhex(record[field])) == size for field, size in sizes.items())
    whole = whole and ("salt" not in record or all(isinstance(record[k], int) for k in SCRYPT))
  except (ValueError, TypeError, KeyError):
    whole = False
  if not whole: raise ValueError(f"key file {path} damaged, restore it from a copy")
  return record

def product_record(name:str) -> dict:
  """Contents of `<name>.key`: the bare seed, or the masked one with what masks it."""
  return key_record(f"{keys_dir()}/{name}.key", {"seed": 32})

def product_seed(name:str, password:str) -> bytes:
  """Seed of product key `name`; a key without a password takes none, a wrong one raises."""
  record = product_record(name)
  seed = bytes.fromhex(record["seed"])
  if "salt" in record: seed = mask(seed, password, bytes.fromhex(record["salt"]), record)
  if ed25519.public_key(seed) != product_public(name):
    raise ValueError(f"wrong password for key {name}")
  return seed

def product_name(public:bytes) -> str|None:
  """Name of the product key with `public` on this machine, `None` without one."""
  if not DIR.exists(keys_dir()): return None
  for path in DIR.iter_files(keys_dir(), exts=[".pub"]):
    if FILE.load(path).strip() == public.hex(): return PATH.stem(path)
  return None

def password_for(name:str, kind:str) -> str:
  """
  Password of key `name` of `kind`, `product key` or `cipher key`:
  `OPENCPLC_KEY_PASSWORD` in CI, otherwise asked without echo.
  """
  return os.environ.get(PASSWORD_ENV) or getpass.getpass(f"Password of {kind} {name}: ")

def new_password(names:list[str], kind:str) -> str:
  """
  Password of new keys `names` of `kind`: `OPENCPLC_KEY_PASSWORD`, or typed twice.

  An empty one leaves the keys bare.
  """
  if os.environ.get(PASSWORD_ENV): return os.environ[PASSWORD_ENV]
  kinds = f"{kind}s" if len(names) > 1 else kind
  password = getpass.getpass(f"Password of new {kinds} {', '.join(names)}, empty for none: ")
  if password and len(password) < PASSWORD_MIN:
    p.err(f"Password shorter than {PASSWORD_MIN} characters")
    sys.exit(1)
  if getpass.getpass("Repeat password: ") != password:
    p.err("Passwords differ")
    sys.exit(1)
  return password

def signing_seed(public:bytes|None=None) -> bytes:
  """
  Seed that signs for `public`, without it the development one; a key not here raises.

  A product key goes first, so signing with it never reads the development key.
  Only a key with a password asks for it.
  """
  name = product_name(public) if public else None
  if name:
    password = password_for(name, "product key") if "salt" in product_record(name) else ""
    return product_seed(name, password)
  seed = dev_seed()
  if public is None or ed25519.public_key(seed) == public: return seed
  raise ValueError(f"no private key for {fingerprint(public)}... in {keys_dir()}")

def cipher_id(key:bytes) -> str:
  """
  Fingerprint of a cipher key: the first 8 bytes of its SHA-512, as 16 hex digits.

  It proves which key a file or device holds without giving the key away,
  and at 64 bits nobody finds another key with the same one.
  """
  return hashlib.sha512(key).digest()[:8].hex()

def cipher_path(name:str) -> str:
  """File of cipher key `name`, beside the product keys."""
  return f"{keys_dir()}/{name}.cipher"

def cipher_make(name:str, password:str) -> str:
  """New cipher key `name`, under `password` or bare without one; its fingerprint."""
  key = secrets.token_bytes(32)
  record = {"cipher": key.hex()}
  if password:
    salt = secrets.token_bytes(16)
    record = SCRYPT | {"salt": salt.hex(), "cipher": mask(key, password, salt, SCRYPT).hex()}
  record["id"] = cipher_id(key)
  if not write_new(cipher_path(name), JSON.smart(record) + "\n"):
    raise ValueError(f"cipher key {name} already exists in {keys_dir()}")
  return record["id"]

def cipher_record(name:str) -> dict|None:
  """Contents of `<name>.cipher`, `None` without such a key here; a damaged one raises."""
  path = cipher_path(name)
  return key_record(path, {"cipher": 32, "id": 8}) if FILE.exists(path) else None

def cipher_key(name:str) -> bytes:
  """
  Cipher key `name`, its password asked only when it has one.

  A missing key raises, and so does a wrong password, which the fingerprint gives away.
  """
  record = cipher_record(name)
  if record is None: raise ValueError(f"no cipher key {name} in {keys_dir()}")
  key = bytes.fromhex(record["cipher"])
  if "salt" in record:
    key = mask(key, password_for(name, "cipher key"), bytes.fromhex(record["salt"]), record)
  if cipher_id(key) != record["id"]: raise ValueError(f"wrong password for cipher key {name}")
  return key
