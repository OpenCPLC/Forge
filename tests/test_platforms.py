# tests/test_platforms.py

"""Chip table: parsing, defines and HAL directories."""

import pytest
from opencplc.platforms import CHIPS, HAL_DIRS, parse_chip, get_hal_dirs
from opencplc.templates import load_templates

def parse_chip_is_case_insensitive():
  assert parse_chip("stm32g0c1").name == "STM32G0C1"

def parse_chip_builds_defines():
  assert parse_chip("STM32G081").defines == ["STM32", "STM32G0", "STM32G081xx"]
  assert parse_chip("STM32G474").defines == ["STM32", "STM32G4", "STM32G474xx"]
  host = parse_chip("HOST")
  assert host.defines[0] == "HOST"
  assert host.platform == "Host"

def parse_chip_unknown_exits():
  with pytest.raises(SystemExit):
    parse_chip("STM32F103")

def every_stm32_chip_has_erase_and_hal():
  for name, chip in CHIPS.items():
    assert chip.name == name and get_hal_dirs(chip.hal), name
    assert chip.erase or chip.platform != "STM32", name

def every_stm32_chip_reserves_whole_bootloader_pages():
  """Whole pages for the bootloader: code pages plus the mailbox page; the host has none."""
  for name, chip in CHIPS.items():
    if chip.platform != "STM32":
      assert chip.boot_kB == 0, name
      continue
    assert chip.page_kB > 0 and chip.boot_kB % chip.page_kB == 0, name
    assert chip.boot_kB >= 2 * chip.page_kB, name

def every_stm32_chip_builds_from_its_row():
  """A row names a linker template and HAL that exist, an FPU its core has, memory in bounds."""
  flash = load_templates()["flash"]
  for name, chip in CHIPS.items():
    if chip.platform != "STM32": continue
    assert chip.ld in flash and chip.hal in HAL_DIRS, name
    assert (chip.fpu == "") == (chip.cpu == "cortex-m0plus"), name
    assert chip.boot_key_kB % chip.page_kB == 0, name
    assert 0 < chip.flash_kB <= chip.flash_max_kB and chip.ram_kB > 0 and chip.dev_id, name

def wb55_flash_stops_below_the_wireless_stack():
  """CPU1 must not be offered flash that belongs to CPU2."""
  stack_start_kB = 0xD0 * 4 # SFSA 0xD0, pages of 4kB
  assert 0x08000000 + stack_start_kB * 1024 == 0x080D0000
  assert CHIPS["STM32WB55"].flash_kB == stack_start_kB

def wb55_erase_clears_cpu1_flash_alone():
  """`mass_erase` fails beside the wireless stack, so pages go one by one up to CPU2 flash."""
  wb = CHIPS["STM32WB55"]
  assert wb.erase == f"flash erase_address 0x08000000 0x{wb.flash_kB * 1024:X}"
