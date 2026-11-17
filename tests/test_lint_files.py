# tests/test_lint_files.py

"""Rules of files: what a header may hold, where `extern` stands, which header comes first."""

from xaeian import FILE, file_context
import pytest
from opencplc.lint.rules import Trees, check_files, check_includes, check_config
from opencplc.lint.sources import (
  build_files, defines_object, top_level, code, call_args, assigned,
)

@pytest.fixture(autouse=True)
def workspace(tmp_path):
  """Paths of a test count from its own folder, as the paths of a build from the workspace."""
  with file_context(root_path=str(tmp_path)):
    yield

HEADER = """// lib/mod.h

#ifndef MOD_H_
#define MOD_H_

// int fake_in_a_comment;
#define TEXT "int fake_in_a_string;"
extern int shared;
typedef struct { int x; } point_t;
struct later;
enum mode { MODE_A, MODE_B };
static inline int twice(int x) { return 2 * x; }
void run(int count);
int counter;
static const unsigned char TABLE[2] = { 1, 2 };
struct later instance;
struct { int y; } anonymous;

#endif
"""

def header_holds_declarations_and_never_storage():
  found = check_files({"lib/mod.h": HEADER})
  assert [(f.rule, f.line) for f in found] == [
    ("header-object", 14), ("header-object", 15), ("header-object", 16), ("header-object", 17)]
  assert found[0].path == "lib/mod.h"

def declarations_tell_storage_from_types_and_prototypes():
  assert defines_object("static uint8_t buffer[64] = { 0 }")
  assert defines_object("const char *name")
  assert not defines_object("extern uint8_t buffer[64]")
  assert not defines_object("typedef struct { int a; } type_t")
  assert not defines_object("int sum(int a, int b)")
  assert not defines_object("struct tag")
  assert not defines_object("enum tag { A, B }")
  assert not defines_object("__PACKED_STRUCT T_UINT16_WRITE { uint16_t v; }")
  assert not defines_object("struct __packed__ T_UINT32 { uint32_t v; }")
  assert defines_object("static uint8_t buffer[8] __attribute__((aligned(8)))")

def function_bodies_are_no_file_scope():
  text = code("int f(void) __attribute__((section(\".x\")))\n{\n  static int inside = 0;\n"
    "  return inside;\n}\nint outside;\n")
  declarations, functions = top_level(text)
  assert [statement.strip() for _, statement in declarations] == ["int outside"]
  assert functions == [("f", 2, 5)]

def arguments_of_a_call_split_at_its_own_commas():
  text = code("  IRQ_EnableI2C(i2c->reg, prio(1, 2), (IRQ_Handler_t)event, error, i2c);\n")
  assert call_args(text, 1, 3) == [
    "i2c->reg", "prio(1, 2)", "(IRQ_Handler_t)event", "error", "i2c",
  ]

def no_arguments_come_from_a_place_where_no_call_is_written():
  # The place gcc gives a call a macro expands into is the macro, with no parentheses after it
  assert call_args(code("#define START thread(loop, stack_loop)\n  START;\n"), 2, 3) == []
  assert call_args(code("  run(1);\n"), 9, 1) == []

def a_function_given_to_a_field_is_read_past_its_cast():
  text = code("  tim.Callback = handler;\n  exti->RiseHandler = (EXTI_Handler_t)trigger;\n"
    "  uart->tim->Callback = (void (*)(void *))(void (*)(void))BUFF_Break;\n"
    "  static TIM_t tim = { .Callback = &tick, .prescaler = 4 };\n"
    "  if(tim.Callback == other) return;\n")
  assert assigned(text, ["Callback", "RiseHandler"]) == [
    "handler", "trigger", "BUFF_Break", "tick"]

def a_header_is_guarded_by_ifndef_and_never_by_pragma_once():
  texts = {
    "a.h": "int sum(int a, int b);\n",
    "b.h": "#pragma once\nint sum(int a, int b);\n",
    "c.h": "// c.h\n\n#ifndef C_H_\n#define C_H_\nint sum(int a, int b);\n#endif\n",
  }
  assert [(f.rule, f.path) for f in check_files(texts)] == [
    ("header-guard", "a.h"), ("header-guard", "b.h")]

def extern_belongs_to_headers():
  text = ('#include "app.h"\n\nextern uint32_t _estack;\n'
    "int run(void) { extern int late; return late; }\n")
  FILE.save("app.h", "#ifndef APP_H_\n#define APP_H_\n#endif\n")
  found = check_files({"app.c": text})
  assert [(f.rule, f.line) for f in found] == [("extern-in-c", 3)]

