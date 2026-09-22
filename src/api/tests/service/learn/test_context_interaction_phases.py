"""Exercise learner-input pause, moderation, validation and access-gate transitions."""

from itertools import count
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr.service.learn import context_v2 as runtime
from flaskr.service.learn.const import ROLE_STUDENT, ROLE_TEACHER
from flaskr.service.learn.learn_dtos import GeneratedType
from flaskr.service.learn.llmsetting import LLMSettings
from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
from flaskr.service.metering import UsageContext
from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS
from markdown_flow.llm import LLMResult


def _consume(stream: object) -> tuple[list, object]:
    events = []
    while True:
        try:
            events.append(next(stream))
        except StopIteration as done:
            return events, done.value


@pytest.fixture
def content_phase(
    phase: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> SimpleNamespace:
    phase.context._preview_mode = False
    phase.context._listen = True
    phase.context._input_type = "normal"
    phase.context._stop_event = None
    phase.state.block_list = [object(), object()]
    phase.drainer = Mock()
    phase.drainer.drain.side_effect = lambda **_kwargs: iter([])
    monkeypatch.setattr(
        runtime, "StreamTTSFinalizeDrainer", lambda *_a, **_kw: phase.drainer
    )
    phase.processor = Mock()
    phase.processor.next_element_index = 4
    phase.processor.process_chunk.side_effect = lambda text: iter([f"audio:{text}"])
    phase.processor.drain_ready_segments.side_effect = lambda: iter([])
    phase.processor.finalize.side_effect = lambda **_kwargs: iter(["audio-final"])
    phase.create_processor = Mock(return_value=phase.processor)
    monkeypatch.setattr(
        phase.context, "_try_create_tts_processor", phase.create_processor
    )
    phase.generated_block = LearnGeneratedBlock(generated_block_bid="streamed-block")
    return phase


def _render_content(phase: SimpleNamespace, parts: list[object]) -> object:
    phase.state.mdflow_context.process.return_value = SimpleNamespace(
        formatted_elements=parts, content="", prompt="Exact generation prompt"
    )
    return phase.context._phase_stream_content_block(
        phase.app, phase.state, phase.generated_block
    )


def test_content_stream_switches_audio_processors_only_at_text_boundaries(
    content_phase: SimpleNamespace,
) -> None:
    phase = content_phase
    events = list(
        _render_content(
            phase,
            [
                {"content": "First", "type": "text", "number": 0},
                {"content": " continuation", "type": "text", "number": 0},
                {"content": "<svg></svg>", "type": "svg", "number": 1},
                {"content": "Last", "type": "text", "number": 2},
            ],
        )
    )
    assert [
        event.content
        for event in events
        if hasattr(event, "type") and event.type == GeneratedType.CONTENT
    ] == ["First", " continuation", "<svg></svg>", "Last"]
    assert [event for event in events if isinstance(event, str)] == [
        "audio:First",
        "audio: continuation",
        "audio:Last",
        "audio-final",
    ]
    assert [
        call.kwargs["position"] for call in phase.create_processor.call_args_list
    ] == [0, 1]
    assert [
        call.kwargs["stream_element_number"]
        for call in phase.create_processor.call_args_list
    ] == [0, 2]
    phase.drainer.submit.assert_called_once_with(phase.processor)
    phase.processor.finalize.assert_called_once_with(commit=False)
    assert phase.context._element_index_cursor == 4
    assert events[-1].type == GeneratedType.BREAK
    finalize = phase.context._recorder.finalize_streamed_block.call_args
    assert finalize.args[1] == "First continuation<svg></svg>Last"
    assert finalize.kwargs["generation_prompt"] == "Exact generation prompt"
    assert finalize.kwargs["block_position"] == 1
    assert phase.context._can_continue is True


@pytest.mark.parametrize("failure_point", ["process_chunk", "drain_ready_segments"])
def test_audio_failure_preserves_complete_text_and_disables_remaining_audio(
    content_phase: SimpleNamespace, failure_point: str
) -> None:
    phase = content_phase
    getattr(phase.processor, failure_point).side_effect = RuntimeError(
        "audio unavailable"
    )
    events = list(
        _render_content(
            phase,
            [
                {"content": "First", "type": "text", "number": 0},
                {"content": "Second", "type": "text", "number": 1},
            ],
        )
    )
    phase.create_processor.assert_called_once()
    phase.processor.finalize.assert_not_called()
    assert events[-1].type == GeneratedType.BREAK
    assert (
        phase.context._recorder.finalize_streamed_block.call_args.args[1]
        == "FirstSecond"
    )
    assert phase.context._can_continue is True


def test_missing_tts_configuration_still_persists_text_content(
    content_phase: SimpleNamespace,
) -> None:
    phase = content_phase
    phase.create_processor.return_value = None
    events = list(
        _render_content(phase, [{"content": "Text", "type": "text", "number": 0}])
    )
    assert [event.type for event in events] == [
        GeneratedType.CONTENT,
        GeneratedType.BREAK,
    ]
    assert phase.context._recorder.finalize_streamed_block.call_args.args[1] == "Text"


def test_client_disconnect_does_not_finalize_or_persist_partial_content(
    content_phase: SimpleNamespace,
) -> None:
    phase = content_phase
    stream = _render_content(
        phase,
        [
            {"content": "First", "type": "text", "number": 0},
            {"content": "Unsent", "type": "text", "number": 1},
        ],
    )
    assert next(stream).content == "First"
    assert next(stream) == "audio:First"
    stream.close()
    phase.drainer.close.assert_called_once()
    phase.processor.finalize.assert_not_called()
    phase.context._recorder.finalize_streamed_block.assert_not_called()


def test_content_stream_forwards_idle_audio_before_next_model_chunk(
    content_phase: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    phase = content_phase
    phase.context._listen = False

    def model_stream() -> object:
        yield LLMResult(content="Text", type="text", number=0)

    def polled_stream(stream: object, **_kwargs: object) -> object:
        yield "idle", "audio-ready-while-model-waits"
        for result in stream:
            yield "item", result

    monkeypatch.setattr(
        phase.context, "_iter_stream_result_with_idle_callback", polled_stream
    )
    phase.state.mdflow_context.process.return_value = model_stream()
    events = list(
        phase.context._phase_stream_content_block(
            phase.app, phase.state, phase.generated_block
        )
    )
    assert events[0] == "audio-ready-while-model-waits"
    assert events[1].content == "Text"
    assert events[-1].type == GeneratedType.BREAK


@pytest.fixture
def phase(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    app = Flask("interaction-phase-contract")
    context = runtime.RunScriptContextV2.__new__(runtime.RunScriptContextV2)
    context.app = app
    context._user_info = SimpleNamespace(user_id="user", mobile="", email="")
    context._outline_item_info = SimpleNamespace(
        bid="outline", shifu_bid="course", title="Lesson"
    )
    context._current_attend = LearnProgressRecord(
        progress_record_bid="progress",
        shifu_bid="course",
        outline_item_bid="outline",
        block_position=0,
    )
    context._run_recorder = Mock()
    context._run_type = runtime.RunType.INPUT
    context._can_continue = True
    context._is_paid = False
    context._trace_args = {
        "metadata": {"chapter_title": "Chapter", "scene": "lesson_runtime"}
    }
    context._trace_root_span = Mock()
    context.append_langfuse_output = Mock()
    context._maybe_emit_feedback_after_access_gate = Mock(return_value=iter([]))
    state = runtime._RunStepState(
        run_script_info=runtime.RunScriptInfo(
            context._current_attend, "outline", 0, "Question?"
        ),
        llm_settings=LLMSettings(model="model", temperature=0.2),
        system_prompt=None,
        usage_context=UsageContext(user_bid="user", shifu_bid="course"),
        llm_provider=Mock(),
        mdflow_context=Mock(),
        block_list=[object()],
        user_profile={"name": "learner"},
        message_list=[],
        variable_definition_key_id_map={"choice": "definition"},
        block=SimpleNamespace(content="Question?", index=0),
    )
    state.mdflow_context.process.return_value = SimpleNamespace(
        content="Translated question", metadata={}, variables={}
    )
    ids = count()
    blocks = []

    def init_block(*_args: object, **_kwargs: object) -> LearnGeneratedBlock:
        block = LearnGeneratedBlock(
            generated_block_bid=f"block-{next(ids)}",
            generated_content="",
            block_content_conf="",
        )
        blocks.append(block)
        return block

    monkeypatch.setattr(runtime, "init_generated_block", init_block)
    monkeypatch.setattr(runtime, "generate_id", lambda _app: "retry-block")
    session = Mock()
    monkeypatch.setattr(runtime, "db", SimpleNamespace(session=session))
    moderation = Mock(return_value=iter([None]))
    monkeypatch.setattr(runtime, "check_text_with_llm_response", moderation)
    memory = Mock()
    monkeypatch.setattr(runtime, "stage_memory", memory)
    return SimpleNamespace(
        context=context,
        state=state,
        app=app,
        blocks=blocks,
        session=session,
        moderation=moderation,
        memory=memory,
    )


@pytest.mark.parametrize("outcome", ["complete", "disconnect", "provider-failure"])
def test_ask_stream_stays_silent_and_commits_only_after_complete_delivery(
    phase: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    context = phase.context
    context._input_type = "ask"
    context._input = {"input": ["First question", "Follow-up"]}
    context._last_position = -1
    context._preview_mode = False
    context._listen = True
    context._stop_event = None
    context._trace = None
    context._anchor_element_bid = "source-element"
    create_tts = Mock()
    monkeypatch.setattr(context, "_try_create_tts_processor", create_tts)
    monkeypatch.setattr(
        runtime,
        "load_memory",
        lambda *_args: SimpleNamespace(as_variables=lambda: {"name": "learner"}),
    )
    first = SimpleNamespace(type=GeneratedType.CONTENT, content="Answer")
    last = SimpleNamespace(type=GeneratedType.BREAK, content="")

    def source() -> object:
        yield first
        if outcome == "provider-failure":
            message = "provider unavailable"
            raise RuntimeError(message)
        yield last

    ask = Mock(return_value=source())
    monkeypatch.setattr(runtime, "handle_input_ask", ask)
    stream = context._phase_handle_ask_input(phase.app, phase.state.run_script_info)
    assert next(stream) is first
    context._recorder.commit_pending_step.assert_not_called()
    if outcome == "complete":
        assert list(stream) == [last]
        context._recorder.commit_pending_step.assert_called_once()
        assert context._can_continue is False
    elif outcome == "disconnect":
        stream.close()
        context._recorder.commit_pending_step.assert_not_called()
    else:
        with pytest.raises(RuntimeError, match="provider unavailable"):
            list(stream)
        context._recorder.commit_pending_step.assert_not_called()
    create_tts.assert_not_called()
    assert ask.call_args.args[4] == "First question,Follow-up"
    assert ask.call_args.kwargs["anchor_element_bid"] == "source-element"
    assert ask.call_args.kwargs["runtime_profiles"] == {"name": "learner"}
    assert context._last_position == 0


@pytest.mark.parametrize("gate", ["_sys_pay", "_sys_login"])
@pytest.mark.parametrize("cached", [True, False])
def test_unsatisfied_access_gate_reemits_cached_translation_and_stops(
    phase: SimpleNamespace, gate: str, cached: bool
) -> None:
    block = (
        LearnGeneratedBlock(
            generated_block_bid="cached",
            block_content_conf="Cached translation",
            generated_content="answer",
        )
        if cached
        else None
    )
    parsed = {"buttons": [{"value": gate}]}
    stream = phase.context._phase_reemit_access_gate_interaction(
        phase.app, phase.state, parsed, block
    )
    event = next(stream)
    assert event.type == GeneratedType.INTERACTION
    assert event.content == ("Cached translation" if cached else "Question?")
    persisted = phase.context._recorder.save_generated_block.call_args.args[0]
    assert persisted.generated_content == ""
    phase.context._recorder.save_generated_block.assert_called_once_with(persisted)
    assert _consume(stream) == ([], True)
    assert phase.context._can_continue is False
    phase.context._recorder.update_progress_pointer.assert_not_called()
    phase.context._maybe_emit_feedback_after_access_gate.assert_called_once_with(
        parsed_interaction=parsed,
        progress_record=phase.context._current_attend,
        is_tail_gate=True,
    )


@pytest.mark.parametrize("identity", ["paid", "email", "mobile"])
def test_satisfied_access_gate_advances_without_replaying_prompt(
    phase: SimpleNamespace, identity: str
) -> None:
    gate = "_sys_pay" if identity == "paid" else "_sys_login"
    if identity == "paid":
        phase.context._is_paid = True
    else:
        setattr(phase.context._user_info, identity, "present")
    assert _consume(
        phase.context._phase_reemit_access_gate_interaction(
            phase.app, phase.state, {"buttons": [{"value": gate}]}, None
        )
    ) == ([], True)
    phase.context._recorder.update_progress_pointer.assert_called_once_with(
        phase.context._current_attend, block_position=1
    )
    assert phase.context._run_type == runtime.RunType.OUTPUT
    assert phase.context._can_continue is True
    assert phase.blocks == []


@pytest.mark.parametrize(
    "parsed", [{}, {"buttons": []}, {"buttons": [{"value": "answer"}]}]
)
def test_regular_interaction_is_not_consumed_as_access_gate(
    phase: SimpleNamespace, parsed: dict
) -> None:
    assert _consume(
        phase.context._phase_reemit_access_gate_interaction(
            phase.app, phase.state, parsed, None
        )
    ) == ([], False)
    phase.context._recorder.save_generated_block.assert_not_called()


@pytest.mark.parametrize("rendered", [True, False])
def test_first_interaction_is_persisted_before_prompt_then_pauses(
    phase: SimpleNamespace, rendered: bool
) -> None:
    if not rendered:
        phase.state.mdflow_context.process.return_value = None
    stream = phase.context._phase_emit_interaction_pause(phase.app, phase.state)
    event = next(stream)
    block = phase.blocks[0]
    assert event.content == ("Translated question" if rendered else "Question?")
    assert block.role == ROLE_TEACHER
    assert block.generated_content == ""
    phase.context._recorder.save_generated_block.assert_called_once_with(block)
    assert list(stream) == []
    assert phase.context._can_continue is False


@pytest.mark.parametrize(
    ("raw", "variable", "expected"),
    [
        ({"input": ["A"]}, "choice", {"choice": ["A"]}),
        ({"old": ["B"]}, "choice", {"choice": ["B"]}),
        (
            {"choice": ["C"], "extra": ["D"]},
            "choice",
            {"choice": ["C"], "extra": ["D"]},
        ),
        ("answer", " ", {"input": ["answer"]}),
    ],
)
def test_accepted_input_is_normalized_recorded_and_passed_to_moderation(
    phase: SimpleNamespace, raw: object, variable: str, expected: dict
) -> None:
    phase.context._input = raw
    block = LearnGeneratedBlock(generated_block_bid="input-block")
    events, result = _consume(
        phase.context._phase_record_input_and_moderate(
            phase.app, phase.state, block, {"variable": variable}
        )
    )
    assert events == []
    assert result == (False, expected)
    assert block.role == ROLE_STUDENT
    assert block.block_content_conf == "Translated question"
    assert block.generated_content == runtime.MdflowContextV2.flatten_user_input_map(
        expected
    )
    phase.context._recorder.save_generated_block.assert_called_once_with(block)
    arguments = phase.moderation.call_args.kwargs
    assert arguments["usage_context"].generated_block_bid == "input-block"
    assert arguments["chapter_title"] == "Chapter"
    assert arguments["scene"] == "lesson_runtime_interaction"


def test_rejected_input_streams_feedback_then_reasks_with_fresh_identity(
    phase: SimpleNamespace,
) -> None:
    phase.context._input = "unsafe input"
    phase.context._trace_args["metadata"] = "invalid legacy metadata"
    phase.moderation.return_value = iter([None, "", "Please ", "try again"])
    block = LearnGeneratedBlock(generated_block_bid="input-block")
    events, result = _consume(
        phase.context._phase_record_input_and_moderate(
            phase.app, phase.state, block, {}
        )
    )
    assert result == (True, {"input": ["unsafe input"]})
    assert [event.type for event in events] == [
        GeneratedType.CONTENT,
        GeneratedType.CONTENT,
        GeneratedType.BREAK,
        GeneratedType.INTERACTION,
    ]
    assert [event.content for event in events] == [
        "Please ",
        "try again",
        "",
        "Translated question",
    ]
    assert events[-1].generated_block_bid == "retry-block"
    assert events[0].generated_block_bid == "input-block"
    assert block.generated_content == ""
    assert phase.context._can_continue is False
    assert phase.context._recorder.save_generated_block.call_count == 2
    assert phase.moderation.call_args.kwargs["chapter_title"] == "Lesson"


@pytest.mark.parametrize(
    ("answer", "expected"),
    [(["A", None, 2], "A,2"), (None, ""), (7, "7"), ("existing", "existing")],
)
def test_nonassignment_answer_is_canonicalized_before_cursor_advance(
    phase: SimpleNamespace, answer: object, expected: str
) -> None:
    block = LearnGeneratedBlock(
        generated_block_bid="block", generated_content="existing"
    )
    phase.state.mdflow_context.process.return_value = SimpleNamespace(
        metadata={"interaction_type": "non_assignment_button", "answer": answer},
        variables=None,
    )
    assert _consume(
        phase.context._phase_validate_input_and_advance(
            phase.app, phase.state, block, {"input": ["choice"]}
        )
    ) == ([], True)
    assert block.generated_content == expected
    assert phase.context._recorder.save_generated_block.call_count == (
        0 if expected == "existing" else 1
    )
    phase.context._recorder.update_progress_pointer.assert_called_once_with(
        phase.context._current_attend, status=LEARN_STATUS_IN_PROGRESS, block_position=1
    )
    assert phase.context._run_type == runtime.RunType.OUTPUT
    phase.memory.assert_not_called()


def test_validated_variables_stage_memory_emit_updates_then_advance(
    phase: SimpleNamespace,
) -> None:
    phase.state.mdflow_context.process.return_value = SimpleNamespace(
        metadata=None, variables={"choice": ["A", None, 2], "empty": None, "count": 3}
    )
    block = LearnGeneratedBlock(generated_block_bid="block")
    stream = phase.context._phase_validate_input_and_advance(
        phase.app, phase.state, block, {}
    )
    first = next(stream)
    assert first.content.variable_value == "A,2"
    update = phase.memory.call_args.args[-1]
    assert [
        (item.key, item.value, item.definition_bid) for item in update.variables
    ] == [("choice", "A,2", "definition"), ("empty", "", ""), ("count", "3", "")]
    phase.context._recorder.update_progress_pointer.assert_not_called()
    events, advanced = _consume(stream)
    assert advanced is True
    assert [event.content.variable_value for event in events] == ["", "3"]
    phase.context._recorder.update_progress_pointer.assert_called_once()


@pytest.mark.parametrize(
    ("error_content", "expected"),
    [
        ("try again", ["try again"]),
        ("", []),
        (["one", None, 2, ""], ["one", "2"]),
        (("first", "second"), ["first", "second"]),
        (12, ["12"]),
        (None, []),
    ],
)
def test_validation_error_replays_content_before_saving_and_reasking(
    phase: SimpleNamespace, error_content: object, expected: list[str]
) -> None:
    result = SimpleNamespace(content=error_content)
    events = list(
        phase.context._phase_emit_validation_error(phase.app, phase.state, result)
    )
    assert [event.content for event in events] == [*expected, "", "Translated question"]
    assert [event.type for event in events] == [
        *[GeneratedType.CONTENT] * len(expected),
        GeneratedType.BREAK,
        GeneratedType.INTERACTION,
    ]
    assert phase.blocks[0].generated_content == "".join(expected)
    assert phase.blocks[1].generated_content == ""
    assert phase.session.add.call_count == 2
    assert phase.context._recorder.save_generated_block.call_count == 2
    assert phase.context._can_continue is False


def test_disconnect_during_validation_error_never_saves_partial_response(
    phase: SimpleNamespace,
) -> None:
    def error_chunks() -> object:
        yield None
        yield ""
        yield "partial"
        yield "rest"

    stream = phase.context._phase_emit_validation_error(
        phase.app, phase.state, SimpleNamespace(content=error_chunks())
    )
    assert next(stream).content == "partial"
    phase.context._recorder.save_generated_block.assert_not_called()
    stream.close()
    phase.context._recorder.save_generated_block.assert_not_called()
    phase.context._recorder.update_progress_pointer.assert_not_called()
    assert len(phase.blocks) == 1


def test_validation_without_variables_uses_error_replay_without_advancing(
    phase: SimpleNamespace,
) -> None:
    block = LearnGeneratedBlock(generated_block_bid="block")
    events, advanced = _consume(
        phase.context._phase_validate_input_and_advance(
            phase.app, phase.state, block, {}
        )
    )
    assert advanced is False
    assert events[-1].type == GeneratedType.INTERACTION
    phase.context._recorder.update_progress_pointer.assert_called_once_with(
        phase.context._current_attend, status=LEARN_STATUS_IN_PROGRESS
    )


@pytest.mark.parametrize("identity", ["paid", "email", "mobile"])
def test_output_phase_skips_already_satisfied_access_gates(
    phase: SimpleNamespace, identity: str
) -> None:
    gate = "_sys_pay" if identity == "paid" else "_sys_login"
    phase.state.block.content = f"?[Continue//{gate}]"
    if identity == "paid":
        phase.context._is_paid = True
    else:
        setattr(phase.context._user_info, identity, "present")
    block = LearnGeneratedBlock(generated_block_bid="gate")
    assert (
        list(
            phase.context._phase_emit_output_interaction(phase.app, phase.state, block)
        )
        == []
    )
    phase.state.mdflow_context.process.assert_not_called()
    phase.context._recorder.save_generated_block.assert_not_called()
    phase.context._recorder.update_progress_pointer.assert_called_once_with(
        phase.context._current_attend, block_position=1
    )
    assert phase.context._can_continue is True


def test_sync_outline_progress_stops_when_reread_progress_has_completed(
    phase: SimpleNamespace,
) -> None:
    phase.context._input_type = "input"
    updates = [object()]
    phase.context._get_next_outline_item = Mock(return_value=updates)
    phase.context._render_outline_updates = Mock(return_value=iter(["outline-event"]))
    refreshed = SimpleNamespace(status=603)
    phase.context._get_current_attend = Mock(return_value=refreshed)
    assert _consume(phase.context._phase_sync_outline_progress(phase.app)) == (
        ["outline-event"],
        False,
    )
    assert phase.context._current_attend is refreshed
    assert phase.context._can_continue is False


def test_missing_script_emits_completion_interactions_before_outline_updates(
    phase: SimpleNamespace,
) -> None:
    updates = [object()]
    phase.context._get_next_outline_item = Mock(return_value=updates)
    phase.context._has_next_outline_item = Mock(return_value=True)
    phase.context._is_current_outline_completed = Mock(return_value=True)
    phase.context._render_outline_updates = Mock(return_value=iter(["outline-event"]))
    phase.context._emit_completion_tail_interactions = Mock(
        return_value=iter(["feedback", "next-chapter"])
    )
    assert list(phase.context._phase_completion_when_script_missing()) == [
        "feedback",
        "next-chapter",
        "outline-event",
    ]
    phase.context._emit_completion_tail_interactions.assert_called_once_with(
        progress_record=phase.context._current_attend,
        current_outline_completed=True,
        has_next_outline_item=True,
    )
    assert phase.context._can_continue is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ([None, " "], False),
        ([None, "answer"], True),
        ({"input": [None, " "]}, False),
        ({"input": [0]}, True),
        (None, False),
    ],
)
def test_effective_input_requires_an_actual_answer(
    phase: SimpleNamespace, raw: object, expected: bool
) -> None:
    phase.context._input = raw
    assert phase.context._has_effective_input() is expected


@pytest.mark.parametrize(
    ("error", "gate"),
    [(runtime.PaidError, "_sys_pay"), (runtime.UserNotLoginError, "_sys_login")],
)
def test_access_exception_becomes_gate_and_feedback_without_advancing(
    phase: SimpleNamespace, error: type, gate: str
) -> None:
    phase.context.run_inner = Mock(side_effect=error())
    phase.context._emit_current_progress_gate_interaction = Mock(
        return_value=iter(["gate"])
    )
    phase.context._emit_feedback_after_exception_gate = Mock(
        return_value=iter(["feedback"])
    )
    assert list(phase.context.run(phase.app)) == ["gate", "feedback"]
    assert (
        gate in phase.context._emit_current_progress_gate_interaction.call_args.args[0]
    )
    assert phase.context.has_next() is False
