# 🧪 Tests

Tests run on the computer, in an STM32 project too, and check the firmware code itself, not a copy of it.
`make test` builds every program in `.tests/` and runs it, and one workflow file does the same on GitHub on every push.
Forge basics are in the [readme](readme.md).

## Test program

Every `.c` file directly in `.tests/` at the top of a project is one test program, by default `test_<module>.c` after the module it checks.
`.tests/` never lies deeper, so it is plain that it is not part of the firmware.

```text
myapp/
├─ main.c
├─ main.h
├─ ctrl/ramp.c
└─ .tests/
   ├─ test_ramp.c  # test program of module ramp
   ├─ fake/link.c  # fake of module link, not a program
   └─ data/        # fixed inputs and expected values, committed
```

A test includes the module it checks by name, `#include "ramp.c"`, since modules share one flat namespace, as in firmware.
So it runs the firmware code itself, `static` functions included.
Only what it includes compiles, so registers elsewhere in the project never stand in the way.
`main()` comes from the harness, so `main.c` never enters a test.

No program bears a module's name: quotes look beside the including file first, and `.tests/ramp.c` would stand in for the module in every test.
The `test_` prefix is the simple way out, any name no module has works as well.

```c
// .tests/test_ramp.c

#include "test.h"
#include "ramp.c"

static void ramp_starts_at_zero(void)
{
  RAMP_t ramp = { .target = 100, .step = 30 };
  TEST_Equal(ramp.value, 0, "value before the first step");
}

static void ramp_stops_at_target(void)
{
  RAMP_t ramp = { .target = 100, .step = 30 };
  for(int i = 0; i < 5; i++) RAMP_Step(&ramp);
  TEST_Equal(ramp.value, 100, "no overshoot");
}

void TEST_Cases(void)
{
  TEST(ramp_starts_at_zero);
  TEST(ramp_stops_at_target);
}
```

- `TEST_Cases()` lists the cases in run order, `TEST(name)` each.
- `TEST_Check(cond)` or `TEST_Check(cond, fmt, ...)` is a verdict, while `TEST_Equal`, `TEST_Near` and `TEST_Bytes` show on a miss the expression as written, its value and the expected one.
- `TEST_Logged(text)`: the firmware logged a line holding `text` since the case began or since the previous `TEST_Logged`.
- `TEST_Run(ms)` makes `ms` steps of virtual time, each a tick forward and every task due by then.

## Running

```sh
make test              # every program in `.tests/`
make test T=test_ramp  # only `.tests/test_ramp.c`, with its output
```

Each program runs in a clean folder of its own and gets a line with its checks passed out of all, and the run ends with a total:

```text
INF test_frame 12/12 OK
INF test_ramp 2/2 OK
INF Test programs 2/2, checks 14/14 in 0.2s OK
```

A failed program shows below its line its output, as it printed it.
A miss names its file and line and the expression with its value, ends its case, and the next case runs:

```text
INF test_frame 12/12 OK
ERR test_ramp 1/2
OK ramp_starts_at_zero
ERR projects/myapp/.tests/test_ramp.c:16 ramp_stops_at_target: no overshoot
  ramp.value is 150, expected 100
ERR Test programs 1/2, checks 13/14 in 0.5s
```

With `T=` the program shows its output even when it passes.
A program that ends early fails, `exit(0)` of a firmware reset too, and one that hangs is cut after a minute.
`make test` goes through all programs and fails when any of them did.
A new file in `.tests/` needs no reload.

## Rules

- Waiting moves the clock: `delay()` and `timeout()` step virtual time, so a test of a timeout takes no time at all.
  `sleep()` holds the core, so time passes and no task runs.
- A module the tested code calls comes in the same way, or as a fake of the whole module from a folder in `.tests/`, `#include "fake/link.c"`, since a fake bears the name of its module.
  For a fake of part of a Core module the linker would pull the original from the archive and clash with the rest.
- Fixed inputs and expected values, such as a recorded frame or a signature made by Forge, lie in `data/` and come by its folder too, `#include "data/forge.h"`.
  They are written by hand or by a script beside them and committed, while a run never writes there: what a program saves stays in its clean folder under `build/`.
- A `#define` before `#include` may tune the module it includes, such as `LOG_LEVEL`.
  A size or type the rest of Core shares, such as `BUFF_MSG_LIMIT`, belongs in `main.h`, or the test and Core quietly disagree.
- Core comes compiled for the test from `hal/host`, `lib` and `tst`, and their modules come by name.
  A module from `plc/`, `brd/`, `dvr/` or `hal/stm32*` comes by its path from Core root, such as `#include "hal/stm32/sys/boot.c"`.
- An STM32 project with tests gets MinGW beside `arm-gcc`.

## GitHub

A project repository runs `make test` and `make` on every push with one file:

```yaml
# .github/workflows/test.yml
name: Test
on: [push, pull_request]
jobs:
  test:
    uses: OpenCPLC/Forge/.github/workflows/project.yml@0.5.0
```

It does what you do in a fresh workspace, for every project in the repository, on Windows with the tools Forge installs.
Core comes from `PRO_FRAMEWORK`, as on your computer.
The tag pins the Forge release, so a new Forge never changes the result on its own.

> [!NOTE]
> In a private repository runs use the free minutes of your plan, and a Windows minute costs more than a Linux one.

## Core

Core tests itself the same way, from `.tests/` at its top:

```text
opencplc/develop/.tests/
├─ test_boot.c   # test program of module boot
├─ test_cron.c
├─ data/forge.h  # key and signature made by Forge, from forge.py
├─ g081/         # project: compile test of STM32G081
├─ g0c1/
├─ wb55/
└─ uno/          # project: PLC layer on the Uno board
```

A `.c` file directly in `.tests/` is a test program, a folder with `main.h` is a project, and any other folder helps the tests, such as `fake/` and `data/`.
Core keeps no fakes, since `hal/host` is its model of the chip: the flash there erases, programs and loses power as the chip does, and a test cuts that power with `FlashBudget`.

```sh
opencplc opencplc/develop              # Core itself
make test                              # its test programs
opencplc opencplc/develop/.tests/g081  # compile test
make                                   # builds it
```

GitHub runs `make` in every project of `.tests/` and `make test` of Core on every push and pull request.
A new module or a bug fix comes with the test that checks it, and a new chip or board with its project in `.tests/`.
