"""Tests for the element protocol freeze (Sections A-D of the design doc).

Covers:
- ElementDTO new fields serialization/deserialization
- ElementType new enum values and legacy fallback
- TypeStateMachine transitions and output
- is_new=false / is_marker constraint behaviour
- audio_segments accumulation
"""

import types

import pytest


@pytest.fixture
def adapter_app():
    from flask import Flask
    import flaskr.dao as dao
    import flaskr.service.learn.models  # noqa: F401

    app = Flask("test-handle-ask-adapter")
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    dao.db.init_app(app)
    with app.app_context():
        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


class _FollowUpDummyGeneration:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.end_kwargs = {}

    def end(self, **kwargs):
        self.end_kwargs = kwargs


class _FollowUpDummySpan:
    def __init__(self):
        self.generations = []
        self.updated = {}
        self.output = ""

    def generation(self, **kwargs):
        generation = _FollowUpDummyGeneration(**kwargs)
        self.generations.append(generation)
        return generation

    def span(self, **_kwargs):
        return _FollowUpDummySpan()

    def update(self, **kwargs):
        self.updated = kwargs

    def event(self, **_kwargs):
        return None

    def end(self, output=None, **kwargs):
        self.output = output or ""
        self.end_kwargs = {"output": output, **kwargs}


class _FollowUpDummyTrace:
    def __init__(self):
        self.updated = {}

    def span(self, **_kwargs):
        return _FollowUpDummySpan()

    def update(self, **kwargs):
        self.updated = kwargs


class _FollowUpContext:
    def __init__(self):
        self._shifu_info = types.SimpleNamespace(use_learner_language=0)
        self.langfuse_outputs = []

    def get_system_prompt(self, _outline_bid: str):
        return "COURSE_PROMPT"

    def append_langfuse_output(self, value: str):
        self.langfuse_outputs.append(value)


class _FollowUpInfo:
    def __init__(self, ask_provider_config):
        self.ask_prompt = "ASK_PROMPT::{shifu_system_message}"
        self.ask_model = "gpt-test"
        self.model_args = {"temperature": 0.2}
        self.ask_provider_config = ask_provider_config

    def __json__(self):
        return {
            "ask_model": self.ask_model,
            "ask_provider_config": self.ask_provider_config,
        }


def _setup_handle_input_ask_test_doubles(
    monkeypatch,
    module,
    ask_provider_config,
    *,
    patch_generated_blocks: bool = True,
):
    from flaskr.service.learn.ask_provider_adapters import AskProviderError

    class _DummyLLMSettings:
        def __init__(self, model, temperature):
            self.model = model
            self.temperature = temperature

    class _DummyAskProviderRuntime:
        def __init__(self, llm_stream_factory=None):
            self.llm_stream_factory = llm_stream_factory

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

        def _fake_init_generated_block(*_args, **_kwargs):
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
    def test_new_enum_values(self):
        from flaskr.service.learn.learn_dtos import ElementType

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

    def test_legacy_aliases_exist(self):
        from flaskr.service.learn.learn_dtos import ElementType

        assert ElementType._SANDBOX.value == "sandbox"
        assert ElementType._PICTURE.value == "picture"
        assert ElementType._VIDEO.value == "video"

    def test_invalid_value_raises(self):
        from flaskr.service.learn.learn_dtos import ElementType

        with pytest.raises(ValueError):
            ElementType("nonexistent")

    def test_element_type_codes_complete(self):
        from flaskr.service.learn.learn_dtos import ElementType
        from flaskr.service.learn.listen_element_types import ELEMENT_TYPE_CODES

        # Every non-legacy type must have a code
        for et in ElementType:
            if et.name.startswith("_"):
                continue
            assert et in ELEMENT_TYPE_CODES, f"Missing code for {et}"

    def test_legacy_mapping(self):
        from flaskr.service.learn.learn_dtos import ElementType
        from flaskr.service.learn.listen_element_types import LEGACY_ELEMENT_TYPE_MAP

        assert LEGACY_ELEMENT_TYPE_MAP[ElementType._SANDBOX] == ElementType.HTML
        assert LEGACY_ELEMENT_TYPE_MAP[ElementType._PICTURE] == ElementType.IMG
        assert LEGACY_ELEMENT_TYPE_MAP[ElementType._VIDEO] == ElementType.HTML


# ---------------------------------------------------------------------------
# ElementDTO new fields tests
# ---------------------------------------------------------------------------


class TestElementDTONewFields:
    def _make_dto(self, **overrides):
        from flaskr.service.learn.learn_dtos import ElementDTO, ElementType

        defaults = {
            "element_bid": "test-bid",
            "element_index": 0,
            "role": "teacher",
            "element_type": ElementType.TEXT,
            "element_type_code": 213,
        }
        defaults.update(overrides)
        return ElementDTO(**defaults)

    def test_default_values(self):
        dto = self._make_dto()
        assert dto.is_renderable is True
        assert dto.is_new is True
        assert dto.is_marker is False
        assert dto.sequence_number == 0
        assert dto.is_speakable is False
        assert dto.audio_url == ""
        assert dto.audio_segments == []

    def test_json_includes_new_fields(self):
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

    def test_json_field_order(self):
        dto = self._make_dto()
        result = dto.__json__()
        keys = list(result.keys())
        # Verify new fields are present
        assert "is_renderable" in keys
        assert "is_new" in keys
        assert "is_marker" in keys
        assert "sequence_number" in keys
        assert "is_speakable" in keys
        assert "audio_url" in keys
        assert "audio_segments" in keys

    def test_final_json_marks_all_audio_segments_final(self):
        dto = self._make_dto(
            is_final=True,
            audio_url="https://example.com/audio.mp3",
            audio_segments=[
                {"position": 0, "segment_index": 0, "is_final": False},
                {"position": 0, "segment_index": 1, "is_final": True},
            ],
        )

        result = dto.__json__()

        assert [segment["is_final"] for segment in result["audio_segments"]] == [
            True,
            True,
        ]
        assert [segment["is_final"] for segment in dto.audio_segments] == [
            False,
            True,
        ]

    def test_non_final_json_preserves_audio_segment_flags(self):
        dto = self._make_dto(
            is_final=False,
            audio_segments=[
                {"position": 0, "segment_index": 0, "is_final": False},
                {"position": 0, "segment_index": 1, "is_final": True},
            ],
        )

        result = dto.__json__()

        assert [segment["is_final"] for segment in result["audio_segments"]] == [
            False,
            True,
        ]


class TestRunMarkdownFlowDTO:
    def test_private_mdflow_stream_parts_do_not_leak_into_json(self):
        from flaskr.service.learn.learn_dtos import GeneratedType, RunMarkdownFlowDTO

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


# ---------------------------------------------------------------------------
# TypeStateMachine tests
# ---------------------------------------------------------------------------


class TestTypeStateMachine:
    def test_initial_state_is_idle(self):
        from flaskr.service.learn.type_state_machine import TypeState, TypeStateMachine

        sm = TypeStateMachine()
        assert sm.state == TypeState.IDLE
        assert not sm.is_terminated

    def test_content_start_transitions_to_building(self):
        from flaskr.service.learn.type_state_machine import (
            TypeInput,
            TypeState,
            TypeStateMachine,
        )

        sm = TypeStateMachine()
        out = sm.feed(TypeInput.CONTENT_START)
        assert out == "element"
        assert sm.state == TypeState.BUILDING

    def test_content_start_with_is_new_false_transitions_to_patching(self):
        from flaskr.service.learn.type_state_machine import (
            TypeInput,
            TypeState,
            TypeStateMachine,
        )

        sm = TypeStateMachine()
        out = sm.feed(TypeInput.CONTENT_START, is_new=False)
        assert out == "element"
        assert sm.state == TypeState.PATCHING

    def test_incremental_update_transitions_to_patching(self):
        from flaskr.service.learn.type_state_machine import (
            TypeInput,
            TypeState,
            TypeStateMachine,
        )

        sm = TypeStateMachine()
        sm.feed(TypeInput.CONTENT_START)
        out = sm.feed(TypeInput.INCREMENTAL_UPDATE)
        assert out == "element"
        assert sm.state == TypeState.PATCHING

    def test_block_break_returns_to_idle(self):
        from flaskr.service.learn.type_state_machine import (
            TypeInput,
            TypeState,
            TypeStateMachine,
        )

        sm = TypeStateMachine()
        sm.feed(TypeInput.CONTENT_START)
        out = sm.feed(TypeInput.BLOCK_BREAK)
        assert out == "break"
        assert sm.state == TypeState.IDLE

    def test_audio_segment_preserves_state(self):
        from flaskr.service.learn.type_state_machine import (
            TypeInput,
            TypeState,
            TypeStateMachine,
        )

        sm = TypeStateMachine()
        sm.feed(TypeInput.CONTENT_START)
        out = sm.feed(TypeInput.AUDIO_SEGMENT)
        assert out == "audio_segment"
        assert sm.state == TypeState.BUILDING

    def test_audio_complete_preserves_state(self):
        from flaskr.service.learn.type_state_machine import (
            TypeInput,
            TypeState,
            TypeStateMachine,
        )

        sm = TypeStateMachine()
        sm.feed(TypeInput.CONTENT_START)
        out = sm.feed(TypeInput.AUDIO_COMPLETE)
        assert out == "audio_complete"
        assert sm.state == TypeState.BUILDING

    def test_done_terminates(self):
        from flaskr.service.learn.type_state_machine import (
            TypeInput,
            TypeState,
            TypeStateMachine,
        )

        sm = TypeStateMachine()
        sm.feed(TypeInput.CONTENT_START)
        out = sm.feed(TypeInput.DONE)
        assert out == "done"
        assert sm.state == TypeState.TERMINATED
        assert sm.is_terminated

    def test_error_terminates(self):
        from flaskr.service.learn.type_state_machine import (
            TypeInput,
            TypeStateMachine,
        )

        sm = TypeStateMachine()
        out = sm.feed(TypeInput.ERROR)
        assert out == "error"
        assert sm.is_terminated

    def test_feed_after_terminated_raises(self):
        from flaskr.service.learn.type_state_machine import (
            TypeInput,
            TypeStateMachine,
        )

        sm = TypeStateMachine()
        sm.feed(TypeInput.DONE)
        with pytest.raises(ValueError, match="already terminated"):
            sm.feed(TypeInput.CONTENT_START)

    def test_reset(self):
        from flaskr.service.learn.type_state_machine import (
            TypeInput,
            TypeState,
            TypeStateMachine,
        )

        sm = TypeStateMachine()
        sm.feed(TypeInput.DONE)
        sm.reset()
        assert sm.state == TypeState.IDLE
        assert not sm.is_terminated

    def test_full_lifecycle(self):
        """Test a realistic sequence: content -> audio -> break -> content -> done."""
        from flaskr.service.learn.type_state_machine import (
            TypeInput,
            TypeState,
            TypeStateMachine,
        )

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
        assert sm.is_terminated


# ---------------------------------------------------------------------------
# Visual kind to element type mapping tests
# ---------------------------------------------------------------------------


class TestVisualKindMapping:
    def test_known_mappings(self):
        from flaskr.service.learn.learn_dtos import ElementType
        from flaskr.service.learn.listen_element_types import (
            _element_type_for_visual_kind,
        )

        assert _element_type_for_visual_kind("video") == ElementType.HTML
        assert _element_type_for_visual_kind("img") == ElementType.IMG
        assert _element_type_for_visual_kind("md_img") == ElementType.MD_IMG
        assert _element_type_for_visual_kind("svg") == ElementType.SVG
        assert _element_type_for_visual_kind("iframe") == ElementType.HTML
        assert _element_type_for_visual_kind("sandbox") == ElementType.HTML
        assert _element_type_for_visual_kind("html_table") == ElementType.HTML
        assert _element_type_for_visual_kind("md_table") == ElementType.TABLES
        assert _element_type_for_visual_kind("fence") == ElementType.CODE
        assert _element_type_for_visual_kind("mermaid") == ElementType.MERMAID
        assert _element_type_for_visual_kind("latex") == ElementType.LATEX
        assert _element_type_for_visual_kind("title") == ElementType.TITLE
        assert _element_type_for_visual_kind("text") == ElementType.TEXT

    def test_unknown_defaults_to_text(self):
        from flaskr.service.learn.learn_dtos import ElementType
        from flaskr.service.learn.listen_element_types import (
            _element_type_for_visual_kind,
        )

        assert _element_type_for_visual_kind("unknown") == ElementType.TEXT
        assert _element_type_for_visual_kind("") == ElementType.TEXT


# ---------------------------------------------------------------------------
# DB-backed integration tests
# ---------------------------------------------------------------------------


def _require_app(app):
    if app is None:
        pytest.skip("App fixture disabled")


