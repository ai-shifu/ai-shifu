"""Reproduce coverage counterexamples with public synthetic inputs and no I/O.

The required-field capability is a test-only proposed policy, never a product
guard. These controls falsify two specific policies; they do not grade teaching
or replay any private classroom. Each SDK case uses one opening request and one
follow-up request, both supplied locally by FunctionModel.
"""

import copy
import json
import socket
from collections.abc import AsyncIterator, Iterator
from dataclasses import replace

import pytest
import requests
from flaskr.service.learn.agent.engine import (
    Engine,
    ErrorEvent,
    InteractionResponseTurn,
    Session,
)
from flaskr.service.learn.agent.engine import engine as engine_module
from flaskr.service.learn.agent.engine.computed_example import (
    ComputedExample,
    execute_example,
)
from flaskr.service.learn.agent.engine.tools import Deps, current_tool_response
from jsonschema import Draft202012Validator
from markdown_flow.formatter.stream import StreamFormatter
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.capabilities import AbstractCapability, RawToolArgs
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelResponse,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.tools import ToolDefinition
from sqlalchemy.engine import Engine as DatabaseEngine

from .test_computed_example import _loop
from .test_direction_feedback import _call, _collect, _text

QUESTION = "Explain this permitted counter example."
ORDINARY = "A stored program supplies instructions from memory."
FALSE_SUM = "The sum of two and one is four."
FENCED = (
    "The ADD instruction executes twice.\n\n"
    "```text\n0 SET R0,1\n1 ADD R1,R0\n2 HALT\n```\n\n"
    "Initial registers: R0=0, R1=0."
)


