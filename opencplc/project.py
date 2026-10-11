# opencplc/project.py

"""
Project generators.

`prepare_project()` creates skeleton files a project keeps for life: main.c and main.h.
`generate()` renders everything Forge owns from the resolved `Project` model:
makefile and flash.ld in the project, workspace dispatcher, VS Code configuration.
An unchanged file keeps its bytes and its mtime.
"""

import re, platform, subprocess
from datetime import datetime
from xaeian import Print, Color as c, FILE, DIR, PATH, replace_end
from xaeian.cmd import which
from .config import OPT_DEFAULT, LOG_LEVEL_DEFAULT
from .templates import load_templates
from .resolver import Project, flash_layout, forge_version
from . import utils

p = Print()

def mk_list(items:list[str]) -> str:
  """Backslash-continued makefile list, one entry per line."""
  return " \\\n".join(items)

def colored_path(path:str, name:str) -> str:
  """Workspace-relative path with the project name picked out of it, Core version greyed."""
  shown = utils.home_name(name)
  return f"{c.GREY}./{replace_end(path, shown, '')}{c.END}{c.BLUE}{shown}{c.END}"

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
  script = f'{bash_exe()} "$(OPENCPLC)/scr/{pro.stack_script}"'
  return f"{script} $(if $(STLINK),--sn=$(STLINK)) $(if $(FUS),--fus) $(if $(FAST),--fast)"

def test_rules(pro:Project, block:str) -> str:
  """
  `make test` of a project: the test block, or a refusal on a Core without the harness.

  The refusal has no prerequisites, so it comes before the archive builds, not after.
  Its colors stay placeholders, so the shell gets them as safe as those of the template.
  """
  if any(PATH.is_under(f, f"{pro.core_dir}/tst") for f in pro.test_core_sources):
    return block.strip()
  separator = block.splitlines()[0] # the `Tests` section keeps its line in the makefile
  refusal = (f"Core ${{VIOLET}}{pro.core_ref}${{END}} has no test harness, "
    "raise ${SKY}PRO_FRAMEWORK${END} in main.h")
  return f"{separator}\ntest:\n\t@echo {refusal}&& exit 1\n\n.PHONY: test"

def config_inputs(pro:Project) -> list[str]:
  """Reload inputs of the project makefile, anchored in `$(PROJECT)`."""
  return ["$(PROJECT)/main.h"] + [anchored(d, pro.pro_dir, "PROJECT") for d in pro.project_dirs]

def include_flags(pro:Project, dirs:list[str]) -> list[str]:
  """-I flags anchored in `$(PROJECT)`, `$(BUILD)` or `$(OPENCPLC)`, resolved by Make."""
  # the project first: a test project of Core lies inside Core
  bases = ((pro.pro_dir, "PROJECT"), (pro.build_dir, "BUILD"), (pro.core_dir, "OPENCPLC"))
  flags = []
  for d in dirs:
    base = next(((path, var) for path, var in bases if PATH.is_under(d, path)), None)
    flags.append("-I" + anchored(d, *base) if base else "-I$(WORKSPACE)/" + d)
  return flags

def project_header(cfg:dict, paths:dict, new:bool=False):
  """
  Print which project and configuration this run works on.

  A new project under the bootloader says what that costs.
  The flag halves flash it can use and nothing else on screen would show it.
  """
  shown = utils.home_name(cfg["pro_name"])
  path_prefix = replace_end(PATH.local(paths["pro"]), shown, "")
  p.inf(f"Project {c.GREY}{path_prefix}{c.END}{c.BLUE}{shown}{c.END}")
  is_windows = platform.system() == "Windows"
  plc_msg = f" {c.TURQUS}PLC{c.END}" if cfg.get("plc") else ""
  if cfg.get("board"):
    chip_msg = f"{c.TURQUS}{cfg['board_title']}{c.END}{plc_msg}"
  elif cfg["platform"] == "STM32":
    chip_msg = f"{c.PINK}{cfg['chip']}{c.END}{plc_msg}"
  else:
    host_os = "Windows" if is_windows else "Linux"
    chip_msg = f"{c.PINK}{cfg['platform']}{c.END} {c.GREY}({host_os}){c.END}"
  p.gap(f"using framework version {c.VIOLET}{cfg['fw_ver']}{c.END} configured for {chip_msg}")
  if new and cfg.get("boot"):
    origin, slot_kB, _ = flash_layout(cfg)
    p.gap(f"bootloader takes {c.GOLD}{cfg['boot_kB']}{c.END}kB, "
      f"image at {c.GOLD}0x{origin:08X}{c.END} in one of two {c.GOLD}{slot_kB}{c.END}kB slots")

