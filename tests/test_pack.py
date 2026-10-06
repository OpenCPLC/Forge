# tests/test_pack.py

"""Flash image packing: CRC in the trailer, bootloader in front, update binary beside."""

import zlib
import pytest
from conftest import write_app_image, write_boot_image
from opencplc.pack import pack, pack_command, update_path
from opencplc.resolver import FLASH_BASE
from opencplc.utils.hexfile import Memory, load_hex, save_hex
from opencplc.utils import keys, ed25519

ORIGIN = 0x08004000  # application slot behind a 16kB bootloader
SIZE = 0x400         # image bytes before the trailer
TRAILER = 72         # CRC32, then the signature

BOOT = bytes.fromhex("00100020" "81000008") + bytes(0xF8) # stack, reset vector 0x08000081
KEY_BOOT = BOOT + b"\xff" * 32 # `key` bootloader, its blank key slot right behind the code
KEY_AT = FLASH_BASE + len(BOOT)

def no_bootloader_keeps_the_application(tmp_path):
  write_app_image(tmp_path / "app.hex", ORIGIN, SIZE)
  pack(str(tmp_path / "app.hex"), str(tmp_path / "app-dist.hex"))
  assert load_hex(tmp_path / "app-dist.hex").segments == load_hex(tmp_path / "app.hex").segments
  assert not (tmp_path / "app-dist.bin").exists()

def crc_covers_the_image_with_gaps_erased(tmp_path):
  write_app_image(tmp_path / "app.hex", ORIGIN, SIZE)
  write_boot_image(tmp_path / "boot.hex", BOOT)
  pack(str(tmp_path / "app.hex"), str(tmp_path / "app-dist.hex"), str(tmp_path / "boot.hex"))
  update = (tmp_path / "app-dist.bin").read_bytes()
  assert len(update) == SIZE + TRAILER
  assert update[0xC0:0x200] == b"\xff" * 0x140
  assert update[SIZE:SIZE + 4] == zlib.crc32(update[:SIZE]).to_bytes(4, "little")
  assert update[SIZE + 4:] == b"\xff" * (TRAILER - 4)

def flash_image_starts_with_the_bootloader(tmp_path):
  write_app_image(tmp_path / "app.hex", ORIGIN, SIZE)
  write_boot_image(tmp_path / "boot.hex", BOOT)
  pack(str(tmp_path / "app.hex"), str(tmp_path / "app-dist.hex"), str(tmp_path / "boot.hex"))
  flash = load_hex(tmp_path / "app-dist.hex")
  assert flash.read(FLASH_BASE, len(BOOT)) == BOOT
  assert flash.read(ORIGIN, SIZE + TRAILER) == (tmp_path / "app-dist.bin").read_bytes()
  assert flash.start == 0x08000081

def flash_image_holds_bootloader_and_application_alone(tmp_path):
  """A programmer writes ones wherever the file says `0xFF`, and flash with ECC keeps them."""
  write_app_image(tmp_path / "app.hex", ORIGIN, SIZE)
  write_boot_image(tmp_path / "boot.hex", BOOT)
  pack(str(tmp_path / "app.hex"), str(tmp_path / "app-dist.hex"), str(tmp_path / "boot.hex"))
  runs = {addr: len(seg) for addr, seg in load_hex(tmp_path / "app-dist.hex").segments.items()}
  assert runs == {FLASH_BASE: len(BOOT), ORIGIN: SIZE + TRAILER} # the mailbox page stays erased

def bootloader_hex_lands_by_its_addresses(tmp_path):
  write_app_image(tmp_path / "app.hex", ORIGIN, SIZE)
  write_boot_image(tmp_path / "boot.hex", BOOT)
  pack(str(tmp_path / "app.hex"), str(tmp_path / "app-dist.hex"), str(tmp_path / "boot.hex"))
  assert load_hex(tmp_path / "app-dist.hex").read(FLASH_BASE, len(BOOT)) == BOOT

def image_without_header_is_refused(tmp_path):
  write_app_image(tmp_path / "app.hex", ORIGIN, SIZE, header=False)
  write_boot_image(tmp_path / "boot.hex", BOOT)
  with pytest.raises(ValueError, match="no image header"):
    pack(str(tmp_path / "app.hex"), str(tmp_path / "app-dist.hex"), str(tmp_path / "boot.hex"))

def application_over_the_bootloader_is_refused(tmp_path):
  write_app_image(tmp_path / "app.hex", FLASH_BASE, SIZE)
  write_boot_image(tmp_path / "boot.hex", BOOT)
  with pytest.raises(ValueError, match="overlaps"):
    pack(str(tmp_path / "app.hex"), str(tmp_path / "app-dist.hex"), str(tmp_path / "boot.hex"))

