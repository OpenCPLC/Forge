# tests/test_main_h.py

"""Contract: values written into generated files can be read back unchanged."""

from opencplc.utils import get_vars
from conftest import load_template, render, parse_main_h, parse_dispatcher

UNO_SUBS = {
  "${NAME}": "myapp",
  "${DATE}": "2026-01-01",
  "${BOARD}": "UNO",
  "${CHIP}": "STM32G0C1",
  "${PRO_VERSION}": "1.0.2",
  "${FLASH}": 492,
  "${RAM}": 144,
  "${OPT_LEVEL}": "Og",
  "${LOG_LEVEL}": "LOG_LEVEL_INF",
  "${FREQ}": 59904000,
}

def embedded_main_h_roundtrip():
  info = parse_main_h(render(load_template("main.h"), UNO_SUBS))
  assert info["PRO_BOARD"] == "UNO"
  assert info["PRO_CHIP"] == "STM32G0C1"
  assert info["PRO_VERSION"] == "1.0.2"
  assert info["PRO_FLASH_kB"] == "492"
  assert info["PRO_RAM_kB"] == "144"
  assert info["PRO_OPT_LEVEL"] == "Og"
  assert info["LOG_LEVEL"] == "LOG_LEVEL_INF"
  assert info["SYS_CLOCK_FREQ"] == "59904000"

def bare_metal_board_reads_as_none():
  subs = UNO_SUBS | {"${BOARD}": "NONE", "${CHIP}": "STM32G081", "${FREQ}": 16000000}
  info = parse_main_h(render(load_template("main.h"), subs))
  assert info["PRO_BOARD"] == "NONE"
  assert info["PRO_CHIP"] == "STM32G081"

def host_main_h_roundtrip():
  subs = {
    "${NAME}": "myapp",
    "${DATE}": "2026-01-01",
    "${CHIP}": "HOST",
    "${PRO_VERSION}": "develop",
    "${OPT_LEVEL}": "O2",
    "${LOG_LEVEL}": "LOG_LEVEL_DBG",
  }
  info = parse_main_h(render(load_template("host/main.h"), subs))
  assert info["PRO_CHIP"] == "HOST"
  assert info["PRO_VERSION"] == "develop"
  assert info["PRO_OPT_LEVEL"] == "O2"
  assert info["LOG_LEVEL"] == "LOG_LEVEL_DBG"
  assert "PRO_BOARD" not in info
  assert "PRO_FLASH_kB" not in info

def project_makefile_roundtrip():
  subs = {
    "${NAME}": "myapp", "${TARGET}": "myapp", "${STLINK}": "SER01",
    "${UP_PATH}": "../..", "${CORE_DIR}": "opencplc/1.0.0",
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
  for name in ("main.c", "main-none.c", "host/main.c", "main.h", "host/main.h"):
    for i, line in enumerate(load_template(name).replace("\r\n", "\n").split("\n"), 1):
      where = f"{name}:{i}"
      if line.startswith("//-"):
        assert len(line) == 99, where
      else:
        assert len(line) <= 95, where
      assert line == line.rstrip(), where

def bare_metal_led_comes_from_the_chip_table():
  from opencplc.platforms import CHIPS
  subs = {"${LED_PORT}": "GPIOB", "${LED_PIN}": 0, "${LED_NAME}": "Nucleo-WB55RG green `LD2`"}
  out = render(load_template("main-none.c"), subs)
  assert ".port = GPIOB," in out and ".pin = 0," in out
  assert "// Nucleo-WB55RG green `LD2`" in out
  for name, cfg in CHIPS.items():
    assert "led" in cfg, name
  assert CHIPS["STM32WB55"]["led"]["port"] == "GPIOB" # LD2 is PB0, not PA5
  assert CHIPS["STM32G0C1"]["led"]["port"] == "GPIOA"