def test_is_new_false_applies_to_target_element_in_records(app):
    """is_new=false elements should be merged into their target in records output."""
    _require_app(app)
    import json

    from flaskr.dao import db
    from flaskr.service.learn.listen_elements import get_listen_element_record
    from flaskr.service.learn.models import LearnGeneratedElement, LearnProgressRecord
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

    user_bid = "user-is-new-false"
    shifu_bid = "shifu-is-new-false"
    outline_bid = "outline-is-new-false"
    progress_bid = "progress-is-new-false"

    with app.app_context():
        LearnGeneratedElement.query.delete()
        LearnProgressRecord.query.delete()
        db.session.commit()

        progress = LearnProgressRecord(
            progress_record_bid=progress_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            user_bid=user_bid,
            status=LEARN_STATUS_IN_PROGRESS,
            block_position=0,
        )
        # Original element
        original = LearnGeneratedElement(
            element_bid="el-original",
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            generated_block_bid="block-1",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            run_session_bid="run-is-new-false",
            run_event_seq=1,
            event_type="element",
            role="teacher",
            element_index=0,
            element_type="text",
            element_type_code=213,
            change_type="render",
            target_element_bid="",
            is_renderable=1,
            is_new=1,
            is_marker=0,
            sequence_number=1,
            is_speakable=0,
            audio_url="",
            audio_segments="[]",
            is_navigable=1,
            is_final=0,
            content_text="version 1",
            payload=json.dumps({"audio": None, "previous_visuals": []}),
            status=1,
        )
        # Patch element (is_new=false targeting el-original)
        patch = LearnGeneratedElement(
            element_bid="el-patch",
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            generated_block_bid="block-1",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            run_session_bid="run-is-new-false",
            run_event_seq=2,
            event_type="element",
            role="teacher",
            element_index=0,
            element_type="text",
            element_type_code=213,
            change_type="render",
            target_element_bid="el-original",
            is_renderable=1,
            is_new=0,
            is_marker=0,
            sequence_number=2,
            is_speakable=0,
            audio_url="",
            audio_segments="[]",
            is_navigable=1,
            is_final=1,
            content_text="version 2 patched",
            payload=json.dumps({"audio": None, "previous_visuals": []}),
            status=1,
        )
        db.session.add_all([progress, original, patch])
        db.session.commit()

        result = get_listen_element_record(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
            preview_mode=False,
        )

    # Only the original element should appear, but with patched content
    assert len(result.elements) == 1
    assert result.elements[0].element_bid == "el-original"
    assert result.elements[0].content_text == "version 2 patched"
    assert result.elements[0].is_renderable is False
    assert result.elements[0].is_speakable is True
    assert result.elements[0].is_final is True


def test_records_ordered_by_sequence_number(app):
    """Records should be sorted by sequence_number, run_event_seq, id."""
    _require_app(app)
    import json

    from flaskr.dao import db
    from flaskr.service.learn.listen_elements import get_listen_element_record
    from flaskr.service.learn.models import LearnGeneratedElement, LearnProgressRecord
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

    user_bid = "user-seq-order"
    shifu_bid = "shifu-seq-order"
    outline_bid = "outline-seq-order"
    progress_bid = "progress-seq-order"

    with app.app_context():
        LearnGeneratedElement.query.delete()
        LearnProgressRecord.query.delete()
        db.session.commit()

        progress = LearnProgressRecord(
            progress_record_bid=progress_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            user_bid=user_bid,
            status=LEARN_STATUS_IN_PROGRESS,
            block_position=0,
        )
        # Insert elements with out-of-order sequence_numbers
        elements = []
        for seq_num, elem_bid in [(3, "el-c"), (1, "el-a"), (2, "el-b")]:
            elements.append(
                LearnGeneratedElement(
                    element_bid=elem_bid,
                    progress_record_bid=progress_bid,
                    user_bid=user_bid,
                    generated_block_bid="block-seq",
                    outline_item_bid=outline_bid,
                    shifu_bid=shifu_bid,
                    run_session_bid="run-seq-order",
                    run_event_seq=seq_num,
                    event_type="element",
                    role="teacher",
                    element_index=seq_num - 1,
                    element_type="text",
                    element_type_code=213,
                    change_type="render",
                    target_element_bid="",
                    is_renderable=1,
                    is_new=1,
                    is_marker=0,
                    sequence_number=seq_num,
                    is_speakable=0,
                    audio_url="",
                    audio_segments="[]",
                    is_navigable=1,
                    is_final=1,
                    content_text=f"element {seq_num}",
                    payload=json.dumps({"audio": None, "previous_visuals": []}),
                    status=1,
                )
            )
        db.session.add(progress)
        db.session.add_all(elements)
        db.session.commit()

        result = get_listen_element_record(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
            preview_mode=False,
        )

    # Should be ordered by sequence_number ascending
    bids = [e.element_bid for e in result.elements]
    assert bids == ["el-a", "el-b", "el-c"]


def test_records_merge_follow_up_history_after_anchor_element(app):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.learn_dtos import ElementPayloadDTO
    from flaskr.service.learn.listen_element_payloads import _serialize_payload
    from flaskr.service.learn.listen_elements import get_listen_element_record
    from flaskr.service.learn.models import LearnGeneratedElement, LearnProgressRecord
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

    user_bid = "user-follow-up-order"
    shifu_bid = "shifu-follow-up-order"
    outline_bid = "outline-follow-up-order"
    progress_bid = "progress-follow-up-order"

    with app.app_context():
        LearnGeneratedElement.query.delete()
        LearnProgressRecord.query.delete()
        db.session.commit()

        progress = LearnProgressRecord(
            progress_record_bid=progress_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            user_bid=user_bid,
            status=LEARN_STATUS_IN_PROGRESS,
            block_position=0,
        )
        db.session.add(progress)
        db.session.add_all(
            [
                LearnGeneratedElement(
                    element_bid="anchor-1",
                    progress_record_bid=progress_bid,
                    user_bid=user_bid,
                    generated_block_bid="block-anchor",
                    outline_item_bid=outline_bid,
                    shifu_bid=shifu_bid,
                    run_session_bid="run-follow-up-order",
                    run_event_seq=1,
                    event_type="element",
                    role="teacher",
                    element_index=0,
                    element_type="text",
                    element_type_code=213,
                    change_type="render",
                    target_element_bid="",
                    is_renderable=0,
                    is_new=1,
                    is_marker=0,
                    sequence_number=1,
                    is_speakable=1,
                    audio_url="",
                    audio_segments="[]",
                    is_navigable=1,
                    is_final=1,
                    content_text="anchor content",
                    payload=_serialize_payload(ElementPayloadDTO()),
                    status=1,
                ),
                LearnGeneratedElement(
                    element_bid="normal-2",
                    progress_record_bid=progress_bid,
                    user_bid=user_bid,
                    generated_block_bid="block-normal",
                    outline_item_bid=outline_bid,
                    shifu_bid=shifu_bid,
                    run_session_bid="run-follow-up-order",
                    run_event_seq=2,
                    event_type="element",
                    role="teacher",
                    element_index=1,
                    element_type="text",
                    element_type_code=213,
                    change_type="render",
                    target_element_bid="",
                    is_renderable=0,
                    is_new=1,
                    is_marker=0,
                    sequence_number=2,
                    is_speakable=1,
                    audio_url="",
                    audio_segments="[]",
                    is_navigable=1,
                    is_final=1,
                    content_text="normal content",
                    payload=_serialize_payload(ElementPayloadDTO()),
                    status=1,
                ),
                LearnGeneratedElement(
                    element_bid="ask-1",
                    progress_record_bid=progress_bid,
                    user_bid=user_bid,
                    generated_block_bid="block-ask",
                    outline_item_bid=outline_bid,
                    shifu_bid=shifu_bid,
                    run_session_bid="run-follow-up-order",
                    run_event_seq=3,
                    event_type="element",
                    role="student",
                    element_index=0,
                    element_type="ask",
                    element_type_code=206,
                    change_type="render",
                    target_element_bid="",
                    is_renderable=0,
                    is_new=1,
                    is_marker=0,
                    sequence_number=3,
                    is_speakable=0,
                    audio_url="",
                    audio_segments="[]",
                    is_navigable=0,
                    is_final=1,
                    content_text="follow up question",
                    payload=_serialize_payload(
                        ElementPayloadDTO(anchor_element_bid="anchor-1")
                    ),
                    status=1,
                ),
                LearnGeneratedElement(
                    element_bid="answer-1",
                    progress_record_bid=progress_bid,
                    user_bid=user_bid,
                    generated_block_bid="block-answer",
                    outline_item_bid=outline_bid,
                    shifu_bid=shifu_bid,
                    run_session_bid="run-follow-up-order",
                    run_event_seq=4,
                    event_type="element",
                    role="teacher",
                    element_index=0,
                    element_type="answer",
                    element_type_code=214,
                    change_type="render",
                    target_element_bid="",
                    is_renderable=0,
                    is_new=1,
                    is_marker=0,
                    sequence_number=4,
                    is_speakable=0,
                    audio_url="",
                    audio_segments="[]",
                    is_navigable=0,
                    is_final=1,
                    content_text="follow up answer",
                    payload=_serialize_payload(
                        ElementPayloadDTO(
                            anchor_element_bid="anchor-1",
                            ask_element_bid="ask-1",
                        )
                    ),
                    status=1,
                ),
            ]
        )
        db.session.commit()

        result = get_listen_element_record(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
            preview_mode=False,
        )

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


def test_include_non_navigable_returns_events(app):
    """include_non_navigable=true should return full events stream."""
    _require_app(app)
    import json

    from flaskr.dao import db
    from flaskr.service.learn.listen_elements import get_listen_element_record
    from flaskr.service.learn.models import LearnGeneratedElement, LearnProgressRecord
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

    user_bid = "user-non-nav"
    shifu_bid = "shifu-non-nav"
    outline_bid = "outline-non-nav"
    progress_bid = "progress-non-nav"

    with app.app_context():
        LearnGeneratedElement.query.delete()
        LearnProgressRecord.query.delete()
        db.session.commit()

        progress = LearnProgressRecord(
            progress_record_bid=progress_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            user_bid=user_bid,
            status=LEARN_STATUS_IN_PROGRESS,
            block_position=0,
        )
        element_row = LearnGeneratedElement(
            element_bid="el-nav-1",
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            generated_block_bid="block-nav",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            run_session_bid="run-non-nav",
            run_event_seq=1,
            event_type="element",
            role="teacher",
            element_index=0,
            element_type="text",
            element_type_code=213,
            change_type="render",
            target_element_bid="",
            is_renderable=1,
            is_new=1,
            is_marker=0,
            sequence_number=1,
            is_speakable=0,
            audio_url="",
            audio_segments="[]",
            is_navigable=1,
            is_final=1,
            content_text="content",
            payload=json.dumps({"audio": None, "previous_visuals": []}),
            status=1,
        )
        audio_event = LearnGeneratedElement(
            element_bid="",
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            generated_block_bid="block-nav",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            run_session_bid="run-non-nav",
            run_event_seq=2,
            event_type="audio_complete",
            role="teacher",
            element_index=0,
            element_type="",
            element_type_code=0,
            change_type="",
            target_element_bid="",
            is_renderable=1,
            is_new=1,
            is_marker=0,
            sequence_number=0,
            is_speakable=0,
            audio_url="",
            audio_segments="[]",
            is_navigable=0,
            is_final=1,
            content_text=json.dumps(
                {
                    "position": 0,
                    "audio_url": "https://example.com/audio.mp3",
                    "audio_bid": "audio-nav-1",
                    "duration_ms": 500,
                }
            ),
            payload="",
            status=1,
        )
        db.session.add_all([progress, element_row, audio_event])
        db.session.commit()

        # Without include_non_navigable
        result = get_listen_element_record(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
            preview_mode=False,
        )
        assert len(result.elements) == 1
        assert result.events is None

        # With include_non_navigable
        result_with = get_listen_element_record(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
            preview_mode=False,
            include_non_navigable=True,
        )
        assert len(result_with.elements) == 1
        assert result_with.events is not None
        assert len(result_with.events) == 1
        event_types = [e.type for e in result_with.events]
        assert "element" in event_types
        assert "audio_complete" not in event_types


def test_legacy_element_type_deserialized_to_new_enum(app):
    """Legacy element_type values like 'sandbox' should map to new enum."""
    _require_app(app)
    import json

    from flaskr.dao import db
    from flaskr.service.learn.learn_dtos import ElementType
    from flaskr.service.learn.listen_elements import get_listen_element_record
    from flaskr.service.learn.models import LearnGeneratedElement, LearnProgressRecord
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

    user_bid = "user-legacy-type"
    shifu_bid = "shifu-legacy-type"
    outline_bid = "outline-legacy-type"
    progress_bid = "progress-legacy-type"

    with app.app_context():
        LearnGeneratedElement.query.delete()
        LearnProgressRecord.query.delete()
        db.session.commit()

        progress = LearnProgressRecord(
            progress_record_bid=progress_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            user_bid=user_bid,
            status=LEARN_STATUS_IN_PROGRESS,
            block_position=0,
        )
        legacy_element = LearnGeneratedElement(
            element_bid="el-legacy",
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            generated_block_bid="block-legacy",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            run_session_bid="run-legacy",
            run_event_seq=1,
            event_type="element",
            role="teacher",
            element_index=0,
            element_type="sandbox",  # Legacy value
            element_type_code=102,
            change_type="render",
            target_element_bid="",
            is_navigable=1,
            is_final=1,
            content_text="legacy content",
            payload=json.dumps({"audio": None, "previous_visuals": []}),
            status=1,
        )
        db.session.add_all([progress, legacy_element])
        db.session.commit()

        result = get_listen_element_record(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
            preview_mode=False,
        )

    assert len(result.elements) == 1
    # Legacy "sandbox" should be mapped to ElementType.HTML
    assert result.elements[0].element_type == ElementType.HTML
    assert result.elements[0].is_marker is True


