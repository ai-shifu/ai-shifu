"""Tests for the element protocol freeze (Sections A-D of the design doc).

Covers:
- ElementDTO new fields serialization/deserialization
- ElementType new enum values and legacy fallback
- TypeStateMachine transitions and output
- is_new=false / is_marker constraint behaviour
- audio_segments accumulation
"""

from __future__ import annotations

import json
import types

import pytest
from flaskr.dao import db
from flaskr.service.learn.ask.context import (
    build_follow_up_element_history,
    is_complete_follow_up_asks,
)
from flaskr.service.learn.ask.providers import AskProviderError
from flaskr.service.learn.elements.element_types import (
    ELEMENT_TYPE_CODES,
    LEGACY_ELEMENT_TYPE_MAP,
    _element_type_for_visual_kind,
)
from flaskr.service.learn.elements.payloads import (
    _deserialize_payload,
    _serialize_payload,
)
from flaskr.service.learn.learn_dtos import (
    ElementChangeType,
    ElementDTO,
    ElementPayloadDTO,
    ElementType,
    GeneratedType,
    RunMarkdownFlowDTO,
)
from flaskr.service.learn.models import LearnGeneratedElement
from flaskr.service.learn.type_state_machine import (
    TypeInput,
    TypeState,
    TypeStateMachine,
)
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDCONTENT_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
)
from flaskr.service.tts.pipeline import build_av_segmentation_contract

from tests.service.learn import listen_element_helpers as helpers
from tests.service.learn.listen_element_helpers import (
    EMPTY_PAYLOAD,
    ListenScope,
    add_rows,
    audio_segment,
    cue_spans,
    require_app,
    reset_learn_tables,
    streamed_elements,
    subtitle_cues,
)

adapter_app = helpers.adapter_app

# Learner, lesson and anchor block shared by the in-memory adapter tests.
LIVE = ListenScope(
    "live",
    user_bid="u1",
    shifu_bid="s1",
    outline_bid="o1",
    progress_bid="pr1",
    generated_block_bid="gb1",
    run_session_bid="rs1",
)


class _FollowUpDummyGeneration:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.end_kwargs = {}

    def end(self, **kwargs: object) -> None:
        self.end_kwargs = kwargs


class _FollowUpDummySpan:
    def __init__(self) -> None:
        self.generations = []
        self.updated = {}
        self.output = ""

    def generation(self, **kwargs: object) -> object:
        generation = _FollowUpDummyGeneration(**kwargs)
        self.generations.append(generation)
        return generation

    def span(self, **_kwargs: object) -> object:
        return _FollowUpDummySpan()

    def update(self, **kwargs: object) -> None:
        self.updated = kwargs

    def event(self, **_kwargs: object) -> None:
        return None

    def end(self, output: object = None, **kwargs: object) -> None:
        self.output = output or ""
        self.end_kwargs = {"output": output, **kwargs}


class _FollowUpDummyTrace:
    def __init__(self) -> None:
        self.updated = {}

    def span(self, **_kwargs: object) -> object:
        return _FollowUpDummySpan()

    def update(self, **kwargs: object) -> None:
        self.updated = kwargs


class _FollowUpContext:
    def __init__(self) -> None:
        self._shifu_info = types.SimpleNamespace(use_learner_language=0)
        self.langfuse_outputs = []

    def get_system_prompt(self, _outline_bid: str) -> object:
        return "COURSE_PROMPT"

    def append_langfuse_output(self, value: str) -> None:
        self.langfuse_outputs.append(value)


class _FollowUpInfo:
    def __init__(self, ask_provider_config: object) -> None:
        self.ask_prompt = "ASK_PROMPT::{shifu_system_message}"
        self.ask_model = "gpt-test"
        self.model_args = {"temperature": 0.2}
        self.ask_provider_config = ask_provider_config

    def __json__(self) -> dict:
        return {
            "ask_model": self.ask_model,
            "ask_provider_config": self.ask_provider_config,
        }


