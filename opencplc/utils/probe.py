# opencplc/utils/probe.py

"""
Programmers that reach the chip over SWD: openocd on every ST-Link, CubeProgrammer beside it.

openocd flashes, erases and writes option bytes.
CubeProgrammer installs the radio stack of a WB and takes its RDP back,
where openocd falls short.
"""

import os, platform
from xaeian import FILE, PATH
from xaeian.cmd import which

#------------------------------------------------------------------------------------------ openocd

def openocd_command(target:str, serial:str="") -> list[str]:
  """
  openocd up to the command it runs: ST-Link, the pinned probe, the chip held in reset.

  `--program` runs it directly, the generated makefile spells it out for `flash` and `erase`.
  """
  cmd = ["openocd", "-f", "interface/stlink.cfg"]
  if serial: cmd += ["-c", f"adapter serial {serial}"]
  return cmd + ["-f", f"target/{target}.cfg",
    "-c", "reset_config srst_only srst_nogate connect_assert_srst"]

#----------------------------------------------------------------------------------- CubeProgrammer

# `make stack` alone needs it: FUS and the radio stack of CPU2 are beyond openocd.
# ST hands it out after a login, so Forge never ships it, only finds it.
CUBE_CLI = "STM32_Programmer_CLI"
CUBE_BIN = "STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin" # under Program Files
CUBE_URL = "https://www.st.com/en/development-tools/stm32cubeprog.html"

def cube_bin() -> str:
  """
  CubeProgrammer's `bin` in its default Windows home, "" when it is not there.

  The path goes into the makefile as text, so it has to hold for every make that reads it.
  A 32-bit make reads `%ProgramFiles%` as `Program Files (x86)`.
  Started from Git Bash, make knows it only as `PROGRAMFILES`.
  `ProgramW6432` names the 64-bit folder to any process, under one name in every language.
  """
  if platform.system() != "Windows": return ""
  home = os.environ.get("ProgramW6432") or os.environ.get("ProgramFiles", "C:/Program Files")
  path = f"{home}/{CUBE_BIN}"
  return PATH.normalize(path) if FILE.exists(f"{path}/{CUBE_CLI}.exe") else ""

def cube_cli() -> str:
  """CubeProgrammer CLI to run: its default home first, then PATH; "" when neither has it."""
  if cube_bin(): return f"{cube_bin()}/{CUBE_CLI}"
  return which(CUBE_CLI) or ""

def cube_found() -> bool:
  """CubeProgrammer reachable by `make stack`: in its default home or on PATH."""
  return bool(cube_cli())
