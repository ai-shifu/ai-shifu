"""Exercise course trace presentation through the host and the real Langfuse SDK."""

import json
from types import SimpleNamespace

import pytest
from flaskr.api import markdownflow as application
from flaskr.api import markdownflow_tracing as tracing_module
from flaskr.api.llm import markdownflow_model as gateway
from flaskr.service.learn.agent import lesson_entry, run_agent
from flaskr.service.learn.learn_dtos import GeneratedType
from flaskr.service.learn.llmsetting import LLMSettings
from markdownflow.engine.events import (
    ContentDelta,
    InteractionRequest,
    ToolCall,
    ToolResult,
    TurnDone,
)
from markdownflow.engine.interaction import InteractionSpec
from pydantic_ai.models import ModelRequestParameters

from tests import test_langfuse_v4_semantics as sdk_tests
from tests.service.learn.agent import test_run_agent as host_tests
from tests.service.learn.agent.test_gateway_model import FakeChunk
from tests.service.learn.agent.test_run_agent import _drive, _Engine, _Session

calls = host_tests.calls
captured_spans = sdk_tests.captured_spans


def _entry(
    monkeypatch: pytest.MonkeyPatch, engine: object, title_context: dict | None = None
) -> None:
    def resolve(*_args: object, **kwargs: object) -> object:
        kwargs["trace_context"].update(
            title_context
            or {
                "course_title": "Course",
                "lesson_title": "Lesson",
                "chapter_path": ["Chapter"],
            }
        )
        return (
            "latest script",
            "Current teaching brief",
            LLMSettings(model="model", temperature=0.3),
            17,
            None,
        )

    monkeypatch.setattr(lesson_entry, "_resolve", resolve)
    monkeypatch.setattr(lesson_entry, "get_global_profile_keys", frozenset)
    monkeypatch.setattr(lesson_entry, "Engine", lambda *_args, **_kwargs: engine)
    monkeypatch.setattr(application, "iter_turn", _drive)


@pytest.mark.usefixtures("calls")
@pytest.mark.parametrize("scene", ["learn", "preview", "debug"])
def test_course_trace_keeps_request_context_output_and_automatic_turn_hierarchy(
    monkeypatch: pytest.MonkeyPatch, captured_spans: object, scene: str
) -> None:
    client, exporter, _provider = captured_spans
    monkeypatch.setattr(tracing_module, "get_langfuse_client", lambda: client)
    stored = []
    models = []
    session = _Session()
    session.id = "native-conversation"
    session.script = application.ScriptBundle(script="Actually executing stored script")

    def model(*args: object, **kwargs: object) -> object:
        instance = gateway.GatewayModel(*args, **kwargs)
        models.append(instance)
        return instance

    def chat(**kwargs: object) -> object:
        generation = kwargs["span"].generation(
            name=kwargs["generation_name"], model="model", input="model input"
        )
        try:
            yield FakeChunk(result="model result", finish_reason="stop")
        finally:
            generation.end(output="model result", usage={"input": 2, "output": 3})

    class Engine(_Engine):
        def run_turn(self, _session: object, turn: object) -> object:
            self.turns.append(turn)

            async def events() -> object:
                for instance in models:
                    list(instance._stream([], ModelRequestParameters()))
                session.started = True
                session.turn += 1
                yield ToolCall(
                    id=f"read-{session.turn}", name="recall", args={"key": "goal"}
                )
                yield ToolResult(
                    id=f"read-{session.turn}",
                    name="recall",
                    content={"value": "private tool result"},
                )
                yield ContentDelta(text=f"Visible turn {session.turn}.\n\n")
                if session.turn == 1:
                    yield TurnDone(reason="end")
                else:
                    yield InteractionRequest(
                        id="question",
                        spec=InteractionSpec(type="confirm", prompt="Ready?"),
                    )
                    yield TurnDone(reason="interaction")

            return events()

    def persist(_app: object, value: object, **_kwargs: object) -> bool:
        stored[:] = [value]
        return True

    monkeypatch.setattr(lesson_entry, "GatewayModel", model)
    monkeypatch.setattr(gateway, "chat_llm", chat)
    monkeypatch.setattr(run_agent, "_persist", persist)
    monkeypatch.setattr(
        run_agent, "load_agent_session", lambda *_a, **_k: stored[0] if stored else None
    )
    _entry(monkeypatch, Engine([], session))
    debug_store = (
        SimpleNamespace(
            load=lambda **_kw: stored[0] if stored else None,
            save=lambda value: persist(None, value),
        )
        if scene == "debug"
        else None
    )
    answer = {"input": ["Use my actual answer"]}
    events = list(
        lesson_entry.agent_lesson_events(
            None,
            user_bid="learner",
            shifu_bid="course",
            outline_bid="lesson",
            user_input=answer,
            preview_mode=scene != "learn",
            debug_store=debug_store,
            script_override="Unsaved editor script" if debug_store else None,
        )
    )

    spans = exporter.get_finished_spans()
    root = next(span for span in spans if span.name.startswith(f"{scene}/"))
    assert root.name == f"{scene}/Course/Chapter/Lesson"
    assert json.loads(root.attributes["langfuse.observation.input"]) == answer
    assert root.attributes["session.id"] == session.id
    output = root.attributes["langfuse.observation.output"]
    assert output == "".join(
        event.content
        for event in events
        if event.type in {GeneratedType.CONTENT, GeneratedType.INTERACTION}
    )
    assert "Visible turn 1" in output
    assert "Visible turn 2" in output
    assert "Ready?" in output
    assert "model result" not in output
    assert "private tool result" not in output
    contexts = [span for span in spans if span.name == "context"]
    assert len(contexts) == 1
    assert (
        json.loads(contexts[0].attributes["langfuse.observation.input"])["script"]
        == session.script.script
    )
    turns = [span for span in spans if span.name == "turn"]
    generations = [
        span
        for span in spans
        if span.attributes.get("langfuse.observation.type") == "generation"
    ]
    assert len(turns) == 2
    assert len(generations) == 6
    tools = [span for span in spans if span.name == "recall"]
    assert len(tools) == 2
    assert all(
        tool.parent.span_id in {turn.context.span_id for turn in turns}
        for tool in tools
    )
    assert all(turn.parent.span_id == root.context.span_id for turn in turns)
    assert all(
        sum(g.parent.span_id == turn.context.span_id for g in generations) == 3
        for turn in turns
    )
    assert len({span.context.trace_id for span in spans}) == 1
    assert root.attributes["langfuse.observation.metadata.runtime_outcome"] == "waiting"