def _setup_handle_input_ask_test_doubles(
    monkeypatch: object,
    module: object,
    ask_provider_config: object,
    *,
    patch_generated_blocks: bool = True,
) -> None:
    class _DummyLLMSettings:
        def __init__(
            self, model: object, temperature: object, usage_metadata: object = None
        ) -> None:
            self.model = model
            self.usage_metadata = usage_metadata
            self.temperature = temperature

    class _DummyAskProviderRuntime:
        def __init__(
            self,
            llm_stream_factory: object = None,
            llm_context_stream_factory: object = None,
            search_query: object = None,
        ) -> None:
            self.llm_stream_factory = llm_stream_factory
            self.llm_context_stream_factory = llm_context_stream_factory
            self.search_query = search_query

    class _DummyAskProviderTimeoutError(AskProviderError):
        pass

    monkeypatch.setattr(
        module,
        "get_follow_up_info_v2",
        lambda *_args, **_kwargs: _FollowUpInfo(ask_provider_config),
    )
    monkeypatch.setattr(
        module,
        "check_text_with_llm_response",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(module, "_", lambda key: key)
    monkeypatch.setattr(
        module,
        "get_effective_ask_provider_config",
        lambda config: config,
    )
    monkeypatch.setattr(
        module,
        "get_fmt_prompt",
        lambda *_args, **_kwargs: "COURSE_PROMPT",
    )
    monkeypatch.setattr(module, "LLMSettings", _DummyLLMSettings)
    monkeypatch.setattr(module, "AskProviderRuntime", _DummyAskProviderRuntime)
    monkeypatch.setattr(module, "AskProviderError", AskProviderError)
    monkeypatch.setattr(
        module,
        "AskProviderTimeoutError",
        _DummyAskProviderTimeoutError,
    )
    monkeypatch.setattr(
        module,
        "stream_provider_with_langfuse",
        lambda provider_stream, **_kwargs: provider_stream,
    )
    if patch_generated_blocks:
        monkeypatch.setattr(module.db.session, "add", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(
            module.db.session,
            "flush",
            lambda *_args, **_kwargs: None,
        )

        call_counter = {"index": 0}

        def _fake_init_generated_block(*_args: object, **_kwargs: object) -> object:
            call_counter["index"] += 1
            return types.SimpleNamespace(
                generated_block_bid=f"gb-{call_counter['index']}",
                generated_content="",
                role="",
                type=0,
                position=-1,
            )

        monkeypatch.setattr(module, "init_generated_block", _fake_init_generated_block)


# ---------------------------------------------------------------------------
# ElementType enum tests
# ---------------------------------------------------------------------------


class TestElementType:
    """Verify element type behavior."""

    def test_new_enum_values(self) -> None:
        expected = {
            "html",
            "svg",
            "diff",
            "img",
            "interaction",
            "ask",
            "answer",
            "tables",
            "code",
            "latex",
            "md_img",
            "mermaid",
            "title",
            "text",
        }
        actual = {et.value for et in ElementType if not et.name.startswith("_")}
        assert actual == expected

    def test_legacy_aliases_exist(self) -> None:
        assert ElementType._SANDBOX.value == "sandbox"
        assert ElementType._PICTURE.value == "picture"
        assert ElementType._VIDEO.value == "video"

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError, match="nonexistent"):
            ElementType("nonexistent")

    def test_element_type_codes_complete(self) -> None:
        # Every non-legacy type must have a code
        for et in ElementType:
            if et.name.startswith("_"):
                continue
            assert et in ELEMENT_TYPE_CODES, f"Missing code for {et}"

    def test_legacy_mapping(self) -> None:
        assert LEGACY_ELEMENT_TYPE_MAP[ElementType._SANDBOX] == ElementType.HTML
        assert LEGACY_ELEMENT_TYPE_MAP[ElementType._PICTURE] == ElementType.IMG
        assert LEGACY_ELEMENT_TYPE_MAP[ElementType._VIDEO] == ElementType.HTML


# ---------------------------------------------------------------------------
# ElementDTO new fields tests
# ---------------------------------------------------------------------------


class TestElementDTONewFields:
    """Verify element DTO new fields behavior."""

    def _make_dto(self, **overrides: object) -> ElementDTO:
        defaults = {
            "element_bid": "test-bid",
            "element_index": 0,
            "role": "teacher",
            "element_type": ElementType.TEXT,
            "element_type_code": 213,
        }
        defaults.update(overrides)
        return ElementDTO(**defaults)

    def test_default_values(self) -> None:
        dto = self._make_dto()
        assert dto.is_renderable is True
        assert dto.is_new is True
        assert dto.is_marker is False
        assert dto.sequence_number == 0
        assert dto.is_speakable is False
        assert dto.audio_url == ""
        assert dto.audio_segments == []

    def test_json_includes_new_fields(self) -> None:
        dto = self._make_dto(
            is_renderable=False,
            is_new=False,
            is_marker=True,
            sequence_number=5,
            is_speakable=True,
            audio_url="https://example.com/audio.mp3",
            audio_segments=[{"position": 0, "segment_index": 1}],
        )
        result = dto.__json__()
        assert result["is_renderable"] is False
        assert result["is_new"] is False
        assert result["is_marker"] is True
        assert result["sequence_number"] == 5
        assert result["is_speakable"] is True
        assert result["audio_url"] == "https://example.com/audio.mp3"
        assert len(result["audio_segments"]) == 1

    @pytest.mark.parametrize(
        ("overrides", "expected_flags"),
        [
            pytest.param(
                {"is_final": True, "audio_url": "https://example.com/audio.mp3"},
                [True, True],
                id="final_marks_all_segments_final",
            ),
            pytest.param(
                {"is_final": False},
                [False, True],
                id="non_final_preserves_segment_flags",
            ),
        ],
    )
    def test_json_audio_segment_final_flags(
        self, overrides: dict, expected_flags: list[bool]
    ) -> None:
        dto = self._make_dto(
            audio_segments=[
                {"position": 0, "segment_index": 0, "is_final": False},
                {"position": 0, "segment_index": 1, "is_final": True},
            ],
            **overrides,
        )

        result = dto.__json__()

        assert [
            segment["is_final"] for segment in result["audio_segments"]
        ] == expected_flags
        # Serialization never mutates the DTO's own segments.
        assert [segment["is_final"] for segment in dto.audio_segments] == [
            False,
            True,
        ]


class TestRunMarkdownFlowDTO:
    """Verify run markdown flow DTO behavior."""

    def test_private_mdflow_stream_parts_do_not_leak_into_json(self) -> None:
        dto = RunMarkdownFlowDTO(
            outline_bid="outline-1",
            generated_block_bid="block-1",
            type=GeneratedType.CONTENT,
            content="hello",
        ).set_mdflow_stream_parts([("hello", "text", 0)])

        assert dto.get_mdflow_stream_parts() == [("hello", "text", 0)]
        assert dto.__json__() == {
            "outline_bid": "outline-1",
            "generated_block_bid": "block-1",
            "type": "content",
            "content": "hello",
        }

    def test_default_anchor_element_bid_empty(self) -> None:
        dto = RunMarkdownFlowDTO(
            outline_bid="o1",
            generated_block_bid="b1",
            type=GeneratedType.CONTENT,
            content="hello",
        )
        assert dto.anchor_element_bid == ""
        assert "anchor_element_bid" not in dto.__json__()

    def test_anchor_element_bid_set(self) -> None:
        dto = RunMarkdownFlowDTO(
            outline_bid="o1",
            generated_block_bid="b1",
            type=GeneratedType.ASK,
            content="user question",
            anchor_element_bid="elem_abc",
        )
        assert dto.anchor_element_bid == "elem_abc"
        assert dto.__json__()["anchor_element_bid"] == "elem_abc"


# ---------------------------------------------------------------------------
# TypeStateMachine tests
# ---------------------------------------------------------------------------


class TestTypeStateMachine:
    """Verify type state machine behavior."""

    def test_initial_state_is_idle(self) -> None:
        sm = TypeStateMachine()
        assert sm.state == TypeState.IDLE
        assert not sm.is_terminated

    @pytest.mark.parametrize(
        ("history", "trigger", "kwargs", "expected_output", "expected_state"),
        [
            pytest.param(
                [],
                TypeInput.CONTENT_START,
                {"is_new": False},
                "element",
                TypeState.PATCHING,
                id="content_start_with_is_new_false_patches",
            ),
            pytest.param(
                [TypeInput.CONTENT_START],
                TypeInput.INCREMENTAL_UPDATE,
                {},
                "element",
                TypeState.PATCHING,
                id="incremental_update_patches",
            ),
            pytest.param(
                [],
                TypeInput.ERROR,
                {},
                "error",
                TypeState.TERMINATED,
                id="error_terminates",
            ),
        ],
    )
    def test_transition(
        self,
        history: list[TypeInput],
        trigger: TypeInput,
        kwargs: dict,
        expected_output: str,
        expected_state: TypeState,
    ) -> None:
        sm = TypeStateMachine()
        for earlier in history:
            sm.feed(earlier)

        assert sm.feed(trigger, **kwargs) == expected_output
        assert sm.state == expected_state
        assert sm.is_terminated is (expected_state == TypeState.TERMINATED)

    def test_feed_after_terminated_raises(self) -> None:
        sm = TypeStateMachine()
        sm.feed(TypeInput.DONE)
        with pytest.raises(ValueError, match="already terminated"):
            sm.feed(TypeInput.CONTENT_START)

    def test_reset(self) -> None:
        sm = TypeStateMachine()
        sm.feed(TypeInput.DONE)
        sm.reset()
        assert sm.state == TypeState.IDLE
        assert not sm.is_terminated

    def test_full_lifecycle(self) -> None:
        """Test a realistic sequence: content -> audio -> break -> content -> done."""
        sm = TypeStateMachine()
        assert sm.feed(TypeInput.CONTENT_START) == "element"
        assert sm.state == TypeState.BUILDING
        assert sm.feed(TypeInput.AUDIO_SEGMENT) == "audio_segment"
        assert sm.state == TypeState.BUILDING
        assert sm.feed(TypeInput.AUDIO_COMPLETE) == "audio_complete"
        assert sm.state == TypeState.BUILDING
        assert sm.feed(TypeInput.BLOCK_BREAK) == "break"
        assert sm.state == TypeState.IDLE
        assert sm.feed(TypeInput.CONTENT_START) == "element"
        assert sm.state == TypeState.BUILDING
        assert sm.feed(TypeInput.DONE) == "done"
        assert sm.state == TypeState.TERMINATED
        assert sm.is_terminated


# ---------------------------------------------------------------------------
# Visual kind to element type mapping tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("visual_kind", "expected"),
    [
        ("video", ElementType.HTML),
        ("img", ElementType.IMG),
        ("md_img", ElementType.MD_IMG),
        ("svg", ElementType.SVG),
        ("iframe", ElementType.HTML),
        ("sandbox", ElementType.HTML),
        ("html_table", ElementType.HTML),
        ("md_table", ElementType.TABLES),
        ("fence", ElementType.CODE),
        ("mermaid", ElementType.MERMAID),
        ("latex", ElementType.LATEX),
        ("title", ElementType.TITLE),
        ("text", ElementType.TEXT),
        pytest.param("unknown", ElementType.TEXT, id="unknown_defaults_to_text"),
        pytest.param("", ElementType.TEXT, id="empty_defaults_to_text"),
    ],
)
def test_visual_kind_maps_to_element_type(
    visual_kind: str, expected: ElementType
) -> None:
    assert _element_type_for_visual_kind(visual_kind) == expected