def test_non_text_elements_are_never_speakable_in_records(app):
    """Non-text elements must normalize is_speakable to false."""
    _require_app(app)
    import json

    from flaskr.dao import db
    from flaskr.service.learn.learn_dtos import ElementType
    from flaskr.service.learn.listen_elements import get_listen_element_record
    from flaskr.service.learn.models import LearnGeneratedElement, LearnProgressRecord
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

    user_bid = "user-non-text-speakable"
    shifu_bid = "shifu-non-text-speakable"
    outline_bid = "outline-non-text-speakable"
    progress_bid = "progress-non-text-speakable"

    with app.app_context():
        LearnGeneratedElement.query.delete()
        LearnProgressRecord.query.delete()
        db.session.commit()

        progress = LearnProgressRecord(
            progress_record_bid=progress_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            user_bid=user_bid,
            status=LEARN_STATUS_IN_PROGRESS,
            block_position=0,
        )
        visual_element = LearnGeneratedElement(
            element_bid="el-visual",
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            generated_block_bid="block-visual",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            run_session_bid="run-visual",
            run_event_seq=1,
            event_type="element",
            role="teacher",
            element_index=0,
            element_type="html",
            element_type_code=201,
            change_type="render",
            target_element_bid="",
            is_renderable=1,
            is_new=1,
            is_marker=1,
            sequence_number=1,
            is_speakable=1,
            audio_url="https://example.com/visual.mp3",
            audio_segments=json.dumps(
                [{"position": 0, "segment_index": 0, "audio_data": ""}]
            ),
            is_navigable=1,
            is_final=1,
            content_text="<div>visual</div>",
            payload=json.dumps({"audio": None, "previous_visuals": []}),
            status=1,
        )
        db.session.add_all([progress, visual_element])
        db.session.commit()

        result = get_listen_element_record(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
            preview_mode=False,
        )

    assert len(result.elements) == 1
    assert result.elements[0].element_type == ElementType.HTML
    assert result.elements[0].is_renderable is True
    assert result.elements[0].is_marker is True
    assert result.elements[0].is_speakable is False


def test_interaction_elements_backfill_user_input_from_generated_blocks(app):
    """Interaction record elements should expose submitted user input."""
    _require_app(app)
    import json

    from flaskr.dao import db
    from flaskr.service.learn.listen_elements import get_listen_element_record
    from flaskr.service.learn.models import (
        LearnGeneratedBlock,
        LearnGeneratedElement,
        LearnProgressRecord,
    )
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS
    from flaskr.service.shifu.consts import BLOCK_TYPE_MDINTERACTION_VALUE

    user_bid = "user-interaction-input"
    shifu_bid = "shifu-interaction-input"
    outline_bid = "outline-interaction-input"
    progress_bid = "progress-interaction-input"
    generated_block_bid = "generated-interaction-input"

    with app.app_context():
        LearnGeneratedElement.query.delete()
        LearnGeneratedBlock.query.delete()
        LearnProgressRecord.query.delete()
        db.session.commit()

        progress = LearnProgressRecord(
            progress_record_bid=progress_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            user_bid=user_bid,
            status=LEARN_STATUS_IN_PROGRESS,
            block_position=0,
        )
        interaction_block = LearnGeneratedBlock(
            generated_block_bid=generated_block_bid,
            progress_record_bid=progress_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            user_bid=user_bid,
            type=BLOCK_TYPE_MDINTERACTION_VALUE,
            role="teacher",
            block_content_conf="?[Agree//agree][Disagree//disagree]",
            generated_content="agree",
            status=1,
            deleted=0,
            position=0,
        )
        interaction_element = LearnGeneratedElement(
            element_bid="el-interaction-input",
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            generated_block_bid=generated_block_bid,
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            run_session_bid="run-interaction-input",
            run_event_seq=1,
            event_type="element",
            role="ui",
            element_index=0,
            element_type="interaction",
            element_type_code=205,
            change_type="render",
            target_element_bid="",
            is_renderable=1,
            is_new=1,
            is_marker=1,
            sequence_number=1,
            is_speakable=0,
            audio_url="",
            audio_segments="[]",
            is_navigable=0,
            is_final=1,
            content_text="?[Agree//agree][Disagree//disagree]",
            payload=json.dumps({"audio": None, "previous_visuals": []}),
            status=1,
        )
        db.session.add_all([progress, interaction_block, interaction_element])
        db.session.commit()

        result = get_listen_element_record(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
            preview_mode=False,
        )

    assert len(result.elements) == 1
    element = result.elements[0]
    assert element.payload is not None
    assert element.payload.user_input == "agree"


