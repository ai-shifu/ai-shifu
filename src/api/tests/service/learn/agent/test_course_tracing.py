"""Exercise course trace presentation through the host and the real Langfuse SDK."""

import json
from types import SimpleNamespace

import pytest
from flaskr.api import langfuse_markdownflow as tracing_module
from flaskr.api import markdownflow as application
from flaskr.api.llm import markdownflow_model as gateway
from flaskr.service.learn.agent import langfuse_tracing as course_tracing
from flaskr.service.learn.agent import lesson_entry, run_agent
from flaskr.service.learn.learn_dtos import (
    GeneratedType,
    LearnStatus,
    OutlineItemUpdateDTO,
)
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


@pytest.mark.parametrize("scene", ["learn", "preview", "debug"])
@pytest.mark.parametrize("shared_http_id", [True, False])
def test_advances_keep_distinct_traces_in_one_document_execution_session(
    monkeypatch: pytest.MonkeyPatch,
    captured_spans: object,
    scene: str,
    shared_http_id: bool,
) -> None:
    """HTTP identity and document continuity cannot merge separate advances."""
    client, exporter, _provider = captured_spans
    monkeypatch.setattr(tracing_module, "get_langfuse_client", lambda: client)
    for index, session_id in enumerate(("conversation", "conversation", "reset")):
        monkeypatch.setattr(
            tracing_module,
            "get_request_id",
            lambda index=index: (
                "shared-request" if shared_http_id else f"request-{index}"
            ),
        )
        trace = course_tracing.CourseTrace(
            user_bid="learner",
            shifu_bid="course",
            outline_bid="lesson",
            user_input=f"answer-{index}",
            preview_mode=scene != "learn",
            debug=scene == "debug",
            listen=False,
            learning_mode="read",
            regenerate=False,
        )
        session = _Session(started=index > 0)
        session.id = session_id
        with trace:
            loaded = trace.prepare_turn(
                user_input=f"answer-{index}",
                regenerate=False,
                teaching_brief="Teach clearly.",
                content_revision=1,
            )
            assert trace.model_parent.trace_id == ""
            if index == 0:
                # New sessions are created on the producer after host progress opens.
                trace.bind_execution(f"progress-{index}", f"block-{index}")
                loaded(session)
            else:
                # Restored sessions arrive before the host opens its next block.
                loaded(session)
                trace.bind_execution(f"progress-{index}", f"block-{index}")
            trace.model_parent.generation(name="teaching", model="test-model").end(
                output=f"model-{index}"
            )
            trace.append_output(f"visible-{index}")
            trace.complete_turn("waiting")

    spans = exporter.get_finished_spans()
    roots = [span for span in spans if span.name == f"{scene}/course/lesson"]
    assert len(roots) == 3
    assert len({span.context.span_id for span in roots}) == 3
    assert len({root.context.trace_id for root in roots}) == 3
    assert [root.attributes["session.id"] for root in roots] == [
        "conversation",
        "conversation",
        "reset",
    ]
    for index, root in enumerate(roots):
        assert root.attributes["langfuse.observation.input"] == f"answer-{index}"
        assert root.attributes["langfuse.observation.output"] == f"visible-{index}"
        assert root.attributes["langfuse.trace.metadata.request_id"] == (
            "shared-request" if shared_http_id else f"request-{index}"
        )
        turn = next(
            span
            for span in spans
            if span.name == "teaching_round"
            and span.parent.span_id == root.context.span_id
        )
        generation = next(
            span
            for span in spans
            if span.name == "teaching" and span.parent.span_id == turn.context.span_id
        )
        assert (
            turn.attributes["langfuse.observation.metadata.progress_record_bid"]
            == f"progress-{index}"
        )
        assert (
            turn.attributes["langfuse.observation.metadata.generated_block_bid"]
            == f"block-{index}"
        )
        assert generation.context.trace_id == root.context.trace_id


