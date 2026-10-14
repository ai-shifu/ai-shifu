"""Compute and render bounded abstract programs, never model-authored result rows.

This explicit no-IO integer language describes generated illustrations. It does
not parse arbitrary code, grade learner submissions or validate free-form prose.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Literal

if TYPE_CHECKING:
    from pydantic_ai.messages import ToolCallPart

from pydantic import BaseModel, ConfigDict, Field

_VALUE_LIMIT = 1_000_000_000
# With at most 8 registers, 16 data cells and 32 instructions, 32 full rows
# (including maximum-width negative integers/names) fit the 16 KiB artifact.
_STEP_LIMIT = 32
Number = Annotated[int, Field(strict=True, ge=-_VALUE_LIMIT, le=_VALUE_LIMIT)]
Address = Annotated[int, Field(strict=True, ge=0, le=4095)]
Register = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,15}$")]


class ExampleError(ValueError):
    """An explicit program cannot be safely evaluated under this language."""


class MemoryCell(BaseModel):
    """One explicitly initialized data address, separate from instruction cells."""

    model_config = ConfigDict(extra="forbid")
    address: Address
    value: Number


class Instruction(BaseModel):
    """One instruction occupies one address; ordinary fall-through adds one."""

    model_config = ConfigDict(extra="forbid")
    address: Address
    op: Literal["SET", "ADD", "SUB", "LOAD", "STORE", "JMP", "JZ", "JNZ", "JLT", "HALT"]
    reg: Register | None = None
    operand: Number | Register | None = None
    target: Address | None = None


class ComputedExample(BaseModel):
    """A complete generated illustration with no asserted trace or final values.

    Registers and data cells must be initialized explicitly. SET/ADD/SUB use an
    integer or register operand; LOAD/STORE use a data address. JZ/JNZ test the
    named register; JLT compares it with the operand. JMP changes PC directly.
    No inputs, external code, overflow or self-modifying instructions exist.
    """

    model_config = ConfigDict(extra="forbid")
    initial_pc: Address
    registers: dict[Register, Number] = Field(max_length=8)
    memory: list[MemoryCell] = Field(max_length=16)
    program: list[Instruction] = Field(min_length=1, max_length=32)
    steps: Annotated[int, Field(strict=True, ge=1, le=_STEP_LIMIT)] | None = Field(
        default=None,
        description="Optional finite prefix; never implies termination. Otherwise reach HALT or an exact repeated state within 32 steps. All schema maxima together fit the 16 KiB display limit.",
    )


@dataclass(frozen=True)
class StateRow:
    """An executed instruction and its resulting complete machine state."""

    pc: int
    next_pc: int | None
    registers: dict[str, int]
    memory: dict[int, int]


@dataclass(frozen=True)
class ExampleResult:
    """Actual numeric states and a mechanically established stopping condition."""

    rows: tuple[StateRow, ...]
    outcome: Literal["halt", "cycle", "prefix"]


def _program(example: ComputedExample) -> dict[int, Instruction]:
    """Check all declarations before executing or rendering any content."""
    program = {instruction.address: instruction for instruction in example.program}
    if len(program) != len(example.program):
        message = "Instruction addresses must be unique"
        raise ExampleError(message)
    if any(name.casefold() == "pc" for name in example.registers):
        message = "PC is the control address, not a data-register name"
        raise ExampleError(message)
    memory = {cell.address for cell in example.memory}
    if len(memory) != len(example.memory) or memory.intersection(program):
        message = "Data addresses must be unique and separate from code"
        raise ExampleError(message)
    if example.initial_pc not in program:
        message = "Initial PC must name an instruction"
        raise ExampleError(message)
    required = {
        "SET": {"reg", "operand"},
        "ADD": {"reg", "operand"},
        "SUB": {"reg", "operand"},
        "LOAD": {"reg", "operand"},
        "STORE": {"reg", "operand"},
        "JMP": {"target"},
        "JZ": {"reg", "target"},
        "JNZ": {"reg", "target"},
        "JLT": {"reg", "operand", "target"},
        "HALT": set(),
    }
    for instruction in example.program:
        supplied = {
            field
            for field in ("reg", "operand", "target")
            if getattr(instruction, field) is not None
        }
        if supplied != required[instruction.op]:
            message = (
                f"{instruction.op} requires exactly {sorted(required[instruction.op])}"
            )
            raise ExampleError(message)
        registers = [instruction.reg] if instruction.reg is not None else []
        if isinstance(instruction.operand, str):
            registers.append(instruction.operand)
        for register in registers:
            if register not in example.registers:
                message = f"Initial register {register} must be declared"
                raise ExampleError(message)
        if instruction.target is not None and instruction.target not in program:
            message = "Branch targets must name declared instructions"
            raise ExampleError(message)
        if instruction.op in ("LOAD", "STORE") and (
            not isinstance(instruction.operand, int)
            or instruction.operand not in memory
        ):
            message = "LOAD/STORE require an initialized data address, never code"
            raise ExampleError(message)
    return program


def execute_example(example: ComputedExample) -> ExampleResult:
    """Run only explicit bounded integer operations; never assume a missing state."""
    program = _program(example)
    registers = dict(example.registers)
    memory = {cell.address: cell.value for cell in example.memory}
    pc = example.initial_pc
    seen: set[tuple] = set()
    rows: list[StateRow] = []
    for _ in range(_STEP_LIMIT):
        state = (pc, tuple(sorted(registers.items())), tuple(sorted(memory.items())))
        if state in seen:
            return ExampleResult(tuple(rows), "cycle")
        seen.add(state)
        instruction = program.get(pc)
        if instruction is None:
            message = f"Execution reaches undeclared instruction {pc}"
            raise ExampleError(message)
        register = instruction.reg
        operand = instruction.operand
        value = registers[operand] if isinstance(operand, str) else operand
        next_pc = pc + 1
        if instruction.op == "SET":
            registers[register] = value
        elif instruction.op == "ADD":
            registers[register] += value
        elif instruction.op == "SUB":
            registers[register] -= value
        elif instruction.op == "LOAD":
            registers[register] = memory[operand]
        elif instruction.op == "STORE":
            memory[operand] = registers[register]
        elif instruction.op == "JMP":
            next_pc = instruction.target
        elif instruction.op in ("JZ", "JNZ", "JLT"):
            taken = (
                registers[register] == 0
                if instruction.op == "JZ"
                else registers[register] != 0
                if instruction.op == "JNZ"
                else registers[register] < value
            )
            if taken:
                next_pc = instruction.target
        elif instruction.op == "HALT":
            next_pc = None
        if any(abs(v) > _VALUE_LIMIT for v in (*registers.values(), *memory.values())):
            message = "Computed value exceeds the explicit integer limit; no overflow is inferred"
            raise ExampleError(message)
        rows.append(StateRow(pc, next_pc, dict(registers), dict(memory)))
        if next_pc is None:
            return ExampleResult(tuple(rows), "halt")
        pc = next_pc
        if example.steps is not None and len(rows) == example.steps:
            return ExampleResult(tuple(rows), "prefix")
    message = "Step budget exhausted; termination is unknown"
    raise ExampleError(message)


def render_example(example: ComputedExample) -> str:
    """Render initial state, actual program and table from the same execution.

    Labels are machine symbols and instruction mnemonics, not new UI copy. The
    returned ordinary Markdown is classified by the existing shared formatter.
    """
    result = execute_example(example)
    registers = sorted(example.registers)
    memory = {cell.address: cell.value for cell in example.memory}
    addresses = sorted(memory)
    initial = [f"PC={example.initial_pc}"]
    initial.extend(f"{key}={example.registers[key]}" for key in registers)
    initial.extend(f"M[{address}]={memory[address]}" for address in addresses)
    code = ["```text", "; ".join(initial)]
    for instruction in sorted(example.program, key=lambda item: item.address):
        arguments = [
            str(value)
            for value in (instruction.reg, instruction.operand, instruction.target)
            if value is not None
        ]
        code.append(
            f"{instruction.address}: {instruction.op}"
            + (" " + ", ".join(arguments) if arguments else "")
        )
    code.extend(["```", ""])
    headers = [
        "#",
        "PC",
        "→ PC",
        *registers,
        *(f"M[{address}]" for address in addresses),
    ]
    code.extend(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
        ]
    )
    initial_row = [0, example.initial_pc, example.initial_pc]
    initial_row.extend(example.registers[key] for key in registers)
    initial_row.extend(memory[address] for address in addresses)
    code.append("| " + " | ".join(map(str, initial_row)) + " |")
    for index, row in enumerate(result.rows, 1):
        values = [index, row.pc, row.next_pc if row.next_pc is not None else "HALT"]
        values.extend(row.registers[key] for key in registers)
        values.extend(row.memory[address] for address in addresses)
        code.append("| " + " | ".join(map(str, values)) + " |")
    if result.outcome != "halt":
        code.extend(
            [
                "",
                ("↻" if result.outcome == "cycle" else "…")
                + f" PC={result.rows[-1].next_pc}",
            ]
        )
    text = "\n".join(code) + "\n"
    if len(text.encode()) > 16_384:
        message = "Computed artifact exceeds its display budget"
        raise ExampleError(message)
    return text


def has_computed_example(
    call: ToolCallPart, *, include_unparseable: bool = False
) -> bool:
    """Recognize the payload, conservatively holding unknown JSON when enabled."""
    if call.tool_name != "interact":
        return False
    try:
        return (
            call.args_as_dict(raise_if_invalid=True).get("computed_example") is not None
        )
    except (TypeError, ValueError, AssertionError):
        return include_unparseable
