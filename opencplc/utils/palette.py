# opencplc/utils/palette.py

"""
Palette of messages: one meaning per color, grouped in families, picked here alone.

A message colors a name by what it is, `color_symbol("PRO_FRAMEWORK")`, never by a hue it likes,
so a new message reads like the old ones and no color stands for two kinds.
A setting takes the color of its layer: sky for the application, turquoise for the bootloader.
Violet marks the active version, at most one in a message, and the `#include` of a header;
the rest reads past in grey: other versions, locations, flags and hints.
A folder Forge keeps, or one a message is about, takes its color, the variable above it grey.
Images and memory keep the hues their reports have, and the C code of `-hl` is highlighted as code.
Forge names more kinds than the `fmt_*` of xaeian cover, chips, boards, keys and layers among them,
so its hues live here, on `Color` and `grey` of xaeian.
"""

from xaeian import Color as c, PATH, grey

# Yours: the project and what is set in it
FILE_COLOR = c.BLUE        # project, its name and its own sources: main.c, main.h, boot.h
SYMBOL_COLOR = c.SKY       # what the application sets: `PRO_FRAMEWORK`, config keys
INCLUDE_COLOR = c.VIOLET   # the include of a header: `#include "boot.h"`
KEY_COLOR = c.PURPLE       # names of sign and cipher keys: `acme`, `acme-1`
KEY_FILE_COLOR = c.SALMON  # files of keys: `.key`, `.pub`, `.cipher`
# Hardware: what runs below the application
CHIP_COLOR = c.PINK        # platform and chip
BOARD_COLOR = c.TURQUS     # board from Core, its drivers and the PLC layer
BOOT_COLOR = c.TURQUS      # what the bootloader takes from boot.h: `BOOT_KEYS`, `BOOT_HOLD`
# Build
CONFIG_COLOR = c.ORANGE    # what Forge generates or reads: makefile, flash.ld, opencplc.json, .ini
PROGRAM_COLOR = c.YELLOW   # tools: Git, Make, arm-none-eabi-gcc, the program of a command
VALUE_COLOR = c.GOLD       # numbers: list index, memory, frequency, address, port
CHOICE_COLOR = c.CYAN      # what you pick or type: optimization level, valid choices, a make goal
# Places: on disk and on the net
FOLDER_COLOR = c.TEAL      # folders of Forge: keys, tools, workspace, Core, one to remove
LINK_COLOR = c.TEAL        # repository URLs, GitHub, sample names
# Version and state
VERSION_COLOR = c.VIOLET   # the active version
WRONG_COLOR = c.MAGNTA     # invalid value, and a count of a run short of the whole
PASSED_COLOR = c.CREAM     # a count of a run that passed whole: tests, checks
GOOD_COLOR = c.GREEN       # yes
BAD_COLOR = c.RED          # no, failed, over a limit
# Images for a programmer, an update, the debugger and the computer, memory of a size report
IMAGE_COLORS = {".hex": c.LIME, ".bin": c.SKY, ".elf": c.VIOLET, ".exe": c.LIME}
MEMORY_COLORS = {"FLASH": c.VIOLET, "RAM": c.GREEN}

def color_file(name:object) -> str:
  """Project, or a source of its own."""
  return f"{FILE_COLOR}{name}{c.END}"

def color_symbol(name:object) -> str:
  """What the application or a config sets."""
  return f"{SYMBOL_COLOR}{name}{c.END}"

def color_include(line:object) -> str:
  """Include of a header, or the word `#include` alone."""
  return f"{INCLUDE_COLOR}{line}{c.END}"

def color_key(name:object) -> str:
  """Name of a sign or cipher key."""
  return f"{KEY_COLOR}{name}{c.END}"

def color_key_file(name:object) -> str:
  """File of a key, or its kind as `.key`."""
  return f"{KEY_FILE_COLOR}{name}{c.END}"

def color_chip(name:object) -> str:
  """Platform or chip."""
  return f"{CHIP_COLOR}{name}{c.END}"

def color_board(name:object) -> str:
  """Board, driver or the PLC layer."""
  return f"{BOARD_COLOR}{name}{c.END}"

def color_boot(name:object) -> str:
  """What the bootloader takes from boot.h."""
  return f"{BOOT_COLOR}{name}{c.END}"

def color_config(name:object) -> str:
  """File Forge generates or reads."""
  return f"{CONFIG_COLOR}{name}{c.END}"

def color_program(name:object) -> str:
  """Tool, or the program of a command."""
  return f"{PROGRAM_COLOR}{name}{c.END}"

def color_value(value:object) -> str:
  """Number, with its unit when it has one."""
  return f"{VALUE_COLOR}{value}{c.END}"

def color_choice(text:object) -> str:
  """What you pick or type."""
  return f"{CHOICE_COLOR}{text}{c.END}"

def color_folder(path:object) -> str:
  """Folder of Forge, or one a message is about."""
  return f"{FOLDER_COLOR}{path}{c.END}"

def color_link(link:str) -> str:
  """Site or address; the scheme of an address reads past in grey."""
  rest = link.removeprefix("https://")
  scheme = grey("https://") if rest != link else ""
  return f"{scheme}{LINK_COLOR}{rest}{c.END}"

def color_version(version:object) -> str:
  """The active version, one in a message."""
  return f"{VERSION_COLOR}{version}{c.END}"

def color_wrong(text:object) -> str:
  """Invalid value."""
  return f"{WRONG_COLOR}{text}{c.END}"

def color_passed(count:object) -> str:
  """Count of a run that passed whole."""
  return f"{PASSED_COLOR}{count}{c.END}"

def color_good(text:object) -> str:
  """Yes."""
  return f"{GOOD_COLOR}{text}{c.END}"

def color_bad(text:object) -> str:
  """No, a failure, or a value over its limit."""
  return f"{BAD_COLOR}{text}{c.END}"

def color_command(cmd:str) -> str:
  """
  Command the way a console colors it: the program, flags grey, arguments plain.

  `fmt_cmd` of xaeian gives the program gold, here it takes the color of tools.
  """
  program, *args = cmd.split(" ")
  shown = [grey(arg) if arg.startswith("-") else arg for arg in args]
  return " ".join([color_program(program), *shown])

def color_image(path:str) -> str:
  """Image file, or its kind as `.bin`, in the color of its kind."""
  return f"{IMAGE_COLORS[(PATH.ext(path) or path).lower()]}{path}{c.END}"
