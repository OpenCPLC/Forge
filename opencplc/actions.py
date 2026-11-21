# opencplc/actions.py

"""
One-shot CLI actions.

`info_actions()` runs the flags that need no project:
-v, -fv, -f, -hl, -u, -a, -z, -p, --test, --cipher, --upload, --record and --verify.
`info_show()` and `program_image()` act on the resolved model, for -i and --program.
"""

import sys
from datetime import datetime
from xaeian import Print, Color as c, Ico, FILE, DIR, PATH, replace_end, grey
from xaeian.cmd import run
from .config import URL_DL, URL_FORGE, URL_CORE, EXE_NAME, ASSETS
from .args import flag, given
from .model import Project
from .pack import pack_command
from .cipher import cipher_command
from .release import record, verify
from .upload import upload
from .runner import run_tests
from .utils.palette import MEMORY_COLORS
from .workspace import ensure_refs
from . import utils, __version__

p = Print()

FROZEN = getattr(sys, "frozen", False) # a PyInstaller build, not a Python package

def memory_usage(elf:str) -> tuple[int, int]:
  """FLASH and RAM bytes taken by an .elf: text+data and data+bss from arm-none-eabi-size."""
  out = run(["arm-none-eabi-size", elf]).stdout
  text, data, bss = (int(x) for x in out.strip().splitlines()[-1].split()[:3])
  return text + data, data + bss

def usage_line(name:str, used:int, total_kB:int) -> str:
  """`FLASH 70.7kB / 72kB (98%)`: usage in the color of its memory, percent in grey."""
  percent = used * 100 // (total_kB * 1024) if total_kB else 0
  usage = f"{MEMORY_COLORS[name]}{used / 1024:.1f}kB{c.END}"
  return f"{name} {usage} / {total_kB}kB {grey(f'({percent}%)')}"

def size_report(elf:str, flash_kB:int, ram_kB:int):
  """Two plain lines for the build log, no level prefix: Make speaks here, not Forge."""
  flash, ram = memory_usage(elf)
  p(usage_line("FLASH", flash, flash_kB))
  p(usage_line("RAM", ram, ram_kB))

def update_forge(args):
  """
  -u: swap the running executable for a release from GitHub.

  New file goes next to the running one, wherever that is, never into the workspace.
  Windows locks a running image, so the old one is renamed aside and dropped on the next run.
  Download happens first, so nothing moves without the bytes.
  """
  if not FROZEN:
    p.err("Forge runs here as a Python package, so it updates through pip")
    p.run(f"Update it with {utils.color_command('pip install -U opencplc')}")
    sys.exit(1)
  latest = args.update in ("last", "latest")
  utils.ensure_git(args.yes)
  versions = utils.git_get_refs(URL_FORGE, "--tags")
  if not versions:
    p.err(f"No access to {utils.color_link('GitHub')}, check the internet connection")
    sys.exit(1)
  target = utils.version_real(args.update, versions[0])
  if target == __version__:
    kind = "latest" if latest else "target"
    p.ok(f"Forge is at {kind} version {utils.color_version(__version__)}")
    return
  p.inf(f"Installed: {grey(__version__)}")
  p.inf(f"{'Latest' if latest else 'Target'}: {utils.color_version(target)}")
  if not args.yes and not utils.is_yes(f"{'Update' if latest else 'Replace'} Forge"): sys.exit(1)
  exe = PATH.resolve(f"{PATH.script_dir()}/{EXE_NAME}", read=False)
  old = f"{exe}.old"
  try:
    data = utils.download(f"{URL_FORGE}/releases/download/{target}/{EXE_NAME}")
    DIR.move(exe, old)
    FILE.save(exe, data)
  except Exception as e:
    if not FILE.exists(exe) and FILE.exists(old): DIR.move(old, exe)
    p.err(f"Update failed: {e}")
    sys.exit(1)
  p.ok(f"Forge updated to {utils.color_version(target)}")

