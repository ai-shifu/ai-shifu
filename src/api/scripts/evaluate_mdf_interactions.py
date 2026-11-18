#!/usr/bin/env python3
"""Evaluate course interactions with local replay or a fresh model response."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict, deque
from contextlib import ExitStack, asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic_ai.messages import ModelRequest, RetryPromptPart, TextPart, ToolCallPart
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
    "needs_review",
)
CRITERION_STATUSES = ("passed", "failed", "needs_review", "not_evaluated")
PROSE_JUDGMENTS = {
    "prose_question": ("question_judgment", "intended_question"),
    "prose_meaning": ("meaning_judgment", "required_meaning"),
}
SCHEMA_VERSION = 5
MAX_AUTOMATIC_CONTINUATIONS = 8


class FixtureModel(BaseModel):
    """Only approved fixture fields are accepted."""

    model_config = ConfigDict(extra="forbid", strict=True)


class ExpectedQuestion(FixtureModel):
    """Expected authored control fields; unspecified fields are unconstrained."""

    type: Literal["single", "multi", "text", "single_or_text", "multi_or_text"]
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
    prose_meaning: str | None = Field(
        default=None, min_length=1, exclude_if=lambda value: value is None
    )
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
    """Observe model calls without retaining provider errors, prompts, or reasoning."""

    def __init__(self, model: Model, *, record_calls: bool = False) -> None:
        """Wrap a model with run-local diagnostics."""
        super().__init__(model)
        self.failures: list[str] = []
        self.requests = 0
        self.retries = 0
        self.instruction_hashes: set[str] = set()
        self.usage: dict[str, int] = {}
        self.model_calls: list[dict[str, object]] | None = [] if record_calls else None

    def _begin(self, messages: list[ModelMessage]) -> dict[str, object] | None:
        self.requests += 1
        last_request = messages[-1] if messages else None
        retries = (
            [part for part in last_request.parts if isinstance(part, RetryPromptPart)]
            if isinstance(last_request, ModelRequest)
            else []
        )
        if retries:
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
        if self.model_calls is None:
            return None
        call: dict[str, object] = {"number": self.requests}
        if retries:
            call["retry_feedback"] = [
                {"tool": part.tool_name, "message": part.model_response()}
                for part in retries
            ]
        self.model_calls.append(call)
        return call

    def _record_response(
        self, call: dict[str, object], response: ModelResponse
    ) -> None:
        parts = []
        for part in response.parts:
            if isinstance(part, TextPart):
                parts.append({"text": part.content})
            elif isinstance(part, ToolCallPart):
                parts.append({"tool": part.tool_name, "arguments": part.args})
        call["parts"] = parts

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
        call = self._begin(messages)
        try:
            result = await super().request(
                messages, model_settings, model_request_parameters
            )
        except Exception as error:
            self.failures.append(type(error).__name__)
            if call is not None:
                call["error"] = self.failures[-1]
            raise
        self._record_usage(result.usage)
        if call is not None:
            self._record_response(call, result)
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
        call = self._begin(messages)
        try:
            async with super().request_stream(
                messages, model_settings, model_request_parameters, run_context
            ) as response:
                try:
                    yield response
                finally:
                    self._record_usage(response.usage)
                    if call is not None:
                        self._record_response(call, response.get())
        except Exception as error:
            self.failures.append(type(error).__name__)
            if call is not None:
                call["error"] = self.failures[-1]
            raise


def sha256(value: bytes) -> str:
    """Hash fixture data or the exact prompt instructions submitted to a model."""
    return hashlib.sha256(value).hexdigest()


def catalog_sha256(cases: list[Case]) -> str:
    """Fingerprint the selected fixtures using the report's canonical order."""
    return sha256(
        json.dumps(
            [case.model_dump(mode="json") for case in cases], sort_keys=True
        ).encode()
    )


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