@pytest.fixture()
def key_files(tmp_path):
  """Application hex, its flash image and a `key` bootloader, the paths `pack` takes."""
  write_app_image(tmp_path / "app.hex", ORIGIN, SIZE)
  write_boot_image(tmp_path / "boot.hex", KEY_BOOT)
  return tuple(str(tmp_path / f) for f in ("app.hex", "app-dist.hex", "boot.hex"))

def build_signs_with_the_development_key_and_puts_it_into_the_bootloader(tmp_path, key_files):
  pack(*key_files, KEY_AT)
  public = keys.dev_public()
  update = (tmp_path / "app-dist.bin").read_bytes()
  assert update[SIZE:SIZE + 4] == zlib.crc32(update[:SIZE]).to_bytes(4, "little")
  assert ed25519.verify(public, update[:SIZE], update[SIZE + 8:SIZE + TRAILER])
  assert load_hex(tmp_path / "app-dist.hex").read(KEY_AT, 32) == public

def dist_signs_for_pro_boot_key_byte_for_byte_as_the_build(tmp_path, key_files):
  """The development key named in `PRO_BOOT_KEY` signs `dist` too, the same bytes as a build."""
  app, _, boot = key_files
  pack(*key_files, KEY_AT)
  pack(app, str(tmp_path / "release.hex"), boot, KEY_AT, keys.dev_public())
  assert (tmp_path / "release.bin").read_bytes() == (tmp_path / "app-dist.bin").read_bytes()
  assert (tmp_path / "release.hex").read_text() == (tmp_path / "app-dist.hex").read_text()

def key_this_machine_lacks_stops_before_any_file(tmp_path, key_files):
  with pytest.raises(ValueError, match="no private key"):
    pack(*key_files, KEY_AT, bytes(32))
  assert not (tmp_path / "app-dist.hex").exists() and not (tmp_path / "app-dist.bin").exists()

def bootloader_without_a_blank_key_slot_is_refused_before_any_file(tmp_path, key_files):
  """A `plain` bootloader where the `key` one belongs, or one keyed already."""
  for image in (BOOT, BOOT + bytes(32)):
    write_boot_image(tmp_path / "boot.hex", image)
    with pytest.raises(ValueError, match="no blank key slot"):
      pack(*key_files, KEY_AT)
  assert not (tmp_path / "app-dist.bin").exists()

def image_needs_its_whole_trailer(tmp_path):
  """CRC and signature, `plain` or `key`: linker leaves the same 72 bytes behind every image."""
  write_app_image(tmp_path / "app.hex", ORIGIN, SIZE, trailer=8)
  write_boot_image(tmp_path / "boot.hex", BOOT)
  with pytest.raises(ValueError, match="no trailer"):
    pack(str(tmp_path / "app.hex"), str(tmp_path / "app-dist.hex"), str(tmp_path / "boot.hex"))

def key_bootloader_hex_leaves_the_gap_below_its_key_erased(tmp_path):
  """A hex keeps code and key slot apart, so the programmer leaves the gap erased."""
  write_app_image(tmp_path / "app.hex", ORIGIN, SIZE)
  key_at = FLASH_BASE + 0x1000
  boot = Memory()
  boot.add(FLASH_BASE, BOOT)
  boot.add(key_at, b"\xff" * 32)
  save_hex(boot, tmp_path / "boot.hex")
  app, out, boot_hex = (str(tmp_path / f) for f in ("app.hex", "app-dist.hex", "boot.hex"))
  pack(app, out, boot_hex, key_at)
  flash = load_hex(tmp_path / "app-dist.hex")
  runs = {addr: len(seg) for addr, seg in flash.segments.items()}
  assert runs == {FLASH_BASE: len(BOOT), key_at: 32, ORIGIN: SIZE + TRAILER}
  assert flash.read(key_at, 32) == keys.dev_public()

def pack_command_reads_the_key_address_and_the_key(tmp_path, key_files):
  public = keys.dev_public()
  pack_command([*key_files, f"0x{KEY_AT:08X}", public.hex()])
  assert load_hex(tmp_path / "app-dist.hex").read(KEY_AT, 32) == public

def update_binary_sits_beside_the_flash_image():
  assert update_path("build/app-dist.hex") == "build/app-dist.bin"

def wrong_file_count_exits():
  with pytest.raises(SystemExit):
    pack_command(["app.hex"])
