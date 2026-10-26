# tests/test_generate.py

"""Generators: project makefile, dispatcher, idempotency, preserved mtime."""

import json, os, re, time
from pathlib import Path
import pytest
from xaeian import file_context, Color as c
from opencplc import actions, utils, project
from opencplc.project import generate, prepare_project
from opencplc.resolver import resolve_project
from opencplc.utils import keys
from conftest import build_workspace, uno_cfg, wb55_cfg, ws_paths, parse_dispatcher, resolve_uno
from conftest import KEY, key_boot, resolve_key_uno, read_makefile

BUILD = Path("build/projects/myapp") # build folder of myapp, the bootloader files in it

@pytest.fixture()
def ws(tmp_path):
  """Synthetic workspace as file root."""
  build_workspace(tmp_path)
  with file_context(root_path=str(tmp_path)):
    yield tmp_path

def project_makefile_and_linker_land_in_the_project(ws):
  generate(resolve_uno())
  make = read_makefile(ws)
  assert "NAME := myapp" in make
  assert "WORKSPACE := $(abspath $(PROJECT)/../..)" in make
  assert "$(WORKSPACE)/opencplc/1.0.0" in make
  assert "$(WORKSPACE)/build/projects/myapp" in make
  assert "hal/arm/core.c" in make # core-relative source
  assert "brd/uno/opencplc_uno.c" in make
  assert "brd/eco" not in make
  assert "main.c \\\nutil/extra.c" in make
  assert "stm32g0x mass_erase 0" in make
  assert (ws / "projects" / "myapp" / "flash.ld").exists()

def drive_goes_upper_case_whichever_spelling_make_starts_on(ws):
  """`.d` files keep the paths they got, so `c:` of VS Code and `C:` of a console must agree."""
  generate(resolve_uno())
  drive = os.path.splitdrive(str(ws))[0]
  anchor = f"$(patsubst {drive.lower()}%,{drive.upper()}%,$(abspath $(THIS_MAKEFILE)))"
  assert f"MAKEFILE_PATH := {anchor}" in read_makefile(ws)

def top_build_asks_its_own_build_so_fresh_files_stay_quiet(ws):
  """A new bootloader alone repacks the image, and the elf, hex and bin say nothing."""
  generate(resolve_uno())
  make = read_makefile(ws)
  assert '"$(MAKE)" --no-print-directory -q build && echo Nothing' in make
  assert '|| "$(MAKE)" --no-print-directory build' in make
  assert '--no-print-directory $(ARTIFACTS)' not in make

def dispatcher_points_at_the_active_project(ws):
  generate(resolve_uno())
  root = (ws / "makefile").read_text()
  assert parse_dispatcher(root) == "projects/myapp"
  assert "clean_all" in root
  assert "--no-print-directory" in root
  assert "\x1b[" in root and "myapp" in root

def one_flash_rule_and_the_debugger_load_the_packed_image(ws):
  """Neither the makefile nor the debugger knows whether a bootloader sits in front."""
  rule = "program $(BUILD)/$(TARGET)-dist.hex verify reset exit"
  for cfg in (uno_cfg(), uno_cfg() | {"boot": True}):
    generate(resolve_project(cfg, ws_paths(), {}))
    make = read_makefile(ws)
    assert make.count(rule) == 1 and "$(TARGET).elf verify" not in make
    launch = json.loads((ws / ".vscode" / "launch.json").read_text())["configurations"][0]
    assert launch["loadFiles"] == ["build/projects/myapp/myapp-dist.hex"]
    assert launch["executable"].endswith("myapp.elf") # symbols stay with the elf

def dist_packs_the_image_again_with_the_bootloader_of_dist(ws):
  """
  Two files: the full image for a bare chip, the image alone for `UPDATE`.

  Packed again rather than copied: under the `key` bootloader the product key signs them,
  behind the bootloader that holds the product keys.
  """
  generate(resolve_uno())
  make = read_makefile(ws)
  dist = make[make.index("\ndist:"):make.index("\nclean:")]
  assert dist.startswith("\ndist: build $(BOOT_DIST_IMAGE)\n")
  packed = ("--pack $(BUILD)/$(TARGET).hex $(PROJECT)/$(DIST).hex $(BOOT_DIST_IMAGE) "
    "$(if $(BOOT_KEYS),$(BOOT_KEYS) $(SIGNING_KEY) dist)")
  assert packed in dist
  assert dist.index("ifeq ($(BOOT),true)") < dist.index("Full image") < dist.index("Update image")
  assert dist.index("Update image") < dist.index("\nelse\n") < dist.index("Flash image")

def color_codes_stay_whole_under_a_posix_shell(ws, monkeypatch):
  """`/bin/sh` ends a command at the `;` of a 256-color code, so every code goes in quotes."""
  monkeypatch.setattr(project.platform, "system", lambda: "Linux")
  generate(resolve_uno())
  quoted = f"for '{c.GOLD}'build'{c.END}'"
  assert quoted in read_makefile(ws)
  assert quoted in (ws / "makefile").read_text() # the dispatcher too

def vscode_points_at_the_project_build_dir(ws):
  generate(resolve_uno())
  launch = (ws / ".vscode" / "launch.json").read_text()
  assert "build/projects/myapp/myapp.elf" in launch
  for name in ("c_cpp_properties.json", "tasks.json", "settings.json"):
    assert (ws / ".vscode" / name).exists(), name

def objects_map_into_disjoint_trees(ws):
  generate(resolve_uno())
  make = read_makefile(ws)
  assert "$(BUILD)/opencplc/%.o: $(OPENCPLC)/%.c" in make
  assert "$(BUILD)/project/%.o: $(PROJECT)/%.c" in make
  assert "vpath" not in make

def unchanged_regeneration_keeps_bytes_and_mtime(ws):
  generate(resolve_uno())
  files = [
    ws / "projects" / "myapp" / "makefile",
    ws / "projects" / "myapp" / "flash.ld",
    ws / "makefile",
    ws / ".vscode" / "launch.json",
  ]
  stamps = {f: (f.read_bytes(), f.stat().st_mtime_ns) for f in files}
  time.sleep(0.02)
  generate(resolve_uno())
  for f in files:
    assert (f.read_bytes(), f.stat().st_mtime_ns) == stamps[f], f.name

def stlink_binds_makefile_and_debugger(ws):
  generate(resolve_uno())
  make = read_makefile(ws)
  assert "STLINK := \n" in make
  assert "OPENOCD = openocd -f interface/stlink.cfg -f target/stm32g0x.cfg" in make
  assert "openOCDPreConfigLaunchCommands" not in (ws / ".vscode" / "launch.json").read_text()
  generate(resolve_uno({"stlink": {"projects/myapp": "ABC123"}}))
  make = read_makefile(ws)
  assert "STLINK := ABC123" in make
  assert 'stlink.cfg -c "adapter serial ABC123" -f target/stm32g0x.cfg' in make
  launch = (ws / ".vscode" / "launch.json").read_text()
  assert "openOCDPreConfigLaunchCommands" in launch
  assert "ABC123" in launch

def nested_project_anchors_deeper(ws, tmp_path):
  build_workspace(tmp_path, project="firm/app")
  cfg = uno_cfg("firm/app")
  paths = ws_paths(name="firm/app")
  pro = resolve_project(cfg, paths, {})
  generate(pro)
  make = (tmp_path / "projects" / "firm" / "app" / "makefile").read_text()
  assert "WORKSPACE := $(abspath $(PROJECT)/../../..)" in make
  assert "$(WORKSPACE)/build/projects/firm/app" in make

def prepare_creates_skeleton_once(ws, tmp_path):
  cfg = uno_cfg("fresh")
  paths = ws_paths(name="fresh")
  prepare_project(cfg, paths)
  main_c = tmp_path / "projects" / "fresh" / "main.c"
  assert main_c.exists()
  main_c.write_text("// user edit\n")
  prepare_project(cfg, paths)
  assert main_c.read_text() == "// user edit\n"

