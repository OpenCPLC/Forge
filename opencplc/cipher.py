# opencplc/cipher.py

"""
`--cipher NAME [FILE]`: cipher key of a product, and update images encrypted with it.

Key `NAME.cipher` lies beside sign keys, under an optional password,
and each device of the product gets it from its application.
Its fingerprint, 16 hex digits, proves which key a file or device holds without showing it.
Encrypted images keep their trailer plain, so clients read size, CRC and signature as before,
while bytes before it go through XChaCha20, with the first 24 bytes of the signature as nonce.
Encryption stands apart from bootloader and signature: devices decrypt as bytes arrive,
and their bootloader checks the plain image as always.
"""

import sys
from xaeian import Print, FILE, PATH
from .args import flag
from .pack import SIGNATURE_OFFSET, TRAILER_SIZE, encrypted, encrypted_path
from .utils import keys, xchacha
from . import utils

p = Print()

NONCE_SIZE = 24 # leading bytes of the signature the nonce takes
# Signature of an image without one: the rest of the trailer, left erased
ERASED = b"\xFF" * (TRAILER_SIZE - SIGNATURE_OFFSET)
NOT_PLAIN = "image encrypted already or damaged, its bytes miss CRC of its trailer"

def nonce(data:bytes) -> bytes:
  """
  Nonce of plain update image `data`: the first bytes of its signature.

  An image encrypted already raises, as its bytes miss its CRC,
  and so does one without a signature, which only the `key` bootloader gives.
  """
  if encrypted(data): raise ValueError(NOT_PLAIN)
  start = len(data) - TRAILER_SIZE + SIGNATURE_OFFSET
  signature = data[start:start + len(ERASED)]
  if signature == ERASED:
    raise ValueError("image without signature gives no nonce, encryption needs key bootloader")
  return signature[:NONCE_SIZE]

def encrypt(data:bytes, key:bytes) -> bytes:
  """Update image `data` with the bytes before its trailer encrypted under `key`."""
  body, trailer = data[:-TRAILER_SIZE], data[-TRAILER_SIZE:]
  return xchacha.xchacha20(body, key, nonce(data)) + trailer

def key_make(name:str):
  """New cipher key `name`, under a password typed twice, or under none."""
  password = keys.new_password(keys.CIPHER_PASSWORD)
  key_id = keys.cipher_make(name, password)
  p.ok(f"Cipher key {utils.color_key(name)} {key_id} made in {keys.keys_shown()}")
  file = utils.color_key_file(".cipher")
  if password:
    p.tip(f"Keep two offline copies of {file} file and password: "
      "lost key leaves its devices without updates")
  else:
    p.wrn(f"Cipher key without password: {file} file alone decrypts every image, "
      "keep it and its copy offline on encrypted drives")
  p.tip(f"Show key for devices: {utils.color_command(f'opencplc --cipher {name}')}")

def fingerprint_show(name:str):
  """Line naming cipher key `name` with its fingerprint, above any question or password."""
  p.inf(f"Cipher key {utils.color_key(name)} {keys.cipher_record(name)['id']}")

def key_show(name:str, yes:bool):
  """
  Fingerprint of cipher key `name`, then the key itself for the application to put into devices,
  once confirmed: with no console to answer, as under CI, it never lands in a log.
  """
  fingerprint_show(name)
  if not yes and not utils.is_yes("Show key itself, which decrypts every image"): return
  p.inf(f"Key {keys.cipher_key(name).hex()}")
  p.wrn("This key goes into devices only")

def failed(e:Exception):
  """A refusal of `--cipher`: its reason, then exit with `1`."""
  p.err(f"Cipher failed: {e}")
  sys.exit(1)

def image_encrypt(name:str, path:str):
  """
  Update image `path` encrypted with key `name` beside it, as `<stem>.<name>.bin`.

  The plain image goes even when encryption fails, at a wrong password say,
  so a release never ships it by mistake; an image encrypted already stays as it is.
  """
  if PATH.ext(path).lower() != ".bin":
    p.err(f"Encryption takes update image {utils.color_image('.bin')}, "
      f"not {utils.color_wrong(PATH.basename(path))}")
    sys.exit(1)
  shown = utils.color_image(PATH.basename(path))
  if not FILE.exists(path):
    p.err(f"No update image {shown}")
    p.tip(f"Build it in project with bootloader: {utils.color_command('make dist')}")
    sys.exit(1)
  data = FILE.load(path, binary=True)
  if encrypted(data): raise ValueError(NOT_PLAIN)
  done = False
  try:
    keys.cipher_needed(name)
    nonce(data) # an image unfit to encrypt stops here, before a password is asked
    fingerprint_show(name)
    key = keys.cipher_key(name)
    out = encrypted_path(path, name)
    FILE.save(out, encrypt(data, key))
    done = True
  except (OSError, ValueError) as e:
    failed(e) # here, so the reason comes before the note on the plain image
  finally:
    FILE.remove(path)
    if not done: p.wrn(f"Plain image {shown} removed, so no release ships it")
  p.ok(f"Image {utils.color_image(PATH.basename(out))} encrypted")

def cipher_command(args:list[str], yes:bool):
  """`--cipher NAME [FILE]`, `yes` showing the key unasked; exits with `1` on a refusal."""
  if len(args) > 2:
    p.err(f"Flag {flag.cipher} takes NAME and optional FILE")
    sys.exit(1)
  name = args[0]
  if not keys.NAME.fullmatch(name):
    p.err(f"Cipher key name {utils.color_wrong(name)} takes letters, digits, `-` and `_`")
    sys.exit(1)
  try:
    if len(args) == 2: image_encrypt(name, args[1])
    elif keys.cipher_record(name) is None: key_make(name)
    else: key_show(name, yes)
  except (OSError, ValueError) as e:
    failed(e)
