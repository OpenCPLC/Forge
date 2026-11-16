# tests/test_lint_build.py

"""The rules of Forge on what `arm-none-eabi-gcc` really writes: graph, map, symbols and image."""

import os
import pytest
from xaeian import DIR, FILE, PATH, YAML, file_context
from xaeian.cmd import run, which
from opencplc.lint.command import forge_check, stack_line
from opencplc.utils import tools

ARM_BIN = tools.bin_dir("arm-gcc")
GCC = which("arm-none-eabi-gcc", f"{ARM_BIN}/arm-none-eabi-gcc")
MCU = ["-mcpu=cortex-m4", "-mthumb"]

VRTS_H = """#ifndef VRTS_H_
#define VRTS_H_
#define stack(name, size) static unsigned int name[size]
#define thread(fn, stack_name) vrts_thread(&fn, stack_name)
void let(void);
void delay(unsigned int ms);
void sleep(unsigned int ms);
void vrts_thread(void (*fn)(void), unsigned int *stack);
#endif
"""
VRTS_C = """#include "vrts.h"
volatile unsigned int ticks;
void let(void) { ticks++; }
void delay(unsigned int ms) { while(ms--) let(); }
void sleep(unsigned int ms) { while(ms--) ticks++; }
void vrts_thread(void (*fn)(void), unsigned int *stack) { if(stack) fn(); }
__attribute__((weak)) void TIM2_IRQHandler(void) { ticks = 0; }
__attribute__((weak)) void USART2_IRQHandler(void) { delay(1); }
"""
MAIN_C = """#include "vrts.h"
stack(stack_loop, 64);
static void loop(void)
{
  while(1) sleep(10);
}
void TIM2_IRQHandler(void) { let(); }
#if 0
  thread(off, stack_off);
#endif
int main(void)
{
  thread(loop, stack_loop);
  return 0;
}
"""
ROLES = {
  "yield": ["let", "delay"], "hold": ["sleep"],
  "heap": {"any": ["heap_new", "heap_clear"], "new": "heap_new", "clear": "heap_clear"},
  "thread": "vrts_thread",
  "irq": {"handler": ["IRQHandler", "_Handler"], "start": ["IRQ_Enable*"], "field": ["Callback"]},
  "frame": {"cortex-m4": 17},
  "log": ["_LOG_*"], "panic": ["panic"], "status": "status_t", "load": ["*_Load"],
}

@pytest.fixture()
def built(tmp_path, monkeypatch):
  """A Core and a project compiled as a chip build compiles them, linked with a map."""
  monkeypatch.setenv("PATH", ARM_BIN + os.pathsep + os.environ.get("PATH", ""))
  root = PATH.normalize(str(tmp_path)) # with `/`, as make passes paths
  FILE.save(f"{root}/core/vrts.h", VRTS_H)
  FILE.save(f"{root}/core/vrts.c", VRTS_C)
  YAML.save(f"{root}/core/lint.yaml", {"roles": ROLES})
  FILE.save(f"{root}/project/main.c", MAIN_C)
  objects = []
  for tree, source in (("opencplc", "core/vrts.c"), ("project", "project/main.c")):
    target = f"{root}/build/{tree}/{PATH.stem(source)}.o"
    DIR.ensure(target, is_file=True)
    run([GCC, *MCU, "-Og", "-c", "-MMD", "-MP", "-fcallgraph-info=su", f"-I{root}/core",
      f"{root}/{source}", "-o", target], check=True)
    objects.append(target)
  run([GCC, *MCU, "-nostdlib", "-nostartfiles", "-Wl,-e,main", f"-Wl,-Map={root}/build/app.map",
    *objects, "-o", f"{root}/build/app.elf"], check=True)
  with file_context(root_path=root):
    yield f"{root}/build/app.elf"

@pytest.mark.skipif(GCC is None, reason="arm-none-eabi-gcc required")
def rules_read_what_gcc_writes(built):
  check = forge_check(built, "core", "project", "cortex-m4")
  assert "irq-yield" in check.ran and any(path.endswith("project/main.c") for path in check.texts)
  assert sorted((f.rule, f.path, f.function) for f in check.found) == [
    ("irq-yield", "core/vrts.c", "USART2_IRQHandler"), # weak, and no other definition
    ("irq-yield", "project/main.c", "TIM2_IRQHandler"), # strong, the weak one gives way
    ("thread-hold", "project/main.c", "loop"),
  ]
  assert [(s.thread, s.frame, s.size) for s in check.stacks] == [("loop", 68, 256)]
  assert "/ 256B" in stack_line(check.stacks[0])
  # `loop` runs in a thread, `main` before them, the handlers in interrupts.
  # A static function is keyed by its file.
  assert {"project/main.c:loop", "main"} <= check.thread
  assert {"TIM2_IRQHandler", "let"} <= check.irq
