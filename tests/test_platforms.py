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
