# opencplc/actions.py

"""
One-shot CLI actions.

`info_actions()` handles -v, -F, -f, -hl, -u, -a, -z and -p, each answers without a project.
`info_show()` and `program_image()` act on the resolved model, for -i and --program.
"""

import sys
from datetime import datetime
from xaeian import Print, Color as c, Ico, FILE, DIR, PATH, replace_end
from xaeian.cmd import run
from .config import URL_DL, URL_FORGE, URL_CORE, EXE_NAME, DIR_FRAMEWORK
from .args import flag
from .resolver import Project
from .pack import pack_command
from .workspace import ensure_refs
from . import utils, __version__

p = Print()

FROZEN = getattr(sys, "frozen", False) # a PyInstaller build, not a Python package

def memory_usage(elf:str) -> tuple[int, int]:
  """FLASH and RAM bytes taken by an .elf: text+data and data+bss from arm-none-eabi-size."""
  out = run(["arm-none-eabi-size", elf]).stdout
  text, data, bss = (int(x) for x in out.strip().splitlines()[-1].split()[:3])
  return text + data, data + bss

def usage_line(name:str, used:int, total_kB:int, color:str) -> str:
  """`FLASH 70.7kB / 72kB (98%)`: usage in color, percent in grey."""
  percent = used * 100 // (total_kB * 1024) if total_kB else 0
  return f"{name} {color}{used / 1024:.1f}kB{c.END} / {total_kB}kB {c.GREY}({percent}%){c.END}"

def size_report(elf:str, flash_kB:int, ram_kB:int):
  """Two plain lines for the build log, no level prefix: Make speaks here, not Forge."""
  flash, ram = memory_usage(elf)
  p(usage_line("FLASH", flash, flash_kB, c.VIOLET))
  p(usage_line("RAM", ram, ram_kB, c.GREEN))

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
    p.err(f"No access to {c.TEAL}GitHub{c.END}, check the internet connection")
    sys.exit(1)
  target = utils.version_real(args.update, versions[0])
  if target == __version__:
    kind = "latest" if latest else "target"
    p.ok(f"Forge is at {kind} version {c.VIOLET}{__version__}{c.END}")
    return
  p.inf(f"Installed: {c.GREY}{__version__}{c.END}")
  p.inf(f"{'Latest' if latest else 'Target'}: {c.VIOLET}{target}{c.END}")
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
  p.ok(f"Forge updated to {c.VIOLET}{target}{c.END}")

# Flags of a project run, where -f is an override, not a download
PROJECT_FLAGS = ("name", "new", "demo", "reload", "delete", "get", "board", "chip", "plc",
  "dvr", "boot", "memory", "opt_level", "project_list", "info", "version", "framework_versions",
  "size", "pack", "program", "lock", "keygen", "hash_list", "update", "assets")

def framework_fetch(args, forge_cfg:dict) -> bool:
  """
  -f VER alone: clone that Core version, no project involved.

  A way to read a version before `PRO_FRAMEWORK` points at it.
  Already cloned stays as it is.
  """
  if not args.framework or args.stlink is not None: return False
  if any(getattr(args, name) for name in PROJECT_FLAGS): return False
  ver = args.framework
  path = PATH.resolve(f"{DIR_FRAMEWORK}/{ver}", read=False)
  if DIR.exists(path):
    p.ok(f"Framework {c.VIOLET}{ver}{c.END} already in {c.GREY}{PATH.local(path)}{c.END}")
    return True
  utils.version_check(ver, ensure_refs(forge_cfg, args.yes),
    f"{Ico.RUN} Check version list: {flag.F}")
  utils.ensure_git(args.yes)
  utils.git_clone_missing(URL_CORE, path, ver, args.yes)
  return True

def info_actions(args, forge_cfg:dict) -> bool:
  """Run each one-shot action the flags ask for; `True` when any of them ran."""
  if FROZEN:
    FILE.remove(f"{PATH.script_dir()}/{EXE_NAME}.old") # what an earlier -u replaced
  ran = False
  if args.size:
    size_report(args.size[0], int(args.size[1]), int(args.size[2]))
    ran = True
  if args.pack:
    pack_command(args.pack)
    ran = True
  if args.version:
    p.inf(f"OpenCPLC Forge {c.VIOLET}{__version__}{c.END}")
    p.gap(utils.color_url("https://github.com/OpenCPLC/Forge"))
    ran = True
  if args.framework_versions:
    available = ensure_refs(forge_cfg, args.yes)
    active = utils.version_active(args.framework, forge_cfg)
    parts = []
    for i, ver in enumerate(available):
      tags = [t for t, on in (("branch", not utils.version_is_release(ver)),
        ("latest", i == 0), ("active", ver == active)) if on]
      suffix = f" {c.GREY}({', '.join(tags)}){c.END}" if tags else ""
      color = c.VIOLET if ver == active else c.CYAN
      parts.append(f"{color}{ver}{c.END}{suffix}")
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
    files = [
      "reference-manual-stm32g0x1.pdf", "datasheet-stm32g081rb.pdf",
      "datasheet-stm32g0c1re.pdf", "pinout-nucleo.pdf", "pinout-opencplc.pdf",
    ]
    for f in files:
      dst = PATH.resolve(f"{args.assets}/{f}", read=False)
      if not FILE.exists(dst):
        utils.fetch(f"{URL_DL}/assets/{f}", dst)
    p.ok(f"Assets downloaded to {c.GREY}{args.assets}{c.END}")
    ran = True
  return ran

