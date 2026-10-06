# opencplc/lock.py

"""
`--lock [0|1|2]`: production option bytes of a board, over SWD.

Level 1 boots main flash whatever BOOT0 pin says and sets RDP1:
debugger and programmer lose flash, the ROM bootloader never starts.
Under a bootloader it write-protects the pages of the bootloader as well.
Level 2 is level 1 for good: RDP2 freezes option bytes with WRP and shuts SWD forever.
Level 0 takes level 1 back, and the chip erases its whole flash on the way.
A WB takes level 0 through STM32CubeProgrammer, the one `make stack` needs anyway.

Lock stands apart from the bootloader: it asks no key and reads no image,
WRP covers a bootloader only where the project has one.
What the board holds is the business of `--program`, run with `--lock` in one call.
Mailbox page stays out of WRP, the application writes its record there.
"""

import re, sys
from xaeian import Print, Color as c
from xaeian.cmd import run
from .args import flag
from .resolver import Project
from . import utils

p = Print()

OPTR, WRP1AR = 0x20, 0x2C          # offsets in flash registers, alike on G0 and WB
RDP = {0: 0xAA, 1: 0xBB, 2: 0xCC}  # any value but 0xAA and 0xCC is level 1
# `OPTR` bits booting main flash whatever BOOT0 pin says: value, mask
BOOT_BITS = {
  "G0": (0x05000000, 0x05000000),     # nBOOT_SEL and nBOOT0 set
  "WB": (0x08000000, 0x0C000000),     # nBOOT0 set, nSWBOOT0 clear
}
WRP_FIELD = {"G0": 0x7F, "WB": 0xFF}  # page offset bits in `WRP1AR`, start and end alike

FLASH_SR = {"G0": 0x40022010, "WB": 0x58004010}  # status register of each family
SR_ERRORS = 0x0000C3FB                           # every error flag, `OPTVERR` too
SR_BUSY = 0x00050000                             # `BSY` and `CFGBSY`
OPTION_WAIT_s = 30                               # an unlock erases whole flash first
SUPPLY_MIN_V = 1.6                               # below the lowest supply of G0 and WB

def define(pro:Project, name:str) -> str:
  """Value of the `name=value` define the project builds with."""
  return next(d for d in pro.defines if d.startswith(f"{name}=")).split("=", 1)[1]

def option_write(reg:int, value:int, mask:int) -> str:
  """openocd command writing `value` under `mask` into option register `reg`."""
  return f"stm32l4x option_write 0 0x{reg:02X} 0x{value:08X} 0x{mask:08X}"

def option_writes(pro:Project, level:int) -> list[str]:
  """openocd commands writing option bytes of `level`; WRP covers a bootloader, if any."""
  family = pro.family.removeprefix("STM32")
  field = WRP_FIELD[family]
  wrp_mask = field << 16 | field
  if level == 0: # start past end: no area
    return [option_write(WRP1AR, field, wrp_mask), option_write(OPTR, RDP[0], 0xFF)]
  boot_value, boot_mask = BOOT_BITS[family]
  writes = [option_write(OPTR, boot_value | RDP[level], boot_mask | 0xFF)]
  if not pro.boot: return writes
  last = int(define(pro, "BOOT_PAGES")) - 2 # last page of the region is the mailbox
  return [option_write(WRP1AR, last << 16, wrp_mask), *writes]

def option_session(pro:Project, writes:list[str]) -> list[str]:
  """
  openocd commands programming `writes`, then loading them through a reset.

  A flag left in `FLASH_SR` refuses option programming, so all of them clear first.
  An unlock erases whole flash and outlasts the wait of the driver, which then gives up:
  its error is caught, and the session waits for the flash itself before loading.
  """
  sr = FLASH_SR[pro.family.removeprefix("STM32")]
  busy = f"[read_memory 0x{sr:08X} 32 1] & 0x{SR_BUSY:08X}"
  wait = f"set n 0; while {{({busy}) && $n < {OPTION_WAIT_s * 10}}} {{sleep 100; incr n}}"
  return ["init", "reset halt", f"mww 0x{sr:08X} 0x{SR_ERRORS:08X}",
    *(f"catch {{{write}}}" for write in writes), wait, "stm32l4x option_load 0", "shutdown"]

def openocd(pro:Project, *commands:str) -> tuple[int, str]:
  """One openocd session over the probe of the project; exit code and all it printed."""
  cmd = utils.openocd_command(pro.openocd_target, pro.stlink)
  for command in filter(None, commands): cmd += ["-c", command]
  result = run(cmd, capture=True)
  return result.returncode, (result.stdout or "") + (result.stderr or "")

def cube_unlock(pro:Project) -> str:
  """
  RDP regression of a WB through CubeProgrammer; all it printed.

  Under RDP1 with a debugger on,
  a WB hangs its flash interface on an option write beside the regression,
  and the regression erases whole flash past the openocd wait.
  CubeProgrammer connects under reset and waits it out; WRP goes with the erase.
  """
  cli = utils.cube_cli()
  if not cli:
    p.err(f"Unlock of {c.PINK}{pro.chip}{c.END} needs STM32CubeProgrammer")
    p.run(f"Install it from {utils.color_url(utils.CUBE_URL)}")
    sys.exit(1)
  connect = ["-c", "port=SWD", "mode=UR"] + ([f"sn={pro.stlink}"] if pro.stlink else [])
  # its progress bar comes in the console code page, `latin-1` takes any byte
  result = run([cli, *connect, "-ob", "RDP=0xAA", "WRP1A_STRT=0xFF", "WRP1A_END=0x0"],
    capture=True, encoding="latin-1")
  return (result.stdout or "") + (result.stderr or "")