def step_criteria(
    expected: ExpectedStep,
    result: dict[str, object] | None,
    *,
    replay: bool,
    call_failed: bool = False,
) -> dict[str, str]:
    """Record every configured check, including checks that could not run."""
    actual = result or {}
    criteria: dict[str, str] = {}

    def record(
        name: str, matched: bool | None, *, requires_model_response: bool = True
    ) -> None:
        if (
            result is None
            or matched is None
            or (call_failed and requires_model_response)
        ):
            criteria[name] = "not_evaluated"
        else:
            criteria[name] = "passed" if matched else "failed"

    for field in ("outcome", "retryable_error"):
        record(field, getattr(expected, field) == actual.get(field))
    if expected.memory is not None:
        # The engine may store the answer before requesting the next response.
        record(
            "memory",
            expected.memory == actual.get("memory"),
            requires_model_response=False,
        )
    for field in ("pending", "retries"):
        value = getattr(expected, field)
        if value is not None:
            record(field, value == actual.get(field))
    expected_count = expected.question_count
    if expected_count is None:
        expected_count = int(expected.outcome == "interaction")
    record("question_count", expected_count == len(actual.get("questions", [])))
    question_fields = (
        expected.question.model_dump(exclude_unset=True) if expected.question else {}
    )
    if expected.outcome == "interaction" and expected.asked_before is not None:
        question_fields["asked_before"] = expected.asked_before
    question = actual.get("question")
    for field, value in question_fields.items():
        matched = question[field] == value if isinstance(question, dict) else None
        record(f"question.{field}", matched)

    prose = str(actual.get("prose", ""))
    once = expected.prose_once + (expected.replay_prose_once if replay else [])
    for index, text in enumerate(expected.prose_contains):
        record(f"prose_contains[{index}]", text in prose)
    for index, text in enumerate(once):
        record(f"prose_once[{index}]", prose.count(text) == 1)
    for index, text in enumerate(expected.prose_excludes):
        record(f"prose_excludes[{index}]", text not in prose)
    narrated = [expected.narrated_control] if expected.narrated_control else []
    record("narrated_controls", actual.get("narrated_controls") == narrated)
    if not replay:
        record("continuation_limit", actual.get("continuation_limit_reached") is False)
    for criterion in PROSE_JUDGMENTS:
        if getattr(expected, criterion) is not None:
            criteria[criterion] = "not_evaluated"
    return criteria


def failed_criteria(
    criteria: dict[str, str], result: dict[str, object], expected: ExpectedStep
) -> list[str]:
    """Preserve existing failure identifiers for callers and case summaries."""
    failures = [name for name, status in criteria.items() if status == "failed"]
    if "question_count" in failures:
        position = failures.index("question_count")
        if not result["questions"]:
            failures[position] = "missing_question"
        elif expected.outcome != "interaction":
            failures[position] = "unexpected_question"
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
    turns = []
    prose = []
    narrated_controls = []
    questions = []
    updates = []
    errors = []
    retryable_error = False
    continuation_limit_reached = False
    memory_before = session.all_memory()
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
        engine_prose = "".join(text)
        raw_text = strip_echoed_memory(engine_prose) if live else engine_prose
        visible = syntax.feed(raw_text) + syntax.flush()
        turns.append(
            {
                "outcome": outcome,
                "prose": visible,
                "engine_prose": engine_prose,
                "narrated_controls": syntax.spans,
            }
        )
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
        "memory_before": memory_before,
        "memory": session.all_memory(),
        "memory_updates": updates,
        "retryable_error": retryable_error,
        "errors": errors,
        "turn_outcomes": turn_outcomes,
        "turns": turns,
        "automatic_continuations": len(turn_outcomes) - 1,
        "continuation_limit_reached": continuation_limit_reached,
        "expected": expected.model_dump(mode="json", exclude_unset=True),
    }
    return result