def test_live_interaction_events_use_ui_role_and_generated_input(adapter_app):
    from flaskr.dao import db
    from flaskr.service.learn.const import ROLE_TEACHER
    from flaskr.service.learn.learn_dtos import (
        ElementType,
        GeneratedType,
        RunMarkdownFlowDTO,
    )
    from flaskr.service.learn.listen_elements import ListenElementRunAdapter
    from flaskr.service.learn.models import LearnGeneratedBlock, LearnGeneratedElement
    from flaskr.service.shifu.consts import BLOCK_TYPE_MDINTERACTION_VALUE

    with adapter_app.app_context():
        block = LearnGeneratedBlock(
            generated_block_bid="generated-live-interaction",
            progress_record_bid="progress-live-interaction",
            user_bid="u1",
            block_bid="block-live-interaction",
            outline_item_bid="o1",
            shifu_bid="s1",
            type=BLOCK_TYPE_MDINTERACTION_VALUE,
            role=ROLE_TEACHER,
            generated_content="agree",
            position=0,
            block_content_conf="?[Agree//agree][Disagree//disagree]",
            status=1,
            deleted=0,
        )
        db.session.add(block)
        db.session.commit()

        adapter = ListenElementRunAdapter(
            adapter_app,
            shifu_bid="s1",
            outline_bid="o1",
            user_bid="u1",
        )
        streamed = list(
            adapter.process(
                [
                    RunMarkdownFlowDTO(
                        outline_bid="o1",
                        generated_block_bid="generated-live-interaction",
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


def test_backfill_populates_sequence_number_and_audio_url(app):
    """Backfill should assign sequence_number and extract audio_url from payload."""
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.const import ROLE_TEACHER
    from flaskr.service.learn.listen_element_legacy import (
        backfill_learn_generated_elements_for_progress,
    )
    from flaskr.service.learn.models import (
        LearnGeneratedBlock,
        LearnGeneratedElement,
        LearnProgressRecord,
    )
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS
    from flaskr.service.shifu.consts import BLOCK_TYPE_MDCONTENT_VALUE
    from flaskr.service.tts.models import (
        AUDIO_STATUS_COMPLETED,
        LearnGeneratedAudio,
    )

    user_bid = "user-backfill-seqnum"
    shifu_bid = "shifu-backfill-seqnum"
    outline_bid = "outline-backfill-seqnum"
    progress_bid = "progress-backfill-seqnum"
    generated_block_bid = "generated-backfill-seqnum"
    raw_content = "Hello world."

    with app.app_context():
        LearnGeneratedElement.query.delete()
        LearnGeneratedAudio.query.delete()
        LearnGeneratedBlock.query.delete()
        LearnProgressRecord.query.delete()
        db.session.commit()

        progress = LearnProgressRecord(
            progress_record_bid=progress_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            user_bid=user_bid,
            status=LEARN_STATUS_IN_PROGRESS,
            block_position=0,
        )
        block = LearnGeneratedBlock(
            generated_block_bid=generated_block_bid,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            block_bid="block-backfill-seqnum",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            type=BLOCK_TYPE_MDCONTENT_VALUE,
            role=ROLE_TEACHER,
            generated_content=raw_content,
            position=0,
            block_content_conf="",
            status=1,
        )
        audio = LearnGeneratedAudio(
            audio_bid="audio-backfill-seqnum",
            generated_block_bid=generated_block_bid,
            position=0,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            oss_url="https://example.com/backfill-seqnum.mp3",
            duration_ms=400,
            status=AUDIO_STATUS_COMPLETED,
        )
        db.session.add_all([progress, block, audio])
        db.session.commit()

        backfill_learn_generated_elements_for_progress(app, progress_bid)

        rows = (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.progress_record_bid == progress_bid,
                LearnGeneratedElement.deleted == 0,
                LearnGeneratedElement.status == 1,
            )
            .order_by(LearnGeneratedElement.run_event_seq.asc())
            .all()
        )

    assert len(rows) == 1
    row = rows[0]
    assert row.sequence_number == 1
    assert row.audio_url == "https://example.com/backfill-seqnum.mp3"
    assert row.is_speakable == 1
    assert row.is_new == 1
    assert row.is_renderable == 0
    assert row.is_marker == 0


# ---------------------------------------------------------------------------
# ElementPayloadDTO.asks tests
# ---------------------------------------------------------------------------


class TestElementPayloadAsks:
    def test_payload_asks_none_by_default(self):
        from flaskr.service.learn.learn_dtos import ElementPayloadDTO

        payload = ElementPayloadDTO()
        assert payload.asks is None
        serialized = payload.__json__()
        assert "asks" not in serialized

    def test_payload_asks_serialization(self):
        from flaskr.service.learn.learn_dtos import ElementPayloadDTO

        asks = [
            {"role": "student", "content": "what is this?"},
            {"role": "teacher", "content": "this is a demo"},
        ]
        payload = ElementPayloadDTO(asks=asks)
        serialized = payload.__json__()
        assert serialized["asks"] == asks

    def test_payload_asks_empty_list_serialization(self):
        from flaskr.service.learn.learn_dtos import ElementPayloadDTO

        payload = ElementPayloadDTO(asks=[])
        serialized = payload.__json__()
        assert serialized["asks"] == []

    def test_payload_asks_deserialization(self):
        from flaskr.service.learn.learn_dtos import ElementPayloadDTO
        from flaskr.service.learn.listen_element_payloads import (
            _deserialize_payload,
            _serialize_payload,
        )

        asks = [
            {"role": "student", "content": "question"},
            {"role": "teacher", "content": "answer"},
        ]
        original = ElementPayloadDTO(asks=asks)
        raw = _serialize_payload(original)
        restored = _deserialize_payload(raw)
        assert restored.asks == asks

    def test_payload_asks_deserialization_missing(self):
        from flaskr.service.learn.listen_element_payloads import _deserialize_payload

        raw = '{"audio": null, "previous_visuals": []}'
        restored = _deserialize_payload(raw)
        assert restored.asks is None

    def test_payload_asks_deserialization_invalid_type(self):
        from flaskr.service.learn.listen_element_payloads import _deserialize_payload

        raw = '{"audio": null, "previous_visuals": [], "asks": "not_a_list"}'
        restored = _deserialize_payload(raw)
        assert restored.asks is None


# ---------------------------------------------------------------------------
# GeneratedType.ASK and RunMarkdownFlowDTO.anchor_element_bid tests
# ---------------------------------------------------------------------------


class TestGeneratedTypeAsk:
    def test_ask_enum_exists(self):
        from flaskr.service.learn.learn_dtos import GeneratedType

        assert GeneratedType.ASK.value == "ask"

    def test_ask_not_in_legacy_types(self):
        from flaskr.service.learn.learn_dtos import GeneratedType

        legacy = {
            GeneratedType.CONTENT,
            GeneratedType.BREAK,
            GeneratedType.INTERACTION,
            GeneratedType.DONE,
        }
        assert GeneratedType.ASK not in legacy


class TestAskContextLoading:
    """Tests for _is_valid_asks and _load_ask_context."""

    def test_is_valid_asks_true(self):
        from flaskr.service.learn.handle_input_ask import _is_valid_asks

        asks = [
            {"role": "student", "content": "q"},
            {"role": "teacher", "content": "a"},
        ]
        assert _is_valid_asks(asks) is True

    def test_is_valid_asks_empty(self):
        from flaskr.service.learn.handle_input_ask import _is_valid_asks

        assert _is_valid_asks([]) is False
        assert _is_valid_asks(None) is False

    def test_is_valid_asks_student_only(self):
        from flaskr.service.learn.handle_input_ask import _is_valid_asks

        asks = [{"role": "student", "content": "q"}]
        assert _is_valid_asks(asks) is False

    def test_load_context_from_follow_up_elements(self):
        import types
        from flaskr.service.learn.handle_input_ask import _load_ask_context
        from flaskr.service.learn.learn_dtos import ElementPayloadDTO
        from flaskr.service.learn.listen_element_payloads import _serialize_payload

        payload = ElementPayloadDTO()
        anchor = types.SimpleNamespace(
            content_text="anchor text",
            payload=_serialize_payload(payload),
        )
        follow_up_elements = [
            types.SimpleNamespace(
                element_type="ask",
                content_text="q1",
                payload=_serialize_payload(
                    ElementPayloadDTO(anchor_element_bid="anchor_elem_1"),
                ),
            ),
            types.SimpleNamespace(
                element_type="answer",
                content_text="a1",
                payload=_serialize_payload(
                    ElementPayloadDTO(
                        anchor_element_bid="anchor_elem_1",
                        ask_element_bid="ask_elem_1",
                    ),
                ),
            ),
        ]
        result = _load_ask_context(anchor, follow_up_elements, 10)
        assert result is not None
        assert result[0] == {"role": "assistant", "content": "anchor text"}
        assert result[1] == {"role": "user", "content": "q1"}
        assert result[2] == {"role": "assistant", "content": "a1"}

    def test_load_context_fallback_to_legacy_payload_asks(self):
        import types
        from flaskr.service.learn.handle_input_ask import _load_ask_context
        from flaskr.service.learn.learn_dtos import ElementPayloadDTO
        from flaskr.service.learn.listen_element_payloads import _serialize_payload

        asks = [
            {"role": "student", "content": "q1"},
            {"role": "teacher", "content": "a1"},
        ]
        payload = ElementPayloadDTO()
        anchor = types.SimpleNamespace(
            content_text="text",
            payload=_serialize_payload(payload),
        )
        follow_up_elements = [
            types.SimpleNamespace(
                element_type="ask",
                content_text="",
                payload=_serialize_payload(ElementPayloadDTO(asks=asks)),
            )
        ]
        result = _load_ask_context(anchor, follow_up_elements, 10)
        assert result is not None
        assert result[0] == {"role": "assistant", "content": "text"}
        assert result[1] == {"role": "user", "content": "q1"}
        assert result[2] == {"role": "assistant", "content": "a1"}

    def test_load_context_fallback_to_none(self):
        import types
        from flaskr.service.learn.handle_input_ask import _load_ask_context
        from flaskr.service.learn.learn_dtos import ElementPayloadDTO
        from flaskr.service.learn.listen_element_payloads import _serialize_payload

        payload = ElementPayloadDTO()
        anchor = types.SimpleNamespace(
            content_text="text",
            payload=_serialize_payload(payload),
        )
        result = _load_ask_context(anchor, [], 10)
        assert result is None

    def test_load_context_none_element(self):
        from flaskr.service.learn.handle_input_ask import _load_ask_context

        assert _load_ask_context(None, [], 10) is None

    def test_load_context_truncation(self):
        import types
        from flaskr.service.learn.handle_input_ask import _load_ask_context
        from flaskr.service.learn.learn_dtos import ElementPayloadDTO
        from flaskr.service.learn.listen_element_payloads import _serialize_payload

        follow_up_elements = [
            types.SimpleNamespace(
                element_type="ask" if i % 2 == 0 else "answer",
                content_text=f"m{i}",
                payload=_serialize_payload(
                    ElementPayloadDTO(anchor_element_bid="anchor")
                ),
            )
            for i in range(20)
        ]
        payload = ElementPayloadDTO()
        anchor = types.SimpleNamespace(
            content_text="anchor",
            payload=_serialize_payload(payload),
        )
        result = _load_ask_context(anchor, follow_up_elements, 4)
        assert result is not None
        # anchor content + last 4 follow-up messages
        assert len(result) == 5


class TestHandleAskAdapter:
    """Tests for ListenElementRunAdapter._handle_ask()."""

    def test_handle_ask_creates_standalone_question_element(self, adapter_app):
        import json
        from flaskr.service.learn.listen_element_payloads import _serialize_payload
        from flaskr.service.learn.listen_elements import ListenElementRunAdapter
        from flaskr.service.learn.learn_dtos import (
            GeneratedType,
            RunMarkdownFlowDTO,
            ElementPayloadDTO,
        )
        from flaskr.service.learn.models import LearnGeneratedElement
        from flaskr.dao import db

        with adapter_app.app_context():
            adapter = ListenElementRunAdapter(
                adapter_app, shifu_bid="s1", outline_bid="o1", user_bid="u1"
            )

            anchor = LearnGeneratedElement(
                element_bid="anchor_elem_1",
                progress_record_bid="pr1",
                user_bid="u1",
                generated_block_bid="gb1",
                outline_item_bid="o1",
                shifu_bid="s1",
                run_session_bid="rs1",
                run_event_seq=1,
                event_type="element",
                role="teacher",
                element_index=0,
                element_type="text",
                element_type_code=0,
                change_type="render",
                is_final=1,
                content_text="hello world",
                payload=_serialize_payload(ElementPayloadDTO()),
                deleted=0,
                status=1,
            )
            db.session.add(anchor)
            db.session.flush()

            event = RunMarkdownFlowDTO(
                outline_bid="o1",
                generated_block_bid="ask_gb1",
                type=GeneratedType.ASK,
                content="user question here",
                anchor_element_bid="anchor_elem_1",
            )

            emitted = list(adapter._handle_ask(event))
            assert len(emitted) == 1

            ask_rows = LearnGeneratedElement.query.filter(
                LearnGeneratedElement.element_type == "ask"
            ).all()
            assert len(ask_rows) == 1
            payload = json.loads(ask_rows[0].payload or "{}")
            assert payload["anchor_element_bid"] == "anchor_elem_1"
            assert "asks" not in payload
            assert ask_rows[0].content_text == "user question here"
            assert ask_rows[0].role == "student"

    def test_process_ask_persists_without_streaming(self, adapter_app):
        import json
        from flaskr.service.learn.listen_element_payloads import _serialize_payload
        from flaskr.service.learn.listen_elements import ListenElementRunAdapter
        from flaskr.service.learn.learn_dtos import (
            GeneratedType,
            RunMarkdownFlowDTO,
            ElementPayloadDTO,
        )
        from flaskr.service.learn.models import LearnGeneratedElement
        from flaskr.dao import db

        with adapter_app.app_context():
            adapter = ListenElementRunAdapter(
                adapter_app, shifu_bid="s1", outline_bid="o1", user_bid="u1"
            )

            anchor = LearnGeneratedElement(
                element_bid="anchor_elem_2",
                progress_record_bid="pr1",
                user_bid="u1",
                generated_block_bid="gb1",
                outline_item_bid="o1",
                shifu_bid="s1",
                run_session_bid="rs1",
                run_event_seq=1,
                event_type="element",
                role="teacher",
                element_index=0,
                element_type="text",
                element_type_code=0,
                change_type="render",
                is_final=1,
                content_text="content",
                payload=_serialize_payload(ElementPayloadDTO()),
                deleted=0,
                status=1,
            )
            db.session.add(anchor)
            db.session.flush()

            events = [
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="ask_gb",
                    type=GeneratedType.ASK,
                    content="question",
                    anchor_element_bid="anchor_elem_2",
                )
            ]
            result = list(adapter.process(events))
            assert result == []

            ask_row = (
                LearnGeneratedElement.query.filter(
                    LearnGeneratedElement.element_type == "ask"
                )
                .order_by(
                    LearnGeneratedElement.run_event_seq.desc(),
                    LearnGeneratedElement.id.desc(),
                )
                .first()
            )
            assert ask_row is not None
            payload = json.loads(ask_row.payload or "{}")
            assert ask_row.content_text == "question"
            assert ask_row.role == "student"
            assert payload["anchor_element_bid"] == "anchor_elem_2"

    def test_handle_ask_sets_anchor_bid_state(self, adapter_app):
        from flaskr.service.learn.listen_element_payloads import _serialize_payload
        from flaskr.service.learn.listen_elements import ListenElementRunAdapter
        from flaskr.service.learn.learn_dtos import (
            GeneratedType,
            RunMarkdownFlowDTO,
            ElementPayloadDTO,
        )
        from flaskr.service.learn.models import LearnGeneratedElement
        from flaskr.dao import db

        with adapter_app.app_context():
            adapter = ListenElementRunAdapter(
                adapter_app, shifu_bid="s1", outline_bid="o1", user_bid="u1"
            )

            anchor = LearnGeneratedElement(
                element_bid="anchor_elem_3",
                progress_record_bid="pr1",
                user_bid="u1",
                generated_block_bid="gb1",
                outline_item_bid="o1",
                shifu_bid="s1",
                run_session_bid="rs1",
                run_event_seq=1,
                event_type="element",
                role="teacher",
                element_index=0,
                element_type="text",
                element_type_code=0,
                change_type="render",
                is_final=1,
                content_text="content",
                payload=_serialize_payload(ElementPayloadDTO()),
                deleted=0,
                status=1,
            )
            db.session.add(anchor)
            db.session.flush()

            event = RunMarkdownFlowDTO(
                outline_bid="o1",
                generated_block_bid="ask_gb",
                type=GeneratedType.ASK,
                content="q",
                anchor_element_bid="anchor_elem_3",
            )
            list(adapter._handle_ask(event))
            assert adapter._current_ask_anchor_bid == "anchor_elem_3"
            assert adapter._current_ask_element_bid

    def test_process_creates_standalone_answer_element(self, adapter_app):
        import json
        from flaskr.service.learn.listen_element_payloads import _serialize_payload
        from flaskr.service.learn.listen_elements import ListenElementRunAdapter
        from flaskr.service.learn.learn_dtos import (
            ElementPayloadDTO,
            ElementType,
            GeneratedType,
            RunMarkdownFlowDTO,
        )
        from flaskr.service.learn.models import LearnGeneratedElement
        from flaskr.dao import db

        with adapter_app.app_context():
            adapter = ListenElementRunAdapter(
                adapter_app, shifu_bid="s1", outline_bid="o1", user_bid="u1"
            )

            anchor = LearnGeneratedElement(
                element_bid="anchor_elem_4",
                progress_record_bid="pr1",
                user_bid="u1",
                generated_block_bid="gb1",
                outline_item_bid="o1",
                shifu_bid="s1",
                run_session_bid="rs1",
                run_event_seq=1,
                event_type="element",
                role="teacher",
                element_index=0,
                element_type="text",
                element_type_code=0,
                change_type="render",
                is_final=1,
                content_text="anchor content",
                payload=_serialize_payload(ElementPayloadDTO()),
                deleted=0,
                status=1,
            )
            db.session.add(anchor)
            db.session.flush()

            events = [
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="ask_gb_answer",
                    type=GeneratedType.ASK,
                    content="question",
                    anchor_element_bid="anchor_elem_4",
                ),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="ask_gb_answer",
                    type=GeneratedType.CONTENT,
                    content="answer",
                ),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="ask_gb_answer",
                    type=GeneratedType.BREAK,
                    content="",
                ),
            ]

            streamed = list(adapter.process(events))
            ask_row = (
                LearnGeneratedElement.query.filter(
                    LearnGeneratedElement.element_type == "ask"
                )
                .order_by(
                    LearnGeneratedElement.run_event_seq.desc(),
                    LearnGeneratedElement.id.desc(),
                )
                .first()
            )
            assert ask_row is not None
            answer_messages = [
                message.content
                for message in streamed
                if message.type == "element"
                and message.content.element_type == ElementType.ANSWER
            ]

            assert answer_messages
            final_answer = answer_messages[-1]
            assert final_answer.content_text == "answer"
            assert final_answer.role == "teacher"
            assert final_answer.payload.anchor_element_bid == "anchor_elem_4"
            assert final_answer.payload.ask_element_bid == ask_row.element_bid

            answer_row = (
                LearnGeneratedElement.query.filter(
                    LearnGeneratedElement.element_type == "answer"
                )
                .order_by(
                    LearnGeneratedElement.run_event_seq.desc(),
                    LearnGeneratedElement.id.desc(),
                )
                .first()
            )
            assert answer_row is not None
            payload = json.loads(answer_row.payload or "{}")
            assert answer_row.content_text == "answer"
            assert answer_row.role == "teacher"
            assert payload["anchor_element_bid"] == "anchor_elem_4"
            assert payload["ask_element_bid"] == ask_row.element_bid
            assert "asks" not in payload

    def test_process_streams_multi_chunk_follow_up_answer_but_persists_only_final_row(
        self, adapter_app
    ):
        from flaskr.service.learn.listen_element_payloads import _serialize_payload
        from flaskr.service.learn.listen_elements import ListenElementRunAdapter
        from flaskr.service.learn.learn_dtos import (
            ElementPayloadDTO,
            ElementType,
            GeneratedType,
            RunMarkdownFlowDTO,
        )
        from flaskr.service.learn.models import LearnGeneratedElement
        from flaskr.dao import db

        with adapter_app.app_context():
            adapter = ListenElementRunAdapter(
                adapter_app, shifu_bid="s1", outline_bid="o1", user_bid="u1"
            )

            anchor = LearnGeneratedElement(
                element_bid="anchor_elem_multi_chunk",
                progress_record_bid="pr1",
                user_bid="u1",
                generated_block_bid="gb1",
                outline_item_bid="o1",
                shifu_bid="s1",
                run_session_bid="rs1",
                run_event_seq=1,
                event_type="element",
                role="teacher",
                element_index=0,
                element_type="text",
                element_type_code=0,
                change_type="render",
                is_final=1,
                content_text="anchor content",
                payload=_serialize_payload(ElementPayloadDTO()),
                deleted=0,
                status=1,
            )
            db.session.add(anchor)
            db.session.flush()

            events = [
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="ask_gb_multi_chunk",
                    type=GeneratedType.ASK,
                    content="question",
                    anchor_element_bid="anchor_elem_multi_chunk",
                ),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="ask_gb_multi_chunk",
                    type=GeneratedType.CONTENT,
                    content="hello",
                ),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="ask_gb_multi_chunk",
                    type=GeneratedType.CONTENT,
                    content=" world",
                ),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="ask_gb_multi_chunk",
                    type=GeneratedType.BREAK,
                    content="",
                ),
            ]

            streamed = list(adapter.process(events))
            answer_messages = [
                message.content
                for message in streamed
                if message.type == "element"
                and message.content.element_type == ElementType.ANSWER
            ]

            assert len(answer_messages) == 3
            assert answer_messages[0].content_text == "hello"
            assert answer_messages[0].is_final is False
            assert answer_messages[1].content_text == "hello world"
            assert answer_messages[1].is_final is False
            assert answer_messages[2].content_text == "hello world"
            assert answer_messages[2].is_final is True

            logical_answer_bid = (
                answer_messages[0].target_element_bid or answer_messages[0].element_bid
            )
            assert logical_answer_bid
            assert (
                answer_messages[1].target_element_bid or answer_messages[1].element_bid
            ) == logical_answer_bid
            assert (
                answer_messages[2].target_element_bid or answer_messages[2].element_bid
            ) == logical_answer_bid

            answer_rows = (
                LearnGeneratedElement.query.filter(
                    LearnGeneratedElement.generated_block_bid == "ask_gb_multi_chunk",
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

    def test_process_creates_answer_element_for_patched_anchor_bid(self, adapter_app):
        from flaskr.service.learn.listen_element_payloads import _serialize_payload
        from flaskr.service.learn.listen_elements import ListenElementRunAdapter
        from flaskr.service.learn.learn_dtos import (
            ElementPayloadDTO,
            ElementType,
            GeneratedType,
            RunMarkdownFlowDTO,
        )
        from flaskr.service.learn.models import LearnGeneratedElement
        from flaskr.dao import db

        with adapter_app.app_context():
            adapter = ListenElementRunAdapter(
                adapter_app, shifu_bid="s1", outline_bid="o1", user_bid="u1"
            )

            retired_anchor = LearnGeneratedElement(
                element_bid="anchor_elem_stable",
                progress_record_bid="pr1",
                user_bid="u1",
                generated_block_bid="gb_anchor",
                outline_item_bid="o1",
                shifu_bid="s1",
                run_session_bid="rs1",
                run_event_seq=1,
                event_type="element",
                role="teacher",
                element_index=0,
                element_type="text",
                element_type_code=0,
                change_type="render",
                is_new=1,
                is_final=0,
                content_text="anchor draft",
                payload=_serialize_payload(ElementPayloadDTO()),
                deleted=0,
                status=0,
            )
            active_anchor_patch = LearnGeneratedElement(
                element_bid="anchor_elem_active",
                progress_record_bid="pr1",
                user_bid="u1",
                generated_block_bid="gb_anchor",
                outline_item_bid="o1",
                shifu_bid="s1",
                run_session_bid="rs1",
                run_event_seq=2,
                event_type="element",
                role="teacher",
                element_index=0,
                element_type="text",
                element_type_code=0,
                change_type="render",
                target_element_bid="anchor_elem_stable",
                is_new=0,
                is_final=1,
                content_text="anchor final",
                payload=_serialize_payload(ElementPayloadDTO()),
                deleted=0,
                status=1,
            )
            db.session.add(retired_anchor)
            db.session.add(active_anchor_patch)
            db.session.flush()

            events = [
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="ask_gb_split",
                    type=GeneratedType.ASK,
                    content="question",
                    anchor_element_bid="anchor_elem_stable",
                ),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="answer_gb_split",
                    type=GeneratedType.CONTENT,
                    content="answer",
                ),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="answer_gb_split",
                    type=GeneratedType.BREAK,
                    content="",
                ),
            ]

            streamed = list(adapter.process(events))
            answer_messages = [
                message.content
                for message in streamed
                if message.type == "element"
                and message.content.element_type == ElementType.ANSWER
            ]

            assert answer_messages
            final_answer = answer_messages[-1]
            assert final_answer.content_text == "answer"
            assert final_answer.payload.anchor_element_bid == "anchor_elem_stable"

            answer_row = (
                LearnGeneratedElement.query.filter(
                    LearnGeneratedElement.generated_block_bid == "answer_gb_split",
                    LearnGeneratedElement.element_type == "answer",
                    LearnGeneratedElement.status == 1,
                )
                .order_by(
                    LearnGeneratedElement.run_event_seq.desc(),
                    LearnGeneratedElement.id.desc(),
                )
                .first()
            )
            assert answer_row is not None
            assert answer_row.content_text == "answer"

    def test_answer_audio_events_do_not_attach_audio(self, adapter_app):
        from flaskr.service.learn.listen_element_payloads import _serialize_payload
        from flaskr.service.learn.listen_elements import ListenElementRunAdapter
        from flaskr.service.learn.learn_dtos import (
            AudioCompleteDTO,
            AudioSegmentDTO,
            ElementPayloadDTO,
            ElementType,
            GeneratedType,
            RunMarkdownFlowDTO,
        )
        from flaskr.service.learn.models import LearnGeneratedElement
        from flaskr.dao import db

        with adapter_app.app_context():
            adapter = ListenElementRunAdapter(
                adapter_app, shifu_bid="s1", outline_bid="o1", user_bid="u1"
            )

            anchor = LearnGeneratedElement(
                element_bid="anchor_elem_audio",
                progress_record_bid="pr1",
                user_bid="u1",
                generated_block_bid="gb1",
                outline_item_bid="o1",
                shifu_bid="s1",
                run_session_bid="rs1",
                run_event_seq=1,
                event_type="element",
                role="teacher",
                element_index=0,
                element_type="text",
                element_type_code=0,
                change_type="render",
                is_final=1,
                content_text="anchor content",
                payload=_serialize_payload(ElementPayloadDTO()),
                deleted=0,
                status=1,
            )
            db.session.add(anchor)
            db.session.flush()

            events = [
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="ask_gb_audio",
                    type=GeneratedType.ASK,
                    content="question",
                    anchor_element_bid="anchor_elem_audio",
                ),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="ask_gb_audio",
                    type=GeneratedType.CONTENT,
                    content="answer",
                ),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="ask_gb_audio",
                    type=GeneratedType.AUDIO_SEGMENT,
                    content=AudioSegmentDTO(
                        position=0,
                        segment_index=0,
                        audio_data="segment-0",
                        duration_ms=120,
                        is_final=False,
                    ),
                ),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="ask_gb_audio",
                    type=GeneratedType.AUDIO_COMPLETE,
                    content=AudioCompleteDTO(
                        audio_url="https://example.com/answer-audio.mp3",
                        audio_bid="answer-audio",
                        duration_ms=120,
                        position=0,
                    ),
                ),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="ask_gb_audio",
                    type=GeneratedType.BREAK,
                    content="",
                ),
            ]

            streamed = list(adapter.process(events))
            answer_messages = [
                message.content
                for message in streamed
                if message.type == "element"
                and message.content.element_type == ElementType.ANSWER
            ]
            assert answer_messages
            final_answer = answer_messages[-1]
            assert final_answer.is_final is True
            assert final_answer.audio_url == ""
            assert final_answer.audio_segments == []
            assert final_answer.payload is not None
            assert final_answer.payload.audio is None

    def test_handle_input_ask_provider_stream_returns_answer_element(
        self, adapter_app, monkeypatch
    ):
        from flaskr.dao import db
        from flaskr.service.learn import handle_input_ask as module
        from flaskr.service.learn.learn_dtos import (
            ElementPayloadDTO,
            ElementType,
            GeneratedType,
        )
        from flaskr.service.learn.listen_element_payloads import _serialize_payload
        from flaskr.service.learn.listen_elements import ListenElementRunAdapter
        from flaskr.service.learn.models import LearnGeneratedElement

        ask_provider_config = {
            "provider": "coze",
            "mode": "provider_then_llm",
            "config": {"bot_id": "bot-1"},
        }

        with adapter_app.app_context():
            _setup_handle_input_ask_test_doubles(
                monkeypatch,
                module,
                ask_provider_config,
                patch_generated_blocks=False,
            )
            monkeypatch.setattr(
                module,
                "stream_ask_provider_response",
                lambda **_kwargs: iter(
                    [types.SimpleNamespace(content="provider-answer")]
                ),
            )
            monkeypatch.setattr(module, "chat_llm", lambda *_args, **_kwargs: iter([]))

            anchor = LearnGeneratedElement(
                element_bid="anchor_elem_handle_stream",
                progress_record_bid="pr1",
                user_bid="u1",
                generated_block_bid="gb_anchor",
                outline_item_bid="o1",
                shifu_bid="s1",
                run_session_bid="rs1",
                run_event_seq=1,
                event_type="element",
                role="teacher",
                element_index=0,
                element_type="text",
                element_type_code=0,
                change_type="render",
                is_final=1,
                content_text="anchor content",
                payload=_serialize_payload(ElementPayloadDTO()),
                deleted=0,
                status=1,
            )
            db.session.add(anchor)
            db.session.flush()

            adapter = ListenElementRunAdapter(
                adapter_app, shifu_bid="s1", outline_bid="o1", user_bid="u1"
            )
            events = list(
                module.handle_input_ask(
                    app=adapter_app,
                    context=_FollowUpContext(),
                    user_info=types.SimpleNamespace(user_id="u1"),
                    attend_id="pr1",
                    input="hello",
                    outline_item_info=types.SimpleNamespace(
                        shifu_bid="s1", bid="o1", title="Outline", position=1
                    ),
                    trace_args={"output": ""},
                    trace=_FollowUpDummyTrace(),
                    anchor_element_bid="anchor_elem_handle_stream",
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
            answer_block_bid = ask_events[0].generated_block_bid

            streamed = list(adapter.process(events))
            answer_messages = [
                message.content
                for message in streamed
                if message.type == "element"
                and message.content.element_type == ElementType.ANSWER
            ]
            assert answer_messages
            assert answer_messages[-1].content_text == "provider-answer"

            answer_row = (
                LearnGeneratedElement.query.filter(
                    LearnGeneratedElement.generated_block_bid == answer_block_bid,
                    LearnGeneratedElement.element_type == "answer",
                    LearnGeneratedElement.status == 1,
                )
                .order_by(
                    LearnGeneratedElement.run_event_seq.desc(),
                    LearnGeneratedElement.id.desc(),
                )
                .first()
            )
            assert answer_row is not None
            assert answer_row.content_text == "provider-answer"

    def test_handle_input_ask_provider_only_error_returns_answer_element(
        self, adapter_app, monkeypatch
    ):
        from flaskr.dao import db
        from flaskr.service.learn import handle_input_ask as module
        from flaskr.service.learn.ask_provider_adapters import AskProviderError
        from flaskr.service.learn.learn_dtos import (
            ElementPayloadDTO,
            ElementType,
            GeneratedType,
        )
        from flaskr.service.learn.listen_element_payloads import _serialize_payload
        from flaskr.service.learn.listen_elements import ListenElementRunAdapter
        from flaskr.service.learn.models import LearnGeneratedElement

        ask_provider_config = {
            "provider": "dify",
            "mode": "provider_only",
            "config": {},
        }

        with adapter_app.app_context():
            _setup_handle_input_ask_test_doubles(
                monkeypatch,
                module,
                ask_provider_config,
                patch_generated_blocks=False,
            )

            def _raise_provider_error(**_kwargs):
                if False:
                    yield None
                raise AskProviderError("provider failed")

            monkeypatch.setattr(
                module,
                "stream_ask_provider_response",
                _raise_provider_error,
            )
            monkeypatch.setattr(module, "chat_llm", lambda *_args, **_kwargs: iter([]))

            anchor = LearnGeneratedElement(
                element_bid="anchor_elem_handle_error",
                progress_record_bid="pr1",
                user_bid="u1",
                generated_block_bid="gb_anchor",
                outline_item_bid="o1",
                shifu_bid="s1",
                run_session_bid="rs1",
                run_event_seq=1,
                event_type="element",
                role="teacher",
                element_index=0,
                element_type="text",
                element_type_code=0,
                change_type="render",
                is_final=1,
                content_text="anchor content",
                payload=_serialize_payload(ElementPayloadDTO()),
                deleted=0,
                status=1,
            )
            db.session.add(anchor)
            db.session.flush()

            adapter = ListenElementRunAdapter(
                adapter_app, shifu_bid="s1", outline_bid="o1", user_bid="u1"
            )
            events = list(
                module.handle_input_ask(
                    app=adapter_app,
                    context=_FollowUpContext(),
                    user_info=types.SimpleNamespace(user_id="u1"),
                    attend_id="pr1",
                    input="hello",
                    outline_item_info=types.SimpleNamespace(
                        shifu_bid="s1", bid="o1", title="Outline", position=1
                    ),
                    trace_args={"output": ""},
                    trace=_FollowUpDummyTrace(),
                    anchor_element_bid="anchor_elem_handle_error",
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
            assert content_events[0].content == "server.learn.askProviderUnavailable"
            answer_block_bid = ask_events[0].generated_block_bid

            streamed = list(adapter.process(events))
            answer_messages = [
                message.content
                for message in streamed
                if message.type == "element"
                and message.content.element_type == ElementType.ANSWER
            ]
            assert answer_messages
            assert (
                answer_messages[-1].content_text
                == "server.learn.askProviderUnavailable"
            )

            answer_row = (
                LearnGeneratedElement.query.filter(
                    LearnGeneratedElement.generated_block_bid == answer_block_bid,
                    LearnGeneratedElement.element_type == "answer",
                    LearnGeneratedElement.status == 1,
                )
                .order_by(
                    LearnGeneratedElement.run_event_seq.desc(),
                    LearnGeneratedElement.id.desc(),
                )
                .first()
            )
            assert answer_row is not None
            assert answer_row.content_text == "server.learn.askProviderUnavailable"


class TestRunMarkdownFlowDTOAnchorBid:
    def test_default_anchor_element_bid_empty(self):
        from flaskr.service.learn.learn_dtos import GeneratedType, RunMarkdownFlowDTO

        dto = RunMarkdownFlowDTO(
            outline_bid="o1",
            generated_block_bid="b1",
            type=GeneratedType.CONTENT,
            content="hello",
        )
        assert dto.anchor_element_bid == ""
        serialized = dto.__json__()
        assert "anchor_element_bid" not in serialized

    def test_anchor_element_bid_set(self):
        from flaskr.service.learn.learn_dtos import GeneratedType, RunMarkdownFlowDTO

        dto = RunMarkdownFlowDTO(
            outline_bid="o1",
            generated_block_bid="b1",
            type=GeneratedType.ASK,
            content="user question",
            anchor_element_bid="elem_abc",
        )
        assert dto.anchor_element_bid == "elem_abc"
        serialized = dto.__json__()
        assert serialized["anchor_element_bid"] == "elem_abc"


class TestElementChangeTypeSemantics:
    def test_text_patch_keeps_render_change_type(self, adapter_app):
        from flaskr.service.learn.learn_dtos import (
            ElementChangeType,
            ElementType,
            GeneratedType,
            RunMarkdownFlowDTO,
        )
        from flaskr.service.learn.listen_elements import ListenElementRunAdapter

        with adapter_app.app_context():
            adapter = ListenElementRunAdapter(
                adapter_app, shifu_bid="s1", outline_bid="o1", user_bid="u1"
            )

            events = [
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-text",
                    type=GeneratedType.CONTENT,
                    content="Hello",
                ).set_mdflow_stream_parts([("Hello", "text", 0)]),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-text",
                    type=GeneratedType.CONTENT,
                    content=" world",
                ).set_mdflow_stream_parts([(" world", "text", 0)]),
            ]

            streamed = list(adapter.process(events))
            text_events = [
                message.content
                for message in streamed
                if message.type == "element"
                and message.content.element_type == ElementType.TEXT
            ]

            assert len(text_events) == 2
            assert [item.is_new for item in text_events] == [True, True]
            assert [item.change_type for item in text_events] == [
                ElementChangeType.RENDER,
                ElementChangeType.RENDER,
            ]
            assert text_events[0].target_element_bid in ("", None)
            assert text_events[1].target_element_bid in ("", None)

    def test_gitdiff_element_uses_diff_change_type_without_forcing_patch(
        self, adapter_app
    ):
        from flaskr.service.learn.learn_dtos import (
            ElementChangeType,
            ElementType,
            GeneratedType,
            RunMarkdownFlowDTO,
        )
        from flaskr.service.learn.listen_elements import ListenElementRunAdapter

        with adapter_app.app_context():
            adapter = ListenElementRunAdapter(
                adapter_app, shifu_bid="s1", outline_bid="o1", user_bid="u1"
            )

            events = [
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-diff",
                    type=GeneratedType.CONTENT,
                    content="@@ -1 +1 @@\n-old\n+new\n",
                ).set_mdflow_stream_parts([("@@ -1 +1 @@\n-old\n+new\n", "diff", 0)]),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-diff",
                    type=GeneratedType.CONTENT,
                    content="+tail\n",
                ).set_mdflow_stream_parts([("+tail\n", "diff", 0)]),
            ]

            streamed = list(adapter.process(events))
            diff_events = [
                message.content
                for message in streamed
                if message.type == "element"
                and message.content.element_type == ElementType.DIFF
            ]

            assert len(diff_events) == 2
            assert [item.is_new for item in diff_events] == [False, False]
            assert [item.change_type for item in diff_events] == [
                ElementChangeType.DIFF,
                ElementChangeType.DIFF,
            ]
            assert diff_events[0].target_element_bid == diff_events[0].element_bid
            assert diff_events[1].target_element_bid == diff_events[0].element_bid

    def test_html_after_text_creates_new_element(self, adapter_app):
        from flaskr.service.learn.learn_dtos import (
            ElementType,
            GeneratedType,
            RunMarkdownFlowDTO,
        )
        from flaskr.service.learn.listen_elements import ListenElementRunAdapter

        with adapter_app.app_context():
            adapter = ListenElementRunAdapter(
                adapter_app, shifu_bid="s1", outline_bid="o1", user_bid="u1"
            )

            events = [
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-html",
                    type=GeneratedType.CONTENT,
                    content="<div>Intro visual</div>\n",
                ).set_mdflow_stream_parts([("<div>Intro visual</div>\n", "html", 0)]),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-html",
                    type=GeneratedType.CONTENT,
                    content="Narration\n",
                ).set_mdflow_stream_parts([("Narration\n", "text", 1)]),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-html",
                    type=GeneratedType.CONTENT,
                    content="<div>Follow-up visual</div>\n",
                ).set_mdflow_stream_parts(
                    [("<div>Follow-up visual</div>\n", "html", 2)]
                ),
            ]

            streamed = list(adapter.process(events))
            html_events = [
                message.content
                for message in streamed
                if message.type == "element"
                and message.content.element_type == ElementType.HTML
            ]

            assert len(html_events) == 2
            assert [item.is_new for item in html_events] == [True, True]
            assert html_events[0].target_element_bid in ("", None)
            assert html_events[1].target_element_bid in ("", None)
            assert html_events[0].element_bid != html_events[1].element_bid

    def test_html_only_stream_does_not_keep_audio_on_finalize(self, adapter_app):
        from flaskr.service.learn.learn_dtos import (
            AudioCompleteDTO,
            AudioSegmentDTO,
            ElementType,
            GeneratedType,
            RunMarkdownFlowDTO,
        )
        from flaskr.service.learn.listen_elements import ListenElementRunAdapter

        with adapter_app.app_context():
            adapter = ListenElementRunAdapter(
                adapter_app, shifu_bid="s1", outline_bid="o1", user_bid="u1"
            )

            events = [
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-html-audio",
                    type=GeneratedType.CONTENT,
                    content="<div>Narration after click</div>\n",
                ).set_mdflow_stream_parts(
                    [("<div>Narration after click</div>\n", "html", 0)]
                ),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-html-audio",
                    type=GeneratedType.AUDIO_SEGMENT,
                    content=AudioSegmentDTO(
                        position=0,
                        segment_index=0,
                        audio_data="html-only-segment",
                        duration_ms=210,
                        is_final=False,
                    ),
                ),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-html-audio",
                    type=GeneratedType.AUDIO_COMPLETE,
                    content=AudioCompleteDTO(
                        audio_url="https://example.com/html-only.mp3",
                        audio_bid="html-only-audio-0",
                        duration_ms=210,
                        position=0,
                    ),
                ),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-html-audio",
                    type=GeneratedType.BREAK,
                    content="",
                ),
            ]

            streamed = list(adapter.process(events))
            html_events = [
                message.content
                for message in streamed
                if message.type == "element"
                and message.content.element_type == ElementType.HTML
            ]
            text_events = [
                message.content
                for message in streamed
                if message.type == "element"
                and message.content.element_type == ElementType.TEXT
            ]

            assert len(html_events) == 2
            assert text_events == []
            assert all(item.audio_segments == [] for item in html_events)
            assert all(item.audio_url == "" for item in html_events)
            assert all(item.is_speakable is False for item in html_events)

    def test_chunked_html_table_stream_stays_single_html_element(self, adapter_app):
        from flaskr.service.learn.learn_dtos import (
            ElementType,
            GeneratedType,
            RunMarkdownFlowDTO,
        )
        from flaskr.service.learn.listen_elements import ListenElementRunAdapter

        with adapter_app.app_context():
            adapter = ListenElementRunAdapter(
                adapter_app, shifu_bid="s1", outline_bid="o1", user_bid="u1"
            )

            events = [
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-table",
                    type=GeneratedType.CONTENT,
                    content="<table><tbody><tr><td>North",
                ).set_mdflow_stream_parts([("<table><tbody><tr><td>North", "html", 0)]),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-table",
                    type=GeneratedType.CONTENT,
                    content=" middle ",
                ).set_mdflow_stream_parts([(" middle ", "html", 0)]),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-table",
                    type=GeneratedType.CONTENT,
                    content="</td></tr></tbody></table>",
                ).set_mdflow_stream_parts([("</td></tr></tbody></table>", "html", 0)]),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-table",
                    type=GeneratedType.BREAK,
                    content="",
                ),
            ]

            streamed = list(adapter.process(events))
            html_events = [
                message.content
                for message in streamed
                if message.type == "element"
                and message.content.element_type == ElementType.HTML
            ]

            assert len(html_events) == 4
            assert [item.is_new for item in html_events] == [True, True, True, True]
            assert html_events[0].target_element_bid in ("", None)
            assert html_events[1].target_element_bid in ("", None)
            assert html_events[2].target_element_bid in ("", None)
            assert html_events[3].target_element_bid in ("", None)
            assert len({item.element_bid for item in html_events}) == 1

    def test_mdflow_stream_elements_are_not_rebuilt_from_av_contract(self, adapter_app):
        from flaskr.service.learn.learn_dtos import (
            AudioCompleteDTO,
            ElementType,
            GeneratedType,
            RunMarkdownFlowDTO,
        )
        from flaskr.service.learn.listen_elements import ListenElementRunAdapter
        from flaskr.service.tts.pipeline import build_av_segmentation_contract

        raw_content = (
            "Before image.\n\n![img](https://example.com/visual.png)\n\nAfter image."
        )
        av_contract = build_av_segmentation_contract(raw_content, "gb-mdflow-av")

        with adapter_app.app_context():
            adapter = ListenElementRunAdapter(
                adapter_app, shifu_bid="s1", outline_bid="o1", user_bid="u1"
            )

            events = [
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-mdflow-av",
                    type=GeneratedType.CONTENT,
                    content="Before image.\n\n",
                ).set_mdflow_stream_parts([("Before image.\n\n", "text", 0)]),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-mdflow-av",
                    type=GeneratedType.CONTENT,
                    content="![img](https://example.com/visual.png)\n\n",
                ).set_mdflow_stream_parts(
                    [("![img](https://example.com/visual.png)\n\n", "img", 1)]
                ),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-mdflow-av",
                    type=GeneratedType.CONTENT,
                    content="After image.",
                ).set_mdflow_stream_parts([("After image.", "text", 2)]),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-mdflow-av",
                    type=GeneratedType.AUDIO_COMPLETE,
                    content=AudioCompleteDTO(
                        audio_url="https://example.com/audio-0.mp3",
                        audio_bid="audio-0",
                        duration_ms=320,
                        position=0,
                        av_contract=av_contract,
                    ),
                ),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-mdflow-av",
                    type=GeneratedType.BREAK,
                    content="",
                ),
            ]

            streamed = list(adapter.process(events))
            navigable_elements = [
                message.content
                for message in streamed
                if message.type == "element" and message.content.is_navigable == 1
            ]
            retire_events = [
                message.content
                for message in streamed
                if message.type == "element" and message.content.is_navigable == 0
            ]
            final_navigable_elements = [
                item for item in navigable_elements if item.is_final is True
            ]
            final_snapshots_by_bid = {}
            for item in final_navigable_elements:
                final_snapshots_by_bid[item.element_bid] = item
            final_snapshots = list(final_snapshots_by_bid.values())

            assert retire_events == []
            assert len(final_snapshots) == 3
            assert (
                sum(
                    1
                    for item in final_snapshots
                    if item.element_type == ElementType.TEXT
                )
                == 2
            )
            assert (
                sum(
                    1
                    for item in final_snapshots
                    if item.element_type == ElementType.IMG
                )
                == 1
            )

            final_text_events = [
                item
                for item in final_snapshots
                if item.element_type == ElementType.TEXT
            ]
            assert sorted(item.content_text for item in final_text_events) == [
                "After image.",
                "Before image.\n\n",
            ]
            before_text = next(
                item
                for item in final_text_events
                if item.content_text == "Before image.\n\n"
            )
            after_text = next(
                item
                for item in final_text_events
                if item.content_text == "After image."
            )
            assert before_text.audio_url == "https://example.com/audio-0.mp3"
            assert after_text.audio_url == ""

    def test_pending_audio_skips_image_stream_and_binds_to_following_text(
        self, adapter_app
    ):
        from flaskr.service.learn.learn_dtos import (
            AudioCompleteDTO,
            AudioSegmentDTO,
            ElementType,
            GeneratedType,
            RunMarkdownFlowDTO,
        )
        from flaskr.service.learn.listen_elements import ListenElementRunAdapter

        with adapter_app.app_context():
            adapter = ListenElementRunAdapter(
                adapter_app, shifu_bid="s1", outline_bid="o1", user_bid="u1"
            )

            events = [
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-img-audio",
                    type=GeneratedType.CONTENT,
                    content="![img](https://example.com/visual.png)\n",
                ).set_mdflow_stream_parts(
                    [("![img](https://example.com/visual.png)\n", "img", 0)]
                ),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-img-audio",
                    type=GeneratedType.AUDIO_SEGMENT,
                    content=AudioSegmentDTO(
                        position=0,
                        segment_index=0,
                        audio_data="img-only-segment",
                        duration_ms=210,
                        is_final=False,
                    ),
                ),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-img-audio",
                    type=GeneratedType.AUDIO_COMPLETE,
                    content=AudioCompleteDTO(
                        audio_url="https://example.com/img-only.mp3",
                        audio_bid="img-only-audio-0",
                        duration_ms=210,
                        position=0,
                    ),
                ),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-img-audio",
                    type=GeneratedType.CONTENT,
                    content="caption line\n",
                ).set_mdflow_stream_parts([("caption line\n", "text", 1)]),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-img-audio",
                    type=GeneratedType.BREAK,
                    content="",
                ),
            ]

            streamed = list(adapter.process(events))
            image_events = [
                message.content
                for message in streamed
                if message.type == "element"
                and message.content.element_type == ElementType.IMG
            ]
            text_events = [
                message.content
                for message in streamed
                if message.type == "element"
                and message.content.element_type == ElementType.TEXT
            ]

            assert len(image_events) >= 1
            assert all(item.audio_url == "" for item in image_events)
            assert all(item.audio_segments == [] for item in image_events)
            assert all(item.is_speakable is False for item in image_events)

            assert len(text_events) >= 1
            assert any(
                item.audio_url == "https://example.com/img-only.mp3"
                for item in text_events
            )
            assert text_events[0].audio_url == "https://example.com/img-only.mp3"
            assert text_events[0].audio_segments == [
                {
                    "position": 0,
                    "segment_index": 0,
                    "audio_data": "img-only-segment",
                    "duration_ms": 210,
                    "is_final": True,
                }
            ]
            final_text_event = next(
                item
                for item in text_events
                if item.audio_url == "https://example.com/img-only.mp3"
                and item.is_final
            )
            assert final_text_event.audio_segments == [
                {
                    "position": 0,
                    "segment_index": 0,
                    "audio_data": "img-only-segment",
                    "duration_ms": 210,
                    "is_final": True,
                }
            ]
            assert final_text_event.is_final is True
            assert all(item.is_speakable is True for item in text_events)

    def test_fallback_text_patch_keeps_bound_audio_during_in_progress_history(
        self, adapter_app
    ):
        from flaskr.dao import db
        from flaskr.service.learn.const import ROLE_TEACHER
        from flaskr.service.learn.learn_dtos import (
            AudioCompleteDTO,
            GeneratedType,
            RunMarkdownFlowDTO,
        )
        from flaskr.service.learn.listen_elements import (
            ListenElementRunAdapter,
            get_listen_element_record,
        )
        from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
        from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS
        from flaskr.service.shifu.consts import BLOCK_TYPE_MDCONTENT_VALUE

        user_bid = "user-fallback-audio-retain"
        shifu_bid = "shifu-fallback-audio-retain"
        outline_bid = "outline-fallback-audio-retain"
        progress_bid = "progress-fallback-audio-retain"
        generated_block_bid = "generated-fallback-audio-retain"

        with adapter_app.app_context():
            progress = LearnProgressRecord(
                progress_record_bid=progress_bid,
                shifu_bid=shifu_bid,
                outline_item_bid=outline_bid,
                user_bid=user_bid,
                status=LEARN_STATUS_IN_PROGRESS,
                block_position=0,
            )
            block = LearnGeneratedBlock(
                generated_block_bid=generated_block_bid,
                progress_record_bid=progress_bid,
                user_bid=user_bid,
                block_bid="block-fallback-audio-retain",
                outline_item_bid=outline_bid,
                shifu_bid=shifu_bid,
                type=BLOCK_TYPE_MDCONTENT_VALUE,
                role=ROLE_TEACHER,
                generated_content="",
                position=0,
                block_content_conf="",
                status=1,
            )
            db.session.add_all([progress, block])
            db.session.commit()

            adapter = ListenElementRunAdapter(
                adapter_app,
                shifu_bid=shifu_bid,
                outline_bid=outline_bid,
                user_bid=user_bid,
            )
            streamed = list(
                adapter.process(
                    [
                        RunMarkdownFlowDTO(
                            outline_bid=outline_bid,
                            generated_block_bid=generated_block_bid,
                            type=GeneratedType.CONTENT,
                            content="Hello",
                        ),
                        RunMarkdownFlowDTO(
                            outline_bid=outline_bid,
                            generated_block_bid=generated_block_bid,
                            type=GeneratedType.AUDIO_COMPLETE,
                            content=AudioCompleteDTO(
                                audio_url="https://example.com/fallback-retain.mp3",
                                audio_bid="fallback-retain-audio",
                                duration_ms=480,
                                position=0,
                            ),
                        ),
                        RunMarkdownFlowDTO(
                            outline_bid=outline_bid,
                            generated_block_bid=generated_block_bid,
                            type=GeneratedType.CONTENT,
                            content=" world",
                        ),
                    ]
                )
            )

            latest_live_element = streamed[-1].content
            history_record = get_listen_element_record(
                adapter_app,
                shifu_bid=shifu_bid,
                outline_bid=outline_bid,
                user_bid=user_bid,
                preview_mode=False,
            )

        assert (
            latest_live_element.audio_url == "https://example.com/fallback-retain.mp3"
        )
        assert latest_live_element.payload is not None
        assert latest_live_element.payload.audio is not None
        assert latest_live_element.payload.audio.audio_bid == "fallback-retain-audio"
        assert latest_live_element.content_text == "Hello world"

        assert len(history_record.elements) == 1
        history_element = history_record.elements[0]
        assert history_element.is_speakable is True
        assert history_element.audio_url == "https://example.com/fallback-retain.mp3"
        assert history_element.payload is not None
        assert history_element.payload.audio is not None
        assert history_element.payload.audio.audio_bid == "fallback-retain-audio"
        assert history_element.content_text == "Hello world"

    def test_stream_text_patch_keeps_bound_audio_during_in_progress_history(
        self, adapter_app
    ):
        from flaskr.dao import db
        from flaskr.service.learn.const import ROLE_TEACHER
        from flaskr.service.learn.learn_dtos import (
            AudioCompleteDTO,
            GeneratedType,
            RunMarkdownFlowDTO,
        )
        from flaskr.service.learn.listen_elements import (
            ListenElementRunAdapter,
            get_listen_element_record,
        )
        from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
        from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS
        from flaskr.service.shifu.consts import BLOCK_TYPE_MDCONTENT_VALUE

        user_bid = "user-stream-audio-retain"
        shifu_bid = "shifu-stream-audio-retain"
        outline_bid = "outline-stream-audio-retain"
        progress_bid = "progress-stream-audio-retain"
        generated_block_bid = "generated-stream-audio-retain"

        with adapter_app.app_context():
            progress = LearnProgressRecord(
                progress_record_bid=progress_bid,
                shifu_bid=shifu_bid,
                outline_item_bid=outline_bid,
                user_bid=user_bid,
                status=LEARN_STATUS_IN_PROGRESS,
                block_position=0,
            )
            block = LearnGeneratedBlock(
                generated_block_bid=generated_block_bid,
                progress_record_bid=progress_bid,
                user_bid=user_bid,
                block_bid="block-stream-audio-retain",
                outline_item_bid=outline_bid,
                shifu_bid=shifu_bid,
                type=BLOCK_TYPE_MDCONTENT_VALUE,
                role=ROLE_TEACHER,
                generated_content="",
                position=0,
                block_content_conf="",
                status=1,
            )
            db.session.add_all([progress, block])
            db.session.commit()

            adapter = ListenElementRunAdapter(
                adapter_app,
                shifu_bid=shifu_bid,
                outline_bid=outline_bid,
                user_bid=user_bid,
            )
            streamed = list(
                adapter.process(
                    [
                        RunMarkdownFlowDTO(
                            outline_bid=outline_bid,
                            generated_block_bid=generated_block_bid,
                            type=GeneratedType.CONTENT,
                            content="Hello ",
                        ).set_mdflow_stream_parts([("Hello ", "text", 0)]),
                        RunMarkdownFlowDTO(
                            outline_bid=outline_bid,
                            generated_block_bid=generated_block_bid,
                            type=GeneratedType.AUDIO_COMPLETE,
                            content=AudioCompleteDTO(
                                audio_url="https://example.com/stream-retain.mp3",
                                audio_bid="stream-retain-audio",
                                duration_ms=520,
                                position=0,
                            ),
                        ),
                        RunMarkdownFlowDTO(
                            outline_bid=outline_bid,
                            generated_block_bid=generated_block_bid,
                            type=GeneratedType.CONTENT,
                            content="world",
                        ).set_mdflow_stream_parts([("world", "text", 0)]),
                    ]
                )
            )

            latest_live_element = streamed[-1].content
            history_record = get_listen_element_record(
                adapter_app,
                shifu_bid=shifu_bid,
                outline_bid=outline_bid,
                user_bid=user_bid,
                preview_mode=False,
            )

        assert latest_live_element.audio_url == "https://example.com/stream-retain.mp3"
        assert latest_live_element.payload is not None
        assert latest_live_element.payload.audio is not None
        assert latest_live_element.payload.audio.audio_bid == "stream-retain-audio"
        assert latest_live_element.content_text == "Hello world"

        assert len(history_record.elements) == 1
        history_element = history_record.elements[0]
        assert history_element.is_speakable is True
        assert history_element.audio_url == "https://example.com/stream-retain.mp3"
        assert history_element.payload is not None
        assert history_element.payload.audio is not None
        assert history_element.payload.audio.audio_bid == "stream-retain-audio"
        assert history_element.content_text == "Hello world"

    def test_live_audio_patches_mirror_progressive_subtitles_on_same_element(
        self, adapter_app
    ):
        from flaskr.service.learn.learn_dtos import (
            AudioCompleteDTO,
            AudioSegmentDTO,
            ElementType,
            GeneratedType,
            RunMarkdownFlowDTO,
        )
        from flaskr.service.learn.listen_elements import ListenElementRunAdapter

        with adapter_app.app_context():
            adapter = ListenElementRunAdapter(
                adapter_app, shifu_bid="s1", outline_bid="o1", user_bid="u1"
            )

            events = [
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-subtitle-freeze",
                    type=GeneratedType.CONTENT,
                    content="First sentence.\n",
                ).set_mdflow_stream_parts([("First sentence.\n", "text", 1)]),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-subtitle-freeze",
                    type=GeneratedType.AUDIO_SEGMENT,
                    content=AudioSegmentDTO(
                        position=0,
                        stream_element_number=1,
                        stream_element_type="text",
                        segment_index=0,
                        audio_data="segment-0",
                        duration_ms=180,
                        is_final=False,
                        subtitle_cues=[
                            {
                                "text": "First sentence.",
                                "start_ms": 0,
                                "end_ms": 180,
                                "segment_index": 0,
                                "position": 0,
                            }
                        ],
                    ),
                ),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-subtitle-freeze",
                    type=GeneratedType.AUDIO_SEGMENT,
                    content=AudioSegmentDTO(
                        position=0,
                        stream_element_number=1,
                        stream_element_type="text",
                        segment_index=1,
                        audio_data="segment-1",
                        duration_ms=320,
                        is_final=False,
                        subtitle_cues=[
                            {
                                "text": "First sentence.",
                                "start_ms": 0,
                                "end_ms": 170,
                                "segment_index": 0,
                                "position": 0,
                            },
                            {
                                "text": "Second sentence.",
                                "start_ms": 180,
                                "end_ms": 320,
                                "segment_index": 1,
                                "position": 0,
                            },
                        ],
                    ),
                ),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-subtitle-freeze",
                    type=GeneratedType.CONTENT,
                    content="Second sentence.\n",
                ).set_mdflow_stream_parts([("Second sentence.\n", "text", 1)]),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-subtitle-freeze",
                    type=GeneratedType.AUDIO_COMPLETE,
                    content=AudioCompleteDTO(
                        audio_url="https://example.com/subtitle-freeze.mp3",
                        audio_bid="subtitle-freeze-audio",
                        duration_ms=500,
                        position=0,
                        stream_element_number=1,
                        stream_element_type="text",
                        subtitle_cues=[
                            {
                                "text": "First sentence.",
                                "start_ms": 0,
                                "end_ms": 160,
                                "segment_index": 0,
                                "position": 0,
                            },
                            {
                                "text": "Second sentence.",
                                "start_ms": 180,
                                "end_ms": 340,
                                "segment_index": 1,
                                "position": 0,
                            },
                        ],
                    ),
                ),
            ]

            streamed = list(adapter.process(events))
            text_events = [
                item.content
                for item in streamed
                if item.type == "element"
                and item.content.element_type == ElementType.TEXT
            ]

        assert len(text_events) == 5
        first_segment_patch = text_events[1]
        second_segment_patch = text_events[2]
        content_patch = text_events[3]
        final_patch = text_events[4]

        assert first_segment_patch.element_bid == final_patch.element_bid
        assert first_segment_patch.payload is not None
        assert first_segment_patch.payload.audio is not None
        assert [
            cue.text for cue in first_segment_patch.payload.audio.subtitle_cues
        ] == ["First sentence."]
        assert [
            (cue.start_ms, cue.end_ms)
            for cue in first_segment_patch.payload.audio.subtitle_cues
        ] == [(0, 180)]
        assert first_segment_patch.payload.audio.duration_ms == 180
        assert first_segment_patch.audio_segments == [
            {
                "position": 0,
                "segment_index": 0,
                "audio_data": "segment-0",
                "duration_ms": 180,
                "is_final": False,
                "subtitle_cues": [
                    {
                        "text": "First sentence.",
                        "start_ms": 0,
                        "end_ms": 180,
                        "segment_index": 0,
                        "position": 0,
                    }
                ],
            }
        ]

        assert [
            cue.text for cue in second_segment_patch.payload.audio.subtitle_cues
        ] == [
            "First sentence.",
            "Second sentence.",
        ]
        assert [
            (cue.start_ms, cue.end_ms)
            for cue in second_segment_patch.payload.audio.subtitle_cues
        ] == [(0, 170), (180, 320)]
        assert second_segment_patch.payload.audio.duration_ms == 320

        assert [cue.text for cue in content_patch.payload.audio.subtitle_cues] == [
            "First sentence.",
            "Second sentence.",
        ]
        assert [
            (cue.start_ms, cue.end_ms)
            for cue in content_patch.payload.audio.subtitle_cues
        ] == [(0, 170), (180, 320)]
        assert content_patch.payload.audio.duration_ms == 320

        assert final_patch.audio_url == "https://example.com/subtitle-freeze.mp3"
        assert final_patch.payload is not None
        assert final_patch.payload.audio is not None
        assert final_patch.payload.audio.audio_bid == "subtitle-freeze-audio"
        assert [cue.text for cue in final_patch.payload.audio.subtitle_cues] == [
            "First sentence.",
            "Second sentence.",
        ]
        assert [
            (cue.start_ms, cue.end_ms)
            for cue in final_patch.payload.audio.subtitle_cues
        ] == [(0, 160), (180, 340)]
        assert final_patch.payload.audio.duration_ms == 340
        assert final_patch.audio_segments == [
            {
                "position": 0,
                "segment_index": 0,
                "audio_data": "segment-0",
                "duration_ms": 180,
                "is_final": False,
                "subtitle_cues": [
                    {
                        "text": "First sentence.",
                        "start_ms": 0,
                        "end_ms": 180,
                        "segment_index": 0,
                        "position": 0,
                    }
                ],
            },
            {
                "position": 0,
                "segment_index": 1,
                "audio_data": "segment-1",
                "duration_ms": 320,
                "is_final": True,
                "subtitle_cues": [
                    {
                        "text": "First sentence.",
                        "start_ms": 0,
                        "end_ms": 170,
                        "segment_index": 0,
                        "position": 0,
                    },
                    {
                        "text": "Second sentence.",
                        "start_ms": 180,
                        "end_ms": 320,
                        "segment_index": 1,
                        "position": 0,
                    },
                ],
            },
        ]

    def test_live_audio_patches_do_not_rewrite_same_count_updates(self, adapter_app):
        from flaskr.service.learn.learn_dtos import (
            AudioCompleteDTO,
            AudioSegmentDTO,
            ElementType,
            GeneratedType,
            RunMarkdownFlowDTO,
        )
        from flaskr.service.learn.listen_elements import ListenElementRunAdapter

        with adapter_app.app_context():
            adapter = ListenElementRunAdapter(
                adapter_app, shifu_bid="s1", outline_bid="o1", user_bid="u1"
            )

            events = [
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-subtitle-grow",
                    type=GeneratedType.CONTENT,
                    content="Sentence one. Sentence two.\n",
                ).set_mdflow_stream_parts(
                    [("Sentence one. Sentence two.\n", "text", 1)]
                ),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-subtitle-grow",
                    type=GeneratedType.AUDIO_SEGMENT,
                    content=AudioSegmentDTO(
                        position=0,
                        stream_element_number=1,
                        stream_element_type="text",
                        segment_index=0,
                        audio_data="segment-grow-0",
                        duration_ms=180,
                        is_final=False,
                        subtitle_cues=[
                            {
                                "text": "Sentence one.",
                                "start_ms": 0,
                                "end_ms": 80,
                                "segment_index": 0,
                                "position": 0,
                            },
                            {
                                "text": "Sentence two.",
                                "start_ms": 100,
                                "end_ms": 180,
                                "segment_index": 1,
                                "position": 0,
                            },
                        ],
                    ),
                ),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-subtitle-grow",
                    type=GeneratedType.AUDIO_SEGMENT,
                    content=AudioSegmentDTO(
                        position=0,
                        stream_element_number=1,
                        stream_element_type="text",
                        segment_index=1,
                        audio_data="segment-grow-1",
                        duration_ms=320,
                        is_final=False,
                        subtitle_cues=[
                            {
                                "text": "Sentence one.",
                                "start_ms": 0,
                                "end_ms": 140,
                                "segment_index": 0,
                                "position": 0,
                            },
                            {
                                "text": "Sentence two.",
                                "start_ms": 180,
                                "end_ms": 320,
                                "segment_index": 1,
                                "position": 0,
                            },
                        ],
                    ),
                ),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-subtitle-grow",
                    type=GeneratedType.AUDIO_COMPLETE,
                    content=AudioCompleteDTO(
                        audio_url="https://example.com/subtitle-grow.mp3",
                        audio_bid="subtitle-grow-audio",
                        duration_ms=360,
                        position=0,
                        stream_element_number=1,
                        stream_element_type="text",
                        subtitle_cues=[
                            {
                                "text": "Sentence one.",
                                "start_ms": 0,
                                "end_ms": 160,
                                "segment_index": 0,
                                "position": 0,
                            },
                            {
                                "text": "Sentence two.",
                                "start_ms": 220,
                                "end_ms": 360,
                                "segment_index": 1,
                                "position": 0,
                            },
                        ],
                    ),
                ),
            ]

            streamed = list(adapter.process(events))
            text_events = [
                item.content
                for item in streamed
                if item.type == "element"
                and item.content.element_type == ElementType.TEXT
            ]

        assert len(text_events) == 4
        first_segment_patch = text_events[1]
        second_segment_patch = text_events[2]
        final_patch = text_events[3]

        assert [
            (cue.start_ms, cue.end_ms)
            for cue in first_segment_patch.payload.audio.subtitle_cues
        ] == [(0, 80), (100, 180)]
        assert first_segment_patch.payload.audio.duration_ms == 180

        assert [
            (cue.start_ms, cue.end_ms)
            for cue in second_segment_patch.payload.audio.subtitle_cues
        ] == [(0, 140), (180, 320)]
        assert second_segment_patch.payload.audio.duration_ms == 320

        assert [
            (cue.start_ms, cue.end_ms)
            for cue in final_patch.payload.audio.subtitle_cues
        ] == [(0, 160), (220, 360)]
        assert final_patch.payload.audio.duration_ms == 360

    def test_live_audio_patches_preserve_incoming_middle_cues(self, adapter_app):
        from flaskr.service.learn.learn_dtos import (
            AudioCompleteDTO,
            AudioSegmentDTO,
            ElementType,
            GeneratedType,
            RunMarkdownFlowDTO,
        )
        from flaskr.service.learn.listen_elements import ListenElementRunAdapter

        with adapter_app.app_context():
            adapter = ListenElementRunAdapter(
                adapter_app, shifu_bid="s1", outline_bid="o1", user_bid="u1"
            )

            events = [
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-subtitle-middle",
                    type=GeneratedType.CONTENT,
                    content="Sentence one. Sentence two. Sentence three.\n",
                ).set_mdflow_stream_parts(
                    [("Sentence one. Sentence two. Sentence three.\n", "text", 1)]
                ),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-subtitle-middle",
                    type=GeneratedType.AUDIO_SEGMENT,
                    content=AudioSegmentDTO(
                        position=0,
                        stream_element_number=1,
                        stream_element_type="text",
                        segment_index=0,
                        audio_data="segment-middle-0",
                        duration_ms=180,
                        is_final=False,
                        subtitle_cues=[
                            {
                                "text": "Sentence one.",
                                "start_ms": 0,
                                "end_ms": 40,
                                "segment_index": 0,
                                "position": 0,
                            },
                            {
                                "text": "Sentence two.",
                                "start_ms": 40,
                                "end_ms": 80,
                                "segment_index": 1,
                                "position": 0,
                            },
                            {
                                "text": "Sentence three.",
                                "start_ms": 80,
                                "end_ms": 180,
                                "segment_index": 2,
                                "position": 0,
                            },
                        ],
                    ),
                ),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-subtitle-middle",
                    type=GeneratedType.AUDIO_SEGMENT,
                    content=AudioSegmentDTO(
                        position=0,
                        stream_element_number=1,
                        stream_element_type="text",
                        segment_index=1,
                        audio_data="segment-middle-1",
                        duration_ms=320,
                        is_final=False,
                        subtitle_cues=[
                            {
                                "text": "Sentence one.",
                                "start_ms": 0,
                                "end_ms": 120,
                                "segment_index": 0,
                                "position": 0,
                            },
                            {
                                "text": "Sentence two.",
                                "start_ms": 120,
                                "end_ms": 220,
                                "segment_index": 1,
                                "position": 0,
                            },
                            {
                                "text": "Sentence three.",
                                "start_ms": 220,
                                "end_ms": 320,
                                "segment_index": 2,
                                "position": 0,
                            },
                        ],
                    ),
                ),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-subtitle-middle",
                    type=GeneratedType.AUDIO_COMPLETE,
                    content=AudioCompleteDTO(
                        audio_url="https://example.com/subtitle-middle.mp3",
                        audio_bid="subtitle-middle-audio",
                        duration_ms=360,
                        position=0,
                        stream_element_number=1,
                        stream_element_type="text",
                        subtitle_cues=[
                            {
                                "text": "Sentence one.",
                                "start_ms": 0,
                                "end_ms": 140,
                                "segment_index": 0,
                                "position": 0,
                            },
                            {
                                "text": "Sentence two.",
                                "start_ms": 140,
                                "end_ms": 250,
                                "segment_index": 1,
                                "position": 0,
                            },
                            {
                                "text": "Sentence three.",
                                "start_ms": 250,
                                "end_ms": 360,
                                "segment_index": 2,
                                "position": 0,
                            },
                        ],
                    ),
                ),
            ]

            streamed = list(adapter.process(events))
            text_events = [
                item.content
                for item in streamed
                if item.type == "element"
                and item.content.element_type == ElementType.TEXT
            ]

        assert len(text_events) == 4
        first_segment_patch = text_events[1]
        second_segment_patch = text_events[2]
        final_patch = text_events[3]

        assert [
            (cue.start_ms, cue.end_ms)
            for cue in first_segment_patch.payload.audio.subtitle_cues
        ] == [(0, 40), (40, 80), (80, 180)]

        assert [
            (cue.start_ms, cue.end_ms)
            for cue in second_segment_patch.payload.audio.subtitle_cues
        ] == [(0, 120), (120, 220), (220, 320)]
        assert second_segment_patch.payload.audio.duration_ms == 320

        assert [
            (cue.start_ms, cue.end_ms)
            for cue in final_patch.payload.audio.subtitle_cues
        ] == [(0, 140), (140, 250), (250, 360)]
        assert final_patch.payload.audio.duration_ms == 360

    def test_explicit_stream_audio_waits_for_matching_text_element(self, adapter_app):
        from flaskr.service.learn.learn_dtos import (
            AudioCompleteDTO,
            AudioSegmentDTO,
            ElementType,
            GeneratedType,
            RunMarkdownFlowDTO,
        )
        from flaskr.service.learn.listen_elements import ListenElementRunAdapter

        with adapter_app.app_context():
            adapter = ListenElementRunAdapter(
                adapter_app, shifu_bid="s1", outline_bid="o1", user_bid="u1"
            )

            events = [
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-pending-explicit-audio",
                    type=GeneratedType.CONTENT,
                    content="Intro line.\n",
                ).set_mdflow_stream_parts([("Intro line.\n", "text", 0)]),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-pending-explicit-audio",
                    type=GeneratedType.AUDIO_SEGMENT,
                    content=AudioSegmentDTO(
                        position=0,
                        stream_element_number=1,
                        stream_element_type="text",
                        segment_index=0,
                        audio_data="segment-0",
                        duration_ms=180,
                        is_final=False,
                        subtitle_cues=[
                            {
                                "text": "Delayed narration.",
                                "start_ms": 0,
                                "end_ms": 180,
                                "segment_index": 0,
                                "position": 0,
                            }
                        ],
                    ),
                ),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-pending-explicit-audio",
                    type=GeneratedType.CONTENT,
                    content="Still intro.\n",
                ).set_mdflow_stream_parts([("Still intro.\n", "text", 0)]),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-pending-explicit-audio",
                    type=GeneratedType.AUDIO_COMPLETE,
                    content=AudioCompleteDTO(
                        audio_url="https://example.com/delayed.mp3",
                        audio_bid="delayed-audio",
                        duration_ms=240,
                        position=0,
                        stream_element_number=1,
                        stream_element_type="text",
                        subtitle_cues=[
                            {
                                "text": "Delayed narration.",
                                "start_ms": 0,
                                "end_ms": 240,
                                "segment_index": 0,
                                "position": 0,
                            }
                        ],
                    ),
                ),
                RunMarkdownFlowDTO(
                    outline_bid="o1",
                    generated_block_bid="gb-pending-explicit-audio",
                    type=GeneratedType.CONTENT,
                    content="Delayed narration.\n",
                ).set_mdflow_stream_parts([("Delayed narration.\n", "text", 1)]),
            ]

            streamed = list(adapter.process(events))
            text_events = [
                item.content
                for item in streamed
                if item.type == "element"
                and item.content.element_type == ElementType.TEXT
            ]

        assert len(text_events) == 3
        intro_event = text_events[0]
        intro_patch = text_events[1]
        delayed_event = text_events[2]

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
        assert [
            (cue.start_ms, cue.end_ms)
            for cue in delayed_event.payload.audio.subtitle_cues
        ] == [(0, 240)]
        assert delayed_event.audio_segments == [
            {
                "position": 0,
                "segment_index": 0,
                "audio_data": "segment-0",
                "duration_ms": 180,
                "is_final": True,
                "subtitle_cues": [
                    {
                        "text": "Delayed narration.",
                        "start_ms": 0,
                        "end_ms": 180,
                        "segment_index": 0,
                        "position": 0,
                    }
                ],
            }
        ]
