# opencplc/host.py

from xaeian import Print, Color as c, FILE, PATH, JSON

p = Print()

def generate_tasks(c_sources:str, c_includes:str, target:str, fw_rel:str, pro_rel:str, is_windows:bool) -> dict:
  args = ["-g"]
  for inc in c_includes.split():
    if inc.startswith("-I"):
      path = inc[2:].replace("$(LIB)", fw_rel).replace("$(PRO)", pro_rel)
      args.append("-I${workspaceRoot}/" + path.lstrip("./"))
  for src in c_sources.replace("\\\n", " ").split():
    if src.endswith(".c"):
      path = src.replace("$(LIB)", fw_rel).replace("$(PRO)", pro_rel)
      args.append("${workspaceRoot}/" + path.lstrip("./"))
  exe = f"{target}.exe" if is_windows else target
  args += ["-o", "${workspaceRoot}/" + exe]
  if is_windows:
    args.append("-lbcrypt")
  else:
    args += ["-lm", "-lpthread"]
  return {
    "version": "2.0.0",
    "tasks": [{
      "type": "shell",
      "label": "debug",
      "command": "gcc",
      "args": args,
      "options": {"cwd": "C:/MinGW/bin"} if is_windows else {}
    }]
  }

def generate_launch(target:str, build_path:str, is_windows:bool) -> dict:
  exe = f"{target}{'.exe' if is_windows else ''}"
  return {
    "version": "0.2.0",
    "configurations": [{
      "name": "debug",
      "type": "cppdbg",
      "request": "launch",
      "program": "${workspaceRoot}/" + exe,
      "args": [],
      "stopAtEntry": False,
      "cwd": "${workspaceFolder}",
      "environment": [],
      "externalConsole": False,
      "MIMode": "gdb",
      "miDebuggerPath": "C:/MinGW/bin/gdb.exe" if is_windows else "gdb",
      "preLaunchTask": "debug"
    }]
  }

def generate_properties(name:str, c_includes:str, define:str, fw_rel:str, pro_rel:str, is_windows:bool) -> dict:
  paths = ["${workspaceFolder}/**"]
  for inc in c_includes.split():
    if inc.startswith("-I"):
      path = inc[2:].replace("$(LIB)", fw_rel).replace("$(PRO)", pro_rel)
      paths.append("${workspaceFolder}/" + path.lstrip("./"))
  defines = ["HOST", define, "_DEBUG"]
  if is_windows: defines += ["UNICODE", "_UNICODE"]
  return {
    "version": 4,
    "configurations": [{
      "name": name,
      "includePath": paths,
      "defines": defines,
      "compilerPath": "C:/MinGW/bin/gcc.exe" if is_windows else "/usr/bin/gcc",
      "cStandard": "gnu17",
      "cppStandard": "gnu++14",
      "intelliSenseMode": "windows-gcc-x64" if is_windows else "linux-gcc-x64"
    }]
  }

def save_json(path:str, data:dict):
  rewrite = FILE.exists(path)
  JSON.save_pretty(path, data)
  name = PATH.basename(path)
  folder = PATH.dirname(path)
  action = "Overwritten" if rewrite else "Created"
  p.ok(f"{action} {c.ORANGE}{name}{c.END} in {c.GREY}{folder}{c.END}")