def plain_project_links_at_the_start_of_flash(ws):
  generate(resolve_uno())
  ld = (ws / "projects" / "myapp" / "flash.ld").read_text()
  assert "ORIGIN = 0x08000000, LENGTH = 492K" in ld
  assert ".app_header ORIGIN(FLASH) + 0x200" in ld and ".app_trailer" in ld
  make = read_makefile(ws)
  assert "BOOT := false" in make and "FLASH_kB := 492" in make
  assert "-DBOOT_CHIP=0x467" in make # every build, the bootloader one too
  assert "BOOT_IMAGE := \n" in make
  assert "$(FORGE) --pack $< $@ $(BOOT_IMAGE)" in make
  assert "boot.elf" not in make and "update:" not in make
  assert not (ws / BUILD / "boot.ld").exists()

def boot_project_links_into_its_slot_and_builds_the_bootloader_under_it(ws):
  generate(resolve_project(uno_cfg() | {"boot": True}, ws_paths(), {}))
  ld = (ws / "projects" / "myapp" / "flash.ld").read_text()
  assert "ORIGIN = 0x08003000, LENGTH = 240K" in ld
  make = read_makefile(ws)
  assert "BOOT := true" in make and "FLASH_kB := 240" in make
  assert "-DBOOT_SLOT_PAGES=120" in make
  # the `plain` bootloader holds no key, so `dist` packs the one of builds
  assert "BOOT_IMAGE := $(BUILD)/boot/boot.hex\n" in make and "BOOT_KEYS := \n" in make
  assert "BOOT_DIST_IMAGE := $(BUILD)/boot/boot.hex\n" in make
  assert "BOOT_kB := 10\n" in make and "BOOT_C = .boot/main.c \\\n" in make
  assert "$(BUILD)/boot/boot.elf:" in make and "\nupdate: build\n" in make
  assert "BOOT_DEV_KEY := \n" in make # a `plain` bootloader takes no key
  # `main.h` of Core `.boot/` first, then `boot.h` of the project
  assert "BOOT_INCLUDES = -I$(OPENCPLC)/.boot \\\n-I$(PROJECT) \\\n" in make
  # the region less its mailbox page, linked at the start of flash
  boot_ld = (ws / BUILD / "boot.ld").read_text()
  assert "ORIGIN = 0x08000000, LENGTH = 10K" in boot_ld

def key_bootloader_of_builds_takes_the_development_key(ws):
  """A board on the desk takes what this computer builds and keeps its floors in the slot."""
  generate(resolve_key_uno())
  ld = (ws / "projects" / "myapp" / "flash.ld").read_text()
  assert "ORIGIN = 0x08008000, LENGTH = 230K" in ld
  make = read_makefile(ws)
  assert "BOOT_IMAGE := $(BUILD)/boot/boot.hex\n" in make
  assert "BOOT_DIST_IMAGE := $(BUILD)/boot-dist/boot.hex\n" in make
  assert f"BOOT_KEYS := {KEY}\n" in make and "SIGNING_KEY := 0\n" in make
  assert "-DBOOT_PAGES=16" in make and "-DBOOT_SLOT_PAGES=115" in make
  assert "-DBOOT_KEYS" not in make # both programs read the keys from boot.h
  # a build signs with the development key, the one the bootloader of builds takes
  assert "--pack $< $@ $(BOOT_IMAGE) $(if $(BOOT_KEYS),$(BOOT_KEYS) $(SIGNING_KEY))\n" in make
  assert "-dist.hex: $(BUILD)/$(TARGET).hex $(BOOT_IMAGE)\n" in make
  assert "BOOT_kB := 30\n" in make
  assert "ORIGIN = 0x08000000, LENGTH = 30K" in (ws / BUILD / "boot.ld").read_text()
  assert f"BOOT_DEV_KEY := {keys.dev_public().hex()}\n" in make
  # the flag goes to the objects of `boot/` alone, `boot-dist/` takes the product keys
  desk = make[make.index("$(BUILD)/boot/%.o: $(OPENCPLC)/%.c"):]
  dist = make[make.index("$(BUILD)/boot-dist/%.o: $(OPENCPLC)/%.c"):]
  assert "$(BOOT_DEV)" in desk.split("\n\n")[0] and "$(BOOT_DEV)" not in dist.split("\n\n")[0]

def boot_h_of_the_project_reloads_the_makefile(ws):
  generate(resolve_key_uno())
  assert "$(wildcard $(PROJECT)/main.h $(PROJECT)/boot.h " in read_makefile(ws)

