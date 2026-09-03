# tests/test_platforms.py

"""Chip table: parsing, defines and HAL directories."""

import pytest
from opencplc.platforms import CHIPS, parse_chip, get_hal_dirs

def parse_chip_is_case_insensitive():
  assert parse_chip("stm32g0c1")["chip"] == "STM32G0C1"

def parse_chip_builds_defines():
  cfg = parse_chip("STM32G081")
  assert cfg["defines"] == ["STM32", "STM32G0", "STM32G081xx"]
  host = parse_chip("HOST")
  assert host["defines"][0] == "HOST"
  assert host["platform"] == "Host"

def parse_chip_unknown_exits():
  with pytest.raises(SystemExit):
    parse_chip("STM32F103")

def every_chip_has_erase_and_hal():
  for name, cfg in CHIPS.items():
    assert "erase" in cfg, name
    assert get_hal_dirs(cfg["hal"]), name

def wb55_flash_stops_below_the_wireless_stack():
  """CPU1 must not be offered flash that belongs to CPU2."""
  stack_start = 0xD0 * 4 # SFSA 0xD0, pages of 4kB
  assert 0x08000000 + stack_start * 1024 == 0x080D0000
  assert CHIPS["STM32WB55"]["flash_kB"] == stack_start
