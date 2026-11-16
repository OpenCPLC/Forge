# tests/test_lint_graph.py

"""Rules of VRTS and the stack, on call graphs as `-fcallgraph-info=su` writes them."""

from xaeian import file_context
import pytest
from opencplc.lint.graph import Graph, read, settle_weak, INDIRECT
from opencplc.lint.rules import (
  Roles, Thread, find_threads, hidden_calls, check_graph, check_stacks, deepest, contexts,
)
from conftest import ci_node as node, ci_edge as edge, ci_graph as graph_of

ROLES = Roles(
  {"let", "delay", "delay_until", "timeout"}, {"sleep", "sleep_until"},
  {"heap_alloc", "heap_free", "heap_new", "heap_clear"}, "heap_new", "heap_clear",
  "vrts_thread", ["IRQHandler", "_Handler"], ["IRQ_Enable*"], ["Callback", "FallHandler"],
  {"cortex-m4": 51}, [], ["_LOG_*", "DBG_*"], {"panic", "vrts_panic"}, "status_t", ["*_Load"],
)
LOOP = Thread("loop", "stack_loop", "a.c", 1)

@pytest.fixture(autouse=True)
def workspace(tmp_path):
  """Paths of a test count from its own folder, as the paths of a build from the workspace."""
  with file_context(root_path=str(tmp_path)):
    yield

def graph_keeps_frames_and_tells_statics_apart():
  graph = Graph()
  source = read("\n".join(['graph: { title: "b.c"',
    node("b.c:helper", "b.c:3:13", "16 bytes (static)"),
    node("helper", "c.c:5:6", "32 bytes (dynamic,bounded)"),
    node("grow", "c.c:9:6", "8 bytes (dynamic)"),
    node("memcpy", "string.h:1:7", None), "}"]), graph)
  assert source == "b.c"
  assert graph.title("helper", "b.c") == "b.c:helper"
  assert graph.title("helper", "c.c") == "helper"
  assert graph.functions["helper"].frame == 32 # a bounded frame gives its bound
  assert graph.functions["grow"].frame is None
  assert "memcpy" not in graph.functions # declared, so compiled elsewhere

def a_weak_definition_gives_way_or_takes_its_global_name():
  graph = graph_of(
    node("vrts.c:vrts_panic", "vrts.c:9:6"), node("vrts_panic", "sys.c:20:6"),
    node("startup.c:USART1_IRQHandler", "startup.c:30:6"), node("heap_alloc", "heap.c:40:7"),
    edge("vrts.c:vrts_panic", "halt", "vrts.c:10:3"),
    edge("heap_alloc", "vrts.c:vrts_panic", "heap.c:50:3"),
    edge("startup.c:USART1_IRQHandler", INDIRECT, "startup.c:30:40"),
  )
  settle_weak(graph, {"vrts.c:vrts_panic", "startup.c:USART1_IRQHandler"})
  assert graph.functions["vrts_panic"].path == "sys.c" # the strong one the linker keeps
  assert "vrts.c:vrts_panic" not in graph.functions and "vrts.c:vrts_panic" not in graph.calls
  assert graph.calls["heap_alloc"] == [("vrts_panic", "heap.c:50:3")]
  assert graph.calls["USART1_IRQHandler"] == [(INDIRECT, "startup.c:30:40")]

def interrupt_reaching_a_yield_is_found_with_its_chain():
  graph = graph_of(
    node("USART1_IRQHandler", "irq.c:10:6"), node("uart_irq", "uart.c:20:6"),
    edge("USART1_IRQHandler", "uart_irq", "irq.c:11:3"), edge("uart_irq", "let", "uart.c:22:5"),
  )
  found = check_graph(graph, {}, [], ROLES)
  assert [(f.rule, f.path, f.line, f.function) for f in found] == [
    ("irq-yield", "irq.c", 10, "USART1_IRQHandler")]
  assert "`let` (uart.c:22)" in found[0].message and "CWE-479" in found[0].refs

def interrupts_a_driver_registers_are_roots_too():
  texts = {
    "u.c": "void init(void)\n{\n  IRQ_EnableUART(reg, 2, (IRQ_Handler_t)uart_irq, &uart);\n}\n",
    "g.c": "void setup(void)\n{\n  button.FallHandler = on_edge;\n}\n",
  }
  graph = graph_of(
    node("init", "u.c:1:6"), node("u.c:uart_irq", "u.c:9:13"), node("setup", "g.c:1:6"),
    node("on_edge", "g.c:9:6"),
    edge("init", "IRQ_EnableUART", "u.c:3:3"), edge("u.c:uart_irq", "delay", "u.c:11:3"),
    edge("on_edge", "timeout", "g.c:11:3"),
  )
  found = check_graph(graph, texts, [], ROLES)
  assert sorted((f.rule, f.function) for f in found) == [
    ("irq-yield", "on_edge"), ("irq-yield", "uart_irq")]

