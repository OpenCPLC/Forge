# tests/test_pack.py

"""Flash image packing: CRC in the trailer, bootloader in front, update binary beside."""

import zlib
import pytest
from conftest import write_app_image, write_boot_image, signed_by
from opencplc.pack import pack, pack_command, update_path
from opencplc.project import ANSI
from opencplc.platforms import FLASH_BASE
from opencplc.utils.hexfile import load_hex
from opencplc.utils import keys

ORIGIN = 0x08004000  # application slot behind a 16kB bootloader
SIZE = 0x400         # image bytes before the trailer
TRAILER = 72         # CRC32, then the signature

BOOT = bytes.fromhex("00100020" "81000008") + bytes(0xF8) # stack, reset vector 0x08000081
KEYS = "8a" * 32 + "5C" * 32 # `BOOT_KEYS` of a product with two keys, as its main.h writes them

def no_bootloader_keeps_the_application(tmp_path):
  write_app_image(tmp_path / "app.hex", ORIGIN, SIZE)
  pack(str(tmp_path / "app.hex"), str(tmp_path / "app-dist.hex"))
  assert (load_hex(str(tmp_path / "app-dist.hex")).segments
    == load_hex(str(tmp_path / "app.hex")).segments)
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
  flash = load_hex(str(tmp_path / "app-dist.hex"))
  assert flash.read(FLASH_BASE, len(BOOT)) == BOOT
  assert flash.read(ORIGIN, SIZE + TRAILER) == (tmp_path / "app-dist.bin").read_bytes()
  assert flash.start == 0x08000081

def flash_image_holds_bootloader_and_application_alone(tmp_path):
  """A programmer writes ones wherever the file says `0xFF`, and flash with ECC keeps them."""
  write_app_image(tmp_path / "app.hex", ORIGIN, SIZE)
  write_boot_image(tmp_path / "boot.hex", BOOT)
  pack(str(tmp_path / "app.hex"), str(tmp_path / "app-dist.hex"), str(tmp_path / "boot.hex"))
  flash = load_hex(str(tmp_path / "app-dist.hex"))
  runs = {addr: len(seg) for addr, seg in flash.segments.items()}
  assert runs == {FLASH_BASE: len(BOOT), ORIGIN: SIZE + TRAILER} # the mailbox page stays erased

def bootloader_hex_lands_by_its_addresses(tmp_path):
  write_app_image(tmp_path / "app.hex", ORIGIN, SIZE)
  write_boot_image(tmp_path / "boot.hex", BOOT)
  pack(str(tmp_path / "app.hex"), str(tmp_path / "app-dist.hex"), str(tmp_path / "boot.hex"))
  assert load_hex(str(tmp_path / "app-dist.hex")).read(FLASH_BASE, len(BOOT)) == BOOT

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

def image_needs_its_whole_trailer(tmp_path):
  """CRC and signature, `plain` or `key`: linker leaves the same 72 bytes behind every image."""
  write_app_image(tmp_path / "app.hex", ORIGIN, SIZE, trailer=8)
  write_boot_image(tmp_path / "boot.hex", BOOT)
  with pytest.raises(ValueError, match="no trailer"):
    pack(str(tmp_path / "app.hex"), str(tmp_path / "app-dist.hex"), str(tmp_path / "boot.hex"))

@pytest.fixture()
def key_files(tmp_path):
  """Application hex, its flash image and a `key` bootloader, the paths `pack` takes."""
  write_app_image(tmp_path / "app.hex", ORIGIN, SIZE)
  write_boot_image(tmp_path / "boot.hex", BOOT)
  return tuple(str(tmp_path / f) for f in ("app.hex", "app-dist.hex", "boot.hex"))

def build_signs_with_the_development_key(tmp_path, key_files):
  """The bootloader of builds holds it in place of every key, so it starts any key's image."""
  pack(*key_files, KEYS, 1)
  update = (tmp_path / "app-dist.bin").read_bytes()
  assert update[SIZE:SIZE + 4] == zlib.crc32(update[:SIZE]).to_bytes(4, "little")
  assert signed_by(keys.dev_public(), update, SIZE)
  flash = load_hex(str(tmp_path / "app-dist.hex"))
  assert flash.read(FLASH_BASE, len(BOOT)) == BOOT # the bootloader as its build linked it
  runs = {addr: len(seg) for addr, seg in flash.segments.items()}
  assert runs == {FLASH_BASE: len(BOOT), ORIGIN: SIZE + TRAILER}

def dist_signs_with_the_sign_key_of_its_number(tmp_path, key_files):
  app, out, boot = key_files
  first, second = keys.sign_make("first", ""), keys.sign_make("second", "")
  pack(app, out, boot, first.hex() + second.hex(), 1, release=True)
  update = (tmp_path / "app-dist.bin").read_bytes()
  assert signed_by(second, update, SIZE) and not signed_by(first, update, SIZE)
  assert load_hex(out).read(FLASH_BASE, len(BOOT)) == BOOT