def _entry(
    monkeypatch: pytest.MonkeyPatch, engine: object, title_context: dict | None = None
) -> None:
    def resolve(*_args: object, **kwargs: object) -> object:
        kwargs["on_resolved"](
            outline_model=None, outline=None, shifu=None, content_revision=17
        )
        return (
            "latest script",
            "Current teaching brief",
            LLMSettings(model="model", temperature=0.3),
            17,
            None,
        )

    monkeypatch.setattr(lesson_entry, "_resolve", resolve)
    monkeypatch.setattr(
        course_tracing,
        "_lesson_context",
        lambda *_a, **_kw: (
            title_context
            or {
                "course_title": "Course",
                "lesson_title": "Lesson",
                "chapter_path": ["Chapter"],
            }
        ),
    )
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
            save=lambda value, **_kw: persist(None, value),
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
    contexts = [span for span in spans if span.name == "prompts"]
    assert len(contexts) == 1
    assert json.loads(contexts[0].attributes["langfuse.observation.input"]) == {
        "teaching_prompt": session.script.script,
        "course_prompt": "Current teaching brief",
    }
    turns = [span for span in spans if span.name == "teaching_round"]
    generations = [
        span
        for span in spans
        if span.attributes.get("langfuse.observation.type") == "generation"
    ]
    assert len(turns) == 2
    assert len(generations) == 6
    assert {generation.name for generation in generations} == {
        "teaching",
        "history_summary",
        "memory_check",
    }
    ordered_turns = sorted(turns, key=lambda span: span.start_time)
    first_output = ordered_turns[0].attributes["langfuse.observation.output"]
    second_output = ordered_turns[1].attributes["langfuse.observation.output"]
    assert "Visible turn 1" in first_output
    assert "Visible turn 2" not in first_output
    assert "Ready?" not in first_output
    assert "Visible turn 2" in second_output
    assert "Ready?" in second_output
    assert "Visible turn 1" not in second_output
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
    "close_at",
    [
        None,
        GeneratedType.OUTLINE_ITEM_UPDATE,
        GeneratedType.INTERACTION,
        GeneratedType.DONE,
    ],
)
def test_completed_course_trace_includes_buffered_text_and_real_next_lesson_controls(
    monkeypatch: pytest.MonkeyPatch,
    captured_spans: object,
    close_at: GeneratedType | None,
) -> None:
    """The real host flushes text and creates next-lesson controls before terminal DONE."""
    client, exporter, _provider = captured_spans
    monkeypatch.setattr(tracing_module, "get_langfuse_client", lambda: client)
    session = _Session()
    session.id = "completed-course-session"
    session.finished = True
    final_text = "Final buffered teaching sentence."
    engine = _Engine(
        [
            ContentDelta(text="Earlier visible teaching.\n\n"),
            ContentDelta(text=final_text),
            TurnDone(reason="finished"),
        ],
        session,
    )
    _entry(monkeypatch, engine)
    updates = [
        OutlineItemUpdateDTO(
            "lesson", "Current lesson", LearnStatus.COMPLETED, has_children=False
        ),
        OutlineItemUpdateDTO(
            "next-lesson", "Next lesson", LearnStatus.IN_PROGRESS, has_children=False
        ),
    ]
    monkeypatch.setattr(
        run_agent, "resolve_outline_progression", lambda *_a, **_k: updates
    )
    controls = []

    def record_next_lesson(_app: object, **kwargs: object) -> str:
        controls.append(kwargs["content"])
        return "next-lesson-control"

    monkeypatch.setattr(run_agent, "record_next_lesson_interaction", record_next_lesson)
    monkeypatch.setattr(run_agent, "_retire_block", lambda *_a, **_k: None)
    stream = lesson_entry.agent_lesson_events(
        None, user_bid="learner", shifu_bid="course", outline_bid="lesson"
    )
    events = []
    for event in stream:
        events.append(event)
        if close_at is not None and event.type == close_at:
            stream.close()
            break
    assert events[-1].type == (close_at or GeneratedType.DONE)
    visible_output = "".join(
        event.content
        for event in events
        if event.type in {GeneratedType.CONTENT, GeneratedType.INTERACTION}
    )
    assert final_text in visible_output
    if close_at == GeneratedType.OUTLINE_ITEM_UPDATE:
        assert controls == []
    else:
        assert len(controls) == 1
        assert run_agent.CONTEXT_INTERACTION_NEXT in controls[0]
        assert controls[0] in visible_output
        assert any(
            event.generated_block_bid == "next-lesson-control" for event in events
        )
    spans = exporter.get_finished_spans()
    root = next(span for span in spans if span.name.startswith("learn/"))
    turn = next(span for span in spans if span.name == "teaching_round")
    assert root.attributes["langfuse.observation.output"] == visible_output
    assert turn.attributes["langfuse.observation.output"] == visible_output
    assert (
        root.attributes["langfuse.observation.metadata.runtime_outcome"] == "completed"
    )
    assert root.attributes["langfuse.observation.metadata.transport_closed"] is (
        close_at is not None
    )


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

    monkeypatch.setattr(course_tracing, "_latest_ancestor", latest)
    context = course_tracing._lesson_context(
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
        "chapter_path_truncated": False,
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
    turn = next(span for span in spans if span.name == "teaching_round")
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