def framework_fetch(args, forge_cfg:dict) -> bool:
  """
  -f VER alone: clone that Core version, no project involved.

  A way to read a version before `PRO_FRAMEWORK` points at it.
  Already cloned stays as it is.
  """
  # Beside any other flag `-f` overrides the Core of a project run, so it downloads only alone
  if not args.framework or given(args) - {"framework", "yes"}: return False
  ver = args.framework
  path = PATH.resolve(utils.core_dir(ver), read=False)
  if DIR.exists(path):
    p.ok(f"Framework {utils.color_version(ver)} already in {grey(PATH.local(path))}")
    return True
  utils.version_check(ver, ensure_refs(forge_cfg, args.yes),
    f"{Ico.RUN} Check version list: {flag.fv}")
  utils.ensure_git(args.yes)
  utils.git_clone_missing(URL_CORE, path, ver, args.yes)
  return True

def info_actions(args, forge_cfg:dict) -> bool:
  """Run each one-shot action the flags ask for; `True` when any of them ran."""
  if FROZEN:
    FILE.remove(f"{PATH.script_dir()}/{EXE_NAME}.old") # what an earlier -u replaced
  ran = False
  if args.size:
    if len(args.size) != 3:
      p.err(f"Flag {flag.z} takes ELF FLASH_kB RAM_kB")
      p.run(f"Reload the project with {utils.color_command('opencplc -r')}")
      sys.exit(1)
    elf, flash_kB, ram_kB = args.size
    size_report(elf, int(flash_kB), int(ram_kB))
    ran = True
  if args.pack:
    pack_command(args.pack)
    ran = True
  if args.cipher:
    cipher_command(args.cipher, args.yes)
    ran = True
  if args.record:
    record(args.record)
    ran = True
  if args.verify:
    verify(args.verify)
    ran = True
  if args.upload:
    upload(args.upload)
    ran = True
  if args.test:
    sys.exit(run_tests(args.test[0], args.test[1:]))
  if args.version:
    p.inf(f"OpenCPLC Forge {utils.color_version(__version__)}")
    p.gap(utils.color_link("https://github.com/OpenCPLC/Forge"))
    ran = True
  if args.framework_versions:
    available = ensure_refs(forge_cfg, args.yes)
    active = utils.version_active(args.framework, forge_cfg)
    parts = []
    for i, ver in enumerate(available):
      tags = [t for t, on in (("branch", not utils.version_is_release(ver)),
        ("latest", i == 0), ("active", ver == active)) if on]
      suffix = " " + grey(f"({', '.join(tags)})") if tags else ""
      shown = utils.color_version(ver) if ver == active else grey(ver)
      parts.append(f"{shown}{suffix}")
    p("Framework Versions: " + ", ".join(parts))
    ran = True
  if framework_fetch(args, forge_cfg):
    ran = True
  if args.hash_list:
    p(utils.c_code_enum(args.hash_list, args.hash_title, args.hash_define))
    ran = True
  if args.update:
    update_forge(args)
    ran = True
  if args.assets:
    DIR.ensure(args.assets)
    for f in ASSETS:
      dst = PATH.resolve(f"{args.assets}/{f}", read=False)
      if not FILE.exists(dst):
        utils.fetch(f"{URL_DL}/assets/{f}", dst)
    p.ok(f"Assets downloaded to {grey(args.assets)}")
    ran = True
  return ran

def dist_image(pro:Project, yes:bool) -> str:
  """
  --program alone: the .hex `make dist` left in the project.

  `dist` with a new `TAG` keeps the older images, so of several the newest goes, once confirmed.
  """
  images = DIR.file_list(pro.pro_dir, exts=[".hex"], deep=False)
  where = PATH.local(pro.pro_dir)
  if not images:
    p.err(f"No .hex image in {grey(where)}")
    p.run(f"Make one with {utils.color_command('make dist')}")
    sys.exit(1)
  images.sort(key=FILE.mtime, reverse=True)
  if len(images) > 1:
    p.inf(f"Images in {grey(where)}, newest first:")
    for image in images:
      stamp = datetime.fromtimestamp(FILE.mtime(image))
      p.dot(f"{PATH.basename(image)} {grey(f'({stamp:%Y-%m-%d %H:%M:%S})')}")
    newest = utils.color_image(PATH.basename(images[0]))
    if not yes and not utils.is_yes(f"Program the newest {newest}"): sys.exit(1)
  return images[0]

