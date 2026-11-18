# .build.py

"""
Entry point PyInstaller freezes into `opencplc.exe`.

`opencplc.exe --python SCRIPT ARGS` runs a script as Python would, with the imports beside it.
The MISRA addon of cppcheck runs so, as a machine without Python has only the one the exe holds.
"""

import os, runpy, sys

# The addon is GPL: it runs in a process of its own before any code of Forge loads, `xaeian` too
if sys.argv[1:2] == ["--python"] and len(sys.argv) > 2:
  sys.argv = sys.argv[2:]
  sys.path.insert(0, os.path.dirname(os.path.abspath(sys.argv[0])))
  runpy.run_path(sys.argv[0], run_name="__main__")
else:
  from opencplc.__main__ import main
  main()