def source_starts_with_the_header_it_implements():
  sources = {
    "dma_g0.c": '#include "dma.h"\n',
    "uart.c": '#include <stdint.h>\n#include "uart.h"\n',
    "main.c": '#include <vrts.h>\n#include "main.h"\n',
  }
  # `main.h` is the configuration of a project, which every header pulls in, so `main.c` is free
  for name in ("dma.h", "dma_g0.h", "uart.h", "main.h"): FILE.save(name, "")
  found = check_files(sources)
  assert [(f.rule, f.path, f.line) for f in found] == [("own-header-first", "uart.c", 1)]

def an_include_marks_the_tree_of_its_file():
  # A model in Core keeps the name of a chip header, and a fake in `.tests` that of a module
  for path in (
    "core/lib/xmath.h", "core/lib/uart.h", "core/inc/stm32g0xx.h", "core/host/stm32g0xx.h",
    "app/main.h", "app/app.h", "app/.tests/uart.h",
  ):
    FILE.save(path, "")
  trees = Trees("core", "app", [("core", "inc/*")])
  texts = {
    "core/lib/uart.c": '#include "uart.h"\n#include <xmath.h>\n#include "stm32g0xx.h"\n'
      '#include "main.h"\n#include <stdint.h>\n',
    "app/app.c": '#include "app.h"\n#include "uart.h"\n#include <xmath.h>\n#include <main.h>\n'
      '#include "stdint.h"\n#include <stm32g0xx.h>\n// #include "stdio.h"\n',
  }
  found = check_includes(texts, trees)
  assert [(f.path, f.line) for f in found] == [
    ("core/lib/uart.c", 2), ("core/lib/uart.c", 3),
    ("app/app.c", 2), ("app/app.c", 4), ("app/app.c", 5),
  ]
  assert found[0].message == '`xmath.h` lies in Core, as this file does, so `"xmath.h"`'
  assert found[1].message == "`stm32g0xx.h` is code of others, so `<stm32g0xx.h>`"

def a_project_inside_core_is_a_tree_of_its_own():
  for path in ("core/lib/uart.h", "core/.tests/wb55/main.h", "core/.tests/wb55/pins.h"):
    FILE.save(path, "")
  trees = Trees("core", "core/.tests/wb55", [])
  texts = {"core/.tests/wb55/main.c": '#include <uart.h>\n#include "pins.h"\n#include "uart.h"\n'}
  assert [f.line for f in check_includes(texts, trees)] == [3]

def a_knob_needs_main_h_above_it():
  # `dbg.h` reaches `main.h` through `uart.h`, while `late.h` includes it below its knob
  texts = {
    "core/uart.h": '#include "main.h"\n#ifndef UART_SIZE\n  #define UART_SIZE 64\n#endif\n',
    "core/dbg.h": '#include "uart.h"\n#ifndef DBG_SIZE\n  #define DBG_SIZE 64\n#endif\n',
    "core/late.h": '#ifndef LATE_H_\n#define LATE_H_\n#ifndef LATE_SIZE\n  // bytes\n'
      '  #define LATE_SIZE 8\n#endif\n#include "main.h"\n#endif\n',
    "app/main.h": "#ifndef MAIN_H_\n#define MAIN_H_\n#endif\n#define UART_SIZE 128\n",
  }
  found = check_config(texts, texts, "app/main.h")
  assert [(f.rule, f.path, f.line, f.function) for f in found] == [
    ("config-order", "core/late.h", 5, "LATE_SIZE"),
  ]

def a_setting_of_main_h_reaches_a_file_reading_it():
  texts = {
    "core/uart.h": '#include "main.h"\n#ifndef UART_SIZE\n  #define UART_SIZE 64\n#endif\n'
      "#define LOG_FORMAT 1\n",
    "app/main.h": "#ifndef MAIN_H_\n#define MAIN_H_\n#define PRO_CHIP_X\n#endif\n"
      "#define UART_SIZE 128\n#define UART_SIZ 256\n#define LOG_FORMAT 2\n#define BLINK_ms 500\n"
      "#define HSE_VALUE 8000000\n",
    "app/main.c": '#include "main.h"\nint blink = BLINK_ms;\n',
  }
  # Code of others reads a setting too, while no rule looks inside it
  every = texts | {"core/ext/system.c": "#if !defined(HSE_VALUE)\n  #define HSE_VALUE 1\n#endif\n"}
  found = check_config(texts, every, "app/main.h")
  assert [(f.rule, f.line, f.function) for f in found] == [
    ("config-unread", 6, "UART_SIZ"),
    ("config-unread", 7, "LOG_FORMAT"),
  ]
  assert "core/uart.h:5" in found[1].message

def files_of_a_build_come_from_its_dependency_files():
  FILE.save("build/project/main.d",
    "build/project/main.o: projects/app/main.c projects/app/main.h \\\n"
    " opencplc/lib/sh/log.h\nprojects/app/main.h:\nopencplc/lib/sh/log.h:\n")
  found = build_files(["build/project/main.d", "build/project/gone.d"])
  assert found == ["projects/app/main.c", "projects/app/main.h", "opencplc/lib/sh/log.h"]
