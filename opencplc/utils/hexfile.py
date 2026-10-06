# opencplc/utils/hexfile.py

"""
Flash contents as bytes by address, read from Intel HEX, written to Intel HEX or raw binary.

The one primitive behind `--pack`: load images, patch bytes in place, merge, save.
Only the record types `objcopy` writes for 32-bit targets are read:
data, end of file, extended linear address and start linear address.

Example:
  >>> memory = load_hex("app.hex")
  >>> memory.merge(load_hex("boot.hex"))
  >>> save_hex(memory, "flash.hex")
"""

from xaeian import FILE

RECORD_DATA = 0x00
RECORD_EOF = 0x01
RECORD_LINEAR = 0x04  # upper 16 bits of the address for the records that follow
RECORD_START = 0x05   # entry point
LINE_BYTES = 16       # data bytes per record, as `objcopy` writes them

class Memory:
  """Bytes by address in contiguous segments; a gap is flash the image leaves untouched."""
  def __init__(self):
    self.segments: dict[int, bytearray] = {}
    self.start: int|None = None

  def add(self, addr:int, data:bytes):
    """New bytes at `addr`; refuses to cover bytes already in the image."""
    end = addr + len(data)
    for seg_addr, seg in self.segments.items():
      if addr < seg_addr + len(seg) and seg_addr < end:
        raise ValueError(
          f"0x{addr:08X}..0x{end:08X} overlaps 0x{seg_addr:08X}..0x{seg_addr + len(seg):08X}")
    self.segments[addr] = bytearray(data)
    self._join()

  def _join(self):
    """Adjacent segments become one."""
    joined: dict[int, bytearray] = {}
    last = None
    for addr in sorted(self.segments):
      if last is not None and last + len(joined[last]) == addr:
        joined[last] += self.segments[addr]
      else:
        joined[addr] = self.segments[addr]
        last = addr
    self.segments = joined

  def _find(self, addr:int, size:int) -> tuple[int, bytearray]:
    """Segment holding all of `addr..addr + size`."""
    for seg_addr, seg in self.segments.items():
      if seg_addr <= addr and addr + size <= seg_addr + len(seg): return seg_addr, seg
    raise ValueError(f"0x{addr:08X}..0x{addr + size:08X} is not in the image")

  def read(self, addr:int, size:int) -> bytes:
    """Bytes `addr..addr + size`, which must be in the image without a gap."""
    seg_addr, seg = self._find(addr, size)
    offset = addr - seg_addr
    return bytes(seg[offset:offset + size])

  def write(self, addr:int, data:bytes):
    """Overwrite bytes already in the image; a patch never grows it."""
    seg_addr, seg = self._find(addr, len(data))
    offset = addr - seg_addr
    seg[offset:offset + len(data)] = data

  def fill(self, addr:int, size:int, byte:int=0xFF):
    """Every gap in `addr..addr + size` filled with `byte`; bytes already there stay."""
    gaps = []
    pos, end = addr, addr + size
    for seg_addr in sorted(self.segments):
      seg_end = seg_addr + len(self.segments[seg_addr])
      if seg_end <= pos or seg_addr >= end: continue
      if seg_addr > pos: gaps.append((pos, seg_addr))
      pos = max(pos, seg_end)
    if pos < end: gaps.append((pos, end))
    for gap_addr, gap_end in gaps:
      self.add(gap_addr, bytes([byte]) * (gap_end - gap_addr))

  def merge(self, other:"Memory"):
    """Bytes of `other` added to this image; any overlap is refused."""
    for addr, seg in other.segments.items():
      self.add(addr, seg)

def _parse(line:str) -> tuple[int, int, bytes]:
  """Type, 16-bit offset and data of one record, its checksum verified."""
  if not line.startswith(":"): raise ValueError("record does not start with ':'")
  raw = bytes.fromhex(line[1:])
  if len(raw) < 5 or len(raw) != raw[0] + 5: raise ValueError("record length does not match")
  if sum(raw) & 0xFF: raise ValueError("record checksum does not match")
  return raw[3], int.from_bytes(raw[1:3], "big"), raw[4:-1]

def _record(kind:int, offset:int, data:bytes) -> str:
  """One record line with its checksum."""
  raw = bytes([len(data)]) + offset.to_bytes(2, "big") + bytes([kind]) + bytes(data)
  return ":" + (raw + bytes([-sum(raw) & 0xFF])).hex().upper()

def load_hex(path:str) -> Memory:
  """Memory from an Intel HEX file."""
  memory = Memory()
  upper = 0
  run_addr, run = 0, bytearray() # consecutive records gathered before they are added
  for number, line in enumerate(FILE.iter_lines(path, strip=True), 1):
    if not line: continue
    try:
      kind, offset, data = _parse(line)
    except ValueError as e:
      raise ValueError(f"{path}:{number}: {e}") from None
    if kind == RECORD_DATA:
      addr = upper + offset
      if run and addr != run_addr + len(run):
        memory.add(run_addr, run)
        run = bytearray()
      if not run: run_addr = addr
      run += data
    elif kind == RECORD_LINEAR:
      upper = int.from_bytes(data, "big") << 16
    elif kind == RECORD_START:
      memory.start = int.from_bytes(data, "big")
    elif kind == RECORD_EOF:
      break
    else:
      raise ValueError(f"{path}:{number}: record type {kind:02X} is not supported")
  if run: memory.add(run_addr, run)
  return memory

def save_hex(memory:Memory, path:str):
  """
  Intel HEX, 16 data bytes per record; no record crosses a 64kB boundary.

  Saved atomically: an interrupted pack leaves no half file that make would take as built.
  """
  lines = []
  upper = None
  for seg_addr in sorted(memory.segments):
    seg = memory.segments[seg_addr]
    pos = 0
    while pos < len(seg):
      addr = seg_addr + pos
      size = min(LINE_BYTES, len(seg) - pos, 0x10000 - (addr & 0xFFFF))
      if addr >> 16 != upper:
        upper = addr >> 16
        lines.append(_record(RECORD_LINEAR, 0, upper.to_bytes(2, "big")))
      lines.append(_record(RECORD_DATA, addr & 0xFFFF, seg[pos:pos + size]))
      pos += size
  if memory.start is not None:
    lines.append(_record(RECORD_START, 0, memory.start.to_bytes(4, "big")))
  lines.append(_record(RECORD_EOF, 0, b""))
  FILE.save(path, "\n".join(lines) + "\n")

def save_bin(memory:Memory, path:str, addr:int, size:int):
  """Raw bytes `addr..addr + size`, which must be in the image without a gap."""
  FILE.save(path, memory.read(addr, size))
