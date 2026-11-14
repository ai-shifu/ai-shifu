#!/usr/bin/env python3
"""Evaluate course interactions with local replay or a fresh model response."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from collections import Counter, deque
from contextlib import ExitStack, asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic_ai.messages import ModelRequest, RetryPromptPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from pydantic_ai.models.wrapper import WrapperModel

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from markdownflow import Engine, InteractionRequest, QuestionRenderer, Session
    from pydantic_ai import RunContext
    from pydantic_ai.messages import ModelMessage, ModelResponse
    from pydantic_ai.models import Model, ModelRequestParameters, StreamedResponse
    from pydantic_ai.models.function import AgentInfo
    from pydantic_ai.settings import ModelSettings
    from pydantic_ai.usage import RequestUsage


API_DIR = Path(__file__).resolve().parents[1]
CASES_PATH = Path(__file__).with_name("mdf_interactions") / "cases.json"
PROMPTS_DIR = API_DIR / "markdownflow" / "engine" / "prompts"
STATUSES = (
    "first_attempt_pass",
    "recovered_pass",
    "expected_failure_replayed",
    "behavior_failure",
    "call_failure",
)
SCHEMA_VERSION = 3
MAX_AUTOMATIC_CONTINUATIONS = 8


class FixtureModel(BaseModel):
    """Only approved fixture fields are accepted."""

    model_config = ConfigDict(extra="forbid", strict=True)


class ExpectedQuestion(FixtureModel):
    """Expected authored control fields; unspecified fields are unconstrained."""

    type: Literal[
        "single", "multi", "text", "single_or_text", "multi_or_text", "confirm"
    ]
    question: str | None = None
    options: list[list[str]] | None = None
    variable: str | None = None
    placeholder: str | None = None

    @model_validator(mode="after")
    def validate_option_pairs(self) -> ExpectedQuestion:
        """Require display and submitted value for every asserted option."""
        if self.options is not None and any(
            len(option) != 2 for option in self.options
        ):
            msg = "expected options must be [display, value] pairs"
            raise ValueError(msg)
        return self


class ExpectedStep(FixtureModel):
    """Observable checks for one learner advancement."""

    outcome: Literal["interaction", "finished", "end", "error"]
    question: ExpectedQuestion | None = None
    question_count: int | None = Field(default=None, ge=0)
    prose_question: str | None = Field(default=None, min_length=1)
    prose_contains: list[str] = Field(default_factory=list)
    prose_once: list[str] = Field(default_factory=list)
    replay_prose_once: list[str] = Field(default_factory=list)
    prose_excludes: list[str] = Field(default_factory=list)
    memory: dict[str, str] | None = None
    asked_before: bool | None = None
    retryable_error: bool = False
    narrated_control: str | None = None
    pending: int | None = Field(default=None, ge=0)
    retries: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_question_outcome(self) -> ExpectedStep:
        """Require question expectations to match the outcome."""
        if self.question is not None and self.outcome != "interaction":
            msg = "expected question requires an interaction outcome"
            raise ValueError(msg)
        if self.prose_question is not None and (
            self.outcome != "interaction" or not self.prose_question.strip()
        ):
            msg = "expected prose question requires nonblank intent and an interaction outcome"
            raise ValueError(msg)
        if self.question_count is not None and (
            (self.question_count > 0) != (self.outcome == "interaction")
        ):
            msg = "only an interaction outcome can expect one or more questions"
            raise ValueError(msg)
        return self


class Step(FixtureModel):
    """A sanitized learner action and its live and optional replay expectations."""

    action: Literal["start", "answer", "continue", "message"]
    values: list[str] = Field(default_factory=list)
    text: str | None = None
    reload: bool = False
    expected: ExpectedStep
    replay_expected: ExpectedStep | None = None

    @model_validator(mode="after")
    def validate_input(self) -> Step:
        """Reject action inputs that the course engine would ignore."""
        if self.action != "answer" and self.values:
            msg = "only an answer may submit option values"
            raise ValueError(msg)
        if self.action in {"start", "continue"} and self.text is not None:
            msg = "start and continue do not submit text"
            raise ValueError(msg)
        if self.action == "message" and not self.text:
            msg = "message requires text"
            raise ValueError(msg)
        return self


class ReplayCall(FixtureModel):
    """A tool call with a reconstructed argument object or original failure shape."""

    name: str = Field(min_length=1)
    args: dict[str, object] | str


class ReplayResponse(FixtureModel):
    """One recorded response, with text preceding the assembled tool calls."""

    text: str = ""
    calls: list[ReplayCall] = Field(default_factory=list)


class Case(FixtureModel):
    """A re-authored course path ready to replay or run against a candidate prompt."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    source: Literal["langfuse", "synthetic"]
    course: str | None = None
    tags: list[str] = Field(min_length=1)
    smoke: bool = False
    teaching_prompt: str = Field(min_length=1)
    course_prompt: str | None = None
    locale: Literal["zh-CN", "en-US", "fr-FR"] = "zh-CN"
    memory: dict[str, str] = Field(default_factory=dict)
    steps: list[Step] = Field(min_length=1)
    replay: list[ReplayResponse] = Field(min_length=1)
    replay_only: bool = False

    @model_validator(mode="after")
    def validate_path(self) -> Case:
        """Require a fresh start and an opaque course grouping for sampled cases."""
        if self.source == "langfuse" and not self.course:
            msg = "a Langfuse-derived case requires a course label"
            raise ValueError(msg)
        if self.steps[0].action != "start" or any(
            step.action == "start" for step in self.steps[1:]
        ):
            msg = "the first action must be the only start"
            raise ValueError(msg)
        return self