def interrupt_touching_the_heap_races_the_threads():
  graph = graph_of(
    node("I2C1_IRQHandler", "irq.c:10:6"), node("i2c_done", "i2c.c:15:13"),
    edge("I2C1_IRQHandler", "i2c_done", "irq.c:11:3"), edge("i2c_done", "heap_free", "i2c.c:20:3"),
  )
  found = check_graph(graph, {}, [], ROLES)
  assert [(f.rule, f.function) for f in found] == [("irq-heap", "I2C1_IRQHandler")]
  assert "`heap_free` (i2c.c:20)" in found[0].message and "CWE-364" in found[0].refs

def the_start_of_the_program_is_no_interrupt():
  graph = graph_of(node("Reset_Handler", "startup.c:5:6"),
    edge("Reset_Handler", "delay", "s.c:7:3"))
  assert check_graph(graph, {}, [], ROLES) == []

def vrts_itself_is_not_searched():
  """`delay` may sleep inside when VRTS is off, and that is not the thread holding the core."""
  graph = graph_of(
    node("loop", "a.c:5:6"), node("delay", "vrts.c:40:6"),
    edge("loop", "delay", "a.c:7:5"), edge("delay", "sleep", "vrts.c:44:5"),
  )
  assert check_graph(graph, {}, [LOOP], ROLES) == []

def thread_reaching_sleep_keeps_the_core():
  graph = graph_of(
    node("loop", "a.c:5:6"), node("calibrate", "a.c:20:13"),
    edge("loop", "calibrate", "a.c:7:5"), edge("calibrate", "sleep", "a.c:22:3"),
  )
  found = check_graph(graph, {}, [LOOP], ROLES)
  assert [(f.rule, f.function) for f in found] == [("thread-hold", "loop")]

THREADS_C = "void master(void)\n{\n  read_bits();\n}\nvoid debug(void)\n{\n  heap_clear();\n}\n"
MODBUS_C = "static int read_bits(void)\n{\n  heap_new(4);\n  heap_clear();\n  return 0;\n}\n"
MASTER = Thread("master", "stack_master", "a.c", 1)
DEBUG = Thread("debug", "stack_debug", "a.c", 2)

def library_clearing_the_arena_is_found_and_the_thread_is_not():
  graph = graph_of(
    node("master", "a.c:1:6"), node("debug", "a.c:5:6"), node("mb.c:read_bits", "mb.c:1:12"),
    edge("master", "mb.c:read_bits", "a.c:3:3"), edge("mb.c:read_bits", "heap_new", "mb.c:3:3"),
    edge("mb.c:read_bits", "heap_clear", "mb.c:4:3"), edge("debug", "heap_clear", "a.c:7:3"),
  )
  found = check_graph(graph, {"a.c": THREADS_C, "mb.c": MODBUS_C}, [MASTER, DEBUG], ROLES)
  # The thread leans on the library to clear, so it breaks the other half of the rule
  assert [(f.rule, f.path, f.line, f.col, f.function) for f in found] == [
    ("heap-owner", "mb.c", 4, 3, "read_bits"), ("heap-cleared", "a.c", 1, 1, "master")]

def an_inlined_helper_still_counts_by_its_source():
  """`-Os` puts `read_bits` inside `master`, and the call to `heap_clear` stays in `read_bits`."""
  graph = graph_of(
    node("master", "a.c:1:6"), node("debug", "a.c:5:6"),
    edge("master", "heap_new", "mb.c:3:3"), edge("master", "heap_clear", "mb.c:4:3"),
    edge("debug", "heap_clear", "a.c:7:3"),
  )
  found = check_graph(graph, {"a.c": THREADS_C, "mb.c": MODBUS_C}, [MASTER, DEBUG], ROLES)
  assert [(f.rule, f.function) for f in found] == [
    ("heap-owner", "read_bits"), ("heap-cleared", "master")]

def thread_taking_blocks_clears_them_itself():
  texts = {"a.c": "void loop(void)\n{\n  format();\n  heap_clear();\n}\n"}
  taking = (node("loop", "a.c:1:6"), node("format", "s.c:9:7"),
    edge("loop", "format", "a.c:3:3"), edge("format", "heap_new", "s.c:11:3"))
  found = check_graph(graph_of(*taking), texts, [LOOP], ROLES)
  assert [f.rule for f in found] == ["heap-cleared"]
  clearing = graph_of(*taking, edge("loop", "heap_clear", "a.c:4:3"))
  assert check_graph(clearing, texts, [LOOP], ROLES) == []

def each_cycle_is_reported_once_at_its_first_function():
  graph = graph_of(
    node("decode", "pb.c:40:13"), node("field", "pb.c:20:13"), node("walk", "t.c:3:6"),
    edge("decode", "field", "pb.c:42:5"), edge("field", "decode", "pb.c:22:5"),
    edge("walk", "walk", "t.c:5:5"),
  )
  found = check_graph(graph, {}, [], ROLES)
  assert sorted((f.path, f.line) for f in found if f.rule == "recursion") == [
    ("pb.c", 20), ("t.c", 3)]

