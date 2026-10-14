"""Verify computed numeric artifacts independently of model prose or grading."""

import pytest
from flaskr.service.learn.agent.engine.computed_example import (
    ComputedExample,
    ExampleError,
    execute_example,
    render_example,
)


def _loop() -> dict:
    """Return a fully initialized two-body program from a retained failure class."""
    return {
        "initial_pc": 100,
        "registers": {"R0": 2, "R1": 0},
        "memory": [],
        "program": [
            {"address": 100, "op": "SET", "reg": "R0", "operand": 2},
            {"address": 101, "op": "ADD", "reg": "R1", "operand": "R0"},
            {"address": 102, "op": "SUB", "reg": "R0", "operand": 1},
            {"address": 103, "op": "JNZ", "reg": "R0", "target": 101},
            {"address": 104, "op": "HALT"},
        ],
    }


def test_two_bodies_use_changed_operand_and_canonical_state() -> None:
    """Compute three, rather than accepting the model's erroneous second-row four."""
    example = ComputedExample.model_validate(_loop())
    result = execute_example(example)
    assert result.outcome == "halt"
    assert [r.registers["R1"] for r in result.rows if r.pc == 101] == [2, 3]
    assert result.rows[-1].registers == {"R0": 0, "R1": 3}
    text = render_example(example)
    assert "R1" in text
    assert "HALT" in text
    assert "101" in text
    assert "| 5 | 101 | 102 | 1 | 3 |" in text


def test_missing_initial_register_is_not_silently_zero() -> None:
    """Refuse the original missing R1 rather than repair the source implicitly."""
    data = _loop()
    del data["registers"]["R1"]
    with pytest.raises(ExampleError, match="R1"):
        execute_example(ComputedExample.model_validate(data))


def test_repeated_complete_state_is_a_cycle_not_halt() -> None:
    """Reloading unchanged memory does not accumulate a decrement toward zero."""
    example = ComputedExample.model_validate(
        {
            "initial_pc": 0,
            "registers": {"ACC": 0},
            "memory": [{"address": 10, "value": 5}],
            "program": [
                {"address": 0, "op": "LOAD", "reg": "ACC", "operand": 10},
                {"address": 1, "op": "SUB", "reg": "ACC", "operand": 1},
                {"address": 2, "op": "JZ", "reg": "ACC", "target": 5},
                {"address": 3, "op": "ADD", "reg": "ACC", "operand": 2},
                {"address": 4, "op": "JMP", "target": 0},
                {"address": 5, "op": "HALT"},
            ],
        }
    )
    result = execute_example(example)
    assert result.outcome == "cycle"
    assert {r.registers["ACC"] for r in result.rows if r.pc == 2} == {4}
    assert "HALT" not in render_example(example).split("```", 2)[-1]


def test_known_correct_counter_keeps_all_six_states() -> None:
    """Preserve a correct two-iteration control rather than merely rejecting input."""
    example = ComputedExample.model_validate(
        {
            "initial_pc": 100,
            "registers": {"I": 0},
            "memory": [],
            "program": [
                {"address": 100, "op": "SET", "reg": "I", "operand": 0},
                {"address": 101, "op": "ADD", "reg": "I", "operand": 1},
                {"address": 102, "op": "JLT", "reg": "I", "operand": 2, "target": 101},
                {"address": 103, "op": "HALT"},
            ],
        }
    )
    result = execute_example(example)
    assert result.outcome == "halt"
    assert [(r.pc, r.registers["I"]) for r in result.rows] == [
        (100, 0),
        (101, 1),
        (102, 1),
        (101, 2),
        (102, 2),
        (103, 2),
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [("initial_pc", True), ("initial_pc", "100"), ("steps", False), ("steps", 33)],
)
def test_scalar_types_and_step_limit_are_explicit(field: str, value: object) -> None:
    """Never coerce a boolean, numeric string or unbounded prefix into a program."""
    from pydantic import ValidationError

    data = _loop()
    data[field] = value
    with pytest.raises(ValidationError):
        ComputedExample.model_validate(data)


