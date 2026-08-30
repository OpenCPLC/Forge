# opencplc/templates

"""Template files shipped in opencplc/files, loaded as one dict."""

import os
from xaeian import FILE, JSON, file_context

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
FILES_DIR = os.path.join(PKG_DIR, "files")

def load_templates() -> dict:
  """Every template under files/ as a dict, read from the PyInstaller bundle when frozen."""
  with file_context(root_path=FILES_DIR, bundle=True):
    return {
      "opencplc.json": JSON.load("opencplc.json", {}),
      "project.mk": FILE.load("project.mk"),
      "workspace.mk": FILE.load("workspace.mk"),
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
        "project.mk": FILE.load("host/project.mk"),
        "properties.json": FILE.load("host/properties.json"),
        "launch.json": FILE.load("host/launch.json"),
        "main.h": FILE.load("host/main.h"),
        "main.c": FILE.load("host/main.c"),
      }
    }