# ---------------------------------------------------------------------------
# DB-backed record tests
# ---------------------------------------------------------------------------


def test_is_new_false_applies_to_target_element_in_records(app: object) -> None:
    """is_new=false elements should be merged into their target in records output."""
    require_app(app)
    scope = ListenScope("is-new-false", generated_block_bid="block-1")

    def text_row(seq: int, **overrides: object) -> object:
        return scope.render(
            run_event_seq=seq,
            element_type="text",
            element_type_code=213,
            sequence_number=seq,
            **overrides,
        )

    with app.app_context():
        reset_learn_tables()
        add_rows(
            scope.progress(),
            text_row(1, element_bid="el-original", content_text="version 1"),
            text_row(
                2,
                element_bid="el-patch",
                target_element_bid="el-original",
                is_new=0,
                is_final=1,
                content_text="version 2 patched",
            ),
        )
        result = scope.record(app)

    # Only the original element should appear, but with patched content
    assert len(result.elements) == 1
    assert result.elements[0].element_bid == "el-original"
    assert result.elements[0].content_text == "version 2 patched"
    assert result.elements[0].is_renderable is False
    assert result.elements[0].is_speakable is True
    assert result.elements[0].is_final is True


def test_records_ordered_by_sequence_number(app: object) -> None:
    """Records should be sorted by sequence_number, run_event_seq, id."""
    require_app(app)
    scope = ListenScope(
        "seq-order", generated_block_bid="block-seq", run_session_bid="run-seq-order"
    )

    with app.app_context():
        reset_learn_tables()
        # Insert elements with out-of-order sequence_numbers
        add_rows(
            scope.progress(),
            *(
                scope.render(
                    element_bid=elem_bid,
                    run_event_seq=seq_num,
                    element_index=seq_num - 1,
                    element_type="text",
                    element_type_code=213,
                    sequence_number=seq_num,
                    is_final=1,
                    content_text=f"element {seq_num}",
                )
                for seq_num, elem_bid in [(3, "el-c"), (1, "el-a"), (2, "el-b")]
            ),
        )
        result = scope.record(app)

    assert [e.element_bid for e in result.elements] == ["el-a", "el-b", "el-c"]


def test_records_merge_follow_up_history_after_anchor_element(app: object) -> None:
    require_app(app)
    scope = ListenScope("follow-up-order")

    def row(seq: int, element_bid: str, block: str, **overrides: object) -> object:
        return scope.with_block(block).element(
            element_bid=element_bid,
            run_event_seq=seq,
            change_type="render",
            is_renderable=0,
            sequence_number=seq,
            is_final=1,
            **overrides,
        )

    with app.app_context():
        reset_learn_tables()
        add_rows(
            scope.progress(),
            row(
                1,
                "anchor-1",
                "block-anchor",
                element_type="text",
                element_type_code=213,
                is_speakable=1,
                content_text="anchor content",
                payload=_serialize_payload(ElementPayloadDTO()),
            ),
            row(
                2,
                "normal-2",
                "block-normal",
                element_index=1,
                element_type="text",
                element_type_code=213,
                is_speakable=1,
                content_text="normal content",
                payload=_serialize_payload(ElementPayloadDTO()),
            ),
            row(
                3,
                "ask-1",
                "block-ask",
                role="student",
                element_type="ask",
                element_type_code=206,
                is_navigable=0,
                content_text="follow up question",
                payload=_serialize_payload(
                    ElementPayloadDTO(anchor_element_bid="anchor-1")
                ),
            ),
            row(
                4,
                "answer-1",
                "block-answer",
                element_type="answer",
                element_type_code=214,
                is_navigable=0,
                content_text="follow up answer",
                payload=_serialize_payload(
                    ElementPayloadDTO(
                        anchor_element_bid="anchor-1",
                        ask_element_bid="ask-1",
                    )
                ),
            ),
        )
        result = scope.record(app)

    bids = [element.element_bid for element in result.elements]
    assert bids == ["anchor-1", "ask-1", "answer-1", "normal-2"]
    assert result.elements[0].payload is not None
    assert result.elements[0].payload.asks == [
        {
            "role": "student",
            "content": "follow up question",
            "generated_block_bid": "block-ask",
        },
        {
            "role": "teacher",
            "content": "follow up answer",
            "generated_block_bid": "block-answer",
        },
    ]


def test_legacy_element_type_deserialized_to_new_enum(app: object) -> None:
    """Legacy element_type values like 'sandbox' should map to new enum."""
    require_app(app)
    scope = ListenScope("legacy-type", generated_block_bid="block-legacy")

    with app.app_context():
        reset_learn_tables()
        add_rows(
            scope.progress(),
            scope.render(
                element_bid="el-legacy",
                run_event_seq=1,
                element_type="sandbox",
                element_type_code=102,
                is_final=1,
                content_text="legacy content",
            ),
        )
        result = scope.record(app)

    assert len(result.elements) == 1
    # Legacy "sandbox" should be mapped to ElementType.HTML
    assert result.elements[0].element_type == ElementType.HTML
    assert result.elements[0].is_marker is True


def test_non_text_elements_are_never_speakable_in_records(app: object) -> None:
    """Non-text elements must normalize is_speakable to false."""
    require_app(app)
    scope = ListenScope(
        "non-text-speakable",
        generated_block_bid="block-visual",
        run_session_bid="run-visual",
    )

    with app.app_context():
        reset_learn_tables()
        add_rows(
            scope.progress(),
            scope.render(
                element_bid="el-visual",
                run_event_seq=1,
                element_type="html",
                element_type_code=201,
                is_marker=1,
                sequence_number=1,
                is_speakable=1,
                audio_url="https://example.com/visual.mp3",
                audio_segments=json.dumps(
                    [{"position": 0, "segment_index": 0, "audio_data": ""}]
                ),
                is_final=1,
                content_text="<div>visual</div>",
            ),
        )
        result = scope.record(app)

    assert len(result.elements) == 1
    assert result.elements[0].element_type == ElementType.HTML
    assert result.elements[0].is_renderable is True
    assert result.elements[0].is_marker is True
    assert result.elements[0].is_speakable is False