def dist_image(pro:Project, yes:bool) -> str:
  """
  --program alone: the .hex `make dist` left, in the project, or in Core for the bootloader.

  `dist` with a new `TAG` keeps the older images, so of several the newest goes, once confirmed.
  """
  if pro.bootloader:
    image = PATH.resolve(f"{pro.core_dir}/{pro.bootloader}.hex", read=False)
    where = PATH.dirname(image)
    images = [image] if FILE.exists(image) else []
  else:
    where = pro.pro_dir
    images = DIR.file_list(where, exts=[".hex"], deep=False)
  if not images:
    p.err(f"No .hex image in {c.GREY}{PATH.local(where)}{c.END}")
    p.run(f"Make one with {utils.color_command('make dist')}")
    sys.exit(1)
  images.sort(key=FILE.mtime, reverse=True)
  if len(images) > 1:
    p.inf(f"Images in {c.GREY}{PATH.local(where)}{c.END}, newest first:")
    for image in images:
      stamp = datetime.fromtimestamp(FILE.mtime(image))
      p.dot(f"{PATH.basename(image)} {c.GREY}({stamp:%Y-%m-%d %H:%M:%S}){c.END}")
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
  # braces keep a path with spaces one word for openocd
  cmd += ["-c", f"program {{{PATH.normalize(path)}}} verify reset exit"]
  name = utils.color_image(PATH.basename(path))
  if run(cmd, capture=False).returncode:
    p.err(f"Programming {name} failed")
    p.run("Check ST-Link cable and board power; a locked board needs "
      f"{utils.color_command('opencplc --lock 0')} first")
    sys.exit(1)
  p.ok(f"Programmed {name} into {c.PINK}{pro.chip}{c.END}")

def info_show(pro:Project):
  """-i: print the resolved project configuration and exit."""
  path_prefix = replace_end(pro.pro_dir, pro.name, "")
  p.inf(f"Project: {c.GREY}{path_prefix}{c.END}{c.BLUE}{pro.name}{c.END}")
  p.gap(f"Platform: {c.PINK}{pro.platform}{c.END}")
  p.gap(f"Board {flag.b}: {c.TURQUS}{pro.board_title or 'None'}{c.END}")
  p.gap(f"PLC layer {flag.P}: {c.TURQUS}{'yes' if pro.plc else 'no'}{c.END}")
  p.gap(f"Chip {flag.c}: {c.PINK}{pro.chip}{c.END}")
  p.gap(f"Project version: {c.VIOLET}{pro.pro_ver}{c.END}")
  p.gap(f"Framework version: {c.VIOLET}{pro.core_ref}{c.END}")
  if pro.platform == "STM32":
    p.gap(f"FLASH{c.GREY}/{c.END}RAM {flag.m}: {c.GOLD}{pro.flash_kB}{c.END}kB"
      f"{c.GREY}/{c.END}{c.GOLD}{pro.ram_kB}{c.END}kB")
    slot = (f", image at {c.GOLD}0x{pro.flash_origin:08X}{c.END}"
      f" in a {c.GOLD}{pro.image_kB}{c.END}kB slot") if pro.boot else ""
    p.gap(f"Bootloader {flag.B}: {c.TURQUS}{'yes' if pro.boot else 'no'}{c.END}{slot}")
    p.gap(f"System clock: {c.GOLD}{pro.freq_Hz}{c.END}Hz")
  p.gap(f"Optimization level {flag.o}: {c.CYAN}{pro.opt_level}{c.END}")
  p.gap(f"Log level: {c.SKY}{pro.log_level.replace('LOG_LEVEL_', '')}{c.END}")
  if pro.board:
    p.gap(f"Board drivers: {c.TURQUS}{', '.join(pro.board_drivers) or 'none'}{c.END}")
  p.gap(f"Project drivers {flag.D}: {c.BLUE}{', '.join(pro.project_drivers) or 'none'}{c.END}")
  if pro.stlink:
    p.gap(f"ST-Link: {c.GOLD}{pro.stlink}{c.END}")
  p.gap(f"Last modification: {utils.last_modification(pro.pro_dir, exts=['.c', '.h'])}")
  sys.exit(0)
