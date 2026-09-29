# opencplc/pack.py

"""
Flash image packing, `--pack`: the application hex made into what goes into flash.

Under the bootloader the application gets the CRC in its trailer and the bootloader in front.
One file then flashes a bare chip, and the update binary for `UPDATE` lands beside it.
Without a bootloader the flash image is the application as linked.
"""

import sys
from xaeian import Print, PATH
from xaeian.crc import crc32_iso
from .args import flag
from .resolver import FLASH_BASE
from .utils import hexfile

p = Print()

HEADER_OFFSET = 0x200 # image header past every vector table, `BOOT_HEADER_OFFSET` in Core
HEADER_MAGIC = b"OPEN" # `BOOT_MAGIC` in Core

def image_size(image:hexfile.Memory, origin:int) -> int:
  """Bytes before the trailer, as the image header at `origin` names them."""
  try:
    header = image.read(origin + HEADER_OFFSET, 8)
  except ValueError:
    header = b""
  if header[:4] != HEADER_MAGIC:
    raise ValueError(f"no image header at 0x{origin + HEADER_OFFSET:08X}")
  return int.from_bytes(header[4:], "little")

def update_path(app_path:str) -> str:
  """Update binary beside the application hex: `app.hex` → `app-update.bin`."""
  return PATH.with_suffix(app_path, "-update.bin")

def pack(app_path:str, out_path:str, boot_path:str|None=None):
  """
  Flash image of the application; under the bootloader also the update binary.

  The trailer CRC covers the image with its gaps erased to `0xFF`, as flash holds them.
  The programmer and the update path then leave the same bytes behind.

  The bootloader region is filled with `0xFF` up to the slot, the mailbox page included.
  A programmer erases only the pages a file covers, so flashing drops a pending install.
  """
  image = hexfile.load_hex(app_path)
  if not boot_path:
    hexfile.save_hex(image, out_path)
    return
  origin = min(image.segments)
  end = max(addr + len(seg) for addr, seg in image.segments.items())
  size = image_size(image, origin)
  if origin + size + 4 > end:
    raise ValueError(f"image of {size}B has no trailer behind it")
  image.fill(origin, size)
  crc = crc32_iso.checksum(image.read(origin, size))
  image.write(origin + size, crc.to_bytes(4, "little"))
  hexfile.save_bin(image, update_path(app_path), origin, end - origin)
  if boot_path.endswith(".bin"):
    boot = hexfile.load_bin(boot_path, FLASH_BASE)
  else:
    boot = hexfile.load_hex(boot_path)
  image.merge(boot)
  image.fill(FLASH_BASE, origin - FLASH_BASE)
  image.start = int.from_bytes(boot.read(FLASH_BASE + 4, 4), "little") # its reset vector
  hexfile.save_hex(image, out_path)

def pack_command(files:list[str]):
  """`--pack APP.hex OUT.hex [BOOT]`, the makefile step after linking; exits on failure."""
  if len(files) not in (2, 3):
    p.err(f"{flag.p} takes APP.hex OUT.hex and, under the bootloader, its image")
    sys.exit(1)
  try:
    pack(*files)
  except (OSError, ValueError) as e:
    p.err(f"Pack failed: {e}")
    sys.exit(1)
