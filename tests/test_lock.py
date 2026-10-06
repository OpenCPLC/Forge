# tests/test_lock.py

"""`--lock`: option bytes of each level, chip checked first, two asks for RDP2, apart from keys."""

import pytest
from xaeian import file_context
from opencplc import lock
from opencplc.resolver import resolve_project
from opencplc.platforms import parse_chip
from conftest import build_workspace, uno_cfg, ws_paths, KEY, ship_key_bootloader, resolve_key_uno
from conftest import resolve_uno

@pytest.fixture()
def ws(tmp_path):
  """Synthetic workspace as file root, its Core shipping `key` bootloaders for G0 and WB."""
  build_workspace(tmp_path)
  ship_key_bootloader(tmp_path)
  ship_key_bootloader(tmp_path, "stm32wb")
  with file_context(root_path=str(tmp_path)):
    yield tmp_path

def level_1_on_g0_protects_pages_0_to_14_and_boots_the_flash(ws):
  wrp, optr = lock.option_writes(resolve_key_uno(), 1)
  assert wrp == "stm32l4x option_write 0 0x2C 0x000E0000 0x007F007F"   # mailbox page 15 left out
  assert optr == "stm32l4x option_write 0 0x20 0x050000BB 0x050000FF"  # nBOOT_SEL, nBOOT0, RDP1

def plain_bootloader_protects_its_own_smaller_region(ws):
  pro = resolve_project(uno_cfg() | {"boot": True}, ws_paths(), {})
  wrp, _ = lock.option_writes(pro, 1)
  assert wrp == "stm32l4x option_write 0 0x2C 0x00020000 0x007F007F" # pages 0 to 2, mailbox 3

def project_without_bootloader_locks_without_wrp(ws):
  """Nothing of Forge sits in front of the image, so no page of it gets write-protected."""
  optr = "stm32l4x option_write 0 0x20 0x050000BB 0x050000FF"
  assert lock.option_writes(resolve_uno(), 1) == [optr]

def level_2_on_wb_takes_rdp_0xcc_and_nswboot0_clear(ws):
  cfg = uno_cfg() | parse_chip("STM32WB55") | {"boot": True, "flash_kB": 818, "boot_key": KEY}
  wrp, optr = lock.option_writes(resolve_project(cfg, ws_paths(), {}), 2)
  assert wrp == "stm32l4x option_write 0 0x2C 0x00060000 0x00FF00FF"
  assert optr == "stm32l4x option_write 0 0x20 0x080000CC 0x0C0000FF"

def level_0_drops_the_area_and_takes_rdp_back_with_or_without_bootloader(ws):
  for pro in (resolve_key_uno(), resolve_uno()):
    wrp, optr = lock.option_writes(pro, 0)
    assert wrp == "stm32l4x option_write 0 0x2C 0x0000007F 0x007F007F" # start past end
    assert optr == "stm32l4x option_write 0 0x20 0x000000AA 0x000000FF"

def probe_reads_the_chip_alone_and_lets_the_board_run_on(ws, monkeypatch):
  """Lock reads no image and no key: what the board holds is the business of `--program`."""
  seen = []
  out = "Info : device idcode = 0x10006467 (STM32G0B/G0Cx)\n"
  monkeypatch.setattr(lock, "openocd", lambda pro, *cmds: seen.append(cmds) or (0, out))
  assert lock.probe_chip(resolve_key_uno()) == 0x467
  assert "read_memory" not in " ".join(seen[0]) and seen[0][-2:] == ("reset run", "shutdown")

def another_chip_on_the_probe_is_refused(ws):
  """Bits of BOOT0 of WB written on G0 would boot it from the ROM bootloader."""
  for chip in (0x495, None):
    with pytest.raises(SystemExit):
      lock.check_chip(resolve_key_uno(), chip)
  lock.check_chip(resolve_key_uno(), 0x467)

def rdp2_asks_a_second_time_even_under_yes(ws, monkeypatch):
  asked = []
  monkeypatch.setattr(lock.utils, "is_yes", lambda msg: asked.append(msg) or False)
  with pytest.raises(SystemExit):
    lock.confirm(resolve_key_uno(), 2, yes=True)
  assert len(asked) == 1 and "for good, never to be undone" in asked[0] # first one skipped

def readback_takes_the_format_of_openocd_0_12_0_too(ws, monkeypatch):
  """Linux distributions ship 0.12.0, which names the register before its value."""
  old = "Option Register: <0x40022020> = 0x50000bb\nOption Register: <0x4002202c> = 0xe0000\n"
  monkeypatch.setattr(lock, "openocd", lambda pro, *cmds: (0, old))
  assert lock.options_read(resolve_key_uno()) == (0x050000BB, 0x000E0000)

def lock_writes_then_reads_back(ws, monkeypatch):
  sessions = []
  def openocd(pro, *cmds):
    sessions.append(cmds)
    return 0, "0x050000BB\n0x000E0000\n" if "stm32l4x option_read 0 0x20" in cmds else ""
  monkeypatch.setattr(lock, "openocd", openocd)
  monkeypatch.setattr(lock, "probe_chip", lambda pro: 0x467)
  lock.lock_board(resolve_key_uno(), 1, yes=True)
  assert "stm32l4x option_load 0" in sessions[0] and len(sessions) == 2