@pytest.mark.parametrize(
    ("slug", "block_fields", "expected_user_input"),
    [
        pytest.param(
            "interaction-input",
            {
                "type": BLOCK_TYPE_MDINTERACTION_VALUE,
                "block_content_conf": "?[Agree//agree][Disagree//disagree]",
                "generated_content": "agree",
            },
            "agree",
            id="interaction_block_backfills_submitted_input",
        ),
        # A 2.0 turn keeps its question in the block that holds what it taught.
        # That block's generated content is the lesson text, not an answer. Read
        # as the learner's input, it pre-filled the question with the sentence
        # before it, enabled its submit button with nothing chosen, and sent the
        # sentence as the answer.
        pytest.param(
            "turn-block",
            {
                "type": BLOCK_TYPE_MDCONTENT_VALUE,
                "generated_content": "Pick one of these, then we go on:",
            },
            None,
            id="turn_block_lesson_text_is_not_the_learner_answer",
        ),
    ],
)
def test_interaction_record_user_input_comes_only_from_interaction_blocks(
    app: object, slug: str, block_fields: dict, expected_user_input: str | None
) -> None:
    require_app(app)
    scope = ListenScope(slug)

    with app.app_context():
        reset_learn_tables()
        add_rows(
            scope.progress(),
            scope.block(block_bid="", role="teacher", **block_fields),
            scope.render(
                element_bid=f"el-{slug}",
                run_event_seq=1,
                role="ui",
                element_type="interaction",
                element_type_code=205,
                is_marker=1,
                sequence_number=1,
                is_navigable=0,
                is_final=1,
                content_text="?[Agree//agree][Disagree//disagree]",
            ),
        )
        result = scope.record(app)

    assert len(result.elements) == 1
    element = result.elements[0]
    assert element.payload is not None
    if expected_user_input is None:
        assert not element.payload.user_input
    else:
        assert element.payload.user_input == expected_user_input


def test_live_interaction_events_use_ui_role_and_generated_input(
    adapter_app: object,
) -> None:
    scope = LIVE.replace(
        progress_bid="progress-live-interaction",
        generated_block_bid="generated-live-interaction",
    )

    with adapter_app.app_context():
        add_rows(
            scope.block(
                block_bid="block-live-interaction",
                type=BLOCK_TYPE_MDINTERACTION_VALUE,
                generated_content="agree",
                block_content_conf="?[Agree//agree][Disagree//disagree]",
            )
        )

        streamed = list(
            scope.adapter(adapter_app).process(
                [
                    RunMarkdownFlowDTO(
                        outline_bid=scope.outline_bid,
                        generated_block_bid=scope.generated_block_bid,
                        type=GeneratedType.INTERACTION,
                        content="?[Agree//agree][Disagree//disagree]",
                    )
                ]
            )
        )

        assert len(streamed) == 1
        assert streamed[0].type == "element"

        interaction_element = streamed[0].content
        assert interaction_element.element_type == ElementType.INTERACTION
        assert interaction_element.role == "ui"
        assert interaction_element.payload is not None
        assert interaction_element.payload.user_input == "agree"

        persisted = LearnGeneratedElement.query.one()
        assert persisted.role == "ui"


# ---------------------------------------------------------------------------
# ElementPayloadDTO.asks tests
# ---------------------------------------------------------------------------


class TestElementPayloadAsks:
    """Verify element payload asks behavior."""

    def test_payload_asks_none_by_default(self) -> None:
        payload = ElementPayloadDTO()
        assert payload.asks is None
        assert "asks" not in payload.__json__()

    @pytest.mark.parametrize(
        "asks",
        [
            pytest.param(
                [
                    {"role": "student", "content": "what is this?"},
                    {"role": "teacher", "content": "this is a demo"},
                ],
                id="non_empty",
            ),
            pytest.param([], id="empty_list"),
        ],
    )
    def test_payload_asks_serialization(self, asks: list[dict]) -> None:
        assert ElementPayloadDTO(asks=asks).__json__()["asks"] == asks

    def test_payload_asks_deserialization(self) -> None:
        asks = [
            {"role": "student", "content": "question"},
            {"role": "teacher", "content": "answer"},
        ]
        raw = _serialize_payload(ElementPayloadDTO(asks=asks))
        assert _deserialize_payload(raw).asks == asks

    @pytest.mark.parametrize(
        "raw",
        [
            pytest.param(EMPTY_PAYLOAD, id="missing"),
            pytest.param(
                '{"audio": null, "previous_visuals": [], "asks": "not_a_list"}',
                id="invalid_type",
            ),
        ],
    )
    def test_payload_asks_deserialization_drops_missing_or_invalid(
        self, raw: str
    ) -> None:
        assert _deserialize_payload(raw).asks is None


# ---------------------------------------------------------------------------
# GeneratedType.ASK tests
# ---------------------------------------------------------------------------


class TestGeneratedTypeAsk:
    """Verify generated type ask behavior."""

    def test_ask_enum_exists(self) -> None:
        assert GeneratedType.ASK.value == "ask"

    def test_ask_not_in_legacy_types(self) -> None:
        legacy = {
            GeneratedType.CONTENT,
            GeneratedType.BREAK,
            GeneratedType.INTERACTION,
            GeneratedType.DONE,
        }
        assert GeneratedType.ASK not in legacy


def _history_row(text: str, payload: ElementPayloadDTO, **fields: object) -> object:
    return types.SimpleNamespace(
        content_text=text, payload=_serialize_payload(payload), **fields
    )


class TestAskContextLoading:
    """Tests for the shared follow-up ask validation and history helpers."""

    @pytest.mark.parametrize(
        ("asks", "expected"),
        [
            pytest.param(
                [
                    {"role": "student", "content": "q"},
                    {"role": "teacher", "content": "a"},
                ],
                True,
                id="question_and_answer",
            ),
            pytest.param([], False, id="empty"),
            pytest.param(None, False, id="none"),
            pytest.param(
                [{"role": "student", "content": "q"}], False, id="student_only"
            ),
        ],
    )
    def test_is_valid_asks(self, asks: list[dict] | None, expected: bool) -> None:
        assert is_complete_follow_up_asks(asks) is expected

    def test_load_context_from_follow_up_elements(self) -> None:
        anchor = _history_row("anchor text", ElementPayloadDTO())
        follow_up_elements = [
            _history_row(
                "q1",
                ElementPayloadDTO(anchor_element_bid="anchor_elem_1"),
                element_type="ask",
            ),
            _history_row(
                "a1",
                ElementPayloadDTO(
                    anchor_element_bid="anchor_elem_1",
                    ask_element_bid="ask_elem_1",
                ),
                element_type="answer",
            ),
        ]
        result = build_follow_up_element_history(anchor, follow_up_elements, 10)
        assert result is not None
        assert result[0] == {"role": "assistant", "content": "anchor text"}
        assert result[1] == {"role": "user", "content": "q1"}
        assert result[2] == {"role": "assistant", "content": "a1"}

    def test_load_context_fallback_to_legacy_payload_asks(self) -> None:
        asks = [
            {"role": "student", "content": "q1"},
            {"role": "teacher", "content": "a1"},
        ]
        anchor = _history_row("text", ElementPayloadDTO())
        follow_up_elements = [
            _history_row("", ElementPayloadDTO(asks=asks), element_type="ask")
        ]
        result = build_follow_up_element_history(anchor, follow_up_elements, 10)
        assert result is not None
        assert result[0] == {"role": "assistant", "content": "text"}
        assert result[1] == {"role": "user", "content": "q1"}
        assert result[2] == {"role": "assistant", "content": "a1"}

    def test_load_context_fallback_to_none(self) -> None:
        anchor = _history_row("text", ElementPayloadDTO())
        assert build_follow_up_element_history(anchor, [], 10) is None

    def test_load_context_none_element(self) -> None:
        assert build_follow_up_element_history(None, [], 10) is None

    def test_load_context_truncation(self) -> None:
        follow_up_elements = [
            _history_row(
                f"m{i}",
                ElementPayloadDTO(anchor_element_bid="anchor"),
                element_type="ask" if i % 2 == 0 else "answer",
            )
            for i in range(20)
        ]
        anchor = _history_row("anchor", ElementPayloadDTO())
        result = build_follow_up_element_history(anchor, follow_up_elements, 4)
        assert result is not None
        # anchor content + last 4 follow-up messages
        assert len(result) == 5


