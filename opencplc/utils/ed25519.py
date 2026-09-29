# opencplc/utils/ed25519.py

"""
Ed25519 signatures after RFC 8032, pure Python, no dependencies.

Signing runs once per build on the developer's machine, so the arithmetic is plain integers,
chosen for being easy to check against the RFC rather than for speed or constant time.

Example:
  >>> pub = public_key(seed)
  >>> sig = sign(seed, image)
  >>> verify(pub, image, sig)
  True
"""

import hashlib

P = 2**255 - 19 # field prime
L = 2**252 + 27742317777372353535851937790883648493 # order of the base point
CURVE_D = -121665 * pow(121666, -1, P) % P
SQRT_M1 = pow(2, (P - 1) // 4, P) # square root of -1 in the field

# Extended coordinates (X, Y, Z, T): x = X/Z, y = Y/Z, x*y = T/Z
Point = tuple[int, int, int, int]
NEUTRAL: Point = (0, 1, 1, 0)

def _point(x:int, y:int) -> Point:
  return (x, y, 1, x * y % P)

def _add(p1:Point, p2:Point) -> Point:
  """Sum of two points; the formula is complete, so it also doubles (RFC 8032 5.1.4)."""
  x1, y1, z1, t1 = p1
  x2, y2, z2, t2 = p2
  a = (y1 - x1) * (y2 - x2) % P
  b = (y1 + x1) * (y2 + x2) % P
  c = 2 * t1 * t2 * CURVE_D % P
  d = 2 * z1 * z2 % P
  e, f, g, h = b - a, d - c, d + c, b + a
  return (e * f % P, g * h % P, f * g % P, e * h % P)

def _mul(scalar:int, point:Point) -> Point:
  """`scalar` times `point`, double-and-add from the lowest bit."""
  result = NEUTRAL
  while scalar > 0:
    if scalar & 1: result = _add(result, point)
    point = _add(point, point)
    scalar >>= 1
  return result

def _equal(p1:Point, p2:Point) -> bool:
  """Same affine point, compared without inverting `Z`."""
  x1, y1, z1, _ = p1
  x2, y2, z2, _ = p2
  return (x1 * z2 - x2 * z1) % P == 0 and (y1 * z2 - y2 * z1) % P == 0

def _recover_x(y:int, sign:int) -> int|None:
  """`x` of the curve point with this `y` and parity `sign`, `None` when there is none."""
  if y >= P: return None
  x2 = (y * y - 1) * pow(CURVE_D * y * y + 1, -1, P) % P
  if x2 == 0: return None if sign else 0
  x = pow(x2, (P + 3) // 8, P)
  if (x * x - x2) % P: x = x * SQRT_M1 % P
  if (x * x - x2) % P: return None
  if (x & 1) != sign: x = P - x
  return x

_BASE_Y = 4 * pow(5, -1, P) % P
BASE = _point(_recover_x(_BASE_Y, 0), _BASE_Y)

def _encode(point:Point) -> bytes:
  """32 bytes: `y` little-endian, the parity of `x` in the top bit."""
  x, y, z, _ = point
  z_inv = pow(z, -1, P)
  x, y = x * z_inv % P, y * z_inv % P
  return (y | (x & 1) << 255).to_bytes(32, "little")

def _decode(data:bytes) -> Point|None:
  """Point from its 32-byte encoding, `None` when the bytes name no point."""
  if len(data) != 32: return None
  y = int.from_bytes(data, "little")
  sign, y = y >> 255, y & ((1 << 255) - 1)
  x = _recover_x(y, sign)
  return None if x is None else _point(x, y)

def _hash_int(*parts:bytes) -> int:
  """SHA-512 of the joined parts, read little-endian."""
  return int.from_bytes(hashlib.sha512(b"".join(parts)).digest(), "little")

def _expand(seed:bytes) -> tuple[int, bytes]:
  """Secret scalar and nonce prefix of a 32-byte seed."""
  if len(seed) != 32: raise ValueError("Ed25519 seed must be 32 bytes")
  digest = hashlib.sha512(seed).digest()
  scalar = int.from_bytes(digest[:32], "little")
  # clamped: low 3 bits and bit 255 cleared, bit 254 set
  scalar &= (1 << 254) - 8
  scalar |= 1 << 254
  return scalar, digest[32:]

def public_key(seed:bytes) -> bytes:
  """32-byte public key of a 32-byte seed."""
  scalar, _ = _expand(seed)
  return _encode(_mul(scalar, BASE))

def sign(seed:bytes, message:bytes) -> bytes:
  """64-byte signature of `message`; deterministic, the same input always signs the same."""
  scalar, prefix = _expand(seed)
  public = public_key(seed)
  r = _hash_int(prefix, message) % L
  r_bytes = _encode(_mul(r, BASE))
  k = _hash_int(r_bytes, public, message) % L
  s = (r + k * scalar) % L
  return r_bytes + s.to_bytes(32, "little")

def verify(public:bytes, message:bytes, signature:bytes) -> bool:
  """`True` when `signature` over `message` was made with the seed behind `public`."""
  if len(signature) != 64: return False
  point_a = _decode(public)
  point_r = _decode(signature[:32])
  if point_a is None or point_r is None: return False
  s = int.from_bytes(signature[32:], "little")
  if s >= L: return False
  k = _hash_int(signature[:32], public, message) % L
  return _equal(_mul(s, BASE), _add(point_r, _mul(k, point_a)))
