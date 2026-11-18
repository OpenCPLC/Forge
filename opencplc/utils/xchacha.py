# opencplc/utils/xchacha.py

"""
XChaCha20 of Monocypher, `crypto_chacha20_x`, in pure Python: Forge encrypts what Core decrypts.

The first 16 bytes of the 24-byte nonce and the key give a subkey through HChaCha20,
the last 8 bytes and a 64-bit block counter run ChaCha20 under it.
Block `n` covers bytes `64n` to `64n + 63`, so a byte decrypts by its place in the data alone.
"""

MASK = 0xFFFFFFFF
SIGMA = [0x61707865, 0x3320646E, 0x79622D32, 0x6B206574] # "expand 32-byte k" as words

def words_of(data:bytes) -> list[int]:
  """`data` as little-endian 32-bit words."""
  return [int.from_bytes(data[i:i + 4], "little") for i in range(0, len(data), 4)]

def bytes_of(words:list[int]) -> bytes:
  """32-bit `words` as little-endian bytes."""
  return b"".join(word.to_bytes(4, "little") for word in words)

def rotate(value:int, bits:int) -> int:
  """`value` rotated left by `bits` within 32 bits."""
  return ((value << bits) | (value >> (32 - bits))) & MASK

def quarter_round(x:list[int], a:int, b:int, c:int, d:int):
  """Quarter round over words `a`, `b`, `c` and `d` of state `x`, in place."""
  x[a] = (x[a] + x[b]) & MASK
  x[d] = rotate(x[d] ^ x[a], 16)
  x[c] = (x[c] + x[d]) & MASK
  x[b] = rotate(x[b] ^ x[c], 12)
  x[a] = (x[a] + x[b]) & MASK
  x[d] = rotate(x[d] ^ x[a], 8)
  x[c] = (x[c] + x[d]) & MASK
  x[b] = rotate(x[b] ^ x[c], 7)

def rounds(state:list[int]) -> list[int]:
  """Twenty rounds over a copy of `state`: ten column rounds, each with its diagonal round."""
  x = list(state)
  for _ in range(10):
    quarter_round(x, 0, 4, 8, 12)
    quarter_round(x, 1, 5, 9, 13)
    quarter_round(x, 2, 6, 10, 14)
    quarter_round(x, 3, 7, 11, 15)
    quarter_round(x, 0, 5, 10, 15)
    quarter_round(x, 1, 6, 11, 12)
    quarter_round(x, 2, 7, 8, 13)
    quarter_round(x, 3, 4, 9, 14)
  return x

def hchacha20(key:bytes, nonce:bytes) -> bytes:
  """Subkey of HChaCha20 from `key` and 16 bytes of `nonce`."""
  x = rounds([*SIGMA, *words_of(key), *words_of(nonce)])
  return bytes_of(x[0:4] + x[12:16])

def block(key:bytes, nonce:bytes, counter:int) -> bytes:
  """Keystream block `counter` of ChaCha20 with a 64-bit counter and an 8-byte `nonce`."""
  state = [*SIGMA, *words_of(key), counter & MASK, (counter >> 32) & MASK, *words_of(nonce)]
  return bytes_of([(a + b) & MASK for a, b in zip(rounds(state), state)])

def xchacha20(data:bytes, key:bytes, nonce:bytes) -> bytes:
  """`data` encrypted, or decrypted, from block `0`, as `crypto_chacha20_x` with counter `0`."""
  subkey = hchacha20(key, nonce[:16])
  out = bytearray()
  for start in range(0, len(data), 64):
    stream = block(subkey, nonce[16:24], start // 64)
    out += bytes(a ^ b for a, b in zip(data[start:start + 64], stream))
  return bytes(out)