# ---------------------------------------------------------------------------
# Follow-up ask and answer through ListenElementRunAdapter
# ---------------------------------------------------------------------------


def _add_anchor(element_bid: str, content_text: str, **overrides: object) -> None:
    """Persist a final teacher text element that a follow-up ask can anchor to."""
    db.session.add(
        LIVE.element(
            element_bid=element_bid,
            run_event_seq=1,
            element_type="text",
            change_type="render",
            content_text=content_text,
            payload=_serialize_payload(ElementPayloadDTO()),
            **{"is_final": 1, **overrides},
        )
    )


def _latest_row(*filters: object) -> LearnGeneratedElement | None:
    return (
        LearnGeneratedElement.query.filter(*filters)
        .order_by(
            LearnGeneratedElement.run_event_seq.desc(),
            LearnGeneratedElement.id.desc(),
        )
        .first()
    )


class TestHandleAskAdapter:
    """Tests for ListenElementRunAdapter._handle_ask()."""

    def test_handle_ask_creates_standalone_question_element(
        self, adapter_app: object
    ) -> None:
        with adapter_app.app_context():
            adapter = LIVE.adapter(adapter_app)
            _add_anchor("anchor_elem_1", "hello world")
            db.session.flush()

            emitted = list(
                adapter._handle_ask(
                    LIVE.with_block("ask_gb1").ask(
                        "user question here", "anchor_elem_1"
                    )
                )
            )
            assert len(emitted) == 1
            assert adapter._current_ask_anchor_bid == "anchor_elem_1"
            assert adapter._current_ask_element_bid

            ask_rows = LearnGeneratedElement.query.filter(
                LearnGeneratedElement.element_type == "ask"
            ).all()
            assert len(ask_rows) == 1
            payload = json.loads(ask_rows[0].payload or "{}")
            assert payload["anchor_element_bid"] == "anchor_elem_1"
            assert "asks" not in payload
            assert ask_rows[0].content_text == "user question here"
            assert ask_rows[0].role == "student"

    def test_process_ask_persists_without_streaming(self, adapter_app: object) -> None:
        with adapter_app.app_context():
            adapter = LIVE.adapter(adapter_app)
            _add_anchor("anchor_elem_2", "content")
            db.session.flush()

            result = list(
                adapter.process(
                    [LIVE.with_block("ask_gb").ask("question", "anchor_elem_2")]
                )
            )
            assert result == []

            ask_row = _latest_row(LearnGeneratedElement.element_type == "ask")
            assert ask_row is not None
            payload = json.loads(ask_row.payload or "{}")
            assert ask_row.content_text == "question"
            assert ask_row.role == "student"
            assert payload["anchor_element_bid"] == "anchor_elem_2"

    def test_process_creates_standalone_answer_element(
        self, adapter_app: object
    ) -> None:
        ask = LIVE.with_block("ask_gb_answer")
        with adapter_app.app_context():
            adapter = LIVE.adapter(adapter_app)
            _add_anchor("anchor_elem_4", "anchor content")
            db.session.flush()

            streamed = list(
                adapter.process(
                    [
                        ask.ask("question", "anchor_elem_4"),
                        ask.content("answer"),
                        ask.block_break(),
                    ]
                )
            )
            ask_row = _latest_row(LearnGeneratedElement.element_type == "ask")
            assert ask_row is not None
            answer_messages = streamed_elements(streamed, ElementType.ANSWER)

            assert answer_messages
            final_answer = answer_messages[-1]
            assert final_answer.content_text == "answer"
            assert final_answer.role == "teacher"
            assert final_answer.payload.anchor_element_bid == "anchor_elem_4"
            assert final_answer.payload.ask_element_bid == ask_row.element_bid

            answer_row = _latest_row(LearnGeneratedElement.element_type == "answer")
            assert answer_row is not None
            payload = json.loads(answer_row.payload or "{}")
            assert answer_row.content_text == "answer"
            assert answer_row.role == "teacher"
            assert payload["anchor_element_bid"] == "anchor_elem_4"
            assert payload["ask_element_bid"] == ask_row.element_bid
            assert "asks" not in payload

    def test_process_streams_multi_chunk_follow_up_answer_but_persists_only_final_row(
        self, adapter_app: object
    ) -> None:
        ask = LIVE.with_block("ask_gb_multi_chunk")
        with adapter_app.app_context():
            adapter = LIVE.adapter(adapter_app)
            _add_anchor("anchor_elem_multi_chunk", "anchor content")
            db.session.flush()

            streamed = list(
                adapter.process(
                    [
                        ask.ask("question", "anchor_elem_multi_chunk"),
                        ask.content("hello"),
                        ask.content(" world"),
                        ask.block_break(),
                    ]
                )
            )
            answer_messages = streamed_elements(streamed, ElementType.ANSWER)

            assert [(item.content_text, item.is_final) for item in answer_messages] == [
                ("hello", False),
                ("hello world", False),
                ("hello world", True),
            ]
            logical_bids = {
                item.target_element_bid or item.element_bid for item in answer_messages
            }
            assert len(logical_bids) == 1
            (logical_answer_bid,) = logical_bids
            assert logical_answer_bid

            answer_rows = (
                LearnGeneratedElement.query.filter(
                    LearnGeneratedElement.generated_block_bid
                    == ask.generated_block_bid,
                    LearnGeneratedElement.element_type == "answer",
                    LearnGeneratedElement.run_session_bid == adapter.run_session_bid,
                )
                .order_by(
                    LearnGeneratedElement.run_event_seq.asc(),
                    LearnGeneratedElement.id.asc(),
                )
                .all()
            )
            assert len(answer_rows) == 1
            assert answer_rows[0].status == 1
            assert answer_rows[0].content_text == "hello world"
            assert answer_rows[0].target_element_bid == logical_answer_bid

    def test_process_creates_answer_element_for_patched_anchor_bid(
        self, adapter_app: object
    ) -> None:
        answer = LIVE.with_block("answer_gb_split")
        with adapter_app.app_context():
            adapter = LIVE.adapter(adapter_app)
            anchor = LIVE.with_block("gb_anchor")
            db.session.add_all(
                [
                    anchor.element(
                        element_bid="anchor_elem_stable",
                        run_event_seq=1,
                        element_type="text",
                        change_type="render",
                        content_text="anchor draft",
                        payload=_serialize_payload(ElementPayloadDTO()),
                        status=0,
                    ),
                    anchor.element(
                        element_bid="anchor_elem_active",
                        run_event_seq=2,
                        element_type="text",
                        change_type="render",
                        target_element_bid="anchor_elem_stable",
                        is_new=0,
                        is_final=1,
                        content_text="anchor final",
                        payload=_serialize_payload(ElementPayloadDTO()),
                    ),
                ]
            )
            db.session.flush()

            streamed = list(
                adapter.process(
                    [
                        LIVE.with_block("ask_gb_split").ask(
                            "question", "anchor_elem_stable"
                        ),
                        answer.content("answer"),
                        answer.block_break(),
                    ]
                )
            )
            answer_messages = streamed_elements(streamed, ElementType.ANSWER)

            assert answer_messages
            final_answer = answer_messages[-1]
            assert final_answer.content_text == "answer"
            assert final_answer.payload.anchor_element_bid == "anchor_elem_stable"

            answer_row = _latest_row(
                LearnGeneratedElement.generated_block_bid == answer.generated_block_bid,
                LearnGeneratedElement.element_type == "answer",
                LearnGeneratedElement.status == 1,
            )
            assert answer_row is not None
            assert answer_row.content_text == "answer"

    def test_answer_audio_events_do_not_attach_audio(self, adapter_app: object) -> None:
        ask = LIVE.with_block("ask_gb_audio")
        with adapter_app.app_context():
            adapter = LIVE.adapter(adapter_app)
            _add_anchor("anchor_elem_audio", "anchor content")
            db.session.flush()

            streamed = list(
                adapter.process(
                    [
                        ask.ask("question", "anchor_elem_audio"),
                        ask.content("answer"),
                        ask.audio_segment(
                            **audio_segment(0, 0, "segment-0", 120, is_final=False)
                        ),
                        ask.audio_complete(
                            audio_url="https://example.com/answer-audio.mp3",
                            audio_bid="answer-audio",
                            duration_ms=120,
                            position=0,
                        ),
                        ask.block_break(),
                    ]
                )
            )
            answer_messages = streamed_elements(streamed, ElementType.ANSWER)
            assert answer_messages
            final_answer = answer_messages[-1]
            assert final_answer.is_final is True
            assert final_answer.audio_url == ""
            assert final_answer.audio_segments == []
            assert final_answer.payload is not None
            assert final_answer.payload.audio is None

    @pytest.mark.parametrize(
        ("ask_provider_config", "provider_fails", "expected_answer"),
        [
            pytest.param(
                {
                    "provider": "coze",
                    "mode": "provider_then_llm",
                    "config": {"bot_id": "bot-1"},
                },
                False,
                "provider-answer",
                id="provider_stream",
            ),
            pytest.param(
                {"provider": "dify", "mode": "provider_only", "config": {}},
                True,
                "server.learn.askProviderUnavailable",
                id="provider_only_error",
            ),
        ],
    )
    def test_handle_input_ask_provider_returns_answer_element(
        self,
        adapter_app: object,
        monkeypatch: pytest.MonkeyPatch,
        ask_provider_config: dict,
        provider_fails: bool,
        expected_answer: str,
    ) -> None:
        from flaskr.service.learn.ask import handler as module

        def _provider_stream(**_kwargs: object) -> object:
            if provider_fails:
                message = "provider failed"
                raise AskProviderError(message)
            yield types.SimpleNamespace(content="provider-answer")

        anchor_bid = f"anchor_elem_handle_{'error' if provider_fails else 'stream'}"
        with adapter_app.app_context():
            _setup_handle_input_ask_test_doubles(
                monkeypatch,
                module,
                ask_provider_config,
                patch_generated_blocks=False,
            )
            monkeypatch.setattr(
                module, "stream_ask_provider_response", _provider_stream
            )
            monkeypatch.setattr(module, "chat_llm", lambda *_args, **_kwargs: iter([]))

            _add_anchor(anchor_bid, "anchor content", generated_block_bid="gb_anchor")
            db.session.flush()

            adapter = LIVE.adapter(adapter_app)
            events = list(
                module.handle_input_ask(
                    app=adapter_app,
                    context=_FollowUpContext(),
                    user_info=types.SimpleNamespace(user_id="u1"),
                    attend_id="pr1",
                    user_input="hello",
                    outline_item_info=types.SimpleNamespace(
                        shifu_bid="s1", bid="o1", title="Outline", position=1
                    ),
                    trace_args={"output": ""},
                    trace=_FollowUpDummyTrace(),
                    anchor_element_bid=anchor_bid,
                )
            )

            ask_events = [event for event in events if event.type == GeneratedType.ASK]
            content_events = [
                event for event in events if event.type == GeneratedType.CONTENT
            ]
            assert len(ask_events) == 1
            assert len(content_events) == 1
            assert (
                ask_events[0].generated_block_bid
                == content_events[0].generated_block_bid
            )
            assert content_events[0].content == expected_answer
            answer_block_bid = ask_events[0].generated_block_bid

            answer_messages = streamed_elements(
                adapter.process(events), ElementType.ANSWER
            )
            assert answer_messages
            assert answer_messages[-1].content_text == expected_answer

            answer_row = _latest_row(
                LearnGeneratedElement.generated_block_bid == answer_block_bid,
                LearnGeneratedElement.element_type == "answer",
                LearnGeneratedElement.status == 1,
            )
            assert answer_row is not None
            assert answer_row.content_text == expected_answer


