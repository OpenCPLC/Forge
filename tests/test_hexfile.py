# tests/test_hexfile.py

"""Intel HEX and binary images: round trips, joins, patches and what gets refused."""

import pytest
from opencplc.utils.hexfile import Memory, load_hex, save_hex, save_bin

def round_trip_keeps_bytes_and_entry(tmp_path):
  memory = Memory()
  memory.add(0x08000000, bytes(range(40)))
  memory.add(0x0800FFF8, bytes(range(100, 132))) # crosses a 64kB boundary
  memory.start = 0x08000101
  save_hex(memory, tmp_path / "image.hex")
  loaded = load_hex(tmp_path / "image.hex")
  assert loaded.segments == memory.segments
  assert loaded.start == 0x08000101

def no_record_crosses_64kB(tmp_path):
  memory = Memory()
  memory.add(0x0800FFF8, bytes(32))
  save_hex(memory, tmp_path / "image.hex")
  for line in (tmp_path / "image.hex").read_text().split():
    size, offset, kind = int(line[1:3], 16), int(line[3:7], 16), int(line[7:9], 16)
    if kind == 0x00: assert offset + size <= 0x10000

def adjacent_bytes_join_into_one_segment():
  memory = Memory()
  memory.add(0x100, b"ab")
  memory.add(0x104, b"ef")
  memory.add(0x102, b"cd")
  assert memory.segments == {0x100: bytearray(b"abcdef")}

def overlap_is_refused():
  memory = Memory()
  memory.add(0x100, bytes(4))
  with pytest.raises(ValueError):
    memory.add(0x102, bytes(4))

def fill_covers_only_the_gaps():
  memory = Memory()
  memory.add(0x100, b"vect")
  memory.add(0x108, b"head")
  memory.fill(0x100, 16)
  assert memory.segments == {0x100: bytearray(b"vect\xff\xff\xff\xffhead\xff\xff\xff\xff")}

def merge_joins_and_refuses_overlap():
  boot, app = Memory(), Memory()
  boot.add(0x0, b"boot")
  app.add(0x4, b"app")
  boot.merge(app)
  assert boot.read(0x0, 7) == b"bootapp"
  with pytest.raises(ValueError):
    boot.merge(app)

def patch_stays_inside_the_image():
  memory = Memory()
  memory.add(0x100, bytes(8))
  memory.add(0x200, bytes(8))
  memory.write(0x104, b"\x01\x02")
  assert memory.read(0x100, 8) == b"\x00\x00\x00\x00\x01\x02\x00\x00"
  with pytest.raises(ValueError):
    memory.write(0x106, bytes(4))  # would grow the image
  with pytest.raises(ValueError):
    memory.read(0x100, 0x108)      # spans the gap

def bin_holds_its_range_alone(tmp_path):
  memory = Memory()
  memory.add(0x08000000, b"\x11\x22\x33")
  save_bin(memory, tmp_path / "copy.bin", 0x08000001, 2)
  assert (tmp_path / "copy.bin").read_bytes() == b"\x22\x33"

def broken_checksum_names_the_line(tmp_path):
  (tmp_path / "bad.hex").write_text(":020000040800F2\n:0400000001020304F1\n:00000001FF\n")
  with pytest.raises(ValueError, match=r":2: record checksum"):
    load_hex(tmp_path / "bad.hex")

def unknown_record_is_refused(tmp_path):
  (tmp_path / "odd.hex").write_text(":020000021000EC\n:00000001FF\n")
  with pytest.raises(ValueError, match="record type 02"):
    load_hex(tmp_path / "odd.hex")
