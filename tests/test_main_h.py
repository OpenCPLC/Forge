# tests/test_main_h.py

"""Contract: values written into generated files can be read back unchanged."""

from opencplc.utils import get_vars, lines_clear
from opencplc.headers import boot_included, main_h_with
from conftest import load_template, render, parse_main_h, parse_dispatcher

GUARDED = ("#ifndef MAIN_H_\r\n#define MAIN_H_\r\n\r\n#include <xdef.h>\r\n\r\n"
  "#define PRO_CHIP_STM32G081\r\n\r\n#endif\r\n")

UNO_SUBS = {
  "${NAME}": "myapp",
  "${DATE}": "2026-01-01",
  "${BOARD}": "Uno",
  "${PLC}": "true",
  "${DRIVERS}": "max31865",
  "${CHIP}": "STM32G0C1",
  "${PRO_FRAMEWORK}": "1.0.2",
  "${FLASH}": 492,
  "${RAM}": 144,
  "${OPT_LEVEL}": "Og",
  "${LOG_LEVEL}": "LOG_LEVEL_INF",
  "${FREQ}": 59904000,
}

def embedded_main_h_roundtrip():
  text = render(load_template("main.h"), UNO_SUBS)
  info = parse_main_h(text)
  assert info["PRO_BOARD"] == "Uno"
  assert info["PRO_CHIP"] == "STM32G0C1"
  assert info["PRO_PLC"] == "true"
  assert info["PRO_DRIVERS"] == "max31865"
  assert info["PRO_FRAMEWORK"] == "1.0.2"
  assert info["PRO_FLASH_kB"] == "492"
  assert info["PRO_RAM_kB"] == "144"
  assert boot_included(lines_clear(text.splitlines(), "//")) # dropped for one without --boot
  assert info["PRO_OPT_LEVEL"] == "Og"
  assert info["LOG_LEVEL"] == "LOG_LEVEL_INF"
  assert info["SYS_CLOCK_FREQ"] == "59904000"

def bare_metal_board_reads_as_none():
  subs = UNO_SUBS | {"${BOARD}": "None", "${PLC}": "false",
    "${CHIP}": "STM32G081", "${FREQ}": 16000000}
  info = parse_main_h(render(load_template("main.h"), subs))
  assert info["PRO_BOARD"] == "None"
  assert info["PRO_PLC"] == "false"
  assert info["PRO_CHIP"] == "STM32G081"

def host_main_h_roundtrip():
  subs = {
    "${NAME}": "myapp",
    "${DATE}": "2026-01-01",
    "${CHIP}": "HOST",
    "${PRO_FRAMEWORK}": "develop",
    "${OPT_LEVEL}": "O2",
    "${LOG_LEVEL}": "LOG_LEVEL_DBG",
  }
  info = parse_main_h(render(load_template("host/main.h"), subs))
  assert info["PRO_CHIP"] == "HOST"
  assert info["PRO_FRAMEWORK"] == "develop"
  assert info["PRO_OPT_LEVEL"] == "O2"
  assert info["LOG_LEVEL"] == "LOG_LEVEL_DBG"
  assert "PRO_BOARD" not in info
  assert "PRO_FLASH_kB" not in info

def settings_take_the_place_of_their_definitions():
  """A value changes where it stands, comments stay, and a new one follows the last `PRO_`."""
  main_h = ('#include <xdef.h>\n// #define PRO_OPT_LEVEL "O0"\n'
    '#define PRO_OPT_LEVEL "Og" // speed\n\n#endif\n')
  text = main_h_with(main_h, {"PRO_OPT_LEVEL": '"O2"', "PRO_DRIVERS": '"shtc3"'}, boot=False)
  assert text == ('#include <xdef.h>\n// #define PRO_OPT_LEVEL "O0"\n'
    '#define PRO_OPT_LEVEL "O2" // speed\n#define PRO_DRIVERS "shtc3"\n\n#endif\n')
  info = parse_main_h(text)
  assert (info["PRO_OPT_LEVEL"], info["PRO_DRIVERS"]) == ("O2", "shtc3")

def include_goes_behind_the_last_include_once():
  """A commented one includes nothing, so the real one goes in beside it; CRLF stays."""
  text = main_h_with(GUARDED, {}, boot=True)
  assert '#include <xdef.h>\r\n#include "boot.h"\r\n' in text
  assert main_h_with(text, {}, boot=True) == text
  commented = GUARDED.replace("<xdef.h>", '<xdef.h>\r\n// #include "boot.h"')
  assert main_h_with(commented, {}, boot=True).count('\r\n#include "boot.h"') == 1

