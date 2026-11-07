# tests/test_args.py

"""Command line: each flag declared once, the parser and `Args` agreeing on every field."""

import re
from xaeian import DIR, FILE, PATH
import opencplc
from opencplc.args import PARSER, Args, given, flag

def parser_and_args_agree_on_every_field_and_default():
  assert Args(**vars(PARSER.parse_args([]))) == Args()

def given_names_what_the_command_line_set():
  args = Args(**vars(PARSER.parse_args(["-f", "1.0.0", "-y"])))
  assert given(args) == {"framework", "yes"}
  assert given(Args(**vars(PARSER.parse_args(["app", "-s"])))) == {"name", "stlink"}

def flags_read_as_their_options():
  assert "-n --new" in flag.n and "--lock" in flag.lock and "-p --pack" in flag.p

def every_flag_the_package_names_exists():
  """`flag` fills up at import, so a misspelled `flag.x` would fail only on its own path."""
  for path in DIR.iter_files(PATH.dirname(opencplc.__file__), exts=[".py"]):
    for name in re.findall(r"\bflag\.(\w+)", FILE.load(path)):
      assert hasattr(flag, name), f"{PATH.basename(path)} names flag.{name}"
