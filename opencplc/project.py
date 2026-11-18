# opencplc/project.py

"""
Files of a project, from its skeleton to its removal.

`prepare_project()` creates skeleton files a project keeps for life: main.c and main.h.
`generate()` renders everything Forge owns from the resolved `Project` model:
makefile and flash.ld in the project, workspace dispatcher, VS Code configuration.
An unchanged file keeps its bytes and its mtime.
`project_delete()` takes the project away, its ST-Link binding and the dispatcher target too.
"""

import os, re, sys, platform, subprocess
from datetime import datetime
from xaeian import Print, Color as c, FILE, DIR, PATH, replace_end
from xaeian.cmd import which
from .config import BOOT_H, BOOT_LINE, WARNINGS
from .templates import load_templates
from .platforms import FLASH_BASE
from .model import Config, Project
from .headers import boot_h_text
from .resolver import flash_layout, forge_version
from .workspace import persist_config
from .utils import keys
from . import utils

p = Print()

def mk_list(items:list[str]) -> str:
  """Backslash-continued makefile list, one entry per line."""
  return " \\\n".join(items)

def shown_path(path:str) -> str:
  """Path as messages print it, `./` before one from the workspace."""
  return path if PATH.is_abs(path) else f"./{path}"

def colored_path(path:str, name:str) -> str:
  """Path with the project name picked out of it, Core version greyed."""
  shown = utils.home_name(name)
  return f"{c.GREY}{shown_path(replace_end(path, shown, ''))}{c.END}{c.BLUE}{shown}{c.END}"

ANSI = re.compile(r"\x1b\[[0-9;]*m")

def recipe_safe(subs:dict) -> dict:
  """
  Color codes fit for the recipe lines of the shell make runs here.

  `/bin/sh` ends a command at each `;` of `ESC[38;5;Nm`, so there every code goes in quotes.
  `cmd.exe` takes the codes bare and would print the quotes.
  """
  if platform.system() == "Windows": return subs
  quote = lambda m: f"'{m.group()}'"
  return {key: ANSI.sub(quote, val) if isinstance(val, str) else val for key, val in subs.items()}

def write_dispatcher(active:str, colored:str=""):
  """Workspace `makefile`: `make` at the root builds `active`, or names none when it is ""."""
  subs = recipe_safe({
    "${ACTIVE}": active,
    "${ACTIVE_COLORED}": colored,
    "${GOLD}": c.GOLD, "${GREY}": c.GREY,
    "${END}": c.END,
    "${ERR}": f"{c.RED}ERR{c.END}",
  })
  # `$(error)` prints its text without a shell, so the codes stay bare
  subs["${CMD}"] = utils.color_command("opencplc <name>")
  utils.create_file("makefile", load_templates()["workspace.mk"], "", subs)

def rel_from(items:list[str], base:str) -> list[str]:
  """Paths relative to a directory, e.g. core paths relative to the Core dir."""
  return [PATH.rel(item, base) for item in items]

def anchored(path:str, base:str, var:str) -> str:
  """`path` spelled from Make variable `var` holding `base`: `$(PROJECT)` or `$(PROJECT)/src`."""
  rel = PATH.rel(path, base)
  return f"$({var})/{rel}" if rel else f"$({var})"

def bash_exe() -> str:
  """
  Bash that can open a Windows path.

  On Windows `bash` from PATH is usually WSL, blind to `C:/...`.
  Git brings its own, so that one wins when present.
  """
  if platform.system() != "Windows": return "bash"
  git = which("git")
  if not git: return "bash"
  root = PATH.dirname(git) # git.exe sits in cmd, bin or mingw64/bin
  for _ in range(3):
    root = PATH.dirname(root)
    for rel in ("bin/bash.exe", "usr/bin/bash.exe"):
      if FILE.exists(f"{root}/{rel}"): return f'"{root}/{rel}"'
  return "bash"

def without(text:str, phrases:list[str]) -> str:
  """Lines of text holding none of the phrases."""
  return "\n".join(ln for ln in text.splitlines() if not any(ph in ln for ph in phrases))

def stack_command(pro:Project) -> str:
  """Radio stack rule of a project: Core script, or a refusal saying what is missing."""
  if not pro.stack_script:
    return f"echo Chip {c.PINK}{pro.chip}{c.END} has no radio stack&& exit 1"
  if not utils.cube_found():
    missing = f"{c.YELLOW}STM32CubeProgrammer{c.END} not found"
    source = f"install it from {utils.color_url(utils.CUBE_URL)}"
    reload = f"reload with {utils.color_command('opencplc -r')}"
    return f"echo {missing}, {source} and {reload}&& exit 1"
  script = f'{bash_exe()} "$(OPENCPLC)/bin/{pro.stack_script}"'
  return f"{script} $(if $(STLINK),--sn=$(STLINK)) $(if $(FUS),--fus) $(if $(FAST),--fast)"

