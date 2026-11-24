# opencplc/pack.py

"""
Flash image packing, `--pack`: the application hex made into what goes into flash.

Under the bootloader the application gets the CRC in its trailer and the bootloader in front.
One file then flashes a bare chip, and the update binary lands beside it.
Under the `key` bootloader the trailer also takes the signature:
a build signs with the development key, which its bootloader holds in place of each sign key,
`dist` signs with the sign key `PRO_SIGNING_KEY` names.
Without a bootloader the flash image is the application as linked.
"""

import sys
from xaeian import Print, PATH, FILE, DIR
from xaeian.crc import crc32_iso
from .args import flag
from .platforms import FLASH_BASE, CHIPS
from .utils import hexfile, keys, ed25519
from . import utils

p = Print()

HEADER_MAGIC = b"OPEN"  # `BLD_MAGIC` in Core
SIGNATURE_OFFSET = 8    # signature in the trailer, past the CRC, `BLD_SIGNATURE_OFFSET` in Core
TRAILER_SIZE = 72       # CRC and signature, `BLD_TRAILER_SIZE` in Core

# Offsets an image header stands at, past the vector table of its chip, `BOOT_HEADER` of Core
HEADER_OFFSETS = sorted({chip.header_offset for chip in CHIPS.values() if chip.dev_id})

def image_size(image:hexfile.Memory, origin:int) -> int:
  """
  Bytes before the trailer, as the image header names them.

  The header stands at the offset of its chip, the first of `HEADER_OFFSETS` holding the magic:
  a vector table holds handler addresses, never `OPEN`.
  """
  for offset in HEADER_OFFSETS:
    try:
      header = image.read(origin + offset, 8)
    except ValueError:
      continue
    if header[:4] == HEADER_MAGIC: return int.from_bytes(header[4:], "little")
  raise ValueError(f"no image header past 0x{origin:08X}")

def update_path(out_path:str) -> str:
  """Update binary beside the flash image, under its name: `app-dist.hex` → `app-dist.bin`."""
  return PATH.with_suffix(out_path, ".bin")

def encrypted_path(update:str, name:str) -> str:
  """Update binary encrypted with cipher key `name`: `app-1.2.0.bin` → `app-1.2.0.acme.bin`."""
  return PATH.with_suffix(update, f".{name}.bin")

def encrypted(data:bytes) -> bool:
  """Update image `data` whose bytes miss the CRC of its plain trailer: encrypted, or damaged."""
  if len(data) <= TRAILER_SIZE: return True
  body, trailer = data[:-TRAILER_SIZE], data[-TRAILER_SIZE:]
  return crc32_iso.checksum(body) != int.from_bytes(trailer[:4], "little")

def older_images(update:str, skip:str="") -> list[tuple[str, str]]:
  """
  Images beside update binary `update` that another build left encrypted, with their key names.

  Encryption leaves the trailer plain, and one build packed twice gives the same one,
  so the last 72 bytes tell builds apart without a key or a password.
  Only names of keys in the key folder count, so images of other tags stay out,
  and key `skip` encrypts anew right after, which overwrites its image.
  """
  folder = keys.keys_dir()
  if not DIR.exists(folder): return []
  trailer = FILE.load(update, binary=True)[-TRAILER_SIZE:]
  older = []
  for key_file in sorted(DIR.file_list(folder, exts=[".cipher"], deep=False)):
    name = PATH.stem(key_file)
    path = encrypted_path(update, name)
    if name == skip or not FILE.exists(path): continue
    data = FILE.load(path, binary=True)
    # A plain image of a tag named like a key goes by the same file name
    if encrypted(data) and data[-TRAILER_SIZE:] != trailer: older.append((name, path))
  return older

def pack(
  app_path:str, out_path:str,
  boot_path:str|None = None,
  keys_hex:str = "", number:int = 0,
  release:bool = False,
):
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
      raise ValueError(f"no key {number} among {len(public)} keys of BOOT_KEYS")
    seed = keys.seed_for(public[number]) if release else keys.dev_seed()
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
  # Every refusal comes above, so a failed pack leaves no file behind
  hexfile.save_bin(image, update_path(out_path), origin, end - origin)
  hexfile.save_hex(image, out_path)

def pack_command(files:list[str]):
  """
  `--pack APP.hex OUT.hex [BOOT [KEYS NUMBER [dist [CIPHER]]]]` after linking; exits on failure.

  `CIPHER` names the key `make dist` encrypts with right after.
  """
  usage = f"Flag {flag.p} takes APP.hex OUT.hex [BOOT [KEYS NUMBER [dist [CIPHER]]]]"
  cipher = ""
  if files[-2:-1] == ["dist"]: files, cipher = files[:-1], files[-1]
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
  if not release: return
  for name, path in older_images(update_path(out), cipher):
    p.wrn(f"Image {utils.color_image(PATH.basename(path))} comes from another build")
    p.tip(f"Encrypt this build with same TAG: {utils.color_command(f'make dist CIPHER={name}')}")
