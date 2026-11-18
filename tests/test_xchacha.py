# tests/test_xchacha.py

"""
XChaCha20 against the published vectors, RFC 8439 and the XChaCha draft.

Monocypher, which decrypts on the device, meets the same bytes in the tests of Core.
"""

from opencplc.utils import xchacha

# Plaintext of draft-irtf-cfrg-xchacha, section A.3.2
DHOLE = (b'The dhole (pronounced "dole") is also known as the Asiatic wild dog, red dog, '
  b"and whistling dog. It is about the size of a German shepherd but looks more like "
  b"a long-legged fox. This highly elusive and skilled jumper is classified with wolves, "
  b"coyotes, jackals, and foxes in the taxonomic family Canidae.")

def chacha20_block_matches_rfc_8439():
  """RFC 8439 2.3.2: its 32-bit counter and 12-byte nonce as a 64-bit counter and 8-byte nonce."""
  block = xchacha.block(bytes(range(32)), bytes.fromhex("0000004a00000000"), 1 | 0x09000000 << 32)
  assert block.hex() == (
    "10f1e7e4d13b5915500fdd1fa32071c4c7d1f4c733c068030422aa9ac3d46c4e"
    "d2826446079faa0914c2d705d98b02a2b5129cd1de164eb9cbd083e8a2503c4e")

def hchacha20_matches_the_xchacha_draft():
  """Vector of draft-irtf-cfrg-xchacha, section 2.2.1."""
  subkey = xchacha.hchacha20(bytes(range(32)), bytes.fromhex("000000090000004a0000000031415927"))
  assert subkey.hex() == "82413b4227b27bfed30e42508a877d73a0f9e4d58a74a853c12ec41326d3ecdc"

def xchacha20_matches_the_xchacha_draft():
  """Vector of draft-irtf-cfrg-xchacha, section A.3.2.1: counter `0`, 304 bytes."""
  nonce = bytes.fromhex("404142434445464748494a4b4c4d4e4f5051525354555658")
  assert xchacha.xchacha20(DHOLE, bytes(range(0x80, 0xA0)), nonce).hex() == (
    "4559abba4e48c16102e8bb2c05e6947f50a786de162f9b0b7e592a9b53d0d4e9"
    "8d8d6410d540a1a6375b26d80dace4fab52384c731acbf16a5923c0c48d3575d"
    "4d0d2c673b666faa731061277701093a6bf7a158a8864292a41c48e3a9b4c0da"
    "ece0f8d98d0d7e05b37a307bbb66333164ec9e1b24ea0d6c3ffddcec4f68e744"
    "3056193a03c810e11344ca06d8ed8a2bfb1e8d48cfa6bc0eb4e2464b74814240"
    "7c9f431aee769960e15ba8b96890466ef2457599852385c661f752ce20f9da0c"
    "09ab6b19df74e76a95967446f8d0fd415e7bee2a12a114c20eb5292ae7a349ae"
    "577820d5520a1f3fb62a17ce6a7e68fa7c79111d8860920bc048ef43fe84486c"
    "cb87c25f0ae045f0cce1e7989a9aa220a28bdd4827e751a24a6d5c62d790a663"
    "93b93111c1a55dd7421a10184974c7c5")
