# tests/test_ed25519.py

"""Ed25519 against the RFC 8032 test vectors, and what verification must refuse."""

import hashlib
import pytest
from opencplc.utils import ed25519

# RFC 8032 7.1: seed, public key, message, signature
VECTORS = [
  (
    "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
    "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
    b"",
    "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
    "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b",
  ),
  (
    "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
    "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
    bytes.fromhex("72"),
    "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
    "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00",
  ),
  (
    "c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
    "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
    bytes.fromhex("af82"),
    "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac"
    "18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a",
  ),
  (
    "833fe62409237b9d62ec77587520911e9a759cec1d19755b7da901b96dca3d42",
    "ec172b93ad5e563bf4932c70e1245034c35467ef2efd4d64ebf819683467e2bf",
    hashlib.sha512(b"abc").digest(),
    "dc2a4459e7369633a52b1bf277839a00201009a3efbf3ecb69bea2186c26b589"
    "09351fc9ac90b3ecfdfbc7c66431e0303dca179c138ac17ad9bef1177331a704",
  ),
]

SEED = bytes.fromhex(VECTORS[1][0])
PUBLIC = bytes.fromhex(VECTORS[1][1])
MESSAGE = b"image bytes"

def rfc8032_vectors_match_byte_for_byte():
  for seed, public, message, signature in VECTORS:
    seed, public, signature = bytes.fromhex(seed), bytes.fromhex(public), bytes.fromhex(signature)
    assert ed25519.public_key(seed) == public
    assert ed25519.sign(seed, message) == signature
    assert ed25519.verify(public, message, signature)

def same_input_signs_the_same():
  assert ed25519.sign(SEED, MESSAGE) == ed25519.sign(SEED, MESSAGE)

def changed_message_is_refused():
  signature = ed25519.sign(SEED, MESSAGE)
  assert not ed25519.verify(PUBLIC, MESSAGE + b"!", signature)

def changed_signature_is_refused():
  signature = ed25519.sign(SEED, MESSAGE)
  for index in (0, 40): # one byte in the point, one in the scalar
    broken = bytearray(signature)
    broken[index] ^= 1
    assert not ed25519.verify(PUBLIC, MESSAGE, bytes(broken))

def other_key_is_refused():
  signature = ed25519.sign(SEED, MESSAGE)
  other = ed25519.public_key(bytes(32))
  assert not ed25519.verify(other, MESSAGE, signature)

def unreduced_scalar_is_refused():
  signature = ed25519.sign(SEED, MESSAGE)
  s = int.from_bytes(signature[32:], "little") + ed25519.L
  assert not ed25519.verify(PUBLIC, MESSAGE, signature[:32] + s.to_bytes(32, "little"))

def malformed_input_is_refused():
  signature = ed25519.sign(SEED, MESSAGE)
  assert not ed25519.verify(PUBLIC, MESSAGE, signature[:63])
  assert not ed25519.verify(b"\xff" * 32, MESSAGE, signature)

def seed_must_be_32_bytes():
  with pytest.raises(ValueError):
    ed25519.sign(bytes(31), MESSAGE)
