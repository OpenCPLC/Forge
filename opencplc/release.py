# opencplc/release.py

"""
Release steps: `--keys` before its build, `--record` after it, `--verify` of a build against it.

`make dist` builds a release in a tree of its own, from nothing and dated by its commit,
so one commit gives the same image on every computer, and the record lands beside its files.
`make verify` builds the same way and compares its image with a record:
a release proves it came from its sources, and nobody needs a key for that.
The record holds what anyone may read: hashes, commits, versions, fingerprints of keys.
"""

import sys
from xaeian import Print, FILE, JSON, PATH, grey
from xaeian.cmd import output
from .args import flag
from .pack import encrypted_path
from .utils import keys
from .utils.tools import COMMANDS
from . import utils, __version__

p = Print()

def keys_check(args:list[str]):
  """
  `--keys [KEYS NUMBER] [CIPHER]`, the first step of `dist`: its keys lie on this computer.

  A key missing, or encryption without the key bootloader, stops the release
  before its build and before any password.
  """
  if len(args) > 3:
    p.err(f"Flag {flag.keys} takes [KEYS NUMBER] [CIPHER]")
    sys.exit(1)
  keys_hex, number = args[:2] if len(args) > 1 else ("", "0")
  cipher = args[-1] if len(args) in (1, 3) else ""
  if cipher and not keys_hex:
    p.err(f"Encryption needs key bootloader, {utils.color_boot('BOOT_KEYS')} in boot.h")
    p.tip(f"Add sign keys: {utils.color_command('opencplc --sign <name>')}")
    sys.exit(1)
  try:
    if keys_hex: keys.sign_needed(bytes.fromhex(keys.keys_split(keys_hex)[int(number)]))
    if cipher: keys.cipher_needed(cipher)
  except (OSError, ValueError, IndexError) as e:
    p.err(f"Keys check failed: {e}")
    sys.exit(1)

def commit_of(folder:str) -> dict:
  """
  Commit of the repository `folder` lies in: its hash, its time and its tracked changes.

  Files a release leaves in the project are untracked, so they never count as changes;
  outside a repository the hash is empty and the time zero.
  """
  head = output(["git", "-C", folder, "rev-parse", "HEAD"]) or ""
  if not head: return {"commit": "", "epoch": 0, "dirty": False}
  # The makefile reads the time the same way, so the record names the date the build took
  stamp = output(["git", "-C", folder, "rev-list", "-1", "--timestamp", "HEAD"]) or "0"
  changes = output(["git", "-C", folder, "status", "--porcelain", "--untracked-files=no"])
  return {"commit": head, "epoch": int(stamp.split()[0]), "dirty": bool(changes)}

def compiler() -> str:
  """First line of `--version` of the compiler the build ran, "" without one."""
  shown = output([COMMANDS["arm-gcc"], "--version"]) or ""
  return shown.splitlines()[0] if shown else ""

def record_data(app:str, out:str, core:str, keys_hex:str, number:int, cipher:str) -> dict:
  """Record of release `out`: its sources, its tools, its image, its files and its keys."""
  files = [f"{out}.hex", f"{out}.bin"] + ([encrypted_path(f"{out}.bin", cipher)] if cipher else [])
  data = {
    "release": PATH.basename(out),
    **commit_of(PATH.dirname(out)),
    "forge": __version__,
    "core": {"version": PATH.basename(core), "commit": commit_of(core)["commit"]},
    "compiler": compiler(),
    "image": {"sha256": FILE.hash(app), "size": FILE.size(app)},
    "files": {PATH.basename(path): FILE.hash(path) for path in files if FILE.exists(path)},
  }
  if keys_hex:
    public = keys.keys_split(keys_hex)[number]
    data["sign"] = {"key": number, "fingerprint": keys.fingerprint(public)}
  if cipher: data["cipher"] = {"name": cipher, "id": keys.cipher_record(cipher)["id"]}
  return data

def record(args:list[str]):
  """
  `--record APP.bin OUT CORE [KEYS NUMBER [CIPHER]]`, the last step of `dist`: `OUT.json`.

  `APP.bin` is the image of the build alone, without bootloader and trailer,
  `OUT` the release files without their extension, `CORE` the Core that built them.
  """
  if len(args) not in (3, 5, 6):
    p.err(f"Flag {flag.record} takes APP.bin OUT CORE [KEYS NUMBER [CIPHER]]")
    sys.exit(1)
  app, out, core, keys_hex, number, cipher = args + [""] * (6 - len(args))
  try:
    data = record_data(app, out, core, keys_hex, int(number or 0), cipher)
  except (OSError, ValueError, KeyError, TypeError, IndexError) as e:
    p.err(f"Record failed: {e}")
    sys.exit(1)
  JSON.save_smart(f"{out}.json", data)
  if data["dirty"]:
    p.wrn("Release from uncommitted changes: dated by last commit, and no commit rebuilds it")

def verify(args:list[str]):
  """
  `--verify APP.bin RECORD.json` after a build like that of `dist`: its image against the record.

  An image that differs gets what the release was made of, the first things to compare.
  """
  app, path = args
  shown = utils.color_config(PATH.basename(path))
  if not FILE.exists(path):
    p.err(f"No release record {shown}")
    p.tip(f"Name one: {utils.color_command('make verify RECORD=<file>')}")
    sys.exit(1)
  try:
    data = JSON.parse(FILE.load(path))
    want, release = data["image"]["sha256"], data["release"]
  except (ValueError, KeyError, TypeError) as e:
    p.err(f"Release record {shown} damaged: {e}")
    sys.exit(1)
  name = utils.color_file(release)
  if FILE.hash(app) == want:
    p.ok(f"Image of this build is the one of release {name}")
    return
  p.err(f"Image of this build differs from release {name}")
  changes = grey(" with changes") if data.get("dirty") else ""
  core = data.get("core", {})
  core = " ".join(part for part in (core.get("version", ""), core.get("commit", "")[:8]) if part)
  p.gap(f"Release from commit {data.get('commit', '')[:12] or grey('none')}{changes}, "
    f"Forge {data.get('forge', '')}, Core {core}")
  if data.get("compiler"): p.gap(f"Compiler {data['compiler']}")
  sys.exit(1)
