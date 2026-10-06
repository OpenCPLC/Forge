# 🥾 Bootloader and 🔒 lock

Two independent mechanisms.
The Core bootloader decides which image runs and takes updates without a programmer.
The lock closes the programmer port and the start from ROM.
Each works without the other, and together they make the production level described under Security.
Forge basics are in the [readme](readme.md).

## 🥾 Bootloader

### Modes

| | `plain` | `key` |
| --- | --- | --- |
| Starts | image with valid CRC | image signed with product key |
| Bootloader region | 8kB on G0, 16kB on WB | 32kB |
| Cost | none | smaller slot, longer start, key to guard |
| For | prototypes, learning | product that takes updates |

`plain` guards against accidents only: an interrupted or damaged update, a power loss, a file for another device.
It is not a secure product configuration.

Behind the bootloader Forge splits the rest of `PRO_FLASH_kB` into two equal slots: the application slot and staging, where an update lands first.
The bootloader copies only a whole, verified image into the application slot, so an interrupted transfer or a power loss during the copy is harmless: the old image runs, or the copy repeats on the next start.
`key` also checks an Ed25519 signature at every start, against the key it carries in its code.

### Keys

- **Development key**: Forge makes it by itself on the first `key` build, one per machine, as `dev.key`.
  `make`, `make flash` and F5 sign with it and write the same key into the bootloader, so a board on the desk takes its own builds.
- **Product key**: `--keygen` makes it, `acme.key` encrypted with a password and `acme.pub` beside it.
  Only `make dist` signs with it, after the password.

Keys live in `%LOCALAPPDATA%/OpenCPLC/keys`, on Linux in `~/.local/share/OpenCPLC/keys`, and `OPENCPLC_KEYS` points elsewhere.
Move a damaged `dev.key` away and Forge makes a new one.

> [!WARNING]
> Losing the product key or its password ends updates of every device in the field, and a leak lets anyone sign an image they accept.
> Keep `acme.key` and its password in two offline copies with limited access, and use a separate key for each product.

### Switching on

```sh
opencplc -n myapp -b uno -B  # new project with PRO_BOOT true in main.h
make run                     # build, then bootloader and image over ST-Link
```

An existing project switches with one line in `main.h`, `#define PRO_BOOT true`, and `make run` reloads it by itself, as `main.h` is newer than the `makefile`.
Back is `PRO_BOOT false` and `make run` again, which writes a plain image over the bootloader.

### Product key

```sh
opencplc myapp --keygen acme  # new key: password twice, PRO_BOOT_KEY and PRO_BOOT_EPOCH 0 into main.h
make run                      # key bootloader with development key and signed image
```

A second project of the same product takes the existing key, without a password:

```sh
opencplc panel --keygen acme
```

A project with `PRO_BOOT_KEY` gets no new key, as it would cut off devices in the field.

### Daily work

```sh
make      # build, signed with development key
make run  # build and flash
```

A build gives `build/projects/myapp/myapp-dist.hex`, bootloader and image in one file, which `make flash` and F5 send, and beside it `myapp-dist.bin`, the image alone for an update.
F5 loads bootloader symbols beside the application, so the debugger steps from the bootloader into the application.
An update on a development board is tested with that `myapp-dist.bin`, as an image of `make dist` carries the product key signature and the board refuses it with `signature`.

### Release

```sh
make dist TAG=1.2.0 # under key asks for password of key acme
```

Into `projects/myapp/` go the full image `myapp-1.2.0.hex` for a programmer and `myapp-1.2.0.bin` for an update, under `key` both signed with the product key.
In CI the key and password come from variables:

```sh
export OPENCPLC_KEYS=/secure/keys # acme.key and acme.pub
export OPENCPLC_KEY_PASSWORD=...
opencplc myapp
make dist TAG=1.2.0
```

Without `acme.key` on the machine `make dist` refuses with `no private key for ...`, with a wrong password with `wrong password for key acme`, leaving no file either way.
With the development key in `PRO_BOOT_KEY`, `make dist` signs with it without a password: that tests the release path before a product key exists.

A release with a security fix raises the epoch:

```sh
# in main.h: #define PRO_BOOT_EPOCH 1
make dist TAG=1.2.1
```

Once it is installed, the device takes no image of epoch 0, so it never goes back to the vulnerable version.
The epoch goes up only with a fix, as it should block going back past the hole, not every return to an older version, e.g. after a failed release.

### Update

