# opencplc/actions.py

"""
One-shot CLI actions.

`info_actions()` handles -v, -F, -hl, -u and -a: things that answer and exit
without touching any project. `info_show()` prints the resolved model for -i.
"""

import sys, subprocess
from xaeian import Print, Color as c, FILE, DIR, PATH, replace_end
from .config import URL_FTP, URL_FORGE
from .args import flag
from .resolver import Project
from .workspace import ensure_refs
from . import utils, __version__

p = Print()

def memory_usage(elf:str) -> tuple[int, int]:
  """FLASH and RAM bytes taken by an .elf: text+data and data+bss from arm-none-eabi-size."""
  out = subprocess.run(["arm-none-eabi-size", elf], capture_output=True, text=True).stdout
  text, data, bss = (int(x) for x in out.strip().splitlines()[-1].split()[:3])
  return text + data, data + bss

def usage_line(name:str, used:int, total_kB:int, color:str) -> str:
  """`FLASH 70.7kB / 72kB (98%)`: usage in color, percent in grey."""
  percent = used * 100 // (total_kB * 1024) if total_kB else 0
  return f"{name} {color}{used / 1024:.1f}kB{c.END} / {total_kB}kB {c.GREY}({percent}%){c.END}"

def size_report(elf:str, flash_kB:int, ram_kB:int):
  """Two plain lines for the build log, no level prefix: Make speaks here, not Forge."""
  flash, ram = memory_usage(elf)
  print(usage_line("FLASH", flash, flash_kB, c.VIOLET))
  print(usage_line("RAM", ram, ram_kB, c.GREEN))

def info_actions(args, forge_cfg:dict) -> bool:
  """One-shot actions: -v, -F, -hl, -u, -a, -z. True when any of them ran."""
  ran = False
  if args.size:
    size_report(args.size[0], int(args.size[1]), int(args.size[2]))
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
    print("Framework Versions: " + ", ".join(parts))
    ran = True
  if args.hash_list:
    print(utils.c_code_enum(args.hash_list, args.hash_title, args.hash_define))
    ran = True
  if args.update:
    new_ver = args.update in ("last", "latest")
    utils.install_git(args.yes)
    versions = utils.git_get_refs(URL_FORGE, "--tags")
    if not versions:
      p.err(f"No access to {c.TEAL}GitHub{c.END}")
      sys.exit(1)
    target = utils.version_real(args.update, versions[0])
    if target != __version__:
      p.inf(f"Installed: {c.GREY}{__version__}{c.END}")
      p.inf(f"{'Latest' if new_ver else 'Target'}: {c.VIOLET}{target}{c.END}")
      p.run(f"{'Update' if new_ver else 'Replace'} required")
      utils.install("opencplc.exe", f"{URL_FORGE}/releases/download/{target}", ".",
        args.yes, False)
    else:
      kind = "latest" if new_ver else "target"
      p.ok(f"Forge is at {kind} version {c.VIOLET}{__version__}{c.END}")
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
        utils.download(f"{URL_FTP}/{f}", dst)
    p.ok(f"Assets downloaded to {c.ORANGE}{args.assets}{c.END}")
    ran = True
  return ran

def info_show(pro:Project):
  """-i: print the resolved project configuration and exit."""
  path_prefix = replace_end(pro.pro_dir, pro.name, "")
  p.inf(f"Project: {c.GREY}{path_prefix}{c.END}{c.BLUE}{pro.name}{c.END}")
  p.gap(f"Platform: {c.PINK}{pro.platform}{c.END}")
  p.gap(f"Board {flag.b}: {c.TURQUS}{str(pro.board or 'None').capitalize()}{c.END}")
  p.gap(f"Chip {flag.c}: {c.PINK}{pro.chip}{c.END}")
  p.gap(f"Project version: {c.VIOLET}{pro.pro_ver}{c.END}")
  p.gap(f"Framework version: {c.VIOLET}{pro.core_ref}{c.END}")
  if pro.platform == "STM32":
    p.gap(f"FLASH{c.GREY}/{c.END}RAM {flag.m}: {c.GOLD}{pro.flash_kB}{c.END}kB"
      f"{c.GREY}/{c.END}{c.GOLD}{pro.ram_kB}{c.END}kB")
    p.gap(f"System frequency clock: {c.GOLD}{pro.freq_Hz}{c.END}Hz")
  p.gap(f"Optimization level {flag.o}: {c.CYAN}{pro.opt_level}{c.END}")
  p.gap(f"Log level: {c.SKY}{pro.log_level.replace('LOG_LEVEL_', '')}{c.END}")
  if pro.board:
    p.gap(f"Board drivers: {c.TURQUS}{', '.join(pro.board_drivers) or 'none'}{c.END}")
    p.gap(f"Project drivers: {c.BLUE}{', '.join(pro.project_drivers) or 'none'}{c.END}")
  if pro.stlink:
    p.gap(f"ST-Link: {c.GOLD}{pro.stlink}{c.END}")
  p.gap(f"Last modification: {utils.last_modification(pro.pro_dir, ext=['.c','.h'])}")
  sys.exit(0)
