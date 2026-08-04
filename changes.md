# Changes `opencplc`

## `0.2.0` ST-Link & versions

- Bind a programmer to a project, so `make flash` hits the right board
- Toolchains land in the system PATH _(admin console required)_
- A version is a folder in `opencplc/`, cloned from GitHub when missing

## `0.1.3` Windows fixes

- Installed toolchains work right away, without reopening the console
- `pwsh` is detected automatically

## `0.1.2` Fix

- Linker scripts ship with the package again

## `0.1.1` Packaging

- `xaeian` declared as a dependency and templates bundled, so `pip install` gives a working tool

## `0.1.0` Initial release

- One command to create, load, download and build an OpenCPLC project
- Targets STM32G0, STM32WB and HOST _(Windows/Linux)_
- Installable with `pip`
