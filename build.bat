py -m pip show pyinstaller > nul 2>&1 ^
  || py -m pip install -U pyinstaller

if exist .\.dist\opencplc.exe ^
  del .\.dist\opencplc.exe

py -m PyInstaller --onefile ^
  --workpath ./.build ^
  --distpath ./.dist ^
  --name opencplc ^
  --icon=opencplc.ico ^
  --add-data "opencplc/files;opencplc/files" ^
  .build.py