def test_result_rows_and_claims_are_not_accepted_inputs() -> None:
    """The model cannot declare a fabricated final value for the host to repeat."""
    from pydantic import ValidationError

    data = {**_loop(), "final_R1": 4, "trace": [{"R1": 4}]}
    with pytest.raises(ValidationError):
        ComputedExample.model_validate(data)


def test_prefix_and_step_exhaustion_never_claim_halt() -> None:
    """Separate a bounded observation from a proved exit or repeated-state cycle."""
    prefix = ComputedExample.model_validate({**_loop(), "steps": 2})
    assert execute_example(prefix).outcome == "prefix"
    assert "… PC=102" in render_example(prefix)
    increasing = ComputedExample.model_validate(
        {
            "initial_pc": 0,
            "registers": {"I": 0},
            "memory": [],
            "program": [
                {"address": 0, "op": "ADD", "reg": "I", "operand": 1},
                {"address": 1, "op": "JMP", "target": 0},
            ],
        }
    )
    with pytest.raises(ExampleError, match="termination is unknown"):
        render_example(increasing)


@pytest.mark.parametrize(
    "case",
    [
        "duplicate_code",
        "code_data_overlap",
        "unknown_target",
        "missing_instruction",
        "extraneous_operand",
        "overflow",
        "uninitialized_data",
        "reserved_pc",
    ],
)
def test_invalid_machine_state_cannot_be_rendered(case: str) -> None:
    """Reject explicit unsafe or ambiguous semantics before returning any artifact."""
    data = _loop()
    if case == "duplicate_code":
        data["program"].append(data["program"][0])
    elif case == "code_data_overlap":
        data["memory"] = [{"address": 100, "value": 0}]
    elif case == "unknown_target":
        data["program"][3]["target"] = 999
    elif case == "missing_instruction":
        data["program"] = data["program"][:1]
    elif case == "extraneous_operand":
        data["program"][-1]["operand"] = 1
    elif case == "overflow":
        data["registers"]["R1"] = 1_000_000_000
    elif case == "reserved_pc":
        data["registers"]["PC"] = 0
    else:
        data["program"][0] = {"address": 100, "op": "LOAD", "reg": "R0", "operand": 50}
    with pytest.raises(ExampleError):
        render_example(ComputedExample.model_validate(data))


def test_simultaneous_schema_maxima_fit_the_display_limit() -> None:
    """Keep maximal columns, names, values and program within the 16 KiB artifact."""
    registers = {f"R{index:015d}": -1_000_000_000 for index in range(8)}
    names = list(registers)
    example = ComputedExample.model_validate(
        {
            "initial_pc": 0,
            "registers": registers,
            "memory": [
                {"address": 4000 + i, "value": -1_000_000_000} for i in range(16)
            ],
            "program": [
                {"address": 0, "op": "ADD", "reg": names[0], "operand": 1},
                {"address": 1, "op": "JMP", "target": 0},
                *[
                    {
                        "address": i,
                        "op": "JLT",
                        "reg": names[0],
                        "operand": names[1],
                        "target": 4095,
                    }
                    for i in range(2, 31)
                ],
                {"address": 4095, "op": "HALT"},
            ],
            "steps": 32,
        }
    )
    assert execute_example(example).outcome == "prefix"
    assert len(execute_example(example).rows) == 32
    assert len(render_example(example).encode()) < 16_384
    assert (
        ComputedExample.model_json_schema()["properties"]["steps"]["anyOf"][0][
            "maximum"
        ]
        == 32
    )


def test_first_repeated_complete_state_at_execution_limit_is_a_cycle() -> None:
    """Inspect the final state too, while an explicit prefix stays incomplete."""
    data = {
        "initial_pc": 0,
        "registers": {"R0": 0},
        "memory": [],
        "program": [
            {"address": i, "op": "SET", "reg": "R0", "operand": "R0"} for i in range(31)
        ]
        + [{"address": 31, "op": "JMP", "target": 0}],
    }
    result = execute_example(ComputedExample.model_validate(data))
    assert result.outcome == "cycle"
    assert len(result.rows) == 32
    prefix = ComputedExample.model_validate({**data, "steps": 32})
    assert execute_example(prefix).outcome == "prefix"
