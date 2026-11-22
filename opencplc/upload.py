# opencplc/upload.py

"""
`--upload FILE [PORT]`, the step of `make update`: an update image sent over the console.

The board takes it with the `boot` shell command, `CMD_BOOT ON` in main.h,
as a device in the field takes an update over its own link, and resets to install it.
Once it answers again, `boot info` shows what the bootloader made of the image.
Without `PORT` the one console of the computer goes; with several, `PORT=` names one.
A board that answers no ping gets no image, so a silent one is never taken for a refusal.
An encrypted `.bin` is refused, as only the application of a device holds its key.
"""

import sys, time
from xaeian import Print, FILE, PATH
from xaeian.serial import Shell, serial_scan
from .args import flag
from .cipher import encrypted
from . import utils

p = Print()

INSTALL_TIMEOUT_s = 15  # a `key` install checks the signature three times, seconds on G0
INSTALL_PINGS = 3       # an image that prints nothing at start is pinged past the timeout

def console_port(port:str|None) -> str:
  """`port`, or the one console of the computer; none or several exits."""
  if port: return port
  ports = serial_scan()
  if len(ports) == 1: return ports[0]
  if not ports:
    p.err("No console port on this computer")
    p.tip(f"Plug the board in and run again: {utils.color_command('make update')}")
  else:
    listed = ", ".join(utils.color_value(name) for name in ports)
    p.err(f"Several console ports: {listed}")
    p.tip(f"Name one: {utils.color_command(f'make update PORT={ports[0]}')}")
  sys.exit(1)

def upload(args:list[str]):
  """`--upload FILE [PORT]`; exits with `1` on a refusal or a silent board."""
  if len(args) > 2:
    p.err(f"Flag {flag.upload} takes FILE and optional PORT")
    sys.exit(1)
  path = args[0]
  if PATH.ext(path).lower() not in (".bin", ".hex"):
    p.err(f"Flag {flag.upload} takes the .bin or .hex of an image")
    sys.exit(1)
  name = utils.color_image(PATH.basename(path))
  if not FILE.exists(path):
    p.err(f"Image {name} not found")
    p.tip(f"Build it: {utils.color_command('make')}")
    sys.exit(1)
  if PATH.ext(path).lower() == ".bin" and encrypted(FILE.load(path, binary=True)):
    p.err(f"Image {name} encrypted or damaged, its bytes miss CRC of its trailer")
    p.tip("Send it through your application, which holds its key")
    sys.exit(1)
  port = console_port(args[1] if len(args) > 1 else None)
  # The console of a project runs without echo, so the first line of a reply is the reply
  with Shell(port, time_disp=False, strip_echo=False) as sh:
    if not sh.serial: sys.exit(1) # the port said why it did not open
    sh.serial.read(sh.buffer_size) # what ST-Link kept while the port was closed
    if not sh.ping(retries=INSTALL_PINGS):
      sh.print_error(f"Board on {utils.color_value(port)} silent, no image sent")
      p.tip("Power it off and on: a locked chip starts only after a power cycle")
      sys.exit(1)
    def progress(taken:int, size:int):
      p.inf(f"Upload {taken}B / {size}B", end="\n" if taken == size else "\r")
    if not sh.boot(path, progress):
      sh.print_error(f"Image {name} refused, the old image keeps running")
      p.inf("The console takes images only with "
        f"{utils.color_symbol('#define CMD_BOOT ON')} in main.h")
      sys.exit(1)
    sh.print_info(f"Image {name} staged, the board resets to install it")
    # The first line of the new image ends the install, so no ping lands inside it
    start = time.monotonic()
    while time.monotonic() - start < INSTALL_TIMEOUT_s:
      if any(sh.read_lines() or []): break
    if not sh.ping(retries=INSTALL_PINGS):
      sh.print_error("Board silent after the reset")
      sys.exit(1)
    sh.exec("boot info")
