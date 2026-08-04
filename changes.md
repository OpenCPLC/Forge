# Changes `opencplc`

## `0.2.0` ST-Link & versions

- `stlink` in `opencplc.json`: programmer pinned to a project
- Environment variables set system-wide
- Version = folder in `opencplc/`, any branch or tag name allowed

## `0.1.3` Windows fixes

- PATH applies immediately after toolchain install
- `pwsh` shell auto-detect

## `0.1.2` Fix

- Nested package-data in wheel _(`files/flash/*.ld`)_

## `0.1.1` Packaging

- `xaeian` added to dependencies, template files included in wheel

## `0.1.0` Initial release

- CLI for OpenCPLC projects: create, reload, download and build with a single command
- Targets: STM32G0, STM32WB and HOST _(Windows/Linux)_
- Installable via `pip`