def test_rules(pro:Project, block:str) -> str:
  """
  `make test` of a project: the test block, or a refusal on a Core without the harness.

  The refusal stands only with programs to build, and has no prerequisites,
  so it comes before the archive builds, not after; with no program `make test` passes.
  Its colors stay placeholders, so the shell gets them as safe as those of the template.
  A comma would end an argument of `$(if)`, so the texts hold none.
  """
  if f"{pro.core_dir}/lib/sh/test.c" in pro.test_core_sources:
    return block.strip()
  separator = block.splitlines()[0] # the `Tests` section keeps its line in the makefile
  programs = f"$(wildcard {anchored(pro.test_dir, pro.pro_dir, 'PROJECT')}/*.c)"
  refusal = (f"Core ${{VIOLET}}{pro.core_ref}${{END}} has no test harness: "
    "raise ${SKY}PRO_FRAMEWORK${END} in main.h")
  return (f"{separator}\ntest:\n\t@$(if {programs},echo {refusal}&& exit 1,"
    "echo No test programs in ${TEST_COLORED})\n\n.PHONY: test")

def config_inputs(pro:Project) -> list[str]:
  """Reload inputs of the project makefile, anchored in `$(PROJECT)`: its settings and folders."""
  dirs = [anchored(d, pro.pro_dir, "PROJECT") for d in pro.project_dirs]
  return ["$(PROJECT)/main.h", f"$(PROJECT)/{BOOT_H}"] + dirs

def editor_paths(pro:Project) -> dict[str, str]:
  """
  Core, project and build folders as `.vscode` spells them, from the folder VS Code opens.

  The workspace opens at its root.
  A local project opens its own folder, so Core and build, both in the workspace, go absolute.
  """
  if utils.is_local(pro.name):
    return {
      "${CORE_PATH}": utils.full_path(pro.core_dir),
      "${PRO_PATH}": "${workspaceFolder}",
      "${BUILD_PATH}": utils.full_path(pro.build_dir),
    }
  return {
    "${CORE_PATH}": f"${{workspaceFolder}}/{pro.core_dir}",
    "${PRO_PATH}": f"${{workspaceFolder}}/{pro.pro_dir}",
    "${BUILD_PATH}": f"${{workspaceFolder}}/{pro.build_dir}",
  }

def dev_key(pro:Project) -> str:
  """Development key the bootloader of builds takes in place of every key, "" for `plain`."""
  return keys.dev_public().hex() if pro.boot_keys else ""

def include_flags(pro:Project, dirs:list[str]) -> list[str]:
  """-I flags anchored in `$(PROJECT)`, `$(BUILD)` or `$(OPENCPLC)`, resolved by Make."""
  # The project first: a test project of Core lies inside Core
  bases = ((pro.pro_dir, "PROJECT"), (pro.build_dir, "BUILD"), (pro.core_dir, "OPENCPLC"))
  flags = []
  for d in dirs:
    base = next(((path, var) for path, var in bases if PATH.is_under(d, path)), None)
    flags.append("-I" + anchored(d, *base) if base else "-I$(WORKSPACE)/" + d)
  return flags

def project_header(cfg:Config, new:bool=False):
  """
  Print which project and configuration this run works on.

  A new project under the bootloader says what that costs.
  The flag halves flash it can use and nothing else on screen would show it.
  """
  shown = utils.home_name(cfg.name)
  path_prefix = replace_end(utils.project_dir(cfg.name), shown, "")
  p.inf(f"Project {c.GREY}{path_prefix}{c.END}{c.BLUE}{shown}{c.END}")
  is_windows = platform.system() == "Windows"
  plc_msg = f" {c.TURQUS}PLC{c.END}" if cfg.plc else ""
  if cfg.board:
    chip_msg = f"{c.TURQUS}{cfg.board_title}{c.END}{plc_msg}"
  elif cfg.chip.platform == "STM32":
    chip_msg = f"{c.PINK}{cfg.chip.name}{c.END}{plc_msg}"
  else:
    host_os = "Windows" if is_windows else "Linux"
    chip_msg = f"{c.PINK}{cfg.chip.platform}{c.END} {c.GREY}({host_os}){c.END}"
  p.gap(f"using framework version {c.VIOLET}{cfg.fw_ver}{c.END} configured for {chip_msg}")
  if new and cfg.boot:
    origin, slot_kB, _ = flash_layout(cfg)
    p.gap(f"bootloader takes {c.GOLD}{cfg.chip.boot_kB}{c.END}kB, "
      f"image at {c.GOLD}0x{origin:08X}{c.END} in one of two {c.GOLD}{slot_kB}{c.END}kB slots")

