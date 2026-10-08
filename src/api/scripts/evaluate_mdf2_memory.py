#!/usr/bin/env python3
"""Evaluate synthetic memory cases through the selected course's existing gateway.

Listing cases requires no app, network or credentials. Live evaluation uses no
profile/session persistence path; existing gateway billing and tracing still run.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from flaskr.service.learn.agent.engine import Session
    from pydantic_ai import RunContext
    from pydantic_ai.messages import ModelMessage, ModelResponse
    from pydantic_ai.models import Model, ModelRequestParameters, StreamedResponse
    from pydantic_ai.settings import ModelSettings

API_DIR = Path(__file__).resolve().parents[1]
CASES_PATH = Path(__file__).with_name("mdf2_memory_quality") / "cases.json"
OLD_CODE = "EVAL-PROJ-7319"
NEW_CODE = "EVAL-PROJ-8426"
RECALL_MODEL_SETTINGS = {"temperature": 0, "max_tokens": 512}


def load_cases(selected: list[str] | None = None) -> list[dict[str, Any]]:
    """Load the fixed catalog, rejecting unknown selections and duplicate IDs."""
    cases = json.loads(CASES_PATH.read_text())
    identifiers = [case["id"] for case in cases]
    if len(set(identifiers)) != len(identifiers):
        message = "duplicate evaluation case IDs"
        raise ValueError(message)
    unknown = set(selected or []) - set(identifiers)
    if unknown:
        raise ValueError("unknown evaluation cases: " + ", ".join(sorted(unknown)))
    return [case for case in cases if not selected or case["id"] in selected]


async def evaluate_admission(case: dict[str, Any], model: Model) -> dict[str, Any]:
    """Distinguish a semantic refusal from provider/structured-output failure."""
    from flaskr.service.learn.agent.engine.usage import accumulate_usage
    from flaskr.service.learn.agent.memory_admission import make_request_check
    from pydantic_ai.messages import ToolCallPart
    from pydantic_ai.models.wrapper import WrapperModel

    class ObservedModel(WrapperModel):
        responses: list[tuple[ModelResponse, set[str]]]

        def __init__(self) -> None:
            super().__init__(model)
            self.responses = []

        async def request(
            self,
            messages: list[ModelMessage],
            model_settings: ModelSettings | None,
            model_request_parameters: ModelRequestParameters,
        ) -> ModelResponse:
            response = await super().request(
                messages, model_settings, model_request_parameters
            )
            names = {tool.name for tool in model_request_parameters.output_tools}
            self.responses.append((response, names))
            return response

    observed = ObservedModel()
    allowed = await make_request_check(observed)(
        case["request"], case["key"], case["value"]
    )
    valid = False
    usage: dict[str, int] = {}
    for response, names in observed.responses:
        usage = accumulate_usage(usage, response.usage)
        calls = [part for part in response.parts if isinstance(part, ToolCallPart)]
        if (
            len(observed.responses) == 1
            and len(calls) == 1
            and calls[0].tool_name in names
        ):
            args = calls[0].args_as_dict()
            valid = (
                set(args) == {"allowed"}
                and type(args["allowed"]) is bool
                and args["allowed"] is allowed
            )
    return {
        "passed": valid and allowed is case["allowed"],
        "error": None if valid else "judge_response_unavailable_or_invalid",
        "expected": case["allowed"],
        "observed": allowed if valid else None,
        "usage": usage,
    }


def recall_session(case: dict[str, Any]) -> Session:
    """Build a synthetic current snapshot plus deliberately stale historical evidence."""
    from flaskr.service.learn.agent.engine import ScriptBundle, Session
    from flaskr.service.learn.agent.engine.script import render_first_prompt
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        TextPart,
        ToolCallPart,
        ToolReturnPart,
        UserPromptPart,
    )

    bundle = ScriptBundle(
        script=(
            ("Collect %{{project_code}} first. " if case.get("answered") else "")
            + "Help the learner review their project setup. Answer their project-code "
            "question. Give the project code exactly once if known, or say "
            "MEMORY_UNAVAILABLE if the information is unavailable. Do not ask a "
            "follow-up question. Then finish."
        )
    )
    snapshot = {"project_code": OLD_CODE + " " * 500}
    mode = case["mode"]
    if mode == "updated":
        snapshot["project_code"] = NEW_CODE + " " * 500
    elif mode == "deleted":
        snapshot = {}
    elif mode == "oversized":
        snapshot["project_code"] = "X" * 9000
    messages = []
    if mode in {"updated", "deleted"}:
        messages = [
            ModelRequest(
                parts=[
                    UserPromptPart(
                        render_first_prompt(
                            bundle,
                            {"project_code": OLD_CODE + " " * 500},
                            memory_limit=100,
                        )
                    )
                ]
            ),
            ModelResponse(
                parts=[ToolCallPart("recall", {"key": "project_code"}, "old")]
            ),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        "recall",
                        json.dumps({"status": "found", "value": OLD_CODE}),
                        "old",
                    )
                ]
            ),
            ModelResponse(parts=[TextPart(OLD_CODE)]),
        ]
        if case.get("answered"):
            messages[1:1] = [
                ModelResponse(
                    parts=[
                        ToolCallPart(
                            "interact",
                            {
                                "type": "text",
                                "prompt": "Project code?",
                                "variable": "project_code",
                            },
                            "project-question",
                        )
                    ]
                ),
                ModelRequest(
                    parts=[
                        ToolReturnPart(
                            "interact", "Learner wrote: " + OLD_CODE, "project-question"
                        )
                    ]
                ),
            ]
    session = Session(
        script=bundle,
        user_memory=snapshot,
        memory=dict(snapshot) if case.get("answered") else {},
        messages=messages,
        initial_variables={} if messages else None,
        turn=1 if messages else 0,
    )
    if case.get("answered"):
        for key, value in snapshot.items():
            session.record_answer(key, value)
        return Session.loads(session.dumps())
    return session


def parse_recall_result(content: object) -> dict | None:
    """Decode a recognized tool result without leaking raw invalid content."""
    try:
        value = json.loads(content)
    except (TypeError, ValueError):
        return None
    if isinstance(value, dict) and value.get("status") in (
        "found",
        "keys",
        "unavailable",
        "too_large",
        "invalid_offset",
    ):
        return value
    return None


def current_recall_evidence(case: dict[str, Any], events: list) -> bool:
    """Require a paired relevant read before the answer, with no conflicting reads."""
    from flaskr.service.learn.agent.engine import ContentDelta, ToolCall, ToolResult

    calls = {}
    reads = []
    text = ""
    answer_at = None
    for index, event in enumerate(events):
        if isinstance(event, ToolCall) and event.name == "recall":
            calls[event.id] = event.args
        elif isinstance(event, ToolResult) and event.name == "recall":
            args = calls.get(event.id, {})
            if args.get("key") == "project_code":
                reads.append((index, parse_recall_result(event.content)))
        elif isinstance(event, ContentDelta):
            text += event.text
            if answer_at is None and case["expected"] in text:
                answer_at = index
    return (
        answer_at is not None
        and any(index < answer_at for index, _ in reads)
        and all(
            result is not None
            and result.get("status") == case["status"]
            and (
                case["status"] != "found"
                or str(result.get("value", "")).strip() == case["expected"]
            )
            for _, result in reads
        )
    )


async def evaluate_recall(case: dict[str, Any], model: Model) -> dict[str, Any]:
    """Score real engine tools, exact learner output, and read-only memory behavior."""
    from flaskr.service.learn.agent.engine import (
        ContentDelta,
        ContinueTurn,
        Engine,
        ErrorEvent,
        MemoryUpdated,
        MessageTurn,
        ToolResult,
        TurnDone,
    )
    from pydantic_ai.messages import ModelMessagesTypeAdapter

    session = recall_session(case)
    original = dict(session.user_memory)
    original_session_memory = dict(session.memory)
    original_answer_hashes = dict(session.answer_hashes)
    history_len = len(session.messages)
    original_messages = ModelMessagesTypeAdapter.dump_json(session.messages)
    engine = Engine(
        model,
        memory_admission=True,
        memory_recall=True,
        memory_context_limit=100,
        recall_history_compaction=True,
        request_limit=6,
        model_settings=dict(RECALL_MODEL_SETTINGS),
    )
    events = [
        event
        async for event in engine.run_turn(
            session,
            MessageTurn(text="What is my project code?"),
            memory_deleted_keys=(
                frozenset({"project_code"})
                if case["mode"] == "deleted"
                else frozenset()
            ),
        )
    ]
    # Like the classroom host, carry on an unpaused content turn once so the
    # model can finish; never retry a failed answer or answer an interaction.
    if (
        events
        and isinstance(events[-1], TurnDone)
        and events[-1].reason == "end"
        and any(
            isinstance(event, ContentDelta) and event.text.strip() for event in events
        )
        and not any(isinstance(event, ErrorEvent) for event in events)
    ):
        events.extend(
            [event async for event in engine.run_turn(session, ContinueTurn())]
        )
    text = "".join(event.text for event in events if isinstance(event, ContentDelta))
    results = [
        parse_recall_result(event.content)
        for event in events
        if isinstance(event, ToolResult) and event.name == "recall"
    ]
    done = [event for event in events if isinstance(event, TurnDone)]
    errors = [event for event in events if isinstance(event, ErrorEvent)]
    checks = {
        "expected_answer": text.count(case["expected"]) == 1,
        "exact_code_only": re.findall(r"\bEVAL-PROJ-\d+\b", text)
        == ([case["expected"]] if case["status"] == "found" else []),
        "current_tool_result": current_recall_evidence(case, events),
        "no_stale_code": case["mode"] not in {"updated", "deleted"}
        or OLD_CODE not in text,
        "memory_unchanged": session.user_memory == original
        and session.memory == original_session_memory,
        "no_memory_events": not any(isinstance(e, MemoryUpdated) for e in events),
        "answer_ownership_unchanged": session.answer_hashes == original_answer_hashes,
        "history_preserved": ModelMessagesTypeAdapter.dump_json(
            session.messages[:history_len]
        )
        == original_messages,
        "completed": bool(done) and done[-1].reason == "finished",
        "no_engine_errors": not errors,
        "valid_recall_results": all(result is not None for result in results),
    }
    return {
        "passed": all(checks.values()),
        "error": (
            "engine_error"
            if errors
            else "invalid_recall_result"
            if any(result is None for result in results)
            else None
        ),
        "checks": checks,
        "usage": done[-1].usage if done else {},
        "recall_statuses": [
            result.get("status") if result else None for result in results
        ],
    }


def teaching_session(case: dict[str, Any]) -> Session:
    """Hide an exact older example between excerpt boundaries and two recent turns."""
    from flaskr.service.learn.agent.engine import ScriptBundle
    from flaskr.service.learn.agent.engine.script import render_first_prompt
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        TextPart,
        UserPromptPart,
    )

    session = recall_session(case)
    session.script = ScriptBundle(
        script="Review the earlier lesson with the learner. Answer their question. "
        "Give the requested code exactly once if known, otherwise say MEMORY_UNAVAILABLE. "
        "Do not ask a follow-up question. Then finish."
    )
    session.messages[0] = ModelRequest(
        parts=[
            UserPromptPart(
                render_first_prompt(
                    session.script,
                    {"project_code": OLD_CODE + " " * 500},
                    memory_limit=100,
                )
            )
        ]
    )
    paragraph = (
        "A worked example explains how to separate observations from assumptions. "
    )
    source = (
        paragraph * 40
        + "\nThe original worked example used project code "
        + OLD_CODE
        + ".\n"
        + paragraph * 40
    )
    session.messages[-1] = ModelResponse(parts=[TextPart(source)])
    session.messages.extend(
        [
            ModelRequest(parts=[UserPromptPart("Continue to the next concept.")]),
            ModelResponse(
                parts=[TextPart("Check assumptions before drawing a conclusion.")]
            ),
            ModelRequest(parts=[UserPromptPart("Explain the following concept.")]),
            ModelResponse(
                parts=[TextPart("Compare an observation with an independent check.")]
            ),
        ]
    )
    return session


def teaching_read_evidence(
    events: list, sources: dict[str, str], expected: str
) -> bool:
    """Require an exact original page containing the answer before learner output."""
    from flaskr.service.learn.agent.engine import ContentDelta, ToolCall, ToolResult

    calls = {}
    verified = False
    text = ""
    for event in events:
        if isinstance(event, ToolCall) and event.name == "read_teaching":
            calls[event.id] = event.args
        elif isinstance(event, ToolResult) and event.name == "read_teaching":
            args = calls.get(event.id, {})
            value = parse_recall_result(event.content)
            reference = args.get("reference")
            if (
                reference not in sources
                or value is None
                or value.get("status") != "found"
            ):
                continue
            offset, end = value.get("offset"), value.get("next_offset")
            page = value.get("text")
            if (
                value.get("reference") == reference
                and type(offset) is int
                and offset == args.get("offset", 0)
                and 0 <= offset <= len(sources[reference])
                and (
                    end is None
                    or (type(end) is int and offset < end < len(sources[reference]))
                )
                and isinstance(page, str)
                and page == sources[reference][offset:end]
                and expected in page
            ):
                verified = True
        elif isinstance(event, ContentDelta):
            text += event.text
            if expected in text:
                return verified
    return False


def observe_summary_usage(model: Model, totals: dict[str, int]) -> Model:
    """Record completed summary responses without changing model identity or requests."""
    from flaskr.service.learn.agent.engine.usage import accumulate_usage
    from pydantic_ai.models.wrapper import WrapperModel

    class ObservedSummaryModel(WrapperModel):
        """Observe the nonstreamed request path used by the production summary factory."""

        async def request(
            self,
            messages: list[ModelMessage],
            model_settings: ModelSettings | None,
            model_request_parameters: ModelRequestParameters,
        ) -> ModelResponse:
            """Retain the actual completed request usage separately from teaching."""
            response = await super().request(
                messages, model_settings, model_request_parameters
            )
            totals.update(accumulate_usage(totals, response.usage))
            return response

    return ObservedSummaryModel(model)


async def evaluate_teaching(
    case: dict[str, Any], model: Model, summary_model: Model
) -> dict[str, Any]:
    """Combine real summary generation, cache reload and current versus historical reads."""
    from flaskr.service.learn.agent.engine import (
        ContentDelta,
        ContinueTurn,
        Engine,
        ErrorEvent,
        MemoryUpdated,
        MessageTurn,
        Session,
        TurnDone,
    )
    from flaskr.service.learn.agent.engine.teaching_history import (
        project_teaching_history,
    )
    from flaskr.service.learn.agent.engine.teaching_summary import (
        TeachingSummarizer,
        summarize_teaching_history,
    )
    from flaskr.service.learn.agent.teaching_summary import make_teaching_summarizer
    from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelResponse, TextPart
    from pydantic_ai.models.wrapper import WrapperModel

    session = teaching_session(case)
    projected, sources = project_teaching_history(session.messages)
    summary_usage: dict[str, int] = {}
    provider = make_teaching_summarizer(
        observe_summary_usage(summary_model, summary_usage)
    )
    summary_calls = 0

    async def summarize(source: str) -> str | None:
        """Count one real summary attempt or an explicitly injected failure."""
        nonlocal summary_calls
        summary_calls += 1
        return None if case.get("summary_failure") else await provider.summarize(source)

    summarizer = TeachingSummarizer(policy=provider.policy, summarize=summarize)
    await summarize_teaching_history(
        projected, sources, session.teaching_summaries, summarizer
    )
    cache = dict(session.teaching_summaries)
    session = Session.loads(session.dumps())
    original = (
        dict(session.memory),
        dict(session.user_memory),
        dict(session.answer_hashes),
    )
    history_len = len(session.messages)
    original_history = ModelMessagesTypeAdapter.dump_json(session.messages)
    markers = set()

    class ObservedModel(WrapperModel):
        """Observe the actual request projection without changing model behavior."""

        @asynccontextmanager
        async def request_stream(
            self,
            messages: list[ModelMessage],
            model_settings: ModelSettings | None,
            model_request_parameters: ModelRequestParameters,
            run_context: RunContext[Any] | None = None,
        ) -> AsyncIterator[StreamedResponse]:
            """Record source-bound excerpt/summary markers sent to the model."""
            for message in messages:
                if not isinstance(message, ModelResponse):
                    continue
                for part in message.parts:
                    if not isinstance(part, TextPart):
                        continue
                    try:
                        marker = json.loads(part.content)
                    except ValueError:
                        continue
                    if (
                        isinstance(marker, dict)
                        and isinstance(marker.get("reference"), str)
                        and marker["reference"] in sources
                    ):
                        markers.add(marker.get("status"))
            async with super().request_stream(
                messages, model_settings, model_request_parameters, run_context
            ) as response:
                yield response

    engine = Engine(
        ObservedModel(model),
        memory_admission=True,
        memory_recall=True,
        memory_context_limit=100,
        recall_history_compaction=True,
        teaching_history_compaction=True,
        teaching_summarizer=summarizer,
        request_limit=6,
        model_settings=dict(RECALL_MODEL_SETTINGS),
    )
    events = [
        event
        async for event in engine.run_turn(session, MessageTurn(text=case["question"]))
    ]
    if (
        events
        and isinstance(events[-1], TurnDone)
        and events[-1].reason == "end"
        and any(isinstance(e, ContentDelta) and e.text.strip() for e in events)
        and not any(isinstance(e, ErrorEvent) for e in events)
    ):
        events.extend(
            [event async for event in engine.run_turn(session, ContinueTurn())]
        )
    text = "".join(e.text for e in events if isinstance(e, ContentDelta))
    done = [e for e in events if isinstance(e, TurnDone)]
    errors = [e for e in events if isinstance(e, ErrorEvent)]
    checks = {
        "expected_answer": text.count(case["expected"]) == 1,
        "exact_code_only": re.findall(r"\bEVAL-PROJ-\d+\b", text)
        == ([] if case["status"] == "unavailable" else [case["expected"]]),
        "paired_current_evidence": (
            teaching_read_evidence(events, sources, case["expected"])
            if case.get("historical")
            else current_recall_evidence(case, events)
        ),
        "expected_summary_outcome": len(cache) == 1
        and all(
            (not value) if case.get("summary_failure") else bool(value.strip())
            for value in cache.values()
        ),
        "cache_reused_after_reload": summary_calls == 1
        and session.teaching_summaries == cache,
        "history_projected": (
            "teaching_excerpt" if case.get("summary_failure") else "teaching_summary"
        )
        in markers,
        "memory_unchanged": original
        == (session.memory, session.user_memory, session.answer_hashes),
        "no_memory_events": not any(isinstance(e, MemoryUpdated) for e in events),
        "history_preserved": ModelMessagesTypeAdapter.dump_json(
            session.messages[:history_len]
        )
        == original_history,
        "completed": bool(done) and done[-1].reason == "finished",
        "no_engine_errors": not errors,
    }
    return {
        "passed": all(checks.values()),
        "error": "engine_error"
        if errors
        else (
            "summary_unavailable_or_invalid"
            if not case.get("summary_failure")
            and not checks["expected_summary_outcome"]
            else None
        ),
        "checks": checks,
        "usage": done[-1].usage if done else {},
        "summary_calls": summary_calls,
        "summary_usage": summary_usage,
        "injected_summary_failure": bool(case.get("summary_failure")),
    }


async def evaluate(
    cases: list[dict[str, Any]], model_factory: Callable[[str], Model], repeats: int
) -> list[dict[str, Any]]:
    """Keep cases and repetitions isolated; errors are results, never successful refusals."""
    results = []
    for repetition in range(1, repeats + 1):
        for case in cases:
            started = time.monotonic()
            try:
                model = model_factory(case["family"])
                if case["family"] == "teaching":
                    result = await evaluate_teaching(
                        case, model, model_factory("teaching_summary")
                    )
                else:
                    runner = (
                        evaluate_admission
                        if case["family"] == "admission"
                        else evaluate_recall
                    )
                    result = await runner(case, model)
            except Exception as exc:
                result = {"passed": False, "error": type(exc).__name__}
            results.append(
                {
                    "id": case["id"],
                    "family": case["family"],
                    "repetition": repetition,
                    "seconds": round(time.monotonic() - started, 3),
                    **result,
                }
            )
    return results


def report(
    cases: list[dict[str, Any]], results: list[dict[str, Any]], repeats: int
) -> dict:
    """Publish denominators and source fingerprints without prompts, answers or credentials."""
    expected = {(case["id"], n) for case in cases for n in range(1, repeats + 1)}
    observed = [(result["id"], result["repetition"]) for result in results]
    complete = (
        bool(expected) and len(observed) == len(expected) and set(observed) == expected
    )
    sources = {
        "scripts/evaluate_mdf2_memory.py": Path(__file__),
        "scripts/mdf2_memory_quality/cases.json": CASES_PATH,
    }
    for name in (
        "memory_admission.py",
        "run_agent.py",
        "gateway_model.py",
        "engine/engine.py",
        "engine/session.py",
        "engine/tools.py",
        "engine/script.py",
        "engine/recall.py",
        "engine/memory_context.py",
        "engine/history_context.py",
        "engine/usage.py",
        "engine/teaching_history.py",
        "engine/teaching_summary.py",
        "teaching_summary.py",
        "engine/prompts/system.md",
        "engine/prompts/memory_admission.md",
        "engine/prompts/memory_policy.md",
        "engine/prompts/memory_recall.md",
        "engine/prompts/recall_history_compaction.md",
        "engine/prompts/teaching_history_compaction.md",
        "engine/prompts/teaching_summary.md",
    ):
        relative = "flaskr/service/learn/agent/" + name
        sources[relative] = API_DIR / relative
    fingerprints = {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in sources.items()
    }
    return {
        "schema_version": 1,
        "usage_semantics": {
            "teaching": "SDK diagnostic totals; summary requests are separate",
            "summary": "Completed summary responses only; partial failures may be billed separately",
            "cache": "Provider prefix-cache reads; coverage counts only valid explicit reports, including zero",
            "cache_coverage": "Use matching cache_reported_read_tokens/cache_reported_input_tokens; missing coverage is unknown",
            "billing": "Use the shared gateway ledger/traces for prices and complete lesson cost",
        },
        "recall_generation_settings": dict(RECALL_MODEL_SETTINGS),
        "teaching_generation_settings": dict(RECALL_MODEL_SETTINGS),
        "teaching_summary_generation_settings": {
            "temperature": 0,
            "max_tokens": 256,
            "timeout_seconds": 8,
            "input_budget_bytes": 40_960,
        },
        "full_catalog": len(cases) == len(load_cases()),
        "selected_cases": [case["id"] for case in cases],
        "repeats": repeats,
        "expected_results": len(expected),
        "complete": complete,
        "passed": complete and all(result["passed"] for result in results),
        "passed_results": sum(result["passed"] for result in results),
        "error_results": sum(bool(result.get("error")) for result in results),
        "fingerprints": fingerprints,
        "results": results,
    }


def write_report(path: Path, value: dict) -> None:
    """Atomically replace a private report after a completed evaluation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".mdf2-quality-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
        Path(temporary).replace(path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def source_revision() -> str | None:
    """Return optional checkout metadata; deployed images need not contain Git."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=API_DIR,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def main(argv: list[str] | None = None) -> int:
    """Require explicit live execution and an accessible course in a 2.0 environment."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list", action="store_true", help="List synthetic cases without app startup"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Make billed requests via the course gateway",
    )
    parser.add_argument("--case", action="append", dest="selected")
    parser.add_argument("--repeat", type=int, choices=range(1, 6), default=1)
    parser.add_argument("--course")
    parser.add_argument("--lesson")
    parser.add_argument(
        "--learner", help="Dedicated temporary learner for gateway usage attribution"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(tempfile.gettempdir()) / "mdf2-memory-quality.json",
    )
    args = parser.parse_args(argv)
    try:
        cases = load_cases(args.selected)
    except ValueError as exc:
        parser.error(str(exc))
    if args.list:
        print(
            json.dumps(
                [{"id": c["id"], "family": c["family"]} for c in cases], indent=2
            )
        )
        return 0
    if not args.live or not all((args.course, args.lesson, args.learner)):
        parser.error(
            "live evaluation requires --live, --course, --lesson and --learner"
        )

    sys.path.insert(0, str(API_DIR))
    from app import create_app
    from flaskr.api.langfuse import (
        create_trace_with_root_span,
        finalize_langfuse_trace,
        get_langfuse_client,
    )
    from flaskr.api.llm.model_selection import resolve_selection
    from flaskr.service.learn.agent.gateway_model import GatewayModel
    from flaskr.service.learn.agent.lesson_entry import _resolve
    from flaskr.service.learn.agent.routing import uses_agent_engine
    from flaskr.service.user.models import UserInfo

    app = create_app(serving_http=False)
    with app.app_context():
        if not uses_agent_engine(args.course):
            parser.error(
                "live evaluation requires an environment already running engine 2.0"
            )
        if UserInfo.query.filter_by(user_bid=args.learner, deleted=0).first() is None:
            parser.error("the dedicated evaluation learner does not exist")
        _, _, settings = _resolve(
            app,
            user_bid=args.learner,
            shifu_bid=args.course,
            outline_bid=args.lesson,
            preview_mode=False,
        )
        resolved_model, usage_metadata = resolve_selection(
            settings.model, dict(settings.usage_metadata)
        )
        trace, span = create_trace_with_root_span(
            client=get_langfuse_client(),
            trace_payload={
                "name": "agent_memory_quality",
                "user_id": args.learner,
                "metadata": {"internal_acceptance": True, "flow_engine": "2.0"},
            },
            root_span_payload={"name": "agent_memory_quality"},
        )

        def model_factory(family: str) -> Model:
            return GatewayModel(
                app,
                resolved_model,
                user_id=args.learner,
                span=span,
                generation_name=f"agent_memory_quality_{family}",
                usage_metadata=dict(usage_metadata),
                timeout=8 if family == "teaching_summary" else 15,
                retry_deadline_seconds=8 if family == "teaching_summary" else 15,
                input_budget_bytes=40_960 if family == "teaching_summary" else 262_144,
                num_retries=0,
            )

        started_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        try:
            results = asyncio.run(evaluate(cases, model_factory, args.repeat))
            value = report(cases, results, args.repeat)
            value["started_at"] = started_at
            value["finished_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            value["model_selection"] = settings.model
            value["model"] = resolved_model
            value["source_commit"] = source_revision()
            write_report(args.output, value)
        finally:
            finalize_langfuse_trace(
                trace=trace,
                root_span=span,
                root_span_payload={"metadata": {"end_reason": "evaluation_ended"}},
            )
    print(
        json.dumps(
            {
                "report": str(args.output),
                "passed": value["passed"],
                "results": len(results),
            }
        )
    )
    return 2 if value["error_results"] else int(not value["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