The application takes `myapp-1.2.0.bin` over its own link, e.g. BLE, RS or USB, and hands the bytes to `BOOT_Begin`, `BOOT_Write` and `BOOT_End` of `hal/stm32/sys/boot.h`, the signature to `BOOT_Signature`.
`BOOT_End` checks the image as the bootloader does, the board resets, and the bootloader copies the image into the application slot and starts it.
Who may start an update and whether the link is encrypted is up to the application.
The STM32WB radio stack is updated by the application too: it takes the ST binary over its link and has FUS install it, while the bootloader never touches the stack.
The application should start without the stack too and keep taking updates over USB, as a power loss during the install leaves CPU2 without a stack: `WPAN_Start` then returns `ERR`, and the copy in staging lets the install finish.

A refused update leaves the previous version running, and `boot info` gives the reason in `result`:

- `installed`: new image installed, `none` when the start had no update
- `crc`: image damaged
- `chip`: image for another chip
- `origin`: image for another slot, e.g. built for `plain` and sent to a `key` bootloader
- `signature`: signed with another key, or not signed
- `epoch`: epoch below running image's

Beside it are `mode` (`plain` or `key`), `key` with the first bytes of the bootloader key and `rdp` with the lock level.

For tests the transfer goes over the console: `#define CMD_BOOT ON` in `main.h` adds the `boot` command, and on the PC `Shell.boot` of the `xaeian` package sends it:

```py
from xaeian.serial import Shell

with Shell("COM5", strip_echo=False) as sh:
  sh.boot("projects/myapp/myapp-1.2.0.bin") # .hex too
```

### Erasing

```sh
make erase  # erases bootloader too
make stack  # STM32WB radio stack, erases bootloader too
make flash  # bootloader and image back
```

Without a bootloader or with an empty slot the board starts no application, and outputs stay in their reset state: whether that is safe for the machine depends on the board design.

### Rebuilding bootloader

Needed after a change in Core files the bootloader runs: `hal/stm32/sys/boot.c`, flash, CRC and clock drivers, `startup.c`, Monocypher under `key`, and `wpan_wb.c` on WB.
`make dist` writes the same hex for the same code, so a hex unchanged in `git status` of Core means only the elf moved, with the source lines F5 steps through.
The bootloader project has `#define BOOT_KEY OFF` or `ON` in `main.h`, and Forge computes its code region:

```sh
opencplc boot/stm32g0  # bootloader project
make dist              # scr/boot_stm32g0.hex, with BOOT_KEY ON scr/boot_stm32g0_key.hex
```

Hex and elf land in `scr/` of Core, and applications pack the new bootloader on the next `make`.

## 🔒 Lock

`--lock` sets chip options over SWD:

- RDP1: debugger and programmer lose the flash, and taking the lock off erases all of it
- start from the ST ROM bootloader off, whatever the `BOOT0` pin says
- under a bootloader, write protection of its pages too, the mailbox page left out

The lock does not depend on the bootloader mode: it works under `plain`, under `key` and without a bootloader.
Nor does it check what the board holds, only the chip on the probe, as options differ between families.
`--program` decides what the board holds, which is why the factory runs both in one call.

| | `--lock`, RDP1 | `--lock 2`, RDP2 |
| --- | --- | --- |
| Debugger | cut off, `--lock 0` erases flash and gives it back | cut off for good |
| Bootloader write protection | hole in application lifts it through option bytes | frozen |
| Analysis of a failed unit at ST | possible | impossible |
| Radio stack on WB | `make stack` before locking | only FUS from application |

### Factory

```sh
opencplc myapp
opencplc --program projects/myapp/myapp-1.2.0.hex --lock     # full image of dist, then RDP1
opencplc --program projects/myapp/myapp-1.2.0.hex --lock -y  # production line, no prompt
```

Under `key` the image comes from `make dist`: a build of `make run` carries the development key, and a unit with it would take updates only from a developer's machine.
Once locked, `make flash`, F5 and `--program` no longer reach the flash, updates still go over the application link, and `boot info` shows `rdp:1`.
With several ST-Links `opencplc myapp -s <serial>` binds the right one to the project, otherwise `--lock` may meet a foreign chip and refuse.

On STM32WB the radio stack goes before the image, as `make stack` uses SWD and erases the bootloader:

```sh
make stack
opencplc --program projects/myapp/myapp-1.2.0.hex --lock
```

> [!NOTE]
> After locking cut power completely and switch it on again, as a chip locked with a debugger attached starts no application.
> A USB-UART adapter on the console pins can power the chip, so unplug it too, and on Nucleo move the power jumper to `CHG`.

### Lock for good

