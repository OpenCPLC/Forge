# opencplc/pack.py

"""
Flash image packing, `--pack`: the application hex made into what goes into flash.

Under the bootloader the application gets the CRC in its trailer and the bootloader in front.
One file then flashes a bare chip, and the update binary for `UPDATE` lands beside it.
Under the `key` bootloader the trailer also takes the signature and the bootloader the key.
Without a bootloader the flash image is the application as linked.
"""

import sys
from xaeian import Print, PATH
from xaeian.crc import crc32_iso
from .args import flag
from .resolver import FLASH_BASE
from .utils import hexfile, keys, ed25519

p = Print()

HEADER_OFFSET = 0x200   # image header past every vector table, `BOOT_HEADER_OFFSET` in Core
HEADER_MAGIC = b"OPEN"  # `BOOT_MAGIC` in Core
SIGNATURE_OFFSET = 8    # signature in the trailer, past the CRC, `BOOT_SIGNATURE_OFFSET` in Core
TRAILER_SIZE = 72       # CRC and signature, `BOOT_TRAILER_SIZE` in Core

def image_size(image:hexfile.Memory, origin:int) -> int:
  """Bytes before the trailer, as the image header at `origin` names them."""
  try:
    header = image.read(origin + HEADER_OFFSET, 8)
  except ValueError:
    header = b""
  if header[:4] != HEADER_MAGIC:
    raise ValueError(f"no image header at 0x{origin + HEADER_OFFSET:08X}")
  return int.from_bytes(header[4:], "little")

def update_path(out_path:str) -> str:
  """Update binary beside the flash image, under its name: `app-dist.hex` → `app-dist.bin`."""
  return PATH.with_suffix(out_path, ".bin")

def write_key(boot:hexfile.Memory, at:int, public:bytes):
  """Public key into the blank slot of the `key` bootloader; any other bootloader raises."""
  try:
    slot = boot.read(at, len(public))
  except ValueError:
    slot = b""
  if slot != b"\xff" * len(public):
    raise ValueError(f"bootloader has no blank key slot at 0x{at:08X}")
  boot.write(at, public)

def pack(app_path:str, out_path:str, boot_path:str|None=None, key_at:int=0, key:bytes|None=None):
  """
  Flash image of the application; under the bootloader also the update binary.

  The trailer CRC covers the image with its gaps erased to `0xFF`, as flash holds them.
  The programmer and the update path then leave the same bytes behind.

  With `key_at` the bootloader is the `key` one: the signature covers the same bytes,
  and the public key goes into its blank slot at `key_at`.
  `key` is the public key to sign for, `PRO_BOOT_KEY` in `dist`.
  A build signs with the development key.

  The bootloader region past the bootloader stays out of the file, the mailbox page with it.
  A programmer would write it as `0xFF`: flash with ECC takes no new record over written ones,
  and `FLASH_Erase` on the device skips a page that reads blank.
  """
  image = hexfile.load_hex(app_path)
  if not boot_path:
    hexfile.save_hex(image, out_path)
    return
  seed = keys.signing_seed(key) if key_at else None
  origin = min(image.segments)
  end = max(addr + len(seg) for addr, seg in image.segments.items())
  size = image_size(image, origin)
  if origin + size + TRAILER_SIZE > end:
    raise ValueError(f"image of {size}B has no trailer behind it")
  image.fill(origin, size)
  body = image.read(origin, size)
  image.write(origin + size, crc32_iso.checksum(body).to_bytes(4, "little"))
  if seed: image.write(origin + size + SIGNATURE_OFFSET, ed25519.sign(seed, body))
  boot = hexfile.load_hex(boot_path)
  if seed: write_key(boot, key_at, ed25519.public_key(seed))
  image.merge(boot)
  image.start = int.from_bytes(boot.read(FLASH_BASE + 4, 4), "little") # its reset vector
  # every refusal comes above, so a failed pack leaves no file behind
  hexfile.save_bin(image, update_path(out_path), origin, end - origin)
  hexfile.save_hex(image, out_path)

def pack_command(files:list[str]):
  """`--pack APP.hex OUT.hex [BOOT [KEY_AT [KEY]]]` after linking; exits on failure."""
  if not 2 <= len(files) <= 5:
    p.err(f"{flag.p} takes APP.hex OUT.hex [BOOT [KEY_AT [KEY]]]")
    sys.exit(1)
  app, out, boot, key_at, key = files + [None] * (5 - len(files))
  try:
    pack(app, out, boot, int(key_at, 16) if key_at else 0, bytes.fromhex(key) if key else None)
  except (OSError, ValueError) as e:
    p.err(f"Pack failed: {e}")
    sys.exit(1)