def repeated_visible_question(
    previous: dict[str, object] | None, current: dict[str, object]
) -> str | None:
    """Identify the previous visible question when its sole control is shown again."""
    before = (previous or {}).get("questions", [])
    after = current.get("questions", [])
    if len(before) != 1 or len(after) != 1:
        return None
    if (
        before[0]["title"] == after[0]["title"]
        and before[0]["controls"] == after[0]["controls"]
    ):
        return before[0]["title"] or None
    return None


async def check_prose(
    criterion: str,
    intent: str,
    prose: str,
    judges: list[ObservedModel],
    *,
    previous_question: str | None = None,
) -> dict[str, object]:
    """Collect semantic decisions and expose disagreements for human judgment."""
    from scripts.mdf_interaction_question_judge import judge_meaning, judge_question

    is_question = criterion == "prose_question"
    verdict_key = "asked" if is_question else "covered"
    report: dict[str, object] = {}
    if is_question and previous_question is not None:
        report["previous_question"] = previous_question
    if not prose.strip():
        return {
            **report,
            "status": "failed",
            verdict_key: False,
            "reason": "No learner-facing prose.",
        }
    decisions = []
    for judge in judges:
        try:
            if is_question:
                judgment = await judge_question(
                    judge,
                    intended_question=intent,
                    prose=prose,
                    previous_question=previous_question,
                )
            else:
                judgment = await judge_meaning(
                    judge, required_meaning=intent, prose=prose
                )
            decision = judgment.model_dump(mode="json")
        except Exception as error:
            decision = {"error": type(error).__name__}
        decisions.append({"model": judge.model_name, **decision})

    report["decisions"] = decisions
    verdicts = {
        decision[verdict_key] for decision in decisions if verdict_key in decision
    }
    if True in verdicts and False in verdicts:
        return {
            **report,
            "status": "needs_review",
            verdict_key: None,
            "reason": "The judges disagree about whether the prose meets the criterion.",
        }
    if None in verdicts:
        return {
            **report,
            "status": "needs_review",
            verdict_key: None,
            "reason": "A judge found the match to the intended prose ambiguous.",
        }
    if any("error" in decision for decision in decisions):
        return {
            **report,
            "status": "not_evaluated",
            "reason": "A judge request failed or returned an invalid decision.",
        }
    passed = verdicts == {True}
    return {
        **report,
        "status": "passed" if passed else "failed",
        verdict_key: passed,
        "reason": decisions[0]["reason"],
    }


def can_submit_live_answer(
    step: Step, result: dict[str, object], session: Session
) -> bool:
    """Check whether the next scripted answer can use the controls actually shown."""
    from markdownflow import InteractionAnswer, answer_is_usable, normalize_answer

    question = result["question"]
    if (
        step.action != "answer"
        or result["outcome"] != "interaction"
        or not session.pending
        or not isinstance(question, dict)
    ):
        return False
    spec = session.pending[0].spec
    visible_values = {value for _, value in question["options"]}
    if any(value not in visible_values for value in step.values) or (
        step.text is not None
        and spec.type not in {"text", "single_or_text", "multi_or_text"}
    ):
        return False
    answer = normalize_answer(
        spec, InteractionAnswer(values=step.values, text=step.text)
    )
    return len(answer.values) == len(step.values) and answer_is_usable(spec, answer)


