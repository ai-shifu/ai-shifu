"""Run the library's asynchronous tests on its supported event loop."""

from functools import partialmethod

import pytest
from markdownflow import Engine

# These existing FunctionModel suites exercise behavior through the archived tool
# arguments. Keep the opt-in local to those fixtures so new tests use the same
# strict contract as production.
_LEGACY_TOOL_FIXTURES = frozenset(
    {
        "test_answer_context",
        "test_bridge",
        "test_clarification_scope",
        "test_direction_evidence",
        "test_direction_feedback",
        "test_engine",
        "test_exercise_statistics",
        "test_feedback_grounding",
        "test_feedback_phase_contract",
        "test_feedback_response_lifetime",
        "test_feedback_tool_schema",
        "test_finish_termination",
        "test_history_context",
        "test_interaction_markup",
        "test_interaction_variable_bindings",
        "test_interrupted_teaching",
        "test_memory_admission",
        "test_memory_budget",
        "test_memory_context",
        "test_memory_lifecycle",
        "test_memory_limits",
        "test_memory_recall",
        "test_optional_memory_key",
        "test_response_buffering",
        "test_script_text_inputs",
        "test_text_answer_controls",
        "test_unavailable_variables",
        "test_variable_name_contract",
        "test_visual_repeat_trimming",
    }
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def archived_interaction_arguments(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Allow old synthetic tool calls only in the explicitly migrated suites."""
    if request.path.stem not in _LEGACY_TOOL_FIXTURES:
        return
    monkeypatch.setattr(
        Engine, "__init__", partialmethod(Engine.__init__, legacy_interact_args=True)
    )