def load_cases(path: Path = CASES_PATH) -> list[Case]:
    """Load the catalog with strict field checks and unique case identifiers."""
    from pydantic import TypeAdapter

    try:
        cases = TypeAdapter(list[Case]).validate_json(path.read_bytes())
    except ValidationError as error:
        # Do not print the rejected content, which can be an accidental raw export.
        details = ", ".join(
            ".".join(map(str, item["loc"])) + ": " + item["type"]
            for item in error.errors(include_input=False, include_context=False)[:8]
        )
        msg = f"invalid fixture catalog fields: {details}"
        raise ValueError(msg) from error
    identifiers = Counter(case.id for case in cases)
    if not cases or any(count > 1 for count in identifiers.values()):
        msg = "catalog must be non-empty and case IDs must be unique"
        raise ValueError(msg)
    return cases


class ReplayExhaustedError(Exception):
    """The engine requested more generations than the fixture provides."""


class Replay:
    """Stream fixture responses through the same native model interface as live runs."""

    def __init__(self, responses: list[ReplayResponse]) -> None:
        """Keep an independent generation queue per case run."""
        self.responses = deque(responses)
        self.requests = 0
        self.model = FunctionModel(stream_function=self._stream, model_name="replay")

    async def _stream(
        self, _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        self.requests += 1
        if not self.responses:
            msg = "missing fixture response"
            raise ReplayExhaustedError(msg)
        response = self.responses.popleft()
        if response.text or not response.calls:
            yield response.text or "\n"
        if response.calls:
            yield {
                index: DeltaToolCall(
                    name=call.name,
                    tool_call_id=f"replay-{self.requests}-{index}",
                    json_args=(
                        call.args
                        if isinstance(call.args, str)
                        else json.dumps(call.args)
                    ),
                )
                for index, call in enumerate(response.calls)
            }


class ObservedModel(WrapperModel):
    """Observe teaching calls without retaining provider exception messages or prompts."""

    def __init__(self, model: Model) -> None:
        """Wrap a model with run-local diagnostics."""
        super().__init__(model)
        self.failures: list[str] = []
        self.requests = 0
        self.retries = 0
        self.instruction_hashes: set[str] = set()
        self.usage: dict[str, int] = {}

    def _begin(self, messages: list[ModelMessage]) -> None:
        self.requests += 1
        last_request = messages[-1] if messages else None
        if isinstance(last_request, ModelRequest) and any(
            isinstance(part, RetryPromptPart) for part in last_request.parts
        ):
            self.retries += 1
        instructions = next(
            (
                message.instructions
                for message in reversed(messages)
                if isinstance(message, ModelRequest) and message.instructions
            ),
            None,
        )
        if instructions:
            self.instruction_hashes.add(sha256(instructions.encode("utf-8")))

    def _record_usage(self, usage: RequestUsage) -> None:
        from markdownflow.engine.usage import accumulate_usage

        self.usage = accumulate_usage(self.usage, usage)

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        """Count a non-streamed request, including an auxiliary admission call."""
        self._begin(messages)
        try:
            result = await super().request(
                messages, model_settings, model_request_parameters
            )
        except Exception as error:
            self.failures.append(type(error).__name__)
            raise
        self._record_usage(result.usage)
        return result

    @asynccontextmanager
    async def request_stream(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
        run_context: RunContext[object] | None = None,
    ) -> AsyncIterator[StreamedResponse]:
        """Count requests and distinguish provider errors from interaction failures."""
        self._begin(messages)
        try:
            async with super().request_stream(
                messages, model_settings, model_request_parameters, run_context
            ) as response:
                try:
                    yield response
                finally:
                    self._record_usage(response.usage)
        except Exception as error:
            self.failures.append(type(error).__name__)
            raise


def sha256(value: bytes) -> str:
    """Hash fixture data or the exact prompt instructions submitted to a model."""
    return hashlib.sha256(value).hexdigest()


def renderer_for(locale: str) -> QuestionRenderer:
    """Use the backend's shared locale strings without starting the app."""
    from markdownflow import QuestionLabels, QuestionRenderer

    strings = json.loads(
        (API_DIR.parent / "i18n" / locale / "modules/backend/learn.json").read_text(
            encoding="utf-8"
        )
    )["__flat__"]
    return QuestionRenderer(
        QuestionLabels(
            continue_label=strings["continueButton"],
            free_text_placeholder=strings["freeTextPlaceholder"],
        )
    )


def course_engine(
    model: ObservedModel, renderer: QuestionRenderer, temperature: float, *, live: bool
) -> Engine:
    """Match the teaching options in lesson_entry without attaching business stores."""
    from flaskr.service.learn.agent.memory_admission import make_request_check
    from flaskr.service.memory.course_references import (
        COURSE_REFERENCE_PREFIX,
        SHARED_ANSWER_PREFIX,
    )
    from flaskr.service.profile.constants import ACTIVE_SYSTEM_PROFILE_KEYS
    from markdownflow import Engine

    return Engine(
        model,
        memory_admission=True,
        memory_context_limit=32_768,
        memory_recall=True,
        exercise_statistics=True,
        feedback_contract=True,
        memory_reserved_keys=ACTIVE_SYSTEM_PROFILE_KEYS,
        allowed_authored_question_keys=ACTIVE_SYSTEM_PROFILE_KEYS,
        memory_readonly_prefixes=(COURSE_REFERENCE_PREFIX, SHARED_ANSWER_PREFIX),
        memory_request_check=make_request_check(model) if live else None,
        model_settings={"temperature": temperature},
        interaction_check=renderer.unrenderable_reason,
        pauses_from_notation=True,
    )


def question_details(
    request: InteractionRequest, renderer: QuestionRenderer
) -> dict[str, object]:
    """Read option pairs and placeholder from the actual rendered controls."""
    from markdownflow import InteractionParser

    title, controls = renderer.render_question(request.spec)
    parsed = InteractionParser().parse(controls) or {}
    return {
        "type": request.spec.type,
        "question": request.spec.question,
        "title": title,
        "options": [
            [option["display"], option["value"]] for option in parsed.get("buttons", [])
        ],
        "variable": parsed.get("variable"),
        "placeholder": parsed.get("question"),
        "controls": controls,
        "asked_before": request.asked_before,
    }


def step_failures(
    expected: ExpectedStep, result: dict[str, object], *, replay: bool = False
) -> list[str]:
    """Check the stage outcome, controls, visible prose, and memory independently."""
    failures = [
        field
        for field in ("outcome", "retryable_error")
        if getattr(expected, field) != result[field]
    ]
    for field in ("pending", "memory", "retries"):
        value = getattr(expected, field)
        if value is not None and value != result[field]:
            failures.append(field)
    expected_count = expected.question_count
    if expected_count is None:
        expected_count = int(expected.outcome == "interaction")
    actual_count = len(result["questions"])
    if actual_count != expected_count:
        if actual_count == 0:
            failures.append("missing_question")
        elif expected_count == 0:
            failures.append("unexpected_question")
        else:
            failures.append("question_count")
    question = result["question"]
    if expected.outcome == "interaction" and isinstance(question, dict):
        fields = (
            expected.question.model_dump(exclude_unset=True)
            if expected.question
            else {}
        )
        for key, value in fields.items():
            if question[key] != value:
                failures.append(f"question.{key}")
        if expected.asked_before is not None and (
            expected.asked_before != question["asked_before"]
        ):
            failures.append("question.asked_before")
    prose = str(result["prose"])
    failures.extend(
        f"prose_contains[{i}]"
        for i, text in enumerate(expected.prose_contains)
        if text not in prose
    )
    once = expected.prose_once + (expected.replay_prose_once if replay else [])
    failures.extend(
        f"prose_once[{i}]" for i, text in enumerate(once) if prose.count(text) != 1
    )
    failures.extend(
        f"prose_excludes[{i}]"
        for i, text in enumerate(expected.prose_excludes)
        if text in prose
    )
    narrated = [expected.narrated_control] if expected.narrated_control else []
    if result["narrated_controls"] != narrated:
        failures.append("narrated_controls")
    return failures


async def run_step(
    engine: Engine,
    session: Session,
    step: Step,
    expected: ExpectedStep,
    renderer: QuestionRenderer,
    *,
    live: bool = False,
) -> dict[str, object]:
    """Advance one learner action through the portable course engine."""
    from flaskr.service.learn.agent.echoed_memory import strip_echoed_memory
    from flaskr.service.learn.agent.interaction_syntax import InteractionSyntaxFilter
    from markdownflow import (
        ContentDelta,
        ContinueTurn,
        ErrorEvent,
        InteractionRequest,
        InteractionResponseTurn,
        MemoryUpdated,
        MessageTurn,
        StartTurn,
        TurnDone,
    )

    if step.action == "start":
        turn = StartTurn()
    elif step.action == "answer":
        turn = InteractionResponseTurn(values=step.values, text=step.text)
    elif step.action == "message":
        turn = MessageTurn(text=step.text or "")
    else:
        turn = ContinueTurn()
    turn_outcomes = []
    prose = []
    narrated_controls = []
    questions = []
    updates = []
    errors = []
    retryable_error = False
    continuation_limit_reached = False
    for attempt in range(MAX_AUTOMATIC_CONTINUATIONS + 1):
        text = []
        outcome = "error"
        async for event in engine.run_turn(session, turn):
            if isinstance(event, ContentDelta):
                text.append(event.text)
            elif isinstance(event, InteractionRequest):
                questions.append(question_details(event, renderer))
            elif isinstance(event, MemoryUpdated):
                updates.append(event.model_dump(mode="json"))
            elif isinstance(event, ErrorEvent):
                retryable_error |= event.retryable
                errors.append(event.error_type or event.code or "turn_error")
            elif isinstance(event, TurnDone):
                outcome = event.reason
        syntax = InteractionSyntaxFilter()
        raw_text = "".join(text)
        if live:
            raw_text = strip_echoed_memory(raw_text)
        visible = syntax.feed(raw_text) + syntax.flush()
        prose.append(visible)
        narrated_controls.extend(syntax.spans)
        turn_outcomes.append(outcome)
        if (
            not live
            or outcome != "end"
            or not visible.strip()
            or syntax.spans
            or questions
            or session.pending
            or errors
        ):
            break
        if attempt == MAX_AUTOMATIC_CONTINUATIONS:
            continuation_limit_reached = True
            break
        # The host continues teaching without submitting the learner's answer again.
        turn = ContinueTurn()
    result: dict[str, object] = {
        "action": step.action,
        "reloaded": step.reload,
        "outcome": outcome,
        "question": questions[0] if questions else None,
        "questions": questions,
        "pending": len(session.pending),
        "prose": "\n\n".join(text for text in prose if text),
        "narrated_controls": narrated_controls,
        "memory": session.all_memory(),
        "memory_updates": updates,
        "retryable_error": retryable_error,
        "errors": errors,
        "turn_outcomes": turn_outcomes,
        "automatic_continuations": len(turn_outcomes) - 1,
        "continuation_limit_reached": continuation_limit_reached,
        "expected": expected.model_dump(mode="json", exclude_unset=True),
    }
    return result


async def check_prose_question(
    intended_question: str, prose: str, judge: ObservedModel
) -> tuple[dict[str, object], str | None]:
    """Return a visible-question judgment and any failure to report for the step."""
    from scripts.mdf_interaction_question_judge import judge_question

    if not prose.strip():
        return {"asked": False, "reason": "No learner-facing prose."}, "prose_question"
    try:
        judgment = await judge_question(
            judge, intended_question=intended_question, prose=prose
        )
    except Exception as error:
        return {"error": type(error).__name__}, "question_judge_call"
    return judgment.model_dump(
        mode="json"
    ), None if judgment.asked else "prose_question"


async def evaluate_case(
    case: Case,
    model: Model | None = None,
    temperature: float = 0.0,
    *,
    repeat: int = 1,
    judge_model: Model | None = None,
) -> dict[str, object]:
    """Replay or regenerate a fixture and stop at its first failed advancement."""
    from markdownflow import ScriptBundle, Session

    started = time.monotonic()
    replay = Replay(case.replay) if model is None else None
    observed = ObservedModel(replay.model if replay is not None else model)
    judge = ObservedModel(judge_model or model) if model is not None else None
    renderer = renderer_for(case.locale)
    engine = course_engine(observed, renderer, temperature, live=replay is None)
    session = await engine.new_session(
        ScriptBundle(script=case.teaching_prompt, constraints=case.course_prompt),
        memory=case.memory,
    )
    steps = []
    failures = []
    judge_failed = False
    automatic_continuations = 0
    for index, step in enumerate(case.steps, start=1):
        if step.reload:
            session = Session.loads(session.dumps())
        if replay is None and index > 1:
            # The teaching host constructs the admission checker per advancement.
            from flaskr.service.learn.agent.memory_admission import make_request_check

            engine.memory_request_check = make_request_check(observed)
        expected = (
            (step.replay_expected or step.expected)
            if replay is not None
            else step.expected
        )
        prior_retries = observed.retries
        result = await run_step(
            engine, session, step, expected, renderer, live=replay is None
        )
        automatic_continuations += result["automatic_continuations"]
        result["stage"] = index
        result["retries"] = observed.retries - prior_retries
        result["failures"] = step_failures(expected, result, replay=replay is not None)
        if result["continuation_limit_reached"]:
            result["failures"].append("continuation_limit")
        if expected.prose_question is not None:
            if judge is None:
                result["question_judgment"] = {"status": "skipped_offline"}
            elif not result["failures"] and not observed.failures:
                judgment, failure = await check_prose_question(
                    expected.prose_question, result["prose"], judge
                )
                result["question_judgment"] = judgment
                if failure is not None:
                    result["failures"].append(failure)
                    judge_failed = failure == "question_judge_call"
        steps.append(result)
        failures.extend(f"step_{index}.{name}" for name in result["failures"])
        if failures or observed.failures:
            break
    if replay is not None and not failures and replay.responses:
        failures.append("unused_replay_responses")
    reproduced_failure = replay is not None and any(
        step.replay_expected is not None
        and step.replay_expected.outcome != step.expected.outcome
        and step.replay_expected.outcome in {"error", "end"}
        for step in case.steps[: len(steps)]
    )
    if judge_failed:
        status = "call_failure"
    elif observed.failures:
        status = "call_failure" if replay is None else "behavior_failure"
        failures.extend(observed.failures)
    elif failures:
        status = "behavior_failure"
    elif reproduced_failure:
        status = "expected_failure_replayed"
    else:
        status = (
            "recovered_pass"
            if observed.retries or automatic_continuations
            else "first_attempt_pass"
        )
    return {
        "case_id": case.id,
        "course": case.course,
        "source": case.source,
        "tags": case.tags,
        "repeat": repeat,
        "status": status,
        "steps": steps,
        "failures": failures,
        "model_requests": observed.requests,
        "retries": observed.retries,
        "automatic_continuations": automatic_continuations,
        "usage": observed.usage,
        "question_judge_requests": judge.requests if judge is not None else 0,
        "question_judge_usage": judge.usage if judge is not None else {},
        "instruction_sha256": sorted(observed.instruction_hashes),
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }


def compare_reports(baseline: dict, candidate: dict) -> dict[str, object]:
    """Compare each matched run and reject mismatched inputs or report versions."""

    def rows(report: dict) -> dict[tuple[str, int], dict]:
        result = {(row["case_id"], row["repeat"]): row for row in report["results"]}
        if len(result) != len(report["results"]):
            msg = "duplicate result in report"
            raise ValueError(msg)
        return result

    baseline_rows = rows(baseline)
    candidate_rows = rows(candidate)
    mismatches = [
        key
        for key in (
            "schema_version",
            "mode",
            "model",
            "temperature",
            "question_judge",
            "cases_sha256",
        )
        if baseline.get(key) != candidate.get(key)
    ]
    if baseline_rows.keys() != candidate_rows.keys():
        mismatches.append("result_set")
    return {
        "compatible": not mismatches,
        "mismatches": mismatches,
        "prompt_changed": baseline.get("prompt_sha256")
        != candidate.get("prompt_sha256"),
        "changes": [
            {
                "case_id": key[0],
                "repeat": key[1],
                "baseline_status": before["status"],
                "candidate_status": after["status"],
                "baseline_failures": before["failures"],
                "candidate_failures": after["failures"],
                "baseline_retries": before["retries"],
                "candidate_retries": after["retries"],
                "baseline_automatic_continuations": before["automatic_continuations"],
                "candidate_automatic_continuations": after["automatic_continuations"],
                "instructions_changed": before["instruction_sha256"]
                != after["instruction_sha256"],
                "baseline_steps": before["steps"],
                "candidate_steps": after["steps"],
            }
            for key, before in baseline_rows.items()
            if not mismatches and (after := candidate_rows[key])
        ],
    }


async def run_cases(
    cases: list[Case],
    model: Model | None,
    temperature: float,
    repeats: int,
    *,
    judge_model: Model | None = None,
) -> list[dict[str, object]]:
    """Run selected fixtures serially, giving each repeat a clean session."""
    results = []
    for case in cases:
        for repeat in range(1, repeats + 1):
            result = await evaluate_case(
                case, model, temperature, repeat=repeat, judge_model=judge_model
            )
            results.append(result)
            details = ", ".join(result["failures"])
            suffix = f" ({details})" if details else ""
            print(f"{case.id} [{repeat}] {result['status']}{suffix}", flush=True)
    return results


def select_cases(
    catalog: list[Case], ids: list[str], suite: str, *, live: bool
) -> tuple[list[Case], list[str]]:
    """Select the requested suite and report replay-only fixtures skipped in live mode."""
    unknown = set(ids) - {case.id for case in catalog}
    if unknown:
        msg = "unknown case IDs: " + ", ".join(sorted(unknown))
        raise ValueError(msg)
    selected = [
        case
        for case in catalog
        if (suite == "all" or case.smoke) and (not ids or case.id in ids)
    ]
    skipped = [case.id for case in selected if live and case.replay_only]
    cases = [case for case in selected if case.id not in skipped]
    if not cases:
        msg = "case selection is empty"
        raise ValueError(msg)
    return cases, skipped


def main(argv: list[str] | None = None) -> int:
    """Run the local interaction evaluator and optionally compare a prior JSON report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases", type=Path, default=CASES_PATH, help="fixture catalog"
    )
    parser.add_argument("--suite", choices=("all", "smoke"), default="all")
    parser.add_argument("--case", action="append", default=[], help="select a case ID")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument(
        "--live", action="store_true", help="call a configured provider"
    )
    parser.add_argument("--model", help="physical provider model ID for a live run")
    parser.add_argument(
        "--judge-model", help="model ID for live question checks (defaults to --model)"
    )
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--json", type=Path, help="write the report to this file")
    parser.add_argument("--compare", type=Path, help="compare a prior JSON report")
    parser.add_argument("--list", action="store_true", help="list matching cases")
    args = parser.parse_args(argv)
    if args.repeat < 1 or not 0 <= args.temperature <= 2:
        parser.error(
            "--repeat must be positive and --temperature must be between 0 and 2"
        )
    if args.live != bool(args.model):
        parser.error("--live and --model must be supplied together")
    if args.judge_model is not None and not args.live:
        parser.error("--judge-model requires --live")
    if args.judge_model is not None and not args.judge_model.strip():
        parser.error("--judge-model must be nonblank")
    if args.json and args.json.resolve() == args.cases.resolve():
        parser.error("--json must not overwrite the fixture catalog")
    if args.json and args.compare and args.json.resolve() == args.compare.resolve():
        parser.error("--json and --compare must use different files")

    try:
        cases, skipped = select_cases(
            load_cases(args.cases), args.case, args.suite, live=args.live
        )
        if args.list:
            for case in cases:
                print(f"{case.id}\t{case.source}\t{', '.join(case.tags)}")
            return 0

        baseline = json.loads(args.compare.read_bytes()) if args.compare else None
        prompt_hashes = {
            path.name: sha256(path.read_bytes())
            for path in sorted(PROMPTS_DIR.glob("*.md"))
        }
        judge_config = None
        with ExitStack() as stack:
            model = judge_model = None
            if args.live:
                from scripts.mdf_interaction_live import build_live_model
                from scripts.mdf_interaction_question_judge import (
                    QUESTION_JUDGE_INSTRUCTIONS,
                )

                model = stack.enter_context(build_live_model(args.model))
                judge_model = model
                if args.judge_model and args.judge_model != args.model:
                    judge_model = stack.enter_context(
                        build_live_model(args.judge_model)
                    )
                judge_config = {
                    "model": judge_model.model_name,
                    "instructions_sha256": sha256(
                        QUESTION_JUDGE_INSTRUCTIONS.encode("utf-8")
                    ),
                }
            results = asyncio.run(
                run_cases(
                    cases, model, args.temperature, args.repeat, judge_model=judge_model
                )
            )
            model_name = model.model_name if model is not None else None
        statuses = Counter(row["status"] for row in results)
        report = {
            "schema_version": SCHEMA_VERSION,
            "mode": "live" if args.live else "offline",
            "model": model_name,
            "temperature": args.temperature,
            "question_judge": judge_config,
            "prompt_sha256": prompt_hashes,
            "cases_sha256": sha256(
                json.dumps(
                    [case.model_dump(mode="json") for case in cases], sort_keys=True
                ).encode()
            ),
            "results": results,
            "summary": {status: statuses[status] for status in STATUSES},
            "skipped_replay_only": skipped,
        }
        if baseline is not None:
            comparison = compare_reports(baseline, report)
            report["comparison"] = comparison
            if comparison["compatible"]:
                for change in comparison["changes"]:
                    print(
                        f"{change['case_id']} [{change['repeat']}] "
                        f"{change['baseline_status']} -> {change['candidate_status']}"
                    )
            else:
                print(
                    "Reports differ in " + ", ".join(comparison["mismatches"]),
                    file=sys.stderr,
                )
        if args.json:
            args.json.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Evaluation could not run: {error}", file=sys.stderr)
        return 2

    print("  ".join(f"{status}={count}" for status, count in report["summary"].items()))
    if statuses["call_failure"] or (
        baseline is not None and not report["comparison"]["compatible"]
    ):
        return 2
    return int(statuses["behavior_failure"] > 0)


if __name__ == "__main__":
    sys.path.insert(0, str(API_DIR))
    raise SystemExit(main())
