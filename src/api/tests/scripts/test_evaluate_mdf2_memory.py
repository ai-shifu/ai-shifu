"""Prove evaluation failures cannot become successful memory-quality evidence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from scripts import evaluate_mdf2_memory as quality

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo

pytestmark = pytest.mark.anyio


def test_list_needs_no_app_or_credentials() -> None:
    process = subprocess.run(
        [sys.executable, str(Path(quality.__file__)), "--list"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    cases = json.loads(process.stdout)
    assert len(cases) == 28
    assert {case["family"] for case in cases} == {
        "admission",
        "recall",
        "teaching",
        "exercise",
    }


@pytest.mark.parametrize("args", [[], ["--live"], ["--course", "course"]])
def test_live_requires_explicit_complete_context(args: list[str]) -> None:
    with pytest.raises(SystemExit) as error:
        quality.main(args)
    assert error.value.code == 2


def test_unknown_case_is_not_silently_dropped() -> None:
    with pytest.raises(ValueError, match="unknown evaluation cases"):
        quality.load_cases(["not-a-case"])


@pytest.mark.parametrize(
    "reply", [False, True, "false", "wrong-tool", "error", "empty"]
)
async def test_refusal_scores_only_a_valid_successful_judge_response(
    reply: object,
) -> None:
    def model(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if reply == "error":
            message = "provider unavailable"
            raise RuntimeError(message)
        if reply == "empty":
            return ModelResponse(parts=[])
        name = "unknown_tool" if reply == "wrong-tool" else info.output_tools[0].name
        return ModelResponse(parts=[ToolCallPart(name, {"allowed": reply})])

    case = quality.load_cases(["ordinary-preference"])[0]
    result = await quality.evaluate_admission(case, FunctionModel(model))
    assert result["passed"] is (reply is False)
    assert bool(result["error"]) is (reply not in (False, True))


async def test_admission_report_preserves_completed_provider_cache_usage() -> None:
    from pydantic_ai.usage import RequestUsage

    def refusal(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, {"allowed": False})],
            usage=RequestUsage(
                input_tokens=100,
                output_tokens=3,
                cache_read_tokens=40,
                details={
                    "mdf2_cache_reported_requests": 1,
                    "mdf2_cache_reported_input_tokens": 100,
                    "mdf2_cache_reported_read_tokens": 40,
                },
            ),
        )

    result = await quality.evaluate_admission(
        quality.load_cases(["ordinary-preference"])[0], FunctionModel(refusal)
    )
    assert result["passed"], result
    assert result["usage"]["requests"] == 1
    assert result["usage"]["cache_reported_read_tokens"] == 40
    assert result["usage"]["cache_reported_input_tokens"] == 100


def _recall_model(
    *,
    stale: bool = False,
    omit_tool: bool = False,
    finish_later: bool = False,
) -> FunctionModel:
    phase = 0

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal phase
        phase += 1
        if phase == 1 and not omit_tool:
            yield {
                0: DeltaToolCall(
                    name="recall",
                    tool_call_id="current",
                    json_args='{"key":"project_code"}',
                )
            }
            return
        if finish_later and phase == 3:
            yield {
                0: DeltaToolCall(
                    name="finish", tool_call_id="done", json_args='{"summary":"done"}'
                )
            }
            return
        last = messages[-1]
        results = [
            json.loads(part.content)
            for part in last.parts
            if isinstance(last, ModelRequest) and isinstance(part, ToolReturnPart)
        ]
        found = next(
            (result for result in results if result.get("status") == "found"), None
        )
        text = found["value"].strip() if found else "MEMORY_UNAVAILABLE"
        yield quality.OLD_CODE if stale or omit_tool else text
        if finish_later:
            return
        yield {
            0: DeltaToolCall(
                name="finish", tool_call_id="done", json_args='{"summary":"done"}'
            )
        }

    return FunctionModel(stream_function=model)


@pytest.mark.parametrize(
    "case",
    [c for c in quality.load_cases() if c["family"] == "recall"],
    ids=lambda c: c["id"],
)
async def test_recall_scorer_runs_real_engine_and_current_tool(case: dict) -> None:
    result = await quality.evaluate_recall(case, _recall_model())
    assert result["passed"], result
    assert all(result["checks"].values())


@pytest.mark.parametrize("mode", ["stale", "omit_tool"])
async def test_plausible_or_stale_answer_cannot_pass_without_current_evidence(
    mode: str,
) -> None:
    case = quality.load_cases(["recall-updated-history"])[0]
    result = await quality.evaluate_recall(case, _recall_model(**{mode: True}))
    assert not result["passed"]


def _summary_model(
    text: str = "Earlier teaching explained an original worked example.",
) -> FunctionModel:
    def model(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        assert len(messages) == 1
        source = json.loads(messages[0].parts[0].content)["historical_teaching"]
        assert quality.OLD_CODE in source
        assert quality.NEW_CODE not in source
        return ModelResponse(parts=[TextPart(text)])

    return FunctionModel(model)


def _teaching_model(case: dict, behavior: str = "correct") -> FunctionModel:
    phase = 0

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal phase
        phase += 1
        if phase > 2:
            yield " "
            return
        if phase == 1 and behavior != "omit_tool":
            if case.get("historical"):
                markers = [
                    json.loads(part.content)
                    for message in messages
                    if isinstance(message, ModelResponse)
                    for part in message.parts
                    if isinstance(part, TextPart)
                    and part.content.startswith('{"status":"teaching_')
                ]
                reference = (
                    "wrong"
                    if behavior == "wrong_reference"
                    else markers[0]["reference"]
                )
                name, args = "read_teaching", {"reference": reference}
            else:
                name, args = "recall", {"key": "project_code"}
            yield {
                0: DeltaToolCall(
                    name=name, tool_call_id="evidence", json_args=json.dumps(args)
                )
            }
            return
        yield (
            quality.NEW_CODE
            if behavior == "stale" and case.get("historical")
            else (quality.OLD_CODE if behavior == "stale" else case["expected"])
        )
        yield {
            0: DeltaToolCall(
                name="finish", tool_call_id="finish", json_args='{"summary":"done"}'
            )
        }

    return FunctionModel(stream_function=model)


@pytest.mark.parametrize("status", ["teaching_summary", "teaching_excerpt"])
@pytest.mark.parametrize(
    "location", ["source", "later-response", "other-part", "unknown-reference"]
)
async def test_projection_evidence_requires_original_message_and_part(
    status: str, location: str
) -> None:
    from copy import deepcopy

    from flaskr.service.learn.agent.engine.teaching_history import (
        project_teaching_history,
    )

    case = quality.load_cases(["teaching-exact-example"])[0]
    original = quality.teaching_session(case).messages
    projected, sources = project_teaching_history(original)
    assert len(sources) == 1
    reference = next(iter(sources))
    _, message_index, part_index, _digest = reference.split("-", 3)
    message_index, part_index = int(message_index), int(part_index)
    marker = TextPart(json.dumps({"reference": reference, "status": status}))
    messages = deepcopy(original)
    if location == "source":
        messages = deepcopy(projected)
        messages[message_index].parts[part_index] = marker
    elif location == "later-response":
        messages.append(ModelResponse(parts=[marker]))
    elif location == "other-part":
        messages[message_index].parts.append(marker)
    else:
        messages[message_index].parts[part_index] = TextPart(
            json.dumps({"reference": reference + "-unknown", "status": status})
        )
    before = deepcopy(messages)

    async def model(sent: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[str]:
        assert sent == before
        yield "Unchanged response."

    markers: set[str] = set()
    observed = quality.observe_teaching_projection(
        FunctionModel(stream_function=model), sources, markers
    )
    async with observed.request_stream(
        messages, None, ModelRequestParameters()
    ) as response:
        async for _event in response:
            pass
        assert response.get().parts == [TextPart("Unchanged response.")]

    assert markers == ({status} if location == "source" else set())
    assert messages == before


@pytest.mark.parametrize(
    "case",
    [c for c in quality.load_cases() if c["family"] == "teaching"],
    ids=lambda c: c["id"],
)
async def test_teaching_scorer_combines_real_projection_reads_and_cache_reload(
    case: dict,
) -> None:
    result = await quality.evaluate_teaching(
        case, _teaching_model(case), _summary_model()
    )
    assert result["passed"], result
    assert result["summary_calls"] == 1


@pytest.mark.parametrize("behavior", ["omit_tool", "stale", "wrong_reference"])
async def test_historical_answer_without_matching_original_evidence_fails(
    behavior: str,
) -> None:
    case = quality.load_cases(["teaching-exact-example"])[0]
    result = await quality.evaluate_teaching(
        case, _teaching_model(case, behavior), _summary_model()
    )
    assert not result["passed"]


async def test_missing_real_summary_is_an_error_even_when_the_answer_is_correct() -> (
    None
):
    case = quality.load_cases(["teaching-current-updated"])[0]
    result = await quality.evaluate_teaching(
        case, _teaching_model(case), _summary_model("")
    )
    assert not result["passed"]
    assert result["error"] == "summary_unavailable_or_invalid"


def test_teaching_fixture_preserves_the_matching_host_script_prompt() -> None:
    from flaskr.service.learn.agent.engine.script import render_first_prompt

    session = quality.teaching_session(
        quality.load_cases(["teaching-exact-example"])[0]
    )
    assert session.messages[0].parts[0].content == render_first_prompt(
        session.script, {"project_code": quality.OLD_CODE + " " * 500}, memory_limit=100
    )


async def test_summary_usage_is_separate_and_not_repeated_after_reload() -> None:
    from pydantic_ai.usage import RequestUsage

    case = quality.load_cases(["teaching-exact-example"])[0]

    def summary(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        return ModelResponse(
            parts=[TextPart("An earlier worked example used a project code.")],
            usage=RequestUsage(
                input_tokens=20,
                output_tokens=3,
                cache_read_tokens=10,
                details={
                    "mdf2_cache_reported_requests": 1,
                    "mdf2_cache_reported_input_tokens": 20,
                    "mdf2_cache_reported_read_tokens": 10,
                },
            ),
        )

    result = await quality.evaluate_teaching(
        case, _teaching_model(case), FunctionModel(summary)
    )
    assert result["passed"], result
    assert result["summary_usage"] == {
        "requests": 1,
        "input_tokens": 20,
        "output_tokens": 3,
        "cache_read_tokens": 10,
        "cache_reported_requests": 1,
        "cache_reported_input_tokens": 20,
        "cache_reported_read_tokens": 10,
    }
    assert result["usage"]["input_tokens"] != 20
    assert result["usage"]["requests"] > 0
    assert "cache_read_tokens" not in result["usage"]
    assert result["summary_calls"] == 1


async def test_injected_summary_failure_cannot_claim_provider_usage() -> None:
    case = quality.load_cases(["teaching-exact-fallback"])[0]

    def summary(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        pytest.fail("injected failure must not call the summary provider")

    result = await quality.evaluate_teaching(
        case, _teaching_model(case), FunctionModel(summary)
    )
    assert result["passed"], result
    assert result["summary_usage"] == {}


def test_partial_or_duplicate_results_cannot_claim_full_completion() -> None:
    cases = quality.load_cases(["remember-direct", "ordinary-preference"])
    good = [{"id": c["id"], "repetition": 1, "passed": True} for c in cases]
    assert quality.report(cases, good, 1)["passed"]
    for results in (good[:1], good[:1] * 2, []):
        value = quality.report(cases, results, 1)
        assert not value["complete"]
        assert not value["passed"]
    assert not quality.report(cases, good, 1)["full_catalog"]


async def test_error_cases_continue_and_each_repetition_gets_a_fresh_model() -> None:
    calls = []

    def factory(family: str) -> FunctionModel:
        calls.append(family)
        message = "injected gateway initialization failure"
        raise RuntimeError(message)

    cases = quality.load_cases(["remember-direct", "ordinary-preference"])
    results = await quality.evaluate(cases, factory, 2)
    assert len(calls) == len(results) == 4
    assert all(not row["passed"] and row["error"] == "RuntimeError" for row in results)
    assert quality.report(cases, results, 2)["error_results"] == 4


def test_report_is_private_and_contains_no_case_payloads(tmp_path: Path) -> None:
    cases = quality.load_cases(["remember-direct"])
    value = quality.report(
        cases, [{"id": cases[0]["id"], "repetition": 1, "passed": True}], 1
    )
    output = tmp_path / "quality.json"
    quality.write_report(output, value)
    assert output.stat().st_mode & 0o777 == 0o600
    assert json.loads(output.read_text()) == value
    assert cases[0]["request"] not in output.read_text()


def test_missing_git_in_runtime_image_cannot_discard_evaluation_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError

    monkeypatch.setattr(quality.subprocess, "run", unavailable)
    assert quality.source_revision() is None


@pytest.mark.parametrize("enabled", [True, False])
def test_live_cli_wires_required_trace_and_refuses_legacy_environment(
    app: object, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, enabled: bool
) -> None:
    from types import SimpleNamespace
    from unittest.mock import Mock
    from uuid import uuid4

    import app as app_module
    from flaskr.api import langfuse
    from flaskr.api.llm import model_selection
    from flaskr.dao.uow import unit_of_work
    from flaskr.service.learn.agent import gateway_model, lesson_entry, routing
    from flaskr.service.metering.api import UsageContext
    from flaskr.service.user.repository import create_user_entity

    identity = uuid4().hex
    with app.app_context(), unit_of_work():
        create_user_entity(user_bid=identity, identify=identity, nickname="Evaluation")
    monkeypatch.setattr(app_module, "create_app", lambda **_kwargs: app)
    monkeypatch.setattr(routing, "uses_agent_engine", lambda _course: enabled)
    resolve = Mock(
        return_value=("", "", SimpleNamespace(model="selected", usage_metadata={}))
    )
    monkeypatch.setattr(lesson_entry, "_resolve", resolve)
    selection = Mock(return_value=("resolved-model", {"source": "evaluation-test"}))
    monkeypatch.setattr(model_selection, "resolve_selection", selection)
    trace, span = object(), object()
    monkeypatch.setattr(langfuse, "get_langfuse_client", lambda: None)
    monkeypatch.setattr(
        langfuse, "create_trace_with_root_span", lambda **_kwargs: (trace, span)
    )
    finalize = Mock()
    monkeypatch.setattr(langfuse, "finalize_langfuse_trace", finalize)
    calls = []

    def gateway(
        _app: object, model: str, *, user_id: str, span: object, **kwargs: object
    ) -> FunctionModel:
        calls.append((model, user_id, span, kwargs))

        def refusal(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            return ModelResponse(
                parts=[ToolCallPart(info.output_tools[0].name, {"allowed": False})]
            )

        return FunctionModel(refusal)

    monkeypatch.setattr(gateway_model, "GatewayModel", gateway)
    output = tmp_path / "live.json"
    args = [
        "--live",
        "--course",
        "course",
        "--lesson",
        "lesson",
        "--learner",
        identity,
        "--case",
        "ordinary-preference",
        "--output",
        str(output),
    ]
    if not enabled:
        with pytest.raises(SystemExit) as error:
            quality.main(args)
        assert error.value.code == 2
        assert not calls
        resolve.assert_not_called()
        assert not output.exists()
        return
    assert quality.main(args) == 0
    assert len(calls) == 1
    assert calls[0][:3] == ("resolved-model", identity, span)
    assert calls[0][3]["generation_name"] == "agent_memory_quality_admission"
    value = json.loads(output.read_text())
    assert value["passed"]
    assert value["model_selection"] == "selected"
    assert value["model"] == "resolved-model"
    assert calls[0][3]["usage_metadata"] == {"source": "evaluation-test"}
    assert calls[0][3]["usage_context"] == UsageContext(
        user_bid=identity, shifu_bid="course", outline_item_bid="lesson"
    )
    selection.assert_called_once_with("selected", {})
    assert finalize.call_args.kwargs["trace"] is trace
    assert finalize.call_args.kwargs["root_span"] is span
    assert resolve.call_args.kwargs["preview_mode"] is False


@pytest.mark.parametrize(
    "identifier", ["recall-updated-history", "recall-deleted-history"]
)
def test_resumed_fixture_contains_the_product_first_prompt(identifier: str) -> None:
    from flaskr.service.learn.agent.engine.memory_context import (
        parse_initial_memory_prompt,
    )
    from flaskr.service.learn.agent.engine.script import render_first_prompt

    case = quality.load_cases([identifier])[0]
    session = quality.recall_session(case)
    content = session.messages[0].parts[0].content
    expected = render_first_prompt(
        session.script, {"project_code": quality.OLD_CODE + " " * 500}, memory_limit=100
    )
    assert content == expected
    assert parse_initial_memory_prompt(content) is not None
    assert session.initial_variables == {}
    assert session.turn == 1


async def test_unpaused_answer_can_finish_on_one_host_continuation() -> None:
    case = quality.load_cases(["recall-updated-history"])[0]
    result = await quality.evaluate_recall(case, _recall_model(finish_later=True))
    assert result["passed"], result
    assert result["checks"]["completed"]


async def test_in_place_history_mutation_cannot_pass_the_preservation_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.service.learn.agent.engine import Engine

    original = Engine.run_turn

    async def mutate(
        engine: object, session: object, *args: object, **kwargs: object
    ) -> AsyncIterator[object]:
        async for event in original(engine, session, *args, **kwargs):
            yield event
        session.messages[0].parts[0].content += "\nUnexpected stored-history mutation."

    monkeypatch.setattr(Engine, "run_turn", mutate)
    case = quality.load_cases(["recall-updated-history"])[0]
    result = await quality.evaluate_recall(case, _recall_model())
    assert not result["passed"]
    assert not result["checks"]["history_preserved"]
    assert result["checks"]["current_tool_result"]


def test_author_fixture_does_not_supply_the_recall_procedure() -> None:
    case = quality.load_cases(["recall-updated-history"])[0]
    script = quality.recall_session(case).script.script
    assert "recall" not in script
    assert "stale" not in script
    assert "project_code" not in script


@pytest.mark.parametrize("content", ["", " \n"])
async def test_silent_first_turn_does_not_get_an_extra_answer_attempt(
    monkeypatch: pytest.MonkeyPatch, content: str
) -> None:
    from flaskr.service.learn.agent.engine import ContentDelta, Engine, TurnDone

    calls = []

    async def silent(*_args: object, **_kwargs: object) -> AsyncIterator[object]:
        calls.append(True)
        if content:
            yield ContentDelta(text=content)
        yield TurnDone(reason="end")

    monkeypatch.setattr(Engine, "run_turn", silent)
    case = quality.load_cases(["recall-updated-history"])[0]
    result = await quality.evaluate_recall(case, _recall_model())
    assert len(calls) == 1
    assert not result["passed"]


@pytest.mark.parametrize(
    "mode", ["correct", "wrong-key", "unpaired", "late", "conflicting", "reversed"]
)
@pytest.mark.parametrize(
    "identifier", ["recall-updated-history", "recall-deleted-history"]
)
def test_current_evidence_requires_the_relevant_ordered_consistent_read(
    mode: str,
    identifier: str,
) -> None:
    from flaskr.service.learn.agent.engine import ContentDelta, ToolCall, ToolResult

    case = quality.load_cases([identifier])[0]
    call = ToolCall(
        id="current",
        name="recall",
        args={"key": "wrong" if mode == "wrong-key" else "project_code"},
    )
    result = ToolResult(
        id="current",
        name="recall",
        content=json.dumps(
            {"status": case["status"], "value": case["expected"]}
            if case["status"] == "found"
            else {"status": case["status"]}
        ),
    )
    answer = ContentDelta(text=case["expected"])
    events = [call, result, answer]
    if mode == "unpaired":
        events = [result, answer]
    elif mode == "late":
        events = [answer, call, result]
    elif mode in {"conflicting", "reversed"}:
        conflicting = [
            ToolCall(id="other", name="recall", args={"key": "project_code"}),
            ToolResult(
                id="other", name="recall", content=json.dumps({"status": "too_large"})
            ),
        ]
        events = (
            [call, result, answer, *conflicting]
            if mode == "conflicting"
            else [*conflicting, call, result, answer]
        )
    assert quality.current_recall_evidence(case, events) is (mode == "correct")


@pytest.mark.parametrize("content", ["LESSON_OVER", "malformed", "[]", "null", None])
async def test_invalid_recall_result_keeps_assertions_and_usage(
    monkeypatch: pytest.MonkeyPatch, content: object
) -> None:
    from flaskr.service.learn.agent.engine import (
        ContentDelta,
        Engine,
        ToolCall,
        ToolResult,
        TurnDone,
    )

    async def invalid(*_args: object, **_kwargs: object) -> AsyncIterator[object]:
        yield ToolCall(id="current", name="recall", args={"key": "project_code"})
        yield ToolResult(id="current", name="recall", content=content)
        yield ContentDelta(text="MEMORY_UNAVAILABLE")
        yield TurnDone(reason="finished", usage={"requests": 1})

    monkeypatch.setattr(Engine, "run_turn", invalid)
    case = quality.load_cases(["recall-deleted-history"])[0]
    result = await quality.evaluate_recall(case, _recall_model())
    assert not result["passed"]
    assert result["error"] == "invalid_recall_result"
    assert not result["checks"]["valid_recall_results"]
    assert not result["checks"]["current_tool_result"]
    assert result["usage"] == {"requests": 1}
    assert result["recall_statuses"] == [None]
