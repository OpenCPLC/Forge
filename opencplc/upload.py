# opencplc/upload.py

"""
`--upload FILE [PORT]`, the step of `make update`: an update image sent over the console.

The board takes it with the `boot` shell command, `CMD_BOOT ON` in main.h,
as a device in the field takes an update over its own link, and resets to install it.
Once it answers again, `boot info` shows what the bootloader made of the image.
Without `PORT` the one console of the computer goes; with several, `PORT=` names one.
A board that answers no ping gets no image, so a silent one is never taken for a refusal.
"""

import sys, time
from xaeian import Print, Color as c, FILE, PATH
from xaeian.serial import Shell, serial_scan
from .args import flag
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
    p.run(f"Plug the board in and run {utils.color_command('make update')} again")
  else:
    listed = ", ".join(f"{c.GOLD}{name}{c.END}" for name in ports)
    p.err(f"Several console ports: {listed}")
    p.run(f"Name one, e.g. {utils.color_command(f'make update PORT={ports[0]}')}")
  sys.exit(1)

def upload(args:list[str]):
  """`--upload FILE [PORT]`; exits with `1` on a refusal or a silent board."""
  if len(args) > 2:
    p.err(f"Flag {flag.upload} takes FILE and an optional PORT")
    sys.exit(1)
  path = args[0]
  if PATH.ext(path).lower() not in (".bin", ".hex"):
    p.err(f"Flag {flag.upload} takes the .bin or .hex of an image")
    sys.exit(1)
  name = utils.color_image(PATH.basename(path))
  if not FILE.exists(path):
    p.err(f"Image {name} not found")
    p.run(f"Build it with {utils.color_command('make')}")
    sys.exit(1)
  port = console_port(args[1] if len(args) > 1 else None)
  # the console of a project runs without echo, so the first line of a reply is the reply
  with Shell(port, time_disp=False, strip_echo=False) as sh:
    if not sh.serial: sys.exit(1) # the port said why it did not open
    sh.serial.read(sh.buffer_size) # what ST-Link kept while the port was closed
    if not sh.ping(retries=INSTALL_PINGS):
      sh.print_error(f"Board on {c.GOLD}{port}{c.END} silent, no image sent")
      p.run("Power it off and on: a locked chip starts only after a power cycle")
      sys.exit(1)
    def progress(taken:int, size:int):
      p.inf(f"Upload {taken}/{size} {c.GREY}[B]{c.END}", end="\n" if taken == size else "\r")
    if not sh.boot(path, progress):
      sh.print_error(f"Image {name} refused, the old image keeps running")
      p.inf(f"The console takes images only with {c.SKY}#define CMD_BOOT ON{c.END} in main.h")
      sys.exit(1)
    sh.print_info(f"Image {name} staged, the board resets to install it")
    # the first line of the new image ends the install, so no ping lands inside it
    start = time.monotonic()
    while time.monotonic() - start < INSTALL_TIMEOUT_s:
      if any(sh.read_lines() or []): break
    if not sh.ping(retries=INSTALL_PINGS):
      sh.print_error("Board silent after the reset")
      sys.exit(1)
    sh.exec("boot info")
