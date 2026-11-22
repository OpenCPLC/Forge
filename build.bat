py -m pip show pyinstaller > nul 2>&1 ^
  || py -m pip install -U pyinstaller

if exist .\.dist\opencplc.exe ^
  del .\.dist\opencplc.exe

rem Hidden imports: what the MISRA addon of cppcheck imports when `opencplc.exe --python` runs it
py -m PyInstaller --onefile ^
  --workpath ./.build ^
  --distpath ./.dist ^
  --name opencplc ^
  --icon=opencplc.ico ^
  --add-data "opencplc/files;opencplc/files" ^
  --hidden-import argparse --hidden-import codecs --hidden-import copy ^
  --hidden-import fnmatch --hidden-import itertools --hidden-import json ^
  --hidden-import pathlib --hidden-import runpy --hidden-import string ^
  --hidden-import subprocess --hidden-import xml.etree.ElementTree ^
  .build.py
