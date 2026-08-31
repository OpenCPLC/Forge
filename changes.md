# Changes `opencplc`

## `0.3.0` One workspace, many builds

Breaking: fixed layout _(`projects/`, `opencplc/`, `build/`)_,
`opencplc.json` keeps `version` and `stlink`.

- Each project owns its `makefile`, `flash.ld` and build directory
- `make` reloads the project itself after a change in `main.h` or the source tree
- Boards come from the Core, a directory in `plc/brd` with an `.ini` manifest

## `0.2.1` HTTPS & startup order

- Downloads over HTTPS, remote names validated
- Toolchain follows the project platform, not the flag

## `0.2.0` ST-Link & versions

- Bind a programmer to a project, so `make flash` hits the right board
- Toolchains land in the system PATH _(admin console required)_
- A version is a folder in `opencplc/`, cloned from GitHub when missing

## `0.1.3` Windows fixes

- Installed toolchains work right away, without reopening the console
- Windows command environment is detected automatically

## `0.1.2` Fix

- Linker scripts ship with the package again

## `0.1.1` Packaging

- `xaeian` declared as a dependency and templates bundled, so `pip install` gives a working tool

## `0.1.0` Initial release

- One command to create, load, download and build an OpenCPLC project
- Targets STM32G0, STM32WB and HOST _(Windows/Linux)_
- Installable with `pip`