def dist_under_a_password_takes_it_from_ci_and_a_wrong_one_writes_nothing(tmp_path, key_files,
  monkeypatch):
  app, out, boot = key_files
  public = keys.sign_make("acme", "correct horse")
  monkeypatch.setenv(keys.SIGN_PASSWORD.env, "wrong horse")
  with pytest.raises(ValueError, match="wrong password"):
    pack(app, out, boot, public.hex(), 0, release=True)
  assert not (tmp_path / "app-dist.hex").exists() and not (tmp_path / "app-dist.bin").exists()
  monkeypatch.setenv(keys.SIGN_PASSWORD.env, "correct horse")
  pack(app, out, boot, public.hex(), 0, release=True)
  assert signed_by(public, (tmp_path / "app-dist.bin").read_bytes(), SIZE)

def dist_and_build_match_byte_for_byte_under_the_development_key(tmp_path, key_files):
  """`BOOT_KEYS` of the development key alone: `dist` signs with it, as the build does."""
  app, _, boot = key_files
  dev = keys.dev_public().hex()
  pack(app, str(tmp_path / "build.hex"), boot, dev, 0)
  pack(app, str(tmp_path / "release.hex"), boot, dev, 0, release=True)
  assert (tmp_path / "release.bin").read_bytes() == (tmp_path / "build.bin").read_bytes()
  assert (tmp_path / "release.hex").read_text() == (tmp_path / "build.hex").read_text()

def key_this_machine_lacks_stops_before_any_file(tmp_path, key_files):
  with pytest.raises(ValueError, match="no sign key"):
    pack(*key_files, KEYS, 0, release=True)
  assert not (tmp_path / "app-dist.hex").exists() and not (tmp_path / "app-dist.bin").exists()

def key_number_outside_the_keys_stops_before_any_file(tmp_path, key_files):
  for number in (2, -1):
    with pytest.raises(ValueError, match="among 2 keys"):
      pack(*key_files, KEYS, number)
  assert not (tmp_path / "app-dist.hex").exists() and not (tmp_path / "app-dist.bin").exists()

def pack_command_reads_the_keys_and_the_number(tmp_path, key_files):
  pack_command([*key_files, KEYS, "1"])
  assert signed_by(keys.dev_public(), (tmp_path / "app-dist.bin").read_bytes(), SIZE)

def pack_command_signs_dist_with_the_sign_key(tmp_path, key_files):
  app, out, boot = key_files
  public = keys.sign_make("acme", "")
  pack_command([app, out, boot, public.hex(), "0", "dist"])
  assert signed_by(public, (tmp_path / "app-dist.bin").read_bytes(), SIZE)

def dist_warns_of_an_image_another_build_left_encrypted(tmp_path, key_files, capsys):
  """
  An encrypted image keeps the plain trailer of its build, and one build packs to one trailer.
  The image of this build under another key stays quiet, one of another build speaks up
  unless `CIPHER=` encrypts it anew right after, and a plain image named like a key is none.
  """
  app, out, boot = key_files
  public = keys.sign_make("acme", "")
  for name in ("same", "older", "rc1"): keys.cipher_make(name, "")
  pack_command([app, out, boot, public.hex(), "0", "dist"])
  update = (tmp_path / "app-dist.bin").read_bytes()
  body, trailer = update[:-TRAILER], update[-TRAILER:]
  scrambled = bytes(byte ^ 0xFF for byte in body) # misses the CRC, as encrypted bytes do
  (tmp_path / "app-dist.same.bin").write_bytes(scrambled + trailer)
  (tmp_path / "app-dist.older.bin").write_bytes(scrambled + bytes(TRAILER))
  zero = bytes(len(body)) # plain: its trailer holds the CRC of its bytes
  (tmp_path / "app-dist.rc1.bin").write_bytes(zero + zlib.crc32(zero).to_bytes(4, "little")
    + b"\xff" * (TRAILER - 4))
  capsys.readouterr()
  pack_command([app, out, boot, public.hex(), "0", "dist"])
  shown = ANSI.sub("", capsys.readouterr().out)
  assert "app-dist.older.bin comes from another build" in shown and "CIPHER=older" in shown
  assert "app-dist.same.bin" not in shown and "app-dist.rc1.bin" not in shown
  pack_command([app, out, boot, public.hex(), "0", "dist", "older"])
  assert "another build" not in capsys.readouterr().out

def update_binary_sits_beside_the_flash_image():
  assert update_path("build/app-dist.hex") == "build/app-dist.bin"

def pack_command_of_other_arguments_exits(tmp_path):
  """
  Files, then keys with a number, `dist` only behind them and a cipher key only behind `dist`;
  a failed pack exits as well.
  """
  for args in (["app.hex"], ["a", "b", "c", KEYS], ["a", "b", "dist"], ["a", "b", "c", "dist"],
    ["a", "b", "c", "dist", "acme"], ["a", "b", "c", KEYS, "0", "x", "dist"],
    [str(tmp_path / "none.hex"), "b"]):
    with pytest.raises(SystemExit):
      pack_command(args)
