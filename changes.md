# Changes `opencplc`

## `0.4.2` Bootloader

- `-B --boot` links image into one of two slots behind Core bootloader
- `make flash` programs bootloader and image
- `Os` joins optimization levels
- Drivers may nest in `dvr/`, found by name

## `0.4.1` Board names and radio stack

- `name` and `reserve_kB` in board manifest
- `make stack` flashes CPU2, `-e --demo` clones Demo
- STM32WB55 keeps 832kB, wireless stack owns the rest

## `0.4.0` Boards and drivers outside PLC

Breaking: `-b custom` is gone,
`PRO_BOARD_CUSTOM` becomes `PRO_BOARD_None` with `PRO_PLC true`.

- Boards come from `brd/`, drivers from `dvr/`, both work without PLC layer
- `PRO_PLC` holds that layer, `--plc` adds it without a board
- `--dvr` picks drivers for a new project
- `-u` replaces executable next to itself

## `0.3.1` Rebuild only what changed

- Save no longer rebuilds whole project, only what changed
- Overwrites in `main.h` apply on every include

## `0.3.0` One workspace, many builds

Breaking: fixed layout _(`projects/`, `opencplc/`, `build/`)_,
`opencplc.json` keeps `version` and `stlink`.

- Each project owns its `makefile`, `flash.ld` and build directory
- `make` reloads project itself after a change in `main.h` or source tree
- Boards come from Core, a directory in `plc/brd` with `.ini` manifest

## `0.2.1` HTTPS & startup order

- Downloads over HTTPS, remote names validated
- Toolchain follows project platform, not flag

## `0.2.0` ST-Link & versions

- Bind a programmer to a project, so `make flash` hits right board
- Toolchains land in system PATH _(admin console required)_
- A version is a folder in `opencplc/`, cloned from GitHub when missing

## `0.1.3` Windows fixes

- Installed toolchains work right away, without reopening console
- Windows command environment is detected automatically

## `0.1.2` Fix

- Linker scripts ship with the package again

## `0.1.1` Packaging

- `xaeian` declared as a dependency and templates bundled, so `pip install` gives a working tool

## `0.1.0` Initial release

- One command to create, load, download and build an OpenCPLC project
- Targets STM32G0, STM32WB and HOST _(Windows/Linux)_
- Installable with `pip`
