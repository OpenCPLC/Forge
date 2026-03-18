# opencplc/templates

import os
from xaeian import FILE, JSON, file_context

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
FILES_DIR = os.path.join(PKG_DIR, "files")

def load_templates() -> dict:
  """Load all template files as dict (supports PyInstaller bundle)."""
  with file_context(root_path=FILES_DIR, bundle=True):
    return {
      "opencplc.json": JSON.load("opencplc.json", {}),
      "makefile.mk": FILE.load("makefile.mk"),
      "flash": {
        "stm32g0.ld": FILE.load("flash/stm32g0.ld"),
        "stm32wb.ld": FILE.load("flash/stm32wb.ld"),
      },
      "properties.json": FILE.load("properties.json"),
      "launch.json": FILE.load("launch.json"),
      "tasks.json": FILE.load("tasks.json"),
      "settings.json": FILE.load("settings.json"),
      "extensions.json": FILE.load("extensions.json"),
      "main.h": FILE.load("main.h"),
      "main.c": FILE.load("main.c"),
      "main-none.c": FILE.load("main-none.c"),
      "host": {
        "makefile.mk": FILE.load("host/makefile.mk"),
        "main.h": FILE.load("host/main.h"),
        "main.c": FILE.load("host/main.c"),
      }
    }