```sh
opencplc --program projects/myapp/myapp-1.2.0.hex --lock 2
```

> [!WARNING]
> RDP2 turns the programmer port off for good, for the manufacturer too.
> The unit can never be unlocked, reprogrammed or debugged again; only updates over the application link remain.

Forge asks a second time, even with `-y`.
RDP2 is only for a product whose customer or standard demands an unchangeable bootloader.

### Service

```sh
opencplc myapp
opencplc --lock 0  # removes lock, erasing whole flash
make flash         # bootloader and image back
```

After `make flash` cut power completely, as STM32G0 with erased flash starts from ROM until a full power cycle.
STM32WB takes the lock off through STM32CubeProgrammer, the one `make stack` needs, and the erase lasts a few seconds.
The whole flash goes with the lock, so analysis of a unit from the field relies on logs collected earlier.

## 🛡️ Security

The bootloader answers for **what** runs: signature, CRC and epoch, checked at every start.
The lock answers for whether the bootloader can be bypassed: programmer port, start from ROM and bootloader write protection.
The application answers for **who** sends an update and **how**: access to the link, authentication such as pairing, and encryption.

Encryption stays in the application, as the bootloader never changes, so neither key nor algorithm could ever be replaced there.
The signature covers the plain content, so the bootloader checks the decrypted result anyway, and staging lies in internal flash under the lock.
One encryption key per product, read out of one torn-down unit, opens every update file though, so the manufacturer decides whether and how to encrypt.

✅ guards, ❌ does not, ⚠️ partly.

| Threat | `plain` | `plain` + `--lock` | `key` | `key` + `--lock` |
| --- | :---: | :---: | :---: | :---: |
| Interrupted or damaged update | ✅ | ✅ | ✅ | ✅ |
| Power loss during install | ✅ | ✅ | ✅ | ✅ |
| Update for another device | ✅ | ✅ | ✅ | ✅ |
| Foreign firmware over update link | ❌ | ❌ | ✅ | ✅ |
| Development build as update of a production unit | ❌ | ❌ | ✅ | ✅ |
| Return to an old version with a known hole | ❌ | ❌ | ✅¹ | ✅¹ |
| Foreign firmware flashed with a programmer | ❌ | ✅ | ❌ | ✅ |
| Copying firmware off device | ❌ | ✅ | ❌ | ✅ |
| Start from ST ROM bootloader (pin `BOOT0`) | ❌ | ✅ | ❌ | ✅ |
| Bootloader overwritten by an application bug | ❌ | ✅ | ❌ | ✅ |
| Lasting takeover through hole in running application | ❌ | ❌ | ❌ | ⚠️² |
| Reading firmware content from an update file³ | ❌ | ❌ | ❌ | ❌ |
| Hardware attacks: power glitching, power analysis | ❌ | ❌ | ❌ | ❌ |

¹ When the hole was closed by a release with a raised epoch.
² A hole that runs foreign code can change option bytes and lift bootloader write protection; only RDP2 freezes them.
³ Confidentiality is the application's job.

A project without a bootloader, locked, is guarded against the programmer, copying and the start from ROM, and has no updates at all.

Left out on purpose:

- **bootloader update in field**, as an interrupted swap would leave a dead device, so a bootloader bug is fixed in service,
- **key revocation**, as the key sits in an unchangeable bootloader, so a separate key per product limits the damage,
- **hardware secure area**, as STM32G0 has one and STM32WB does not, and one path for both families is easier to verify,
- **automatic lock at first start**, as every release test on a board would end in erasing flash,
- **watchdog in bootloader**, as it clashes with sleep modes, so the application starts it itself.

The EU Cyber Resilience Act (CRA), IEC 62443-4-2 for automation components and, for radio devices, the RED directive with EN 18031 expect authentic firmware, secure updates and closed service interfaces, among others:

| Expectation | Ready | With manufacturer |
| --- | --- | --- |
| Authentic firmware only | signature checked at every start | guarding product key |
| Secure updates | signature, power-loss safety, result report | who may start an update, releasing fixes |
| No rollback | epoch | raising epoch with every fix |
| Closed service interfaces | `--lock`: programmer port and `BOOT0` | locking every unit before shipping |
| Secure factory configuration | `key` and `--lock`, one command each | `key` + `--lock` for the product |
| Firmware confidentiality | none in bootloader | encryption in application, if required |
| Vulnerability handling | outside bootloader | reports, fixes, informing customers |

> [!NOTE]
> This document is no declaration of conformity.
> It shows where the mechanisms help; which regulations cover a product is up to the manufacturer.
