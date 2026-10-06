# opencplc/keygen.py

"""
`--keygen <name>`: product key of a project, made or taken, written into its main.h.

Key lands right under `PRO_BOOT` as `PRO_BOOT_KEY`, with `PRO_BOOT_EPOCH 0` below it,
and `PRO_BOOT` turns true: `key` without a bootloader means nothing.
A project with a key keeps it, a new one would cut off devices in the field.
"""

import os, re, sys, getpass
from xaeian import Print, Color as c, FILE
from .utils import keys

p = Print()

NAME = re.compile(r"[A-Za-z0-9_-]+")
DEV_NAME = keys.DEV_KEY.removesuffix(".key") # `dev`, the development key file
PASSWORD_MIN = 8

def new_password(name:str) -> str:
  """Password of a new key: `OPENCPLC_KEY_PASSWORD`, or typed twice."""
  if os.environ.get(keys.PASSWORD_ENV): return os.environ[keys.PASSWORD_ENV]
  password = getpass.getpass(f"Password of new key {name}: ")
  if len(password) < PASSWORD_MIN:
    p.err(f"Password shorter than {PASSWORD_MIN} characters")
    sys.exit(1)
  if getpass.getpass("Repeat password: ") != password:
    p.err("Passwords differ")
    sys.exit(1)
  return password

def with_key(main_h:str, public:bytes) -> str:
  """main.h with the key under `PRO_BOOT`; a project that has one exits."""
  nl = "\r\n" if "\r\n" in main_h else "\n"
  lines = main_h.split(nl)
  if any(re.match(r"\s*#define\s+PRO_BOOT_KEY\b", line) for line in lines):
    p.err(f"Project has {c.SKY}PRO_BOOT_KEY{c.END} already, "
      "new key would cut off devices in the field")
    sys.exit(1)
  # commented key of earlier tries gives way
  commented = re.compile(r"\s*//\s*#define\s+PRO_BOOT_(KEY|EPOCH)\b")
  lines = [line for line in lines if not commented.match(line)]
  boot = re.compile(r"\s*#define\s+PRO_BOOT\s")
  at = next((i for i, line in enumerate(lines) if boot.match(line)), None)
  if at is None:
    p.err(f"File {c.BLUE}main.h{c.END} has no {c.SKY}PRO_BOOT{c.END} definition, "
      "the key goes right below it")
    p.run(f"Add {c.SKY}#define PRO_BOOT true{c.END} to it and run again")
    sys.exit(1)
  lines[at:at + 1] = ["#define PRO_BOOT true",
    f'#define PRO_BOOT_KEY "{public.hex()}"', "#define PRO_BOOT_EPOCH 0"]
  return nl.join(lines)

def keygen(name:str, main_h_path:str):
  """Product key `name` made, or taken when this machine has it, and written into main.h."""
  # Windows file names ignore case, so `DEV` would land on the development key
  if not NAME.fullmatch(name) or name.lower() == DEV_NAME:
    p.err(f"Key name {c.MAGNTA}{name}{c.END} takes letters, digits, `-` and `_`, "
      f"`{DEV_NAME}` is reserved")
    sys.exit(1)
  text = FILE.load(main_h_path, binary=True).decode("utf-8")
  public = keys.product_public(name)
  if public is None:
    with_key(text, bytes(32)) # its refusals come before any password: a key already, no `PRO_BOOT`
    if FILE.exists(f"{keys.keys_dir()}/{name}.key"):
      p.err(f"Key {c.GOLD}{name}{c.END} lost {c.BLUE}{name}.pub{c.END} "
        f"beside {c.BLUE}{name}.key{c.END} in {c.CREAM}{keys.keys_dir()}{c.END}")
      p.run(f"Recreate {c.BLUE}{name}.pub{c.END} with one line: the {c.SKY}PRO_BOOT_KEY{c.END} "
        "hex of a project signed with this key")
      sys.exit(1)
    public = keys.product_make(name, new_password(name))
    p.ok(f"Key {c.GOLD}{name}{c.END} made in {c.CREAM}{keys.keys_dir()}{c.END}")
    p.wrn(f"Keep two offline copies of {c.BLUE}{name}.key{c.END} and its password: "
      "losing either ends updates of every device")
  else:
    p.inf(f"Key {c.GOLD}{name}{c.END} taken from {c.CREAM}{keys.keys_dir()}{c.END}")
  FILE.save(main_h_path, with_key(text, public).encode("utf-8"))
  p.ok(f"{c.SKY}PRO_BOOT_KEY{c.END} {c.GOLD}{keys.fingerprint(public)}{c.GREY}...{c.END} "
    f"written into {c.BLUE}main.h{c.END}")