@pytest.mark.usefixtures("calls")
@pytest.mark.parametrize(
    "outcome", ["waiting", "completed", "disconnected", "error", "discarded"]
)
def test_course_trace_finishes_from_committed_outcome_when_consumer_closes(
    monkeypatch: pytest.MonkeyPatch, captured_spans: object, outcome: str
) -> None:
    client, exporter, _provider = captured_spans
    monkeypatch.setattr(tracing_module, "get_langfuse_client", lambda: client)
    session = _Session()
    session.id = "course-conversation"
    session.finished = outcome == "completed"
    engine = _Engine(
        [
            ContentDelta(text="Partial visible result.\n\n"),
            TurnDone(reason="finished" if session.finished else "interaction"),
        ],
        session,
    )
    _entry(monkeypatch, engine)

    def persist(*_args: object, **_kwargs: object) -> bool:
        if outcome == "error":
            message = "business write failed"
            raise RuntimeError(message)
        return outcome != "discarded"

    monkeypatch.setattr(run_agent, "_persist", persist)
    monkeypatch.setattr(run_agent, "_retire_block", lambda *_a, **_k: None)
    stream = lesson_entry.agent_lesson_events(
        None, user_bid="learner", shifu_bid="course", outline_bid="lesson"
    )
    if outcome == "error":
        with pytest.raises(RuntimeError, match="business write failed"):
            list(stream)
    else:
        for event in stream:
            if outcome == "disconnected" or event.type in {
                GeneratedType.BREAK,
                GeneratedType.DONE,
            }:
                stream.close()
                break
    root = next(
        span for span in exporter.get_finished_spans() if span.name.startswith("learn/")
    )
    assert json.loads(root.attributes["langfuse.observation.input"]) == {
        "action": "start"
    }
    assert root.attributes["langfuse.observation.metadata.runtime_outcome"] == outcome
    assert "Partial visible result" in root.attributes["langfuse.observation.output"]


def test_trace_context_uses_the_selected_version_for_each_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    draft, published = object(), object()
    parent = SimpleNamespace(
        title="Draft chapter", outline_item_bid="chapter", parent_bid=""
    )
    seen = []

    def latest(model: object, **_kwargs: object) -> object:
        seen.append(model)
        return parent

    monkeypatch.setattr(lesson_entry, "_latest", latest)
    context = lesson_entry._lesson_trace_context(
        draft,
        outline=SimpleNamespace(
            title="Draft lesson",
            outline_item_bid="lesson",
            parent_bid="chapter",
            shifu_bid="course",
            id=12,
        ),
        shifu=SimpleNamespace(title="Draft course", shifu_bid="course", id=8),
    )
    assert context == {
        "course_title": "Draft course",
        "lesson_title": "Draft lesson",
        "chapter_path": ["Draft chapter"],
        "course_record_id": 8,
        "outline_record_id": 12,
    }
    assert seen == [draft]
    assert published not in seen