@pytest.fixture(autouse=True)
def forbid_external_io(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fail even if a runtime accidentally catches a network/database exception."""
    attempts = []

    def forbidden(*_args: object, **_kwargs: object) -> None:
        """Record every forbidden connection before rejecting it."""
        attempts.append(True)
        message = "Coverage controls must not access HTTP, sockets or a database"
        raise AssertionError(message)

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(DatabaseEngine, "connect", forbidden)
    yield
    assert attempts == []


class _RequiredFieldPrototype(AbstractCapability[Deps]):
    """Test the offered required schema and native validation for a proposed gate."""

    def __init__(self, *, nullable: bool) -> None:
        """Permit null only in the explicitly nullable experimental policy."""
        self.nullable = nullable

    async def prepare_tools(
        self, ctx: RunContext[Deps], tool_defs: list[ToolDefinition]
    ) -> list[ToolDefinition]:
        """Alter only test-local supported interact definitions before model input."""
        definitions = []
        for definition in tool_defs:
            if definition.name != "interact" or not ctx.deps.direction_sections:
                definitions.append(definition)
                continue
            schema = copy.deepcopy(definition.parameters_json_schema)
            if self.nullable:
                original = schema["properties"]["computed_example"]
                schema["properties"]["computed_example"] = {
                    "anyOf": [original, {"type": "null"}]
                }
            schema["required"] = list(
                dict.fromkeys([*schema.get("required", []), "computed_example"])
            )
            definitions.append(replace(definition, parameters_json_schema=schema))
        return definitions

    async def before_tool_validate(
        self,
        ctx: RunContext[Deps],
        *,
        args: RawToolArgs,
        call: ToolCallPart,
        **_metadata: object,
    ) -> RawToolArgs:
        """Enforce the test policy without rewriting native call evidence."""
        if call.tool_name != "interact" or not ctx.deps.direction_sections:
            return args
        values = json.loads(args) if isinstance(args, str) else args
        valid = isinstance(values, dict) and "computed_example" in values
        if valid and not self.nullable:
            valid = isinstance(values["computed_example"], dict)
        if not valid:
            ctx.deps.hide_feedback_response(current_tool_response(ctx))
            message = "Test-only coverage policy requires the declared field"
            raise ModelRetry(message)
        return args


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("policy", "payload_kind", "prose", "accepted", "artifacts"),
    [
        pytest.param(None, "omitted", FENCED, True, 0, id="optional-omitted"),
        pytest.param("nullable", "omitted", FENCED, False, 0, id="required-missing"),
        pytest.param("nullable", "null", FENCED, True, 0, id="required-null-bypass"),
        pytest.param("nullable", "null", ORDINARY, True, 0, id="ordinary-null"),
        pytest.param("object", "omitted", ORDINARY, False, 0, id="ordinary-blocked"),
        pytest.param("object", "object", FALSE_SUM, True, 1, id="false-free-prose"),
        pytest.param(
            "object",
            "object",
            "A computed illustration follows.",
            True,
            1,
            id="canonical-positive",
        ),
    ],
)
async def test_native_coverage_policy_counterexamples(
    monkeypatch: pytest.MonkeyPatch,
    policy: str | None,
    payload_kind: str,
    prose: str,
    accepted: bool,
    artifacts: int,
) -> None:
    """Keep bypasses, ordinary compatibility and positive delivery reproducible."""
    requests_seen = 0
    observations = []
    ordinary = {"type": "text", "prompt": "", "placeholder": "Answer"}
    payload = {
        **ordinary,
        "feedback": {
            "answer_id": "original",
            "phase": "clarification",
            "submission_quote": QUESTION,
            "reason": "Answer the knowledge question and retain the authored input.",
        },
    }
    if payload_kind != "omitted":
        payload["computed_example"] = None if payload_kind == "null" else _loop()

    async def stream(_messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator:
        """Inspect the actual native schema and supply a bounded local response."""
        nonlocal requests_seen
        requests_seen += 1
        assert requests_seen <= 2
        if requests_seen == 1:
            yield _call(ordinary, "original")
            return
        schema = next(
            tool.parameters_json_schema
            for tool in info.function_tools
            if tool.name == "interact"
        )
        validator = Draft202012Validator(schema)
        assert validator.is_valid(payload) is accepted
        # Nullable means object OR null; it must not accidentally mean null only.
        assert validator.is_valid({**payload, "computed_example": _loop()})
        yield prose
        yield _call(payload, "candidate")

    original_agent = engine_module.Agent

    def agent(*args: object, **kwargs: object) -> Agent:
        """Install the experimental capability only on this test's local Agent."""
        if policy is not None:
            existing = kwargs.get("capabilities", [])
            assert isinstance(existing, list)
            kwargs["capabilities"] = [
                *existing,
                _RequiredFieldPrototype(nullable=policy == "nullable"),
            ]
        return original_agent(*args, **kwargs)

    monkeypatch.setattr(engine_module, "Agent", agent)
    engine = Engine(
        FunctionModel(stream_function=stream),
        computed_examples=True,
        feedback_contract=True,
        computed_example_observer=lambda: observations.append(True),
        request_limit=1,
    )
    session = await engine.new_session(
        "Explain briefly using permitted examples.\n?[...Answer]\n"
    )
    await _collect(engine.run_turn(session))
    session = Session.loads(session.dumps())
    old_count = len(session.messages)
    old_prefix = ModelMessagesTypeAdapter.dump_json(session.messages)
    events = [
        event
        async for event in engine.run_turn(
            session, InteractionResponseTurn(text=QUESTION)
        )
    ]
    assert requests_seen == 2
    assert (
        ModelMessagesTypeAdapter.dump_json(session.messages[:old_count]) == old_prefix
    )
    assert len(observations) == artifacts
    args = [event.args for event in events if event.type == "tool.call"]
    assert [
        json.loads(value) if isinstance(value, str) else value for value in args
    ] == [payload]
    new_responses = [
        message
        for message in session.messages[old_count:]
        if isinstance(message, ModelResponse)
    ]
    saved_text = "".join(
        part.content
        for message in new_responses
        for part in message.parts
        if isinstance(part, TextPart)
    )
    errors = [event for event in events if isinstance(event, ErrorEvent)]
    assert bool(errors) is not accepted
    if accepted:
        assert prose in _text(events)
        assert prose in saved_text
        saved_args = [
            part.args_as_dict()
            for message in new_responses
            for part in message.parts
            if isinstance(part, ToolCallPart)
        ]
        assert saved_args == [payload]
    else:
        assert _text(events) == saved_text == ""
    if artifacts:
        assert "| 5 | 101 | 102 | 1 | 3 |" in _text(events)
        result = execute_example(ComputedExample.model_validate(_loop()))
        assert result.rows[-1].registers["R1"] == 3


@pytest.mark.parametrize(
    ("content", "types", "blocked"),
    [
        pytest.param(FENCED, {"code", "text"}, True, id="fenced-program"),
        pytest.param(
            "\n".join(
                line for line in FENCED.splitlines() if not line.startswith("```")
            ),
            {"text"},
            False,
            id="plain-program-bypass",
        ),
        pytest.param(
            "<div><pre>SET R0,1\nADD R1,R0\nHALT</pre></div>",
            {"html"},
            False,
            id="html-program-bypass",
        ),
        pytest.param(
            '```python\nprint("hello")\n```', {"code"}, True, id="ordinary-python"
        ),
        pytest.param(
            "```text\nLOAD R1,[10]\nHALT\n```", {"code"}, True, id="authored-code"
        ),
        pytest.param(
            "| Name | Value |\n|---|---|\n| x | 1 |", {"tables"}, True, id="data-table"
        ),
        pytest.param(
            '<div class="card">Supported card</div>\n<style>.card {color:red}</style>',
            {"html"},
            False,
            id="html-css",
        ),
        pytest.param(FALSE_SUM, {"text"}, False, id="false-prose-bypass"),
    ],
)
def test_shared_formatter_does_not_define_semantic_eligibility(
    content: str,
    types: set[str],
    blocked: bool,
) -> None:
    """Show both bypasses and false positives without replacing the formatter."""
    formatter = StreamFormatter()
    parts = formatter.process(content) + formatter.flush()
    actual = {str(part.type) for part in parts if str(part.content or "").strip()}
    assert actual == types
    assert bool(actual & {"code", "tables"}) is blocked
