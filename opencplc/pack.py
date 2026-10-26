# opencplc/pack.py

"""
Flash image packing, `--pack`: the application hex made into what goes into flash.

Under the bootloader the application gets the CRC in its trailer and the bootloader in front.
One file then flashes a bare chip, and the update binary lands beside it.
Under the `key` bootloader the trailer also takes the signature:
a build signs with the development key, which its bootloader holds in place of each product key,
`dist` signs with the product key `PRO_SIGNING_KEY` names.
Without a bootloader the flash image is the application as linked.
"""

import sys
from xaeian import Print, Color as c, PATH
from xaeian.crc import crc32_iso
from .args import flag
from .resolver import FLASH_BASE
from .utils import hexfile, keys, ed25519
from . import utils

p = Print()

HEADER_OFFSET = 0x200   # image header past every vector table, `BLD_HEADER_OFFSET` in Core
HEADER_MAGIC = b"OPEN"  # `BLD_MAGIC` in Core
SIGNATURE_OFFSET = 8    # signature in the trailer, past the CRC, `BLD_SIGNATURE_OFFSET` in Core
TRAILER_SIZE = 72       # CRC and signature, `BLD_TRAILER_SIZE` in Core

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

def pack(app_path:str, out_path:str, boot_path:str|None=None, keys_hex:str="", number:int=0,
  release:bool=False):
  """
  Flash image of the application; under the bootloader also the update binary.

  The trailer CRC covers the image with its gaps erased to `0xFF`, as flash holds them.
  The programmer and the update path then leave the same bytes behind.

  With `keys_hex`, `BOOT_KEYS` of a `key` bootloader, the signature covers the same bytes.
  A `release` signs with key `number` of them, a build with the development key.

  The bootloader region past the bootloader stays out of the file, the mailbox page with it.
  A programmer would write it as `0xFF`: flash with ECC takes no new record over written ones,
  and `FLASH_Erase` on the device skips a page that reads blank.
  """
  image = hexfile.load_hex(app_path)
  if not boot_path:
    hexfile.save_hex(image, out_path)
    return
  seed = None
  if keys_hex:
    public = [bytes.fromhex(key) for key in keys.keys_split(keys_hex)]
    if not 0 <= number < len(public):
      raise ValueError(f"no key {number} among the {len(public)} keys of BOOT_KEYS")
    seed = keys.signing_seed(public[number]) if release else keys.dev_seed()
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
  image.merge(boot)
  image.start = int.from_bytes(boot.read(FLASH_BASE + 4, 4), "little") # its reset vector
  # every refusal comes above, so a failed pack leaves no file behind
  hexfile.save_bin(image, update_path(out_path), origin, end - origin)
  hexfile.save_hex(image, out_path)

def pack_command(files:list[str]):
  """`--pack APP.hex OUT.hex [BOOT [KEYS NUMBER [dist]]]` after linking; exits on failure."""
  usage = f"{flag.p} takes APP.hex OUT.hex [BOOT [KEYS NUMBER [dist]]]"
  release = files[-1:] == ["dist"]
  files = files[:-1] if release else files
  if len(files) not in (2, 3, 5) or (release and len(files) != 5):
    p.err(usage)
    sys.exit(1)
  app, out, boot, keys_hex, number = files + [None] * (5 - len(files))
  try:
    pack(app, out, boot, keys_hex or "", int(number or 0), release)
  except (OSError, ValueError) as e:
    p.err(f"Pack failed: {e}")
    sys.exit(1)
  if release and keys_hex and len(keys.keys_split(keys_hex)) == 1:
    name = keys.product_name(bytes.fromhex(keys_hex)) or "<name>"
    p.wrn(f"{c.SKY}BOOT_KEYS{c.END} holds one key: its leak would end the updates of every device")
    p.run("Add spare keys before the first unit ships, "
      f"e.g. {utils.color_command(f'opencplc --keygen {name} 3')}")