# ---------------------------------------------------------------------------
# Live element change semantics through ListenElementRunAdapter
# ---------------------------------------------------------------------------


def _process(app: object, scope: ListenScope, events: list[object]) -> list[object]:
    return list(scope.adapter(app).process(events))


class TestElementChangeTypeSemantics:
    """Verify element change type semantics behavior."""

    def test_text_patch_keeps_render_change_type(self, adapter_app: object) -> None:
        scope = LIVE.with_block("gb-text")
        with adapter_app.app_context():
            streamed = _process(
                adapter_app,
                scope,
                [scope.content("Hello", "text", 0), scope.content(" world", "text", 0)],
            )
            text_events = streamed_elements(streamed, ElementType.TEXT)

            assert len(text_events) == 2
            assert [item.is_new for item in text_events] == [True, True]
            assert [item.change_type for item in text_events] == [
                ElementChangeType.RENDER,
                ElementChangeType.RENDER,
            ]
            assert all(item.target_element_bid in ("", None) for item in text_events)

    def test_gitdiff_element_uses_diff_change_type_without_forcing_patch(
        self, adapter_app: object
    ) -> None:
        scope = LIVE.with_block("gb-diff")
        with adapter_app.app_context():
            streamed = _process(
                adapter_app,
                scope,
                [
                    scope.content("@@ -1 +1 @@\n-old\n+new\n", "diff", 0),
                    scope.content("+tail\n", "diff", 0),
                ],
            )
            diff_events = streamed_elements(streamed, ElementType.DIFF)

            assert len(diff_events) == 2
            assert [item.is_new for item in diff_events] == [False, False]
            assert [item.change_type for item in diff_events] == [
                ElementChangeType.DIFF,
                ElementChangeType.DIFF,
            ]
            assert diff_events[0].target_element_bid == diff_events[0].element_bid
            assert diff_events[1].target_element_bid == diff_events[0].element_bid

    def test_html_after_text_creates_new_element(self, adapter_app: object) -> None:
        scope = LIVE.with_block("gb-html")
        with adapter_app.app_context():
            streamed = _process(
                adapter_app,
                scope,
                [
                    scope.content("<div>Intro visual</div>\n", "html", 0),
                    scope.content("Narration\n", "text", 1),
                    scope.content("<div>Follow-up visual</div>\n", "html", 2),
                ],
            )
            html_events = streamed_elements(streamed, ElementType.HTML)

            assert len(html_events) == 2
            assert [item.is_new for item in html_events] == [True, True]
            assert html_events[0].target_element_bid in ("", None)
            assert html_events[1].target_element_bid in ("", None)
            assert html_events[0].element_bid != html_events[1].element_bid

    def test_mdflow_stream_elements_are_not_rebuilt_from_av_contract(
        self, adapter_app: object
    ) -> None:
        scope = LIVE.with_block("gb-mdflow-av")
        raw_content = (
            "Before image.\n\n![img](https://example.com/visual.png)\n\nAfter image."
        )
        av_contract = build_av_segmentation_contract(
            raw_content, scope.generated_block_bid
        )

        with adapter_app.app_context():
            streamed = _process(
                adapter_app,
                scope,
                [
                    scope.content("Before image.\n\n", "text", 0),
                    scope.content(
                        "![img](https://example.com/visual.png)\n\n", "img", 1
                    ),
                    scope.content("After image.", "text", 2),
                    scope.audio_complete(
                        audio_url="https://example.com/audio-0.mp3",
                        audio_bid="audio-0",
                        duration_ms=320,
                        position=0,
                        av_contract=av_contract,
                    ),
                    scope.block_break(),
                ],
            )
            elements = streamed_elements(streamed)
            retire_events = [item for item in elements if item.is_navigable == 0]
            final_snapshots = list(
                {
                    item.element_bid: item
                    for item in elements
                    if item.is_navigable == 1 and item.is_final is True
                }.values()
            )

            assert retire_events == []
            assert len(final_snapshots) == 3
            assert [
                item.element_type
                for item in final_snapshots
                if item.element_type == ElementType.IMG
            ] == [ElementType.IMG]

            final_text_events = {
                item.content_text: item
                for item in final_snapshots
                if item.element_type == ElementType.TEXT
            }
            assert sorted(final_text_events) == ["After image.", "Before image.\n\n"]
            assert (
                final_text_events["Before image.\n\n"].audio_url
                == "https://example.com/audio-0.mp3"
            )
            assert final_text_events["After image."].audio_url == ""

    def test_pending_audio_skips_image_stream_and_binds_to_following_text(
        self, adapter_app: object
    ) -> None:
        scope = LIVE.with_block("gb-img-audio")
        bound_segment = audio_segment(0, 0, "img-only-segment", 210, is_final=True)
        with adapter_app.app_context():
            streamed = _process(
                adapter_app,
                scope,
                [
                    scope.content("![img](https://example.com/visual.png)\n", "img", 0),
                    scope.audio_segment(**{**bound_segment, "is_final": False}),
                    scope.audio_complete(
                        audio_url="https://example.com/img-only.mp3",
                        audio_bid="img-only-audio-0",
                        duration_ms=210,
                        position=0,
                    ),
                    scope.content("caption line\n", "text", 1),
                    scope.block_break(),
                ],
            )
            image_events = streamed_elements(streamed, ElementType.IMG)
            text_events = streamed_elements(streamed, ElementType.TEXT)

            assert len(image_events) >= 1
            assert all(item.audio_url == "" for item in image_events)
            assert all(item.audio_segments == [] for item in image_events)
            assert all(item.is_speakable is False for item in image_events)

            assert len(text_events) >= 1
            assert text_events[0].audio_url == "https://example.com/img-only.mp3"
            assert text_events[0].audio_segments == [bound_segment]
            final_text_event = next(
                item
                for item in text_events
                if item.audio_url == "https://example.com/img-only.mp3"
                and item.is_final
            )
            assert final_text_event.audio_segments == [bound_segment]
            assert final_text_event.is_final is True
            assert all(item.is_speakable is True for item in text_events)

    @pytest.mark.parametrize(
        ("label", "chunks", "stream_kind", "duration_ms"),
        [
            pytest.param(
                "fallback", ("Hello", " world"), None, 480, id="fallback_text"
            ),
            pytest.param(
                "stream", ("Hello ", "world"), "text", 520, id="mdflow_stream_text"
            ),
        ],
    )
    def test_text_patch_keeps_bound_audio_during_in_progress_history(
        self,
        adapter_app: object,
        label: str,
        chunks: tuple[str, str],
        stream_kind: str | None,
        duration_ms: int,
    ) -> None:
        scope = ListenScope(f"{label}-audio-retain")
        audio_url = f"https://example.com/{label}-retain.mp3"
        audio_bid = f"{label}-retain-audio"

        with adapter_app.app_context():
            scope.seed_block(type=BLOCK_TYPE_MDCONTENT_VALUE)
            streamed = _process(
                adapter_app,
                scope,
                [
                    scope.content(chunks[0], stream_kind, 0),
                    scope.audio_complete(
                        audio_url=audio_url,
                        audio_bid=audio_bid,
                        duration_ms=duration_ms,
                        position=0,
                    ),
                    scope.content(chunks[1], stream_kind, 0),
                ],
            )
            latest_live_element = streamed[-1].content
            history_record = scope.record(adapter_app)

        assert len(history_record.elements) == 1
        history_element = history_record.elements[0]
        assert history_element.is_speakable is True
        for element in (latest_live_element, history_element):
            assert element.audio_url == audio_url
            assert element.payload is not None
            assert element.payload.audio is not None
            assert element.payload.audio.audio_bid == audio_bid
            assert element.content_text == "Hello world"

    def test_live_audio_patches_mirror_progressive_subtitles_on_same_element(
        self, adapter_app: object
    ) -> None:
        scope = LIVE.with_block("gb-subtitle-freeze")
        stream = {"stream_element_number": 1, "stream_element_type": "text"}
        first_cues = subtitle_cues(("First sentence.", 0, 180))
        second_cues = subtitle_cues(
            ("First sentence.", 0, 170), ("Second sentence.", 180, 320)
        )

        with adapter_app.app_context():
            streamed = _process(
                adapter_app,
                scope,
                [
                    scope.content("First sentence.\n", "text", 1),
                    scope.audio_segment(
                        **audio_segment(0, 0, "segment-0", 180, is_final=False),
                        **stream,
                        subtitle_cues=first_cues,
                    ),
                    scope.audio_segment(
                        **audio_segment(0, 1, "segment-1", 320, is_final=False),
                        **stream,
                        subtitle_cues=second_cues,
                    ),
                    scope.content("Second sentence.\n", "text", 1),
                    scope.audio_complete(
                        audio_url="https://example.com/subtitle-freeze.mp3",
                        audio_bid="subtitle-freeze-audio",
                        duration_ms=500,
                        position=0,
                        **stream,
                        subtitle_cues=subtitle_cues(
                            ("First sentence.", 0, 160), ("Second sentence.", 180, 340)
                        ),
                    ),
                ],
            )
            text_events = streamed_elements(streamed, ElementType.TEXT)

        assert len(text_events) == 5
        _, first_segment_patch, second_segment_patch, content_patch, final_patch = (
            text_events
        )

        assert first_segment_patch.element_bid == final_patch.element_bid
        assert first_segment_patch.payload is not None
        assert first_segment_patch.payload.audio is not None
        assert [
            cue.text for cue in first_segment_patch.payload.audio.subtitle_cues
        ] == ["First sentence."]
        assert cue_spans(first_segment_patch) == [(0, 180)]
        assert first_segment_patch.payload.audio.duration_ms == 180
        assert first_segment_patch.audio_segments == [
            audio_segment(
                0, 0, "segment-0", 180, is_final=False, subtitle_cues=first_cues
            )
        ]

        # The content patch keeps mirroring the latest segment's cues.
        for patch in (second_segment_patch, content_patch):
            assert [cue.text for cue in patch.payload.audio.subtitle_cues] == [
                "First sentence.",
                "Second sentence.",
            ]
            assert cue_spans(patch) == [(0, 170), (180, 320)]
            assert patch.payload.audio.duration_ms == 320

        assert final_patch.audio_url == "https://example.com/subtitle-freeze.mp3"
        assert final_patch.payload is not None
        assert final_patch.payload.audio is not None
        assert final_patch.payload.audio.audio_bid == "subtitle-freeze-audio"
        assert [cue.text for cue in final_patch.payload.audio.subtitle_cues] == [
            "First sentence.",
            "Second sentence.",
        ]
        assert cue_spans(final_patch) == [(0, 160), (180, 340)]
        assert final_patch.payload.audio.duration_ms == 340
        assert final_patch.audio_segments == [
            audio_segment(
                0, 0, "segment-0", 180, is_final=False, subtitle_cues=first_cues
            ),
            audio_segment(
                0, 1, "segment-1", 320, is_final=True, subtitle_cues=second_cues
            ),
        ]

    @pytest.mark.parametrize(
        ("block", "texts", "segment_spans", "complete_spans"),
        [
            pytest.param(
                "gb-subtitle-grow",
                ("Sentence one.", "Sentence two."),
                ([(0, 80), (100, 180)], [(0, 140), (180, 320)]),
                [(0, 160), (220, 360)],
                id="same_cue_count_with_moving_bounds",
            ),
            pytest.param(
                "gb-subtitle-middle",
                ("Sentence one.", "Sentence two.", "Sentence three."),
                (
                    [(0, 40), (40, 80), (80, 180)],
                    [(0, 120), (120, 220), (220, 320)],
                ),
                [(0, 140), (140, 250), (250, 360)],
                id="middle_cue_bounds_move",
            ),
        ],
    )
    def test_live_audio_patches_keep_incoming_cue_bounds(
        self,
        adapter_app: object,
        block: str,
        texts: tuple[str, ...],
        segment_spans: tuple[list[tuple[int, int]], list[tuple[int, int]]],
        complete_spans: list[tuple[int, int]],
    ) -> None:
        """Each patch carries the cue bounds it received, never a rewritten copy."""
        scope = LIVE.with_block(block)
        stream = {"stream_element_number": 1, "stream_element_type": "text"}

        def cues(spans: list[tuple[int, int]]) -> list[dict]:
            return subtitle_cues(
                *(
                    (text, start, end)
                    for text, (start, end) in zip(texts, spans, strict=True)
                )
            )

        with adapter_app.app_context():
            streamed = _process(
                adapter_app,
                scope,
                [
                    scope.content(" ".join(texts) + "\n", "text", 1),
                    *(
                        scope.audio_segment(
                            position=0,
                            segment_index=index,
                            audio_data=f"{block}-segment-{index}",
                            duration_ms=spans[-1][1],
                            is_final=False,
                            subtitle_cues=cues(spans),
                            **stream,
                        )
                        for index, spans in enumerate(segment_spans)
                    ),
                    scope.audio_complete(
                        audio_url=f"https://example.com/{block}.mp3",
                        audio_bid=f"{block}-audio",
                        duration_ms=complete_spans[-1][1],
                        position=0,
                        subtitle_cues=cues(complete_spans),
                        **stream,
                    ),
                ],
            )
            text_events = streamed_elements(streamed, ElementType.TEXT)

        assert len(text_events) == 4
        patches = text_events[1:]
        for patch, spans in zip(patches, (*segment_spans, complete_spans), strict=True):
            assert cue_spans(patch) == spans
            assert patch.payload.audio.duration_ms == spans[-1][1]

    def test_explicit_stream_audio_waits_for_matching_text_element(
        self, adapter_app: object
    ) -> None:
        scope = LIVE.with_block("gb-pending-explicit-audio")
        stream = {"stream_element_number": 1, "stream_element_type": "text"}
        segment_cues = subtitle_cues(("Delayed narration.", 0, 180))

        with adapter_app.app_context():
            streamed = _process(
                adapter_app,
                scope,
                [
                    scope.content("Intro line.\n", "text", 0),
                    scope.audio_segment(
                        **audio_segment(0, 0, "segment-0", 180, is_final=False),
                        **stream,
                        subtitle_cues=segment_cues,
                    ),
                    scope.content("Still intro.\n", "text", 0),
                    scope.audio_complete(
                        audio_url="https://example.com/delayed.mp3",
                        audio_bid="delayed-audio",
                        duration_ms=240,
                        position=0,
                        **stream,
                        subtitle_cues=subtitle_cues(("Delayed narration.", 0, 240)),
                    ),
                    scope.content("Delayed narration.\n", "text", 1),
                ],
            )
            text_events = streamed_elements(streamed, ElementType.TEXT)

        assert len(text_events) == 3
        intro_event, intro_patch, delayed_event = text_events

        assert intro_event.element_bid == intro_patch.element_bid
        assert intro_event.payload is not None
        assert intro_event.payload.audio is None
        assert intro_patch.payload is not None
        assert intro_patch.payload.audio is None
        assert intro_patch.audio_url == ""
        assert intro_patch.audio_segments == []

        assert delayed_event.element_bid != intro_event.element_bid
        assert delayed_event.audio_url == "https://example.com/delayed.mp3"
        assert delayed_event.payload is not None
        assert delayed_event.payload.audio is not None
        assert delayed_event.payload.audio.audio_bid == "delayed-audio"
        assert [cue.text for cue in delayed_event.payload.audio.subtitle_cues] == [
            "Delayed narration."
        ]
        assert cue_spans(delayed_event) == [(0, 240)]
        assert delayed_event.audio_segments == [
            audio_segment(
                0, 0, "segment-0", 180, is_final=True, subtitle_cues=segment_cues
            )
        ]
