# tests/test_upload.py

"""`--upload`, the step of `make update`: the file checked first, then the port and the board."""

import pytest
from opencplc import upload as upload_mod
from opencplc.upload import console_port, upload
from opencplc.project import ANSI

class Port:
  """Serial port of a board that kept nothing while it was closed."""
  def read(self, size:int) -> bytes: return b""

class Board:
  """Shell of a board, in place of the `Shell` class: takes the image or not, answers each ping."""
  def __init__(self, takes:bool=True, answers:tuple[bool, ...]=(True, True)):
    self.takes, self.answers, self.calls = takes, list(answers), []
    self.serial, self.buffer_size = Port(), 8192
  def __call__(self, port:str, **kwargs):
    self.calls.append(("open", port))
    return self
  def __enter__(self): return self
  def __exit__(self, *exc): pass
  def boot(self, path:str, progress) -> bool:
    self.calls.append(("boot", path))
    return self.takes
  def read_lines(self) -> list[str]: return ["started"] # the first line of the new image
  def ping(self, retries:int) -> bool:
    self.calls.append(("ping", retries))
    return self.answers.pop(0)
  def exec(self, command:str):
    self.calls.append(("exec", command))
  def print_info(self, text:str): print(text)
  def print_error(self, text:str): print(text)

@pytest.fixture()
def image(tmp_path):
  """Update image of a build, where `make update` takes it."""
  path = tmp_path / "app-dist.bin"
  path.write_bytes(bytes(16))
  return str(path)

def console_port_is_the_named_one_or_the_only_one(monkeypatch):
  monkeypatch.setattr(upload_mod, "serial_scan", lambda: ["COM7"])
  assert console_port("COM3") == "COM3" and console_port(None) == "COM7"
  for ports in ([], ["COM7", "COM8"]):
    monkeypatch.setattr(upload_mod, "serial_scan", lambda: ports)
    with pytest.raises(SystemExit):
      console_port(None)

def a_file_that_is_no_image_stops_before_any_port(tmp_path, monkeypatch, image):
  monkeypatch.setattr(upload_mod, "serial_scan", lambda: pytest.fail("port looked for"))
  (tmp_path / "app.elf").write_bytes(b"")
  for args in ([str(tmp_path / "app.elf")], [str(tmp_path / "none.bin")], [image, "COM3", "x"]):
    with pytest.raises(SystemExit):
      upload(args)

def staged_image_waits_for_the_board_then_asks_boot_info(monkeypatch, image):
  board = Board()
  monkeypatch.setattr(upload_mod, "Shell", board)
  upload([image, "COM3"])
  ping = ("ping", upload_mod.INSTALL_PINGS)
  assert board.calls == [("open", "COM3"), ping, ("boot", image), ping, ("exec", "boot info")]

def board_silent_before_the_transfer_gets_no_image(monkeypatch, capsys, image):
  """A locked chip waiting for a power cycle answers nothing: no slot or setting is to blame."""
  board = Board(answers=(False,))
  monkeypatch.setattr(upload_mod, "Shell", board)
  with pytest.raises(SystemExit):
    upload([image, "COM3"])
  assert ("boot", image) not in board.calls
  assert "power cycle" in ANSI.sub("", capsys.readouterr().out)

def refused_image_names_the_setting_the_console_needs(monkeypatch, capsys, image):
  monkeypatch.setattr(upload_mod, "Shell", Board(takes=False))
  with pytest.raises(SystemExit):
    upload([image, "COM3"])
  assert "#define CMD_BOOT ON" in ANSI.sub("", capsys.readouterr().out)

def board_silent_after_the_reset_exits(monkeypatch, image):
  board = Board(answers=(True, False))
  monkeypatch.setattr(upload_mod, "Shell", board)
  with pytest.raises(SystemExit):
    upload([image, "COM3"])
  assert ("exec", "boot info") not in board.calls
