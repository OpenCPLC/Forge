# tests/test_hash.py

"""DJB2 hashing and generated C output."""

from opencplc.utils.hash import hash_string, c_code_enum

def djb2_known_values():
  assert hash_string("") == 5381
  assert hash_string("a") == 177670

def hash_is_case_sensitive_input_lowered_by_caller():
  assert hash_string("ABC") != hash_string("abc")

def enum_output_contains_names_and_values():
  out = c_code_enum(["alpha", "beta"], "Cmd")
  assert "typedef enum" in out
  assert "CMD_Hash_Alpha" in out
  assert str(hash_string("alpha")) in out
  assert "CMD_Hash_t" in out

def define_output_uses_defines():
  out = c_code_enum(["alpha"], "Cmd", define=True)
  assert "#define" in out
  assert "CMD_HASH_ALPHA" in out
  assert "typedef enum" not in out