def stack_adds_frames_on_the_deepest_path_and_names_what_it_cannot_see():
  graph = graph_of(
    node("loop", "a.c:5:6", "24 bytes (static)"), node("parse", "a.c:9:6", "100 bytes (static)"),
    node("leaf", "a.c:20:6", "40 bytes (static)"), node("grow", "a.c:30:6", "16 bytes (dynamic)"),
    edge("loop", "parse", "a.c:6:3"), edge("parse", "leaf", "a.c:10:3"),
    edge("loop", "grow", "a.c:7:3"), edge("parse", INDIRECT, "a.c:11:3"),
    edge("leaf", "memcpy", "a.c:21:3"),
  )
  depth, holes = deepest(graph, "loop")
  assert depth == 24 + 100 + 40
  assert holes == {"pointer", "dynamic", "library"}
  stacks, found = check_stacks(graph, [LOOP], {"stack_loop": 256}, 204)
  assert stacks[0].size == 256 and [f.rule for f in found] == ["stack-fit"]
  assert "needs at least 368B" in found[0].message

def threads_are_the_calls_gcc_compiled():
  """A `thread()` an `#if` leaves out has no call in the graph, so it is no thread."""
  text = ("static void loop(void) { }\n#if 0\n  thread(off, stack_off);\n#endif\n"
    "int main(void)\n{\n  thread(DBG_Loop, stack_dbg);\n"
    "  vrts_thread(&loop, (uint32_t *)stack_loop, array_len(stack_loop));\n}\n")
  graph = graph_of(
    node("a.c:loop", "a.c:1:13"), node("DBG_Loop", "dbg.c:115:6"), node("main", "a.c:5:5"),
    edge("main", "vrts_thread", "a.c:7:3"), edge("main", "vrts_thread", "a.c:8:3"),
  )
  found = find_threads(graph, {"a.c": text}, ROLES)
  assert [(t.title, t.stack, t.line) for t in found] == [
    ("DBG_Loop", "stack_dbg", 7), ("a.c:loop", "stack_loop", 8)]

def a_thread_started_inside_a_macro_is_named_as_hidden():
  text = ("#define START thread(loop, stack_loop)\nstatic void loop(void) { }\n"
    "int main(void)\n{\n  START;\n}\n")
  graph = graph_of(node("a.c:loop", "a.c:2:13"), node("main", "a.c:3:5"),
    edge("main", "vrts_thread", "a.c:5:3"))
  assert find_threads(graph, {"a.c": text}, ROLES) == []
  assert hidden_calls(graph, {"a.c": text}, ROLES) == ["a.c:5"]

def an_interrupt_never_logs_except_on_its_way_to_a_panic():
  """A panic ends the program, so the log it writes races no thread any more."""
  graph = graph_of(
    node("TIM2_IRQHandler", "irq.c:1:6"), node("SysTick_Handler", "irq.c:5:6"),
    node("vrts_panic", "sys.c:9:6"),
    edge("TIM2_IRQHandler", "_LOG_Info", "irq.c:2:3"),
    edge("SysTick_Handler", "vrts_panic", "irq.c:6:3"),
    edge("vrts_panic", "_LOG_Panic", "sys.c:10:3"),
  )
  found = check_graph(graph, {}, [], ROLES)
  assert [(f.rule, f.function) for f in found] == [("irq-log", "TIM2_IRQHandler")]
  assert "`_LOG_Info` (irq.c:2)" in found[0].message

def the_heap_is_off_limits_to_the_project_once_turned_on():
  graph = graph_of(
    node("loop", "app/main.c:3:6"), node("CORE_Init", "core/lib.c:1:6"),
    edge("loop", "malloc", "app/main.c:4:3"), edge("CORE_Init", "heap_alloc", "core/lib.c:2:3"),
  )
  assert check_graph(graph, {}, [], ROLES) == []
  found = check_graph(graph, {}, [], ROLES, {"no-heap"}, "app")
  assert [(f.rule, f.path, f.line, f.function) for f in found] == [
    ("no-heap", "app/main.c", 4, "loop")]

def a_margin_keeps_a_quarter_of_each_stack_free_once_turned_on():
  thread = Thread("loop", "stack_loop", "a.c", 1)
  for frame, left in (("200 bytes (static)", ["stack-margin"]), ("180 bytes (static)", [])):
    graph = graph_of(node("loop", "a.c:1:6", frame))
    assert check_stacks(graph, [thread], {"stack_loop": 256}, 0)[1] == []
    assert [f.rule for f in check_stacks(graph, [thread], {"stack_loop": 256}, 0, True)[1]] == left

def interrupts_and_threads_share_what_both_call():
  graph = graph_of(
    node("TIM2_IRQHandler", "irq.c:1:6"), node("tick", "t.c:1:6"), node("loop", "a.c:1:6"),
    node("main", "a.c:9:5"), node("setup", "a.c:5:6"),
    edge("TIM2_IRQHandler", "tick", "irq.c:2:3"), edge("loop", "tick", "a.c:2:3"),
    edge("main", "setup", "a.c:10:3"),
  )
  irq, thread = contexts(graph, {}, [Thread("loop", "stack_loop", "a.c", 1)], ROLES)
  assert {"TIM2_IRQHandler", "tick"} <= irq and "setup" not in irq
  assert {"loop", "tick", "main", "setup"} <= thread
