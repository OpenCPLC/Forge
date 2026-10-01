# tests/test_pack.py

"""Flash image packing: CRC in the trailer, bootloader in front, update binary beside."""

import zlib
import pytest
from conftest import write_app_image
from opencplc.pack import pack, pack_command, update_path
from opencplc.resolver import FLASH_BASE
from opencplc.utils.hexfile import Memory, load_hex, save_hex

ORIGIN = 0x08004000 # application slot behind a 16kB bootloader
SIZE = 0x400 # image bytes before the trailer
TRAILER = 72 # CRC32, then the signature
BOOT = bytes.fromhex("00100020" "81000008") + bytes(0xF8) # stack, reset vector 0x08000081

def no_bootloader_keeps_the_application(tmp_path):
  write_app_image(tmp_path / "app.hex", ORIGIN, SIZE)
  pack(str(tmp_path / "app.hex"), str(tmp_path / "app-dist.hex"))
  assert load_hex(tmp_path / "app-dist.hex").segments == load_hex(tmp_path / "app.hex").segments
  assert not (tmp_path / "app-dist.bin").exists()

def crc_covers_the_image_with_gaps_erased(tmp_path):
  write_app_image(tmp_path / "app.hex", ORIGIN, SIZE)
  (tmp_path / "boot.bin").write_bytes(BOOT)
  pack(str(tmp_path / "app.hex"), str(tmp_path / "app-dist.hex"), str(tmp_path / "boot.bin"))
  update = (tmp_path / "app-dist.bin").read_bytes()
  assert len(update) == SIZE + TRAILER
  assert update[0xC0:0x200] == b"\xff" * 0x140
  assert update[SIZE:SIZE + 4] == zlib.crc32(update[:SIZE]).to_bytes(4, "little")
  assert update[SIZE + 4:] == b"\xff" * (TRAILER - 4)

def flash_image_starts_with_the_bootloader(tmp_path):
  write_app_image(tmp_path / "app.hex", ORIGIN, SIZE)
  (tmp_path / "boot.bin").write_bytes(BOOT)
  pack(str(tmp_path / "app.hex"), str(tmp_path / "app-dist.hex"), str(tmp_path / "boot.bin"))
  flash = load_hex(tmp_path / "app-dist.hex")
  assert flash.read(FLASH_BASE, len(BOOT)) == BOOT
  assert flash.read(ORIGIN, SIZE + TRAILER) == (tmp_path / "app-dist.bin").read_bytes()
  assert flash.start == 0x08000081

def flash_image_holds_bootloader_and_application_alone(tmp_path):
  """A programmer writes ones wherever the file says `0xFF`, and flash with ECC keeps them."""
  write_app_image(tmp_path / "app.hex", ORIGIN, SIZE)
  (tmp_path / "boot.bin").write_bytes(BOOT)
  pack(str(tmp_path / "app.hex"), str(tmp_path / "app-dist.hex"), str(tmp_path / "boot.bin"))
  runs = {addr: len(seg) for addr, seg in load_hex(tmp_path / "app-dist.hex").segments.items()}
  assert runs == {FLASH_BASE: len(BOOT), ORIGIN: SIZE + TRAILER} # the mailbox page stays erased

def bootloader_hex_lands_by_its_addresses(tmp_path):
  write_app_image(tmp_path / "app.hex", ORIGIN, SIZE)
  boot = Memory()
  boot.add(FLASH_BASE, BOOT)
  save_hex(boot, tmp_path / "boot.hex")
  pack(str(tmp_path / "app.hex"), str(tmp_path / "app-dist.hex"), str(tmp_path / "boot.hex"))
  assert load_hex(tmp_path / "app-dist.hex").read(FLASH_BASE, len(BOOT)) == BOOT

def older_core_with_8_byte_trailer_still_packs(tmp_path):
  """A project pinned to a Core older than the signature has the CRC alone behind its image."""
  write_app_image(tmp_path / "app.hex", ORIGIN, SIZE, trailer=8)
  (tmp_path / "boot.bin").write_bytes(BOOT)
  pack(str(tmp_path / "app.hex"), str(tmp_path / "app-dist.hex"), str(tmp_path / "boot.bin"))
  update = (tmp_path / "app-dist.bin").read_bytes()
  assert len(update) == SIZE + 8
  assert update[SIZE:SIZE + 4] == zlib.crc32(update[:SIZE]).to_bytes(4, "little")

def image_without_header_is_refused(tmp_path):
  write_app_image(tmp_path / "app.hex", ORIGIN, SIZE, header=False)
  (tmp_path / "boot.bin").write_bytes(BOOT)
  with pytest.raises(ValueError, match="no image header"):
    pack(str(tmp_path / "app.hex"), str(tmp_path / "app-dist.hex"), str(tmp_path / "boot.bin"))

def application_over_the_bootloader_is_refused(tmp_path):
  write_app_image(tmp_path / "app.hex", FLASH_BASE, SIZE)
  (tmp_path / "boot.bin").write_bytes(BOOT)
  with pytest.raises(ValueError, match="overlaps"):
    pack(str(tmp_path / "app.hex"), str(tmp_path / "app-dist.hex"), str(tmp_path / "boot.bin"))

def update_binary_sits_beside_the_flash_image():
  assert update_path("build/app-dist.hex") == "build/app-dist.bin"

def wrong_file_count_exits():
  with pytest.raises(SystemExit):
    pack_command(["app.hex"])
