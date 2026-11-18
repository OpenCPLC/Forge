# opencplc/cipher.py

"""
`--cipher NAME [FILE]`: cipher key of a product, and update images encrypted with it.

Key `NAME.cipher` lies beside product keys, under an optional password,
and each device of the product gets it from its application.
Its fingerprint, 16 hex digits, proves which key a file or device holds without showing it.
Encrypted images keep their trailer plain, so clients read size, CRC and signature as before,
while bytes before it go through XChaCha20, with the first 24 bytes of the signature as nonce.
Encryption stands apart from bootloader and signature: devices decrypt as bytes arrive,
and their bootloader checks the plain image as always.
"""

import sys
from xaeian import Print, Color as c, FILE, PATH
from .args import flag
from .pack import SIGNATURE_OFFSET, TRAILER_SIZE, encrypted, encrypted_path
from .utils import keys, xchacha
from . import utils

p = Print()

NONCE_SIZE = 24 # leading bytes of the signature the nonce takes
# Signature of an image without one: the rest of the trailer, left erased
ERASED = b"\xFF" * (TRAILER_SIZE - SIGNATURE_OFFSET)
NOT_PLAIN = "image encrypted already or damaged, its bytes miss the CRC of its trailer"

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
    raise ValueError("image without a signature, which gives the nonce: "
      "encryption takes the key bootloader")
  return signature[:NONCE_SIZE]

def encrypt(data:bytes, key:bytes) -> bytes:
  """Update image `data` with the bytes before its trailer encrypted under `key`."""
  body, trailer = data[:-TRAILER_SIZE], data[-TRAILER_SIZE:]
  return xchacha.xchacha20(body, key, nonce(data)) + trailer

def key_make(name:str):
  """New cipher key `name`, under a password typed twice, or under none."""
  password = keys.new_password([name], "cipher key")
  key_id = keys.cipher_make(name, password)
  p.ok(f"Cipher key {c.GOLD}{name}{c.END} {key_id} made in {c.CREAM}{keys.keys_dir()}{c.END}")
  if password:
    p.wrn("Keep two offline copies of the .cipher file and its password: "
      "a lost key leaves its devices without updates")
  else:
    p.wrn("Cipher key without a password: the .cipher file alone reads every image, "
      "keep it and its copy offline on encrypted drives")
  p.run(f"Show the key for devices with {utils.color_command(f'opencplc --cipher {name}')}")

def key_show(name:str, yes:bool):
  """
  Fingerprint of cipher key `name`, then the key itself for the application to put into devices,
  once confirmed: with no console to answer, as under CI, it never lands in a log.
  """
  p.inf(f"Cipher key {c.GOLD}{name}{c.END} {keys.cipher_record(name)['id']}")
  if not yes and not utils.is_yes("Show the key itself, which opens every image it encrypts"):
    return
  key = keys.cipher_key(name)
  p.gap(f"Key {key.hex()}")
  p.wrn("Anyone with this key reads every image it encrypts, so it goes only into devices")

def failed(e:Exception):
  """A refusal of `--cipher`: its reason, then exit with `1`."""
  p.err(f"Cipher failed: {e}")
  sys.exit(1)

def image_encrypt(name:str, path:str):
  """
  Update image `path` encrypted with key `name` beside it, as `<stem>-<name>.bin`.

  The plain image goes even when encryption fails, at a wrong password say,
  so a release never ships it by mistake; an image encrypted already stays as it is.
  """
  shown = utils.color_image(PATH.basename(path))
  if PATH.ext(path).lower() != ".bin":
    p.err(f"Encryption takes an update image .bin, not {shown}")
    sys.exit(1)
  if not FILE.exists(path):
    p.err(f"No update image {shown}")
    p.run(f"{utils.color_command('make dist')} leaves one beside the .hex under the bootloader")
    sys.exit(1)
  data = FILE.load(path, binary=True)
  if encrypted(data): raise ValueError(NOT_PLAIN)
  done = False
  try:
    if keys.cipher_record(name) is None:
      p.err(f"No cipher key {c.GOLD}{name}{c.END} in {c.CREAM}{keys.keys_dir()}{c.END}")
      p.run(f"Make it with {utils.color_command(f'opencplc --cipher {name}')}")
      sys.exit(1)
    nonce(data) # an image unfit to encrypt stops here, before a password is asked
    key = keys.cipher_key(name)
    out = encrypted_path(path, name)
    FILE.save(out, encrypt(data, key))
    done = True
  except (OSError, ValueError) as e:
    failed(e) # here, so the reason comes before the note on the plain image
  finally:
    FILE.remove(path)
    if not done: p.wrn(f"Plain image {shown} removed, so no release ships it")
  p.inf(f"Image {utils.color_image(PATH.basename(out))} encrypted with "
    f"{c.GOLD}{name}{c.END} {keys.cipher_id(key)}")

def cipher_command(args:list[str], yes:bool):
  """`--cipher NAME [FILE]`, `yes` showing the key unasked; exits with `1` on a refusal."""
  if len(args) > 2:
    p.err(f"Flag {flag.cipher} takes NAME and an optional FILE")
    sys.exit(1)
  name = args[0]
  if not keys.NAME.fullmatch(name):
    p.err(f"Cipher key name {c.MAGNTA}{name}{c.END} takes letters, digits, `-` and `_`")
    sys.exit(1)
  try:
    if len(args) == 2: image_encrypt(name, args[1])
    elif keys.cipher_record(name) is None: key_make(name)
    else: key_show(name, yes)
  except (OSError, ValueError) as e:
    failed(e)