def mixed_line_endings_stay_and_a_new_line_takes_the_common_one():
  """One CRLF line among LF ones: a value changes in place, and no other byte moves."""
  main_h = ('#ifndef MAIN_H_\r\n#define MAIN_H_\n#include <xdef.h>\n#include "boot.h"\n'
    '#define PRO_OPT_LEVEL "Og"\n#endif\n')
  text = main_h_with(main_h, {"PRO_OPT_LEVEL": '"O2"', "PRO_DRIVERS": '"shtc3"'}, boot=True)
  assert text == main_h.replace('"Og"\n', '"O2"\n#define PRO_DRIVERS "shtc3"\n')
  last = '#include <xdef.h>\n#define PRO_CHIP_STM32G081\n#endif\r\n'
  assert main_h_with(last, {"PRO_DRIVERS": '"shtc3"'}, boot=False) == (
    '#include <xdef.h>\n#define PRO_CHIP_STM32G081\n#define PRO_DRIVERS "shtc3"\n#endif\r\n')

def definitions_count_as_c_sees_them():
  """An indented one counts, one in a block comment does not, and writing agrees with reading."""
  main_h = ('#include <xdef.h>\n#if 1\n  #define PRO_OPT_LEVEL "Os" // size\n#endif\n'
    '/*\n#define PRO_PLC false\n*/\n')
  text = main_h_with(main_h, {"PRO_OPT_LEVEL": '"O1"', "PRO_PLC": "true"}, boot=False)
  assert text == ('#include <xdef.h>\n#if 1\n  #define PRO_OPT_LEVEL "O1" // size\n'
    '#define PRO_PLC true\n#endif\n/*\n#define PRO_PLC false\n*/\n')
  info = parse_main_h(text)
  assert (info["PRO_OPT_LEVEL"], info["PRO_PLC"]) == ("O1", "true")

def a_definition_continued_over_lines_stays_whole():
  """A new value takes all its lines, and a new definition goes behind the last of them."""
  main_h = '#include <xdef.h>\n#define PRO_DRIVERS \\\n  "shtc3"\n#endif\n'
  assert main_h_with(main_h, {"PRO_DRIVERS": '"shtc3, max31865"'}, boot=False) == (
    '#include <xdef.h>\n#define PRO_DRIVERS "shtc3, max31865"\n#endif\n')
  assert main_h_with(main_h, {"PRO_OPT_LEVEL": '"O2"'}, boot=False) == (
    '#include <xdef.h>\n#define PRO_DRIVERS \\\n  "shtc3"\n#define PRO_OPT_LEVEL "O2"\n#endif\n')

def project_makefile_roundtrip():
  subs = {
    "${NAME}": "myapp", "${TARGET}": "myapp", "${STLINK}": "SER01",
    "${WORKSPACE}": "$(abspath $(PROJECT)/../..)", "${CORE_DIR}": "opencplc/1.0.0",
    "${BUILD_DIR}": "build/projects/myapp",
    "${CORE_C}": "hal/arm/core.c", "${CORE_S}": "", "${PRO_C}": "main.c", "${PRO_S}": "",
    "${C_INCLUDES}": "-I$(PROJECT)", "${C_DEFS}": "-DSTM32", "${MCU_FLAGS}": "-mthumb",
    "${OPT_LEVEL}": "Og", "${OPENOCD_TARGET}": "stm32g0x",
    "${ERASE_CMD}": "stm32g0x mass_erase 0",
  }
  text = render(load_template("project.mk"), subs)
  info = get_vars(text.splitlines(), ["NAME", "TARGET", "STLINK"], ":=", required=False)
  assert info["NAME"] == "myapp"
  assert info["TARGET"] == "myapp"
  assert info["STLINK"] == "SER01"

def dispatcher_roundtrip():
  text = render(load_template("workspace.mk"), {"${ACTIVE}": "projects/myapp"})
  assert parse_dispatcher(text) == "projects/myapp"
  empty = render(load_template("workspace.mk"), {"${ACTIVE}": ""})
  assert parse_dispatcher(empty) == ""

def generated_c_follows_the_c_style():
  """Separators exactly 99 chars, lines within 95, no trailing whitespace."""
  for name in ("main.c", "main-none.c", "host/main.c", "main.h", "boot.h", "host/main.h"):
    for i, line in enumerate(load_template(name).replace("\r\n", "\n").split("\n"), 1):
      where = f"{name}:{i}"
      if line.startswith("//-"):
        assert len(line) == 99, where
      else:
        assert len(line) <= 95, where
      assert line == line.rstrip(), where

def bare_metal_led_comes_from_the_chip_table():
  from opencplc.platforms import CHIPS
  subs = {"${LED_PORT}": "GPIOB", "${LED_PIN}": 0, "${LED_NAME}": "green `LD2` of Nucleo-WB55RG"}
  out = render(load_template("main-none.c"), subs)
  assert ".port = GPIOB," in out and ".pin = 0," in out
  assert "// green `LD2` of Nucleo-WB55RG" in out
  for name, chip in CHIPS.items():
    assert set(chip.led) == {"port", "pin", "name"}, name
  assert CHIPS["STM32WB55"].led["port"] == "GPIOB" # LD2 is PB0, not PA5
  assert CHIPS["STM32G0C1"].led["port"] == "GPIOA"