def prepare_project(cfg:Config):
  """Create the project skeleton: its directory plus main.c/main.h when missing."""
  templates = load_templates()
  chip = cfg.chip
  tpl = templates.get(chip.hal, {})
  pro_dir = utils.project_dir(cfg.name)
  project_header(cfg, new=not FILE.exists(f"{pro_dir}/main.h"))
  if utils.is_core(cfg.name): return # the Core itself: its tests are all there is
  DIR.ensure(pro_dir)
  if cfg.plc:
    DIR.ensure(f"{utils.core_dir(cfg.fw_ver)}/plc")
  subs = {
    "${NAME}": utils.home_name(cfg.name),
    "${DATE}": datetime.now().strftime("%Y-%m-%d"),
    "${PRO_FRAMEWORK}": cfg.pro_ver,
    "${OPT_LEVEL}": cfg.opt_level,
    "${LOG_LEVEL}": cfg.log_level,
    "${BOARD}": cfg.board_title or "None",
    "${PLC}": "true" if cfg.plc else "false",
    "${DRIVERS}": ", ".join(cfg.project_drivers),
    "${CHIP}": chip.name,
    "${FLASH}": cfg.flash_kB,
    "${RAM}": cfg.ram_kB,
    "${FREQ}": cfg.freq_Hz,
    "${PLATFORM}": chip.platform,
    "${UART_NBR}": chip.uart["nbr"],
    "${UART_TX}": chip.uart["tx"],
    "${UART_RX}": chip.uart["rx"],
    "${UART_DMA}": chip.uart["dma"],
    "${LED_PORT}": chip.led["port"],
    "${LED_PIN}": chip.led["pin"],
    "${LED_NAME}": chip.led["name"],
  }
  # A project in Core builds with the Core it lies in, so it neither pins nor prints a version
  pinless = ["PRO_FRAMEWORK"] if utils.core_version(cfg.name) else []
  if not FILE.exists(f"{pro_dir}/main.c"):
    if chip.platform == "STM32":
      # A board on the PLC layer ships `PLC_Main`; the rest starts from the plain skeleton
      on_plc = cfg.board and cfg.plc
      main_c = templates["main.c"] if on_plc else templates["main-none.c"]
    else:
      main_c = tpl.get("main.c", templates["main-none.c"])
    utils.create_file("main.c", without(main_c, pinless), pro_dir, subs, color=c.BLUE)
  if not FILE.exists(f"{pro_dir}/main.h"):
    main_h = tpl.get("main.h", templates["main.h"])
    drop = ([] if cfg.project_drivers else ["PRO_DRIVERS"]) + pinless
    drop += [] if cfg.boot else [BOOT_LINE]
    utils.create_file("main.h", without(main_h, drop), pro_dir, subs, color=c.BLUE)
  if cfg.boot and not FILE.exists(f"{pro_dir}/{BOOT_H}"):
    utils.create_file(BOOT_H, boot_h_text(cfg.name), pro_dir, color=c.BLUE)

def project_delete(args, projects:dict, make_info:dict|None, forge_cfg:dict):
  """Remove the project folder, its ST-Link binding and, when active, the dispatcher target."""
  key = utils.project_key(projects, args.name)
  if key is None:
    p.err(f"Project {c.MAGNTA}{args.name}{c.END} does not exist")
    sys.exit(1)
  if utils.is_core(key):
    p.err(f"{c.BLUE}{key}{c.END} is a Core, its tests stay with it")
    sys.exit(1)
  if utils.is_local(key):
    p.err(f"{c.BLUE}{key}{c.END} lies outside the workspace, where Forge deletes nothing")
    p.run("Remove its folder by hand")
    sys.exit(1)
  try:
    active = PATH.local(projects[key])
    if forge_cfg["stlink"].pop(utils.project_dir(key), None) is not None:
      persist_config(forge_cfg)
    DIR.remove(projects[key], force=True)
    if make_info and make_info.get("ACTIVE") == active:
      write_dispatcher("")
      p.inf("Active project removed - "
        f"select another with {utils.color_command('opencplc <name>')}")
    p.ok(f"Project {c.BLUE}{args.name}{c.END} deleted")
    sys.exit(0)
  except Exception as e:
    p.err(f"Failed to delete: {e}")
    sys.exit(1)