def plain_project_locks_with_no_key(ws, monkeypatch):
  sessions = []
  def openocd(pro, *cmds):
    sessions.append(cmds)
    return 0, "0x050000BB\n0x00020000\n" if "stm32l4x option_read 0 0x20" in cmds else ""
  monkeypatch.setattr(lock, "openocd", openocd)
  monkeypatch.setattr(lock, "probe_chip", lambda pro: 0x467)
  lock.lock_board(resolve_project(uno_cfg() | {"boot": True}, ws_paths(), {}), 1, yes=True)
  assert "catch {stm32l4x option_write 0 0x2C 0x00020000 0x007F007F}" in sessions[0]

def session_clears_flags_catches_writes_and_waits_for_the_flash(ws):
  """An unlock outlasts the wait of the openocd driver: its error is caught, the session waits."""
  cmds = lock.option_session(resolve_key_uno(), ["write a", "write b"])
  assert cmds[:3] == ["init", "reset halt", "mww 0x40022010 0x0000C3FB"] # every error flag
  assert cmds[3:5] == ["catch {write a}", "catch {write b}"]
  assert "read_memory 0x40022010 32 1" in cmds[5] and "$n < 300" in cmds[5]
  assert cmds[6:] == ["stm32l4x option_load 0", "shutdown"]

def refused_write_shows_what_openocd_said(ws, monkeypatch, capsys):
  """The readback decides, and the session errors say why it failed."""
  def openocd(pro, *cmds):
    if "stm32l4x option_read 0 0x20" in cmds: return 0, "0x050000BB\n0x000E0000\n"
    return 0, "Info : ok\nError: timed out waiting for flash\n"
  monkeypatch.setattr(lock, "openocd", openocd)
  monkeypatch.setattr(lock, "probe_chip", lambda pro: 0x467)
  with pytest.raises(SystemExit):
    lock.lock_board(resolve_key_uno(), 0, yes=True)
  assert "timed out waiting for flash" in capsys.readouterr().out

def wb_unlock_goes_through_cubeprogrammer_with_rdp_alone(ws, monkeypatch):
  """A WB under RDP1 hangs on an openocd option write beside the regression."""
  calls = []
  def run(cmd, **kw):
    calls.append(cmd)
    return type("R", (), {"stdout": "", "stderr": ""})()
  monkeypatch.setattr(lock.utils, "cube_cli", lambda: "cube")
  monkeypatch.setattr(lock, "run", run)
  monkeypatch.setattr(lock, "openocd", lambda pro, *cmds: (0, "0x39FFF1AA\n0x000000FF\n"))
  monkeypatch.setattr(lock, "probe_chip", lambda pro: 0x495)
  cfg = uno_cfg() | parse_chip("STM32WB55") | {"boot": True, "flash_kB": 818, "boot_key": KEY}
  lock.lock_board(resolve_project(cfg, ws_paths(), {}), 0, yes=True)
  assert calls == [["cube", "-c", "port=SWD", "mode=UR",
    "-ob", "RDP=0xAA", "WRP1A_STRT=0xFF", "WRP1A_END=0x0"]]

def rdp2_takes_a_powered_chip_gone_silent_for_proof(ws, monkeypatch, capsys):
  """The probe reads the supply over its own pin, SWD shut or not."""
  silent = ("Info : STLINK V2J39M27 (API v2) VID:PID 0483:374B\n"
    "Info : Target voltage: 3.244473\n"
    "Error: init mode failed (unable to connect to the target)\n")
  def openocd(pro, *cmds):
    return (0, "") if "stm32l4x option_load 0" in cmds else (1, silent)
  monkeypatch.setattr(lock, "openocd", openocd)
  monkeypatch.setattr(lock, "probe_chip", lambda pro: 0x467)
  monkeypatch.setattr(lock.utils, "is_yes", lambda msg: True)
  lock.lock_board(resolve_key_uno(), 2, yes=True)
  assert "at RDP2" in capsys.readouterr().out

def rdp2_never_takes_an_unplugged_probe_for_proof(ws, monkeypatch):
  def openocd(pro, *cmds):
    return (0, "") if "stm32l4x option_load 0" in cmds else (1, "Error: open failed\n")
  monkeypatch.setattr(lock, "openocd", openocd)
  monkeypatch.setattr(lock, "probe_chip", lambda pro: 0x467)
  monkeypatch.setattr(lock.utils, "is_yes", lambda msg: True)
  with pytest.raises(SystemExit):
    lock.lock_board(resolve_key_uno(), 2, yes=True)

def wb_unlock_without_cubeprogrammer_exits(ws, monkeypatch):
  monkeypatch.setattr(lock.utils, "cube_cli", lambda: "")
  monkeypatch.setattr(lock, "probe_chip", lambda pro: 0x495)
  cfg = uno_cfg() | parse_chip("STM32WB55") | {"boot": True, "flash_kB": 818, "boot_key": KEY}
  with pytest.raises(SystemExit):
    lock.lock_board(resolve_project(cfg, ws_paths(), {}), 0, yes=True)