def test_course_engine_setup_failure_closes_the_open_trace(
    monkeypatch: pytest.MonkeyPatch, captured_spans: object
) -> None:
    client, exporter, _provider = captured_spans
    monkeypatch.setattr(tracing_module, "get_langfuse_client", lambda: client)
    _entry(monkeypatch, None)

    def fail(*_args: object, **_kwargs: object) -> object:
        message = "engine setup failed"
        raise RuntimeError(message)

    monkeypatch.setattr(lesson_entry, "Engine", fail)
    with pytest.raises(RuntimeError, match="engine setup failed"):
        list(
            lesson_entry.agent_lesson_events(
                None, user_bid="learner", shifu_bid="course", outline_bid="lesson"
            )
        )
    root = next(
        span for span in exporter.get_finished_spans() if span.name.startswith("learn/")
    )
    assert root.attributes["langfuse.observation.metadata.runtime_outcome"] == "error"


@pytest.mark.usefixtures("calls")
def test_course_stream_still_completes_when_langfuse_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail() -> object:
        message = "tracing service unavailable"
        raise RuntimeError(message)

    monkeypatch.setattr(tracing_module, "get_langfuse_client", fail)
    engine = _Engine(
        [ContentDelta(text="Visible teaching."), TurnDone(reason="interaction")]
    )
    _entry(monkeypatch, engine)
    events = list(
        lesson_entry.agent_lesson_events(
            None, user_bid="learner", shifu_bid="course", outline_bid="lesson"
        )
    )
    assert (
        "".join(
            event.content for event in events if event.type == GeneratedType.CONTENT
        )
        == "Visible teaching."
    )
    assert events[-1].type == GeneratedType.BREAK


@pytest.mark.usefixtures("calls")
@pytest.mark.parametrize("user_input", [None, " ", "", {}, {"input": []}])
@pytest.mark.parametrize("action", ["start", "continue", "regenerate"])
def test_empty_course_input_records_the_actual_session_action(
    monkeypatch: pytest.MonkeyPatch,
    captured_spans: object,
    app: object,
    user_input: object,
    action: str,
) -> None:
    client, exporter, _provider = captured_spans
    monkeypatch.setattr(tracing_module, "get_langfuse_client", lambda: client)
    session = _Session(started=action != "start")
    session.id = "native-session"
    session.memory_generations = {}
    engine = _Engine(
        [ContentDelta(text="Visible."), TurnDone(reason="interaction")], session
    )
    _entry(monkeypatch, engine)
    options = {}
    if action != "start":
        monkeypatch.setattr(run_agent, "load_agent_session", lambda *_a, **_k: session)
    if action == "regenerate":
        rewind = SimpleNamespace(checkpoint={}, replay_values=None)
        monkeypatch.setattr(lesson_entry, "plan_rewind", lambda **_kw: rewind)
        monkeypatch.setattr(run_agent, "restore", lambda *_args: None)
        monkeypatch.setattr(run_agent, "_persist", lambda *_args, **_kw: True)
        options["reload_generated_block_bid"] = "previous-block"
    list(
        lesson_entry.agent_lesson_events(
            app,
            user_bid="learner",
            shifu_bid="course",
            outline_bid="lesson",
            user_input=user_input,
            **options,
        )
    )
    spans = exporter.get_finished_spans()
    root = next(span for span in spans if span.name.startswith("learn/"))
    turn = next(span for span in spans if span.name == "turn")
    assert json.loads(root.attributes["langfuse.observation.input"]) == {
        "action": action
    }
    assert json.loads(turn.attributes["langfuse.observation.input"]) == {
        "action": action
    }


@pytest.mark.usefixtures("calls")
@pytest.mark.parametrize(
    "chapters", [[], ["Chapter " + "m" * 100 + " end", "Nested " + "n" * 100 + " end"]]
)
def test_long_course_names_preserve_both_titles_and_propagate_in_the_real_sdk(
    monkeypatch: pytest.MonkeyPatch, captured_spans: object, chapters: list[str]
) -> None:
    client, exporter, _provider = captured_spans
    monkeypatch.setattr(tracing_module, "get_langfuse_client", lambda: client)
    course_title = "Course-start " + "c" * 75 + " Course-end"
    lesson_title = "Lesson-start " + "l" * 75 + " Lesson-end"
    engine = _Engine([ContentDelta(text="Visible."), TurnDone(reason="interaction")])
    _entry(
        monkeypatch,
        engine,
        {
            "course_title": course_title,
            "lesson_title": lesson_title,
            "chapter_path": chapters,
        },
    )
    list(
        lesson_entry.agent_lesson_events(
            None, user_bid="learner", shifu_bid="course", outline_bid="lesson"
        )
    )
    root = next(
        span for span in exporter.get_finished_spans() if span.name.startswith("learn/")
    )
    assert len(root.name) <= 180
    assert root.attributes["langfuse.trace.name"] == root.name
    assert "Course-start" in root.name
    assert "Course-end" in root.name
    assert "Lesson-start" in root.name
    assert "Lesson-end" in root.name
    assert root.attributes["langfuse.observation.metadata.course_title"] == course_title
    assert root.attributes["langfuse.observation.metadata.lesson_title"] == lesson_title
    assert (
        json.loads(root.attributes["langfuse.observation.metadata.chapter_path"])
        == chapters
    )