def generate(pro:Project, activate:bool=True):
  """
  Render the project makefile and linker from the model.

  With `activate` the workspace follows too: dispatcher points here, VS Code gets its config.
  A reload from inside a project directory leaves both alone.
  Parallel builds never fight over the active project.
  A local project is never the active one: its VS Code config goes to its own folder.
  """
  templates = load_templates()
  tpl = templates.get(pro.hal, {})
  is_windows = platform.system() == "Windows"
  local = utils.is_local(pro.name)
  # A local project names the workspace in full, which holds on another drive as well
  if local: workspace = utils.full_path(".")
  else: workspace = f"$(abspath $(PROJECT)/{PATH.rel('.', pro.pro_dir)})"
  drive = os.path.splitdrive(PATH.resolve(pro.pro_dir))[0] # empty off Windows
  editor = editor_paths(pro)
  # Make of a local project runs in its folder, where a workspace-relative path means nothing
  build_shown = utils.full_path(pro.build_dir) if local else pro.build_dir
  boot_image = "$(BUILD)/boot/boot.hex" if pro.boot else ""
  # A `plain` bootloader holds no key, so `dist` packs the one of builds
  boot_dist_image = "$(BUILD)/boot-dist/boot.hex" if pro.boot_keys else boot_image
  subs = {
    "${NAME}": pro.name,
    "${LOAD_FLAGS}": pro.load_flags,
    "${TARGET}": pro.target,
    "${STLINK}": pro.stlink,
    "${WORKSPACE}": workspace,
    "${DRIVE}": drive.upper(),
    "${DRIVE_LOWER}": drive.lower(),
    "${CORE_DIR}": pro.core_dir,
    "${BUILD_DIR}": pro.build_dir,
    "${CORE_C}": mk_list(rel_from(pro.core_c_sources, pro.core_dir)),
    "${CORE_S}": mk_list(rel_from(pro.core_asm_sources, pro.core_dir)),
    "${PRO_C}": mk_list(rel_from(pro.project_c_sources, pro.pro_dir)),
    "${PRO_S}": mk_list(rel_from(pro.project_asm_sources, pro.pro_dir)),
    "${C_INCLUDES}": mk_list(include_flags(pro, pro.include_dirs)),
    "${CONFIG_INPUTS}": " ".join(config_inputs(pro)),
    "${C_DEFS}": " ".join(f"-D{d}" for d in pro.defines),
    "${WARNINGS}": " ".join(WARNINGS),
    "${FORGE_VERSION}": forge_version(),
    "${MCU_FLAGS}": pro.mcu_flags,
    "${OPT_LEVEL}": pro.opt_level,
    "${LOG_LEVEL}": pro.log_level,
    "${BOARD}": pro.board_title or "None",
    "${BOARD_LOWER}": (pro.board or "").lower(),
    "${CHIP}": pro.chip,
    "${FLASH}": pro.image_kB,
    "${FLASH_ORIGIN}": f"0x{pro.flash_origin:08X}",
    "${BOOT}": "true" if pro.boot else "false",
    "${BOOT_IMAGE}": boot_image,
    "${BOOT_DIST_IMAGE}": boot_dist_image,
    "${BOOT_ELF}": f"{editor['${BUILD_PATH}']}/boot/boot.elf" if pro.boot else "",
    "${BOOT_kB}": pro.boot_kB,
    "${BOOT_C}": mk_list(rel_from(pro.boot_c_sources, pro.core_dir)),
    "${BOOT_S}": mk_list(rel_from(pro.boot_asm_sources, pro.core_dir)),
    "${BOOT_INCLUDES}": mk_list(include_flags(pro, pro.boot_include_dirs)),
    "${BOOT_DEFS}": " ".join(f"-D{d}" for d in pro.boot_defines),
    "${BOOT_DEV_KEY}": dev_key(pro),
    "${BOOT_KEYS}": pro.boot_keys,
    "${SIGNING_KEY}": pro.signing_key if pro.boot_keys else "",
    "${RAM}": pro.ram_kB,
    "${FREQ}": pro.freq_Hz,
    "${HAL}": pro.hal,
    "${PLATFORM}": pro.platform,
    "${FAMILY}": pro.family,
    "${DEFINE}": pro.define,
    "${CPU}": pro.cpu,
    "${DEVICE}": pro.device,
    "${SVD}": pro.svd,
    "${OPENOCD_TARGET}": pro.openocd_target,
    "${OPENOCD}": subprocess.list2cmdline(utils.openocd_command(pro.openocd_target, pro.stlink)),
    "${ERASE_CMD}": pro.erase_command,
    "${STACK_CMD}": stack_command(pro),
    "${CUBE_PATH}": utils.cube_bin(),
    "${EXE_EXT}": ".exe" if is_windows else "",
    "${PROJECT_COLORED}": colored_path(pro.pro_dir, pro.name),
    "${BUILD_COLORED}": colored_path(build_shown, pro.name),
    "${TEST_DIR}": anchored(pro.test_dir, pro.pro_dir, "PROJECT"),
    "${TEST_CORE_C}": mk_list(rel_from(pro.test_core_sources, pro.core_dir)),
    "${TEST_INCLUDES}": mk_list(include_flags(pro, pro.test_include_dirs)),
    "${TEST_DEFS}": " ".join(f"-D{d}" for d in pro.test_defines),
    "${TEST_COLORED}": f"{c.GREY}{shown_path(pro.test_dir)}{c.END}",
    "${GOLD}": c.GOLD, "${PINK}": c.PINK, "${RED}": c.RED,
    "${LIME}": c.LIME, "${SKY}": c.SKY, "${VIOLET}": c.VIOLET,
    "${END}": c.END,
  } | editor | utils.template_paths(pro.platform == "STM32", pro.tests)
  # Linker script and makefile live inside the project, so parallel builds stay disjoint
  if pro.linker:
    ld_template = templates["flash"].get(pro.linker, templates["flash"]["stm32g0.ld"])
    utils.create_file("flash.ld", ld_template, pro.pro_dir, subs)
    # The bootloader links in the build folder, so a reload after `make clean` brings it back
    if pro.boot:
      region = {"${FLASH_ORIGIN}": f"0x{FLASH_BASE:08X}", "${FLASH}": pro.boot_kB}
      utils.create_file("boot.ld", ld_template, pro.build_dir, subs | region)
  # The Core itself has tests alone, and no `main.h`: Forge writes one into its build
  if utils.is_core(pro.name):
    makefile = tpl["core.mk"]
    utils.create_file("main.h", tpl["core.h"], pro.build_dir, subs)
  else:
    makefile = tpl.get("project.mk", templates["project.mk"])
  makefile = makefile.replace("${TEST}", test_rules(pro, templates["test.mk"]))
  makefile = makefile.replace("${BOOT_RULES}", templates["boot.mk"].strip() if pro.boot else "")
  # CubeProgrammer joins PATH of `make stack` only from its default home, elsewhere PATH has it
  keep_cube = bool(pro.stack_script and subs["${CUBE_PATH}"])
  utils.create_file("makefile", makefile, pro.pro_dir, recipe_safe(subs),
    remove_line="" if keep_cube else "${CUBE_PATH}")
  # `make` takes this makefile as reloaded, a reload now would only write the same
  FILE.save(f"{pro.build_dir}/.forge", "")
  if not activate: return
  if not local: write_dispatcher(pro.pro_dir, colored_path(pro.pro_dir, pro.name))
  vscode = f"{pro.pro_dir}/.vscode" if local else ".vscode"
  DIR.ensure(vscode)
  props = tpl.get("properties.json", templates["properties.json"])
  drop = ([] if pro.plc else ["/plc/", '"OpenCPLC"']) + ([] if pro.board else ["/brd/"])
  drop += [] if utils.is_core(pro.name) else ["${BUILD_PATH}"] # `main.h` of the Core itself
  utils.create_file("c_cpp_properties.json", without(props, drop), vscode, subs)
  # `cortex-debug` takes its tools from `PATH` where Forge has no packages to point at
  launch = tpl.get("launch.json", templates["launch.json"])
  drop = [] if pro.stlink else ["openOCDPreConfigLaunchCommands"]
  drop += [] if pro.boot else ["symbolFiles"]
  drop += [] if is_windows else ["TOOLS_ARM_DIR", "TOOLS_OPENOCD_EXE"]
  utils.create_file("launch.json", without(launch, drop), vscode, subs)
  utils.create_file("tasks.json", templates["tasks.json"], vscode, subs)
  # Shared files: created once, kept afterwards
  if not FILE.exists(f"{vscode}/settings.json"):
    utils.create_file("settings.json", templates["settings.json"], vscode, subs)
  if not FILE.exists(f"{vscode}/extensions.json"):
    utils.create_file("extensions.json", templates["extensions.json"], vscode, subs)
