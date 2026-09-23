# opencplc/config.py

"""
URLs and console conventions of Forge.

Console color conventions (xaeian.Color) - one meaning per color, grouped in families:

  yours    BLUE   → project: its name and its own sources (main.c, main.h)
           SKY    → what is set inside them: PRO_VERSION, PRO_CHIP, LOG_LEVEL, config keys, PATH
  hardware PINK   → platform and chip (STM32, STM32G0C1)
           TURQUS → board from Core (Uno) and the PLC layer
  build    ORANGE → what Forge generates: makefile, flash.ld, opencplc.json, .vscode
           CREAM  → a folder that is the point: workspace, missing version, one to remove or fix
           YELLOW → tools: Git, Make, arm-none-eabi-gcc
           GOLD   → numbers: list index, memory, frequency
           CYAN   → what you pick or type: optimization level, valid choices, commands
  version  VIOLET → the active one (max one per message)
           GREY   → the rest: other versions, locations, flags, hints
  outside  TEAL   → GitHub, repository URLs, sample names
  state    MAGNTA → invalid value
           GREEN  → yes, RED → no (prompts and log icons)

Generated C code (-hl) is syntax-highlighted instead, and every message closes its color spans.

Framework version rules:
  version → a folder in the framework dir: when present it builds as-is, never touched
  git     → used only to clone a missing version (tag or branch)
  active  → PRO_VERSION (main.h); a new project takes -f or the opencplc.json "version"
"""

# Workspace layout, fixed by Forge; Demo holds ordinary projects, cloned as a whole
DIR_PROJECTS = "projects"
DIR_DEMO = "projects/demo"
DIR_FRAMEWORK = "opencplc"
DIR_BUILD = "build"

# Remote homes: GitHub for code, dl.opencplc.com for tool packages and assets
URL_GIT = "https://github.com/OpenCPLC"
URL_DL = "https://dl.opencplc.com"
URL_CORE = f"{URL_GIT}/Core"
EXE_NAME = "opencplc.exe"
URL_FORGE = f"{URL_GIT}/Forge"
URL_DEMO = f"{URL_GIT}/Demo"