async def evaluate_case(
    case: Case,
    model: Model | None = None,
    temperature: float = 0.0,
    *,
    repeat: int = 1,
    judge_model: Model | None = None,
    second_judge_model: Model | None = None,
    record_calls: bool = False,
) -> dict[str, object]:
    """Evaluate a fixture and follow submitted answers that remain available live."""
    from markdownflow import ScriptBundle, Session

    started = time.monotonic()
    replay = Replay(case.replay) if model is None else None
    offline = replay is not None
    observed = ObservedModel(
        replay.model if replay is not None else model, record_calls=record_calls
    )
    judges = [ObservedModel(judge_model or model)] if model is not None else []
    if judges and second_judge_model is not None:
        judges.append(ObservedModel(second_judge_model))
    renderer = renderer_for(case.locale)
    engine = course_engine(observed, renderer, temperature, live=not offline)
    session = await engine.new_session(
        ScriptBundle(script=case.teaching_prompt, constraints=case.course_prompt),
        memory=case.memory,
    )
    steps = []
    failures = []
    judge_failed = False
    automatic_continuations = 0
    expectations = [
        (step.replay_expected or step.expected) if offline else step.expected
        for step in case.steps
    ]
    for index, (step, expected) in enumerate(
        zip(case.steps, expectations, strict=True), start=1
    ):
        if step.reload:
            session = Session.loads(session.dumps())
        if not offline and index > 1:
            # The teaching host constructs the admission checker per advancement.
            from flaskr.service.learn.agent.memory_admission import make_request_check

            engine.memory_request_check = make_request_check(observed)
        prior_retries = observed.retries
        prior_requests = observed.requests
        result = await run_step(
            engine, session, step, expected, renderer, live=not offline
        )
        automatic_continuations += result["automatic_continuations"]
        result["stage"] = index
        result["retries"] = observed.retries - prior_retries
        if observed.model_calls is not None:
            result["model_calls"] = observed.model_calls[prior_requests:]
        criteria = step_criteria(
            expected, result, replay=offline, call_failed=bool(observed.failures)
        )
        result["criteria"] = criteria
        judge_call_failures = []
        for criterion, (judgment_key, _) in PROSE_JUDGMENTS.items():
            intent = getattr(expected, criterion)
            if intent is None:
                continue
            if offline:
                result[judgment_key] = {"status": "skipped_offline"}
            elif not observed.failures:
                previous_question = (
                    repeated_visible_question(steps[-1], result)
                    if steps and criterion == "prose_question"
                    else None
                )
                judgment = await check_prose(
                    criterion,
                    intent,
                    result["prose"],
                    judges,
                    previous_question=previous_question,
                )
                result[judgment_key] = judgment
                criteria[criterion] = judgment["status"]
                if any(
                    "error" in decision for decision in judgment.get("decisions", [])
                ):
                    judge_call_failures.append(
                        f"{judgment_key.removesuffix('_judgment')}_judge_call"
                    )
        result["failures"] = (
            failed_criteria(criteria, result, expected) + judge_call_failures
        )
        judge_failed |= bool(judge_call_failures)
        steps.append(result)
        failures.extend(f"step_{index}.{name}" for name in result["failures"])
        if observed.failures:
            break
        if result["failures"] and (
            offline
            or index == len(case.steps)
            or not can_submit_live_answer(case.steps[index], result, session)
        ):
            break
    case_criteria = {}
    if replay is not None:
        if failures or observed.failures:
            case_criteria["replay_consumption"] = "not_evaluated"
        elif replay.responses:
            case_criteria["replay_consumption"] = "failed"
            failures.append("unused_replay_responses")
        else:
            case_criteria["replay_consumption"] = "passed"
    reproduced_failure = offline and any(
        step.replay_expected is not None
        and step.replay_expected.outcome != step.expected.outcome
        and step.replay_expected.outcome in {"error", "end"}
        for step in case.steps[: len(steps)]
    )
    if observed.failures:
        failures.extend(observed.failures)
    review_needed = any("needs_review" in step["criteria"].values() for step in steps)
    if judge_failed or (not offline and observed.failures):
        status = "call_failure"
    elif failures:
        status = "behavior_failure"
    elif reproduced_failure:
        status = "expected_failure_replayed"
    elif review_needed:
        status = "needs_review"
    else:
        status = (
            "recovered_pass"
            if observed.retries or automatic_continuations
            else "first_attempt_pass"
        )
    judge_usage: Counter[str] = Counter()
    for judge in judges:
        judge_usage.update(judge.usage)
    return {
        "case_id": case.id,
        "course": case.course,
        "source": case.source,
        "tags": case.tags,
        "repeat": repeat,
        "status": status,
        "criteria": case_criteria,
        "steps": steps,
        "unreached_steps": [
            {"stage": index, "criteria": step_criteria(expected, None, replay=offline)}
            for index, expected in enumerate(expectations[len(steps) :], len(steps) + 1)
        ],
        "failures": failures,
        "model_requests": observed.requests,
        "retries": observed.retries,
        "automatic_continuations": automatic_continuations,
        "usage": observed.usage,
        "question_judge_requests": sum(judge.requests for judge in judges),
        "question_judge_usage": judge_usage,
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
    second_judge_model: Model | None = None,
    record_calls: bool = False,
) -> list[dict[str, object]]:
    """Run selected fixtures serially, giving each repeat a clean session."""
    results = []
    for case in cases:
        for repeat in range(1, repeats + 1):
            result = await evaluate_case(
                case,
                model,
                temperature,
                repeat=repeat,
                judge_model=judge_model,
                second_judge_model=second_judge_model,
                record_calls=record_calls,
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


def summarize_criteria(
    results: list[dict[str, object]],
) -> tuple[dict[str, dict[str, int]], list[dict[str, object]]]:
    """Count assertion outcomes and collect the evidence for human review."""
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    review_items = []
    for result in results:
        for name, status in result["criteria"].items():
            counts[name][status] += 1
        for step in [*result["steps"], *result["unreached_steps"]]:
            for name, status in step["criteria"].items():
                counts[name.partition("[")[0]][status] += 1
                if status == "needs_review":
                    judgment_key, intent_key = PROSE_JUDGMENTS[name]
                    judgment = step[judgment_key]
                    item = {
                        "case_id": result["case_id"],
                        "repeat": result["repeat"],
                        "stage": step["stage"],
                        "criterion": name,
                        intent_key: step["expected"][name],
                        "learner_prose": step["prose"],
                        "reason": judgment["reason"],
                        "decisions": judgment["decisions"],
                    }
                    if "previous_question" in judgment:
                        item["previous_question"] = judgment["previous_question"]
                    review_items.append(item)
    summary = {
        name: {status: count[status] for status in CRITERION_STATUSES}
        for name, count in sorted(counts.items())
    }
    return summary, review_items


def print_assessment(
    criteria: dict[str, dict[str, int]], review_items: list[dict[str, object]]
) -> None:
    """Print criterion totals and each decision that needs a reviewer."""

    def print_evidence(line: str) -> None:
        if encoding := sys.stdout.encoding:
            line = line.encode(encoding, errors="backslashreplace").decode(encoding)
        print(line)

    print("\nCriterion assessment (counts by assertion)")
    print(f"{'criterion':<24}" + "".join(f"{name:>15}" for name in CRITERION_STATUSES))
    for criterion, counts in criteria.items():
        values = "".join(f"{counts[status]:>15}" for status in CRITERION_STATUSES)
        print(f"{criterion:<24}{values}")
    print(f"\nItems needing human review: {len(review_items)}")
    for item in review_items:
        _, intent_key = PROSE_JUDGMENTS[item["criterion"]]
        expected = json.dumps(item[intent_key], ensure_ascii=False)
        prose = json.dumps(item["learner_prose"], ensure_ascii=False)
        print(
            f"{item['case_id']} [{item['repeat']}] step {item['stage']} "
            f"({item['criterion']})"
        )
        print_evidence(f"  {item['reason']}")
        print_evidence(f"  {intent_key.replace('_', ' ').capitalize()}  {expected}")
        if "previous_question" in item:
            print_evidence(
                f"  Previous question  {json.dumps(item['previous_question'], ensure_ascii=False)}"
            )
        print_evidence(f"  Learner-facing prose  {prose}")
        for decision in item["decisions"]:
            print_evidence(f"  Judge  {json.dumps(decision, ensure_ascii=False)}")


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
        "--judge-model", help="model ID for live prose checks (defaults to --model)"
    )
    parser.add_argument(
        "--second-judge-model",
        help="optional second model for detecting disagreements on live prose checks",
    )
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument(
        "--json", type=Path, help="write JSON and a companion review page"
    )
    parser.add_argument("--compare", type=Path, help="compare a prior JSON report")
    parser.add_argument("--list", action="store_true", help="list matching cases")
    args = parser.parse_args(argv)
    if args.repeat < 1 or not 0 <= args.temperature <= 2:
        parser.error(
            "--repeat must be positive and --temperature must be between 0 and 2"
        )
    if args.live != bool(args.model):
        parser.error("--live and --model must be supplied together")
    for flag, model_id in (
        ("--judge-model", args.judge_model),
        ("--second-judge-model", args.second_judge_model),
    ):
        if model_id is not None:
            if not args.live:
                parser.error(f"{flag} requires --live")
            if not model_id.strip():
                parser.error(f"{flag} must be nonblank")
    review_path = args.json.with_suffix(".review.html") if args.json else None
    if args.json:
        inputs = {path.resolve() for path in (args.cases, args.compare) if path}
        outputs = {args.json.resolve(), review_path.resolve()}
        if len(outputs) != 2 or inputs & outputs:
            parser.error(
                "reports and the review page must use different files from the inputs"
            )

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
            model = judge_model = second_judge_model = None
            if args.live:
                from scripts.mdf_interaction_live import build_live_model
                from scripts.mdf_interaction_question_judge import (
                    MEANING_JUDGE_INSTRUCTIONS,
                    QUESTION_JUDGE_INSTRUCTIONS,
                )

                model = stack.enter_context(build_live_model(args.model))
                live_models = {args.model: model}
                for model_id in (args.judge_model, args.second_judge_model):
                    if model_id is not None and model_id not in live_models:
                        live_models[model_id] = stack.enter_context(
                            build_live_model(model_id)
                        )
                judge_model = live_models[args.judge_model or args.model]
                second_judge_model = live_models.get(args.second_judge_model)
                judge_config = {
                    "model": judge_model.model_name,
                    "second_model": (
                        second_judge_model.model_name if second_judge_model else None
                    ),
                    "instructions_sha256": sha256(
                        (
                            QUESTION_JUDGE_INSTRUCTIONS
                            + "\n"
                            + MEANING_JUDGE_INSTRUCTIONS
                        ).encode("utf-8")
                    ),
                }
            results = asyncio.run(
                run_cases(
                    cases,
                    model,
                    args.temperature,
                    args.repeat,
                    judge_model=judge_model,
                    second_judge_model=second_judge_model,
                    record_calls=bool(args.json),
                )
            )
            model_name = model.model_name if model is not None else None
        statuses = Counter(row["status"] for row in results)
        criteria_summary, review_items = summarize_criteria(results)
        report = {
            "schema_version": SCHEMA_VERSION,
            "mode": "live" if args.live else "offline",
            "model": model_name,
            "temperature": args.temperature,
            "question_judge": judge_config,
            "prompt_sha256": prompt_hashes,
            "cases_sha256": catalog_sha256(cases),
            "results": results,
            "summary": {status: statuses[status] for status in STATUSES},
            "criteria_summary": criteria_summary,
            "review_items": review_items,
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
            from scripts.mdf_interaction_review import fixture_context, write_review

            report["run_id"] = uuid4().hex
            report["review_context"] = fixture_context(cases)
            args.json.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            write_review(review_path, [report])
            print(f"Review page: {review_path}")
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Evaluation could not run: {error}", file=sys.stderr)
        return 2

    print("  ".join(f"{status}={count}" for status, count in report["summary"].items()))
    print_assessment(criteria_summary, review_items)
    if statuses["call_failure"] or (
        baseline is not None and not report["comparison"]["compatible"]
    ):
        return 2
    if statuses["behavior_failure"]:
        return 1
    return 3 if review_items else 0


if __name__ == "__main__":
    sys.path.insert(0, str(API_DIR))
    raise SystemExit(main())
