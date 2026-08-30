# opencplc/config.py

"""
URLs and the console conventions of Forge.

Console color conventions (xaeian.Color) - one meaning per color, grouped in families:

  yours    BLUE   → project: its name and its own sources (main.c, main.h)
           SKY    → what is set inside them: PRO_VERSION, PRO_CHIP, LOG_LEVEL, config keys, PATH
  hardware PINK   → platform and chip (STM32, STM32G0C1)
           TURQUS → board from Core (Uno) and Custom
  build    ORANGE → what Forge generates: makefile, flash.ld, opencplc.json, .vscode, opencplc/
           YELLOW → tools: Git, Make, arm-none-eabi-gcc
           GOLD   → numbers: list index, memory, frequency
           CYAN   → what you pick or type: optimization level, valid choices, commands
  version  VIOLET → the active one (max one per message)
           GREY   → the rest: other versions, location prefixes, flags, hints
  outside  TEAL   → GitHub, repository URLs, sample names
  state    MAGNTA → invalid value
           GREEN  → yes, RED → no (prompts and log icons)

Generated C code (-hl) is syntax-highlighted instead, and every message closes its color spans.

Framework version rules:
  version → a folder in the framework dir: when present it builds as-is, never touched
  git     → used only to clone a missing version (tag or branch)
  active  → PRO_VERSION (main.h); a new project takes -f or the opencplc.json "version"
"""

# Workspace layout, fixed by Forge; examples are ordinary projects cloned from Demo
DIR_PROJECTS = "projects"
DIR_EXAMPLES = "projects/examples"
DIR_FRAMEWORK = "opencplc"
DIR_BUILD = "build"

# GitHub URLs
URL_GIT = "https://github.com/OpenCPLC"
URL_FTP = "https://sqrt.pl/opencplc"
URL_CORE = f"{URL_GIT}/Core"
URL_FORGE = f"{URL_GIT}/Forge"
URL_DEMO = f"{URL_GIT}/Demo"