def dist_signs_with_the_key_pro_signing_key_names(ws):
  cfg = uno_cfg() | key_boot(KEY * 2) | {"signing_key": 1}
  generate(resolve_project(cfg, ws_paths(), {}))
  assert "SIGNING_KEY := 1\n" in read_makefile(ws)

def stack_rule_takes_cube_from_its_default_home(ws, monkeypatch):
  monkeypatch.setattr(utils, "cube_bin", lambda: "C:/Program Files/cube/bin")
  monkeypatch.setattr(utils, "cube_found", lambda: True)
  generate(resolve_project(wb55_cfg(), ws_paths(), {}))
  make = read_makefile(ws)
  assert "stack: export PATH := C:/Program Files/cube/bin;$(PATH)" in make
  assert "flash_cpu2.sh" in make and "$(if $(FAST),--fast)" in make

def stack_rule_leaves_cube_elsewhere_to_path(ws, monkeypatch):
  monkeypatch.setattr(utils, "cube_bin", lambda: "")
  monkeypatch.setattr(utils, "cube_found", lambda: True)
  generate(resolve_project(wb55_cfg(), ws_paths(), {}))
  make = read_makefile(ws)
  assert "stack: export PATH" not in make
  assert "flash_cpu2.sh" in make

def stack_rule_without_cube_says_where_to_get_it(ws, monkeypatch):
  monkeypatch.setattr(utils, "cube_bin", lambda: "")
  monkeypatch.setattr(utils, "cube_found", lambda: False)
  generate(resolve_project(wb55_cfg(), ws_paths(), {}))
  make = read_makefile(ws)
  assert "STM32CubeProgrammer" in make and "stm32cubeprog" in make
  assert "flash_cpu2.sh" not in make

def chip_without_radio_stack_gets_no_cube(ws, monkeypatch):
  monkeypatch.setattr(utils, "cube_bin", lambda: "C:/Program Files/cube/bin")
  generate(resolve_uno())
  make = read_makefile(ws)
  assert "has no radio stack" in make
  assert "stack: export PATH" not in make

def no_placeholder_outlives_generation(ws):
  """Make reads a stray `${KEY}` as an empty variable, so a missing color would vanish silently."""
  files = ["projects/myapp/makefile", "makefile", "projects/myapp/flash.ld",
    ".vscode/launch.json", ".vscode/c_cpp_properties.json"]
  for cfg in (uno_cfg(), uno_cfg() | {"boot": True}, uno_cfg() | key_boot(), wb55_cfg(),
    wb55_cfg() | key_boot()):
    generate(resolve_project(cfg, ws_paths(), {}))
    for name in files + ([f"{BUILD.as_posix()}/boot.ld"] if cfg.get("boot") else []):
      assert not re.findall(r"\$\{[A-Z_]+\}", (ws / name).read_text()), name

def the_dispatcher_forwards_every_project_target(ws):
  """Anything a project declares in `.PHONY` is reachable from the workspace root."""
  def phony(text:str) -> set:
    return {t for ln in text.splitlines() if ln.startswith(".PHONY:") for t in ln.split()[1:]}
  generate(resolve_key_uno())
  assert phony(read_makefile(ws)) - phony((ws / "makefile").read_text()) == set()

def program_alone_takes_the_image_dist_left_in_the_project(ws):
  (ws / "projects" / "myapp" / "myapp-1.0.hex").write_text(":00000001FF\n")
  found = actions.dist_image(resolve_uno(), yes=False)
  assert Path(found) == ws / "projects" / "myapp" / "myapp-1.0.hex"

def debugger_takes_the_symbols_of_the_bootloader_the_build_makes(ws):
  """`make` before the debugger builds the bootloader under the image, its elf with it."""
  generate(resolve_uno())
  launch = json.loads((ws / ".vscode" / "launch.json").read_text())["configurations"][0]
  assert "symbolFiles" not in launch
  generate(resolve_key_uno())
  launch = json.loads((ws / ".vscode" / "launch.json").read_text())["configurations"][0]
  assert launch["symbolFiles"] == [{"file": "build/projects/myapp/myapp.elf"},
    {"file": "build/projects/myapp/boot/boot.elf"}]
