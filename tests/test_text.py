# tests/test_text.py

"""Line parsing used to read makefile and main.h: comments, continuations, variables."""

from opencplc.utils.text import (
  line_remove, lines_clear,
  get_vars, find_missing_keys, last_line_len,
)

def lines_clear_strips_comments_and_blanks():
  lines = ["NAME = app # active", "# full comment", "", "LIB = opencplc/1.0.0"]
  assert lines_clear(lines, "#") == ["NAME = app", "LIB = opencplc/1.0.0"]

def lines_clear_joins_continuations_gluing_fragments():
  # each fragment is rstripped before the join, so the space at the joint is lost;
  # production reads only single-line vars (NAME/LIB/PRO) through this path
  lines = ["C_SOURCES = a.c \\", "b.c"]
  assert lines_clear(lines, "#") == ["C_SOURCES = a.cb.c"]

def lines_clear_c_comments():
  lines = ["#define LOG_LEVEL LOG_LEVEL_INF // default", "// note"]
  assert lines_clear(lines, "//") == ["#define LOG_LEVEL LOG_LEVEL_INF"]

def get_vars_makefile_form():
  lines = ["NAME = myapp", "LIB = opencplc/1.0.0", "PRO = projects/myapp"]
  assert get_vars(lines, ["NAME", "LIB", "PRO"]) == {
    "NAME": "myapp", "LIB": "opencplc/1.0.0", "PRO": "projects/myapp",
  }

def get_vars_define_space_form_strips_quotes():
  lines = ['PRO_VERSION "1.0.2"', "PRO_FLASH_kB 492"]
  got = get_vars(lines, ["PRO_VERSION", "PRO_FLASH_kB"], " ", required=False)
  assert got == {"PRO_VERSION": "1.0.2", "PRO_FLASH_kB": "492"}

def get_vars_define_underscore_form():
  lines = ["#define PRO_BOARD_UNO", "#define PRO_CHIP_STM32G0C1"]
  got = get_vars(lines, ["PRO_BOARD", "PRO_CHIP"], "_", "#define", required=False)
  assert got == {"PRO_BOARD": "UNO", "PRO_CHIP": "STM32G0C1"}

def get_vars_required_missing_returns_empty():
  assert get_vars(["NAME = x"], ["NAME", "MISSING"]) == {}

def get_vars_optional_missing_returns_partial():
  got = get_vars(["NAME = x"], ["NAME", "MISSING"], required=False)
  assert got == {"NAME": "x"}

def line_remove_respects_limit():
  text = "keep\ndrop me\ndrop me\nkeep"
  assert line_remove(text, "drop", limit=1) == "keep\ndrop me\nkeep"

def find_missing_keys_nested():
  template = {"a": 1, "sub": {"x": 1, "y": 2}}
  assert find_missing_keys(template, {"a": 1, "sub": {"x": 1}}) == ["sub.y"]
  assert find_missing_keys(template, {"a": 1, "sub": {"x": 1, "y": 0}}) == []

def last_line_len_measures_final_line():
  assert last_line_len("abc") == 3
  assert last_line_len("abcdef\nxy ") == 2
