"""Replay historical scripted tool calls only in the existing host suites."""

from functools import partialmethod

import pytest
from markdownflow import Engine

_LEGACY_TOOL_FIXTURES = frozenset(
    {
        "test_answer_bindings",
        "test_course_references",
        "test_debug_session",
        "test_deleted_memory",
        "test_draft_classroom_history",
        "test_draft_classroom_rewind",
        "test_evidence_variable_names",
        "test_follow_up_agent_history",
        "test_history_compaction",
        "test_interaction_identity",
        "test_memory_admission_integration",
        "test_memory_integration",
        "test_memory_recall_integration",
        "test_memory_refresh_integration",
        "test_mixed_answers",
        "test_output_language",
        "test_pending_validation",
        "test_resumed_nickname",
        "test_retry_content",
        "test_rewind_interrupted_turn",
        "test_run_agent",
        "test_session_contracts",
        "test_runtime",
        "test_session_continuation",
        "test_shared_answers",
        "test_single_session_engine",
        "test_tracing",
        "test_v2_runtime",
    }
)


@pytest.fixture(autouse=True)
def archived_host_interaction_arguments(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep historical call fixtures explicit while new host tests use the live schema."""
    if request.path.stem in _LEGACY_TOOL_FIXTURES and (
        "learn" in request.path.parts or "profile_research" in request.path.parts
    ):
        monkeypatch.setattr(
            Engine,
            "__init__",
            partialmethod(Engine.__init__, legacy_interact_args=True),
        )