def program_image(pro:Project, path:str|bool, yes:bool):
  """--program: send a file to the board the way `make flash` does; alone, the one from dist."""
  if pro.platform != "STM32":
    p.err(f"Flag {flag.program} needs an STM32 project")
    sys.exit(1)
  if path is True: path = dist_image(pro, yes)
  if PATH.ext(path).lower() not in (".hex", ".elf"):
    p.err(f"Flag {flag.program} takes a .hex or .elf, a raw binary carries no address")
    sys.exit(1)
  if not FILE.exists(path):
    p.err(f"File {utils.color_image(path)} not found")
    sys.exit(1)
  cmd = utils.openocd_command(pro.openocd_target, pro.stlink)
  # Braces keep a path with spaces one word for `openocd`
  cmd += ["-c", f"program {{{PATH.normalize(path)}}} verify reset exit"]
  name = utils.color_image(PATH.basename(path))
  if run(cmd, capture=False).returncode:
    p.err(f"Programming {name} failed")
    p.run("Check ST-Link cable and board power; a locked board needs "
      f"{utils.color_command('opencplc --lock 0')} first")
    sys.exit(1)
  p.ok(f"Programmed {name} into {utils.color_chip(pro.chip)}")

def info_show(pro:Project):
  """-i: print the resolved project configuration and exit."""
  shown = utils.home_name(pro.name)
  p.inf(f"Project: {grey(replace_end(pro.pro_dir, shown, ''))}{utils.color_file(shown)}")
  p.gap(f"Platform: {utils.color_chip(pro.platform)}")
  p.gap(f"Board {flag.b}: {utils.color_board(pro.board_title or 'None')}")
  p.gap(f"PLC layer {flag.plc}: {utils.color_board('yes' if pro.plc else 'no')}")
  p.gap(f"Chip {flag.c}: {utils.color_chip(pro.chip)}")
  p.gap(f"Project version: {utils.color_version(pro.pro_ver)}")
  p.gap(f"Framework version: {utils.color_version(pro.core_ref)}")
  if pro.platform == "STM32":
    p.gap(f"FLASH{grey('/')}RAM {flag.m}: {utils.color_value(pro.flash_kB)}kB"
      f"{grey('/')}{utils.color_value(pro.ram_kB)}kB")
    slot = (f", image at {utils.color_value(f'0x{pro.flash_origin:08X}')}"
      f" in a {utils.color_value(pro.image_kB)}kB slot") if pro.boot else ""
    p.gap(f"Bootloader {flag.boot}: {utils.color_board('yes' if pro.boot else 'no')}{slot}")
    p.gap(f"System clock: {utils.color_value(pro.freq_Hz)}Hz")
  p.gap(f"Optimization level {flag.o}: {utils.color_choice(pro.opt_level)}")
  p.gap(f"Log level: {utils.color_symbol(pro.log_level.replace('LOG_LEVEL_', ''))}")
  if pro.board:
    p.gap(f"Board drivers: {utils.color_board(', '.join(pro.board_drivers) or 'none')}")
  p.gap(f"Project drivers {flag.drv}: "
    f"{utils.color_board(', '.join(pro.project_drivers) or 'none')}")
  if pro.stlink:
    p.gap(f"ST-Link: {utils.color_value(pro.stlink)}")
  p.gap(f"Last modification: {utils.last_modification(pro.pro_dir, exts=['.c', '.h'])}")
  sys.exit(0)