def session_errors(out:str) -> list[str]:
  """`Error` lines of an openocd session, all a refused option write leaves behind."""
  return [line.strip() for line in out.splitlines() if line.lstrip().startswith("Error")]

def probe_chip(pro:Project) -> int|None:
  """`DEV_ID` of the chip on the probe, `None` when SWD sees none; a locked chip shows it too."""
  _, out = openocd(pro, "init", "reset halt", "flash probe 0", "reset run", "shutdown")
  idcode = re.search(r"device idcode = 0x([0-9a-fA-F]+)", out)
  return int(idcode.group(1), 16) & 0xFFF if idcode else None # `DEV_ID` is its low 12 bits

def check_chip(pro:Project, chip:int|None):
  """Option bytes of one family set boot of another wrong, so another chip exits."""
  want = int(define(pro, "BOOT_CHIP"), 16)
  if chip == want: return
  seen = f"chip {c.GOLD}0x{chip:03X}{c.END}" if chip is not None else "no chip"
  p.err(f"ST-Link sees {seen}, "
    f"project {c.PINK}{pro.chip}{c.END} needs {c.GOLD}0x{want:03X}{c.END}")
  p.run("Check the board on the ST-Link; with several, bind the right one by "
    f"{utils.color_command('opencplc <name> -s <serial>')}")
  sys.exit(1)

def options_read(pro:Project) -> tuple[int, int]|None:
  """`OPTR` and `WRP1AR` read back from the chip, `None` when the session fails or SWD is shut."""
  code, out = openocd(pro, "init", "reset halt",
    f"stm32l4x option_read 0 0x{OPTR:02X}", f"stm32l4x option_read 0 0x{WRP1AR:02X}", "shutdown")
  # openocd 0.12.0 of Linux distributions prints `Option Register: <address> = value`,
  # builds since 2025 the value alone
  values = re.findall(r"^(?:Option Register: <0x\w+> = )?(0x[0-9a-fA-F]+)\s*$", out, re.M)
  if code or len(values) < 2: return None
  return int(values[-2], 16), int(values[-1], 16)

def swd_shut(pro:Project) -> bool:
  """
  Probe up beside a powered chip that no longer answers: all of SWD that RDP2 leaves.

  The probe reads the supply over its own pin, so an unplugged probe or a dead board never pass.
  """
  code, out = openocd(pro, "init", "shutdown")
  volts = re.search(r"Target voltage: ([\d.]+)", out)
  return bool(code) and bool(volts) and float(volts.group(1)) > SUPPLY_MIN_V

def confirm(pro:Project, level:int, yes:bool):
  """Say what `level` does and ask; level 2 asks once more even under `-y`."""
  chip = f"{c.PINK}{pro.chip}{c.END}"
  if level == 0:
    p.wrn("Unlock erases whole flash")
    question = f"Unlock {chip}"
  else:
    protected = "bootloader write-protected, " if pro.boot else ""
    p.wrn(f"Lock: {protected}BOOT0 off, RDP{level}, flash closed to debugger and programmer")
    if pro.stack_script:
      p.wrn(f"{utils.color_command('make stack')} stops working, "
        "SWD no longer reaches radio stack")
    question = f"Lock {chip} at RDP{level}"
  if not yes and not utils.is_yes(question): sys.exit(1)
  if level == 2:
    p.err("RDP2 is for good: no debugger ever, option bytes and WRP frozen, "
      "no failure analysis at ST")
    if not utils.is_yes(f"Lock {chip} for good, never to be undone"): sys.exit(1)

def lock_board(pro:Project, level:int, yes:bool):
  """`--lock`: option bytes of `level` written, then read back."""
  if pro.platform != "STM32":
    p.err(f"Flag {flag.lock} needs an STM32 project")
    sys.exit(1)
  check_chip(pro, probe_chip(pro))
  confirm(pro, level, yes)
  if level == 0 and pro.family == "STM32WB":
    out = cube_unlock(pro)
  else:
    _, out = openocd(pro, *option_session(pro, option_writes(pro, level)))
  read = options_read(pro)
  if level == 2 and read is None and swd_shut(pro): # RDP2 shuts SWD at once
    p.ok(f"{c.PINK}{pro.chip}{c.END} at RDP2: powered, silent on SWD for good")
    # the silence of SWD alone could have another cause, the chip itself names its level
    p.run("Unplug and plug board power, "
      f"then {utils.color_command('boot info')} shows {c.GOLD}rdp:2{c.END}")
    return
  if read is None or (read[0] & 0xFF) != RDP[level]:
    got = f"OPTR 0x{read[0]:08X}, WRP1AR 0x{read[1]:08X}" if read else "nothing readable"
    p.err(f"Option bytes did not take RDP{level}, chip holds {got}")
    for line in session_errors(out): p.gap(f"{c.GREY}{line}{c.END}")
    sys.exit(1)
  p.ok(f"{c.PINK}{pro.chip}{c.END} at RDP{level}, OPTR 0x{read[0]:08X}, WRP1AR 0x{read[1]:08X}")
  if level == 0:
    # option reload saw flash empty, and G0 boots its ROM until next power-on
    p.run(f"Program board with {utils.color_command('make flash')}, "
      "then unplug and plug its power")
    return
  # a debugger seen since power-on keeps flash shut until next power-on
  p.run("Unplug and plug board power, a chip locked under the debugger starts nothing until then")