def prepare_project(cfg:dict, paths:dict):
  """Create the project skeleton: its directory plus main.c/main.h when missing."""
  templates = load_templates()
  is_embedded = cfg["platform"] == "STM32"
  tpl = templates.get(cfg["hal"], {})
  project_header(cfg, paths, new=not FILE.exists(f"{paths['pro']}/main.h"))
  if utils.is_core(cfg["pro_name"]): return # the Core itself: its tests are all there is
  DIR.ensure(paths["pro"])
  if cfg.get("plc"):
    DIR.ensure(f"{paths['fw']}/plc")
  subs = {
    "${NAME}": utils.home_name(cfg["pro_name"]),
    "${DATE}": datetime.now().strftime("%Y-%m-%d"),
    "${PRO_FRAMEWORK}": cfg["pro_ver"],
    "${OPT_LEVEL}": cfg.get("opt_level", OPT_DEFAULT if is_embedded else "O2"),
    "${LOG_LEVEL}": cfg.get("log_level", LOG_LEVEL_DEFAULT),
    "${BOARD}": cfg["board_title"] or "None",
    "${PLC}": "true" if cfg.get("plc") else "false",
    "${BOOT}": "true" if cfg.get("boot") else "false",
    "${DRIVERS}": ", ".join(cfg.get("project_drivers", [])),
    "${CHIP}": cfg.get("chip", "").upper(),
    "${FLASH}": cfg["flash_kB"],
    "${RAM}": cfg["ram_kB"],
    "${FREQ}": cfg.get("freq_Hz", 64000000),
    "${PLATFORM}": cfg["platform"],
    "${UART_NBR}": cfg["uart"]["nbr"],
    "${UART_TX}": cfg["uart"]["tx"],
    "${UART_RX}": cfg["uart"]["rx"],
    "${UART_DMA}": cfg["uart"]["dma"],
    "${LED_PORT}": cfg["led"]["port"],
    "${LED_PIN}": cfg["led"]["pin"],
    "${LED_NAME}": cfg["led"]["name"],
  }
  # a project in Core builds with the Core it lies in, so it neither pins nor prints a version
  pinless = ["PRO_FRAMEWORK"] if utils.core_version(cfg["pro_name"]) else []
  if not FILE.exists(f"{paths['pro']}/main.c"):
    if is_embedded:
      # A board on the PLC layer ships `PLC_Main`; the rest starts from the plain skeleton
      on_plc = cfg.get("board") and cfg.get("plc")
      main_c = templates["main.c"] if on_plc else templates["main-none.c"]
    else:
      main_c = tpl.get("main.c", templates["main-none.c"])
    utils.create_file("main.c", without(main_c, pinless), paths["pro"], subs, color=c.BLUE)
  if not FILE.exists(f"{paths['pro']}/main.h"):
    main_h = tpl.get("main.h", templates["main.h"])
    drop = ([] if cfg["project_drivers"] else ["PRO_DRIVERS"]) + pinless
    utils.create_file("main.h", without(main_h, drop), paths["pro"], subs, color=c.BLUE)

def generate(pro:Project, activate:bool=True):
  """
  Render the project makefile and linker from the model.

  With `activate` the workspace follows too: dispatcher points here, VS Code gets its config.
  A reload from inside a project directory leaves both alone.
  Parallel builds never fight over the active project.
  """
  templates = load_templates()
  tpl = templates.get(pro.hal, {})
  is_windows = platform.system() == "Windows"
  up_path = PATH.rel(".", pro.pro_dir)
  subs = {
    "${NAME}": pro.name,
    "${TARGET}": pro.target,
    "${STLINK}": pro.stlink,
    "${UP_PATH}": up_path,
    "${CORE_DIR}": pro.core_dir,
    "${PRO_DIR}": pro.pro_dir,
    "${BUILD_DIR}": pro.build_dir,
    "${CORE_C}": mk_list(rel_from(pro.core_c_sources, pro.core_dir)),
    "${CORE_S}": mk_list(rel_from(pro.core_asm_sources, pro.core_dir)),
    "${PRO_C}": mk_list(rel_from(pro.project_c_sources, pro.pro_dir)),
    "${PRO_S}": mk_list(rel_from(pro.project_asm_sources, pro.pro_dir)),
    "${C_INCLUDES}": mk_list(include_flags(pro, pro.include_dirs)),
    "${CONFIG_INPUTS}": " ".join(config_inputs(pro)),
    "${C_DEFS}": " ".join(f"-D{d}" for d in pro.defines),
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
    "${BOOT_IMAGE}": f"$(OPENCPLC)/{pro.boot_image}" if pro.boot_image else "",
    "${BOOT_ELF}": pro.boot_elf,
    # the bootloader project hands its hex and elf to Core, an application to the project
    "${DIST_HEX}": f"$(OPENCPLC)/{pro.bootloader}.hex" if pro.bootloader
      else "$(PROJECT)/$(DIST).hex",
    "${DIST_ELF}": f"$(OPENCPLC)/{pro.bootloader}.elf" if pro.bootloader else "",
    "${BOOT_KEY}": pro.boot_key,
    "${BOOT_KEY_AT}": f"0x{pro.boot_key_at:08X}" if pro.boot_key_at else "",
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
    "${BUILD_COLORED}": colored_path(pro.build_dir, pro.name),
    "${TEST_DIR}": anchored(pro.test_dir, pro.pro_dir, "PROJECT"),
    "${TEST_CORE_C}": mk_list(rel_from(pro.test_core_sources, pro.core_dir)),
    "${TEST_INCLUDES}": mk_list(include_flags(pro, pro.test_include_dirs)),
    "${TEST_DEFS}": " ".join(f"-D{d}" for d in pro.test_defines),
    "${TEST_COLORED}": f"{c.GREY}./{pro.test_dir}{c.END}",
    "${GOLD}": c.GOLD, "${PINK}": c.PINK, "${RED}": c.RED,
    "${LIME}": c.LIME, "${SKY}": c.SKY, "${VIOLET}": c.VIOLET,
    "${END}": c.END,
  } | utils.template_paths(pro.platform == "STM32", pro.tests)
  # Linker script and makefile live inside the project - parallel builds stay disjoint
  if pro.linker:
    ld_template = templates["flash"].get(pro.linker, templates["flash"]["stm32g0.ld"])
    utils.create_file("flash.ld", ld_template, pro.pro_dir, subs)
  # the Core itself has tests alone, and no `main.h`: Forge writes one into its build
  if utils.is_core(pro.name):
    makefile = tpl["core.mk"]
    utils.create_file("main.h", tpl["core.h"], pro.build_dir, subs)
  else:
    makefile = tpl.get("project.mk", templates["project.mk"])
  makefile = makefile.replace("${TEST}", test_rules(pro, templates["test.mk"]))
  # CubeProgrammer joins PATH of `make stack` only from its default home, elsewhere PATH has it
  keep_cube = bool(pro.stack_script and subs["${CUBE_PATH}"])
  utils.create_file("makefile", makefile, pro.pro_dir, recipe_safe(subs),
    remove_line="" if keep_cube else "${CUBE_PATH}")
  # make takes this makefile as reloaded: a reload would write the same and drop -f of this run
  FILE.save(f"{pro.build_dir}/.forge", "")
  if not activate: return
  write_dispatcher(pro.pro_dir, colored_path(pro.pro_dir, pro.name))
  DIR.ensure(".vscode")
  props = tpl.get("properties.json", templates["properties.json"])
  drop = ([] if pro.plc else ["/plc/", '"OpenCPLC"']) + ([] if pro.board else ["/brd/"])
  drop += [] if utils.is_core(pro.name) else ["${BUILD_DIR}"] # `main.h` of the Core itself
  utils.create_file("c_cpp_properties.json", without(props, drop), ".vscode", subs)
  # cortex-debug takes its tools from PATH where Forge has no packages to point at
  launch = tpl.get("launch.json", templates["launch.json"])
  drop = [] if pro.stlink else ["openOCDPreConfigLaunchCommands"]
  drop += [] if pro.boot_elf else ["symbolFiles"]
  drop += [] if is_windows else ["TOOLS_ARM_DIR", "TOOLS_OPENOCD_EXE"]
  utils.create_file("launch.json", without(launch, drop), ".vscode", subs)
  utils.create_file("tasks.json", templates["tasks.json"], ".vscode", subs)
  # Shared files - created once, kept afterwards
  if not FILE.exists(".vscode/settings.json"):
    utils.create_file("settings.json", templates["settings.json"], ".vscode", subs)
  if not FILE.exists(".vscode/extensions.json"):
    utils.create_file("extensions.json", templates["extensions.json"], ".vscode", subs)
