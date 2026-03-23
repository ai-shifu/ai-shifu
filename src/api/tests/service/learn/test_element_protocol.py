"""Tests for the element protocol freeze (Sections A-D of the design doc).

Covers:
- ElementDTO new fields serialization/deserialization
- ElementType new enum values and legacy fallback
- TypeStateMachine transitions and output
- is_new=false / is_marker constraint behaviour
- audio_segments accumulation
"""

import pytest


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
        from flaskr.service.learn.listen_elements import ELEMENT_TYPE_CODES

        # Every non-legacy type must have a code
        for et in ElementType:
            if et.name.startswith("_"):
                continue
            assert et in ELEMENT_TYPE_CODES, f"Missing code for {et}"

    def test_legacy_mapping(self):
        from flaskr.service.learn.learn_dtos import ElementType
        from flaskr.service.learn.listen_elements import LEGACY_ELEMENT_TYPE_MAP

        assert LEGACY_ELEMENT_TYPE_MAP[ElementType._SANDBOX] == ElementType.HTML
        assert LEGACY_ELEMENT_TYPE_MAP[ElementType._PICTURE] == ElementType.IMG
        assert LEGACY_ELEMENT_TYPE_MAP[ElementType._VIDEO] == ElementType.HTML

    def test_mdflow_stream_mapping_keeps_only_compat_special_cases(self):
        from flaskr.service.learn.learn_dtos import ElementType
        from flaskr.service.learn.listen_elements import (
            _element_type_from_mdflow_stream,
        )

        assert _element_type_from_mdflow_stream("text", "hello") == ElementType.TEXT
        assert _element_type_from_mdflow_stream("code", "```py\nprint(1)\n```") == (
            ElementType.CODE
        )
        assert _element_type_from_mdflow_stream("img", "![x](y)") == ElementType.MD_IMG
        assert _element_type_from_mdflow_stream(
            "html", "<table><tr><td>x</td></tr></table>"
        ) == (ElementType.TABLES)


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
        from flaskr.service.learn.listen_elements import _element_type_for_visual_kind

        assert _element_type_for_visual_kind("video") == ElementType.HTML
        assert _element_type_for_visual_kind("img") == ElementType.IMG
        assert _element_type_for_visual_kind("md_img") == ElementType.MD_IMG
        assert _element_type_for_visual_kind("svg") == ElementType.SVG
        assert _element_type_for_visual_kind("iframe") == ElementType.HTML
        assert _element_type_for_visual_kind("sandbox") == ElementType.HTML
        assert _element_type_for_visual_kind("html_table") == ElementType.TABLES
        assert _element_type_for_visual_kind("md_table") == ElementType.TABLES
        assert _element_type_for_visual_kind("fence") == ElementType.CODE
        assert _element_type_for_visual_kind("mermaid") == ElementType.MERMAID
        assert _element_type_for_visual_kind("latex") == ElementType.LATEX
        assert _element_type_for_visual_kind("title") == ElementType.TITLE
        assert _element_type_for_visual_kind("text") == ElementType.TEXT

    def test_unknown_defaults_to_text(self):
        from flaskr.service.learn.learn_dtos import ElementType
        from flaskr.service.learn.listen_elements import _element_type_for_visual_kind

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
        assert len(result_with.events) == 2
        event_types = [e.type for e in result_with.events]
        assert "element" in event_types
        assert "audio_complete" in event_types


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


def test_backfill_populates_sequence_number_and_audio_url(app):
    """Backfill should assign sequence_number and extract audio_url from payload."""
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.const import ROLE_TEACHER
    from flaskr.service.learn.listen_elements import (
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
        from flaskr.service.learn.listen_elements import (
            _deserialize_payload,
            _serialize_payload,
        )
        from flaskr.service.learn.learn_dtos import ElementPayloadDTO

        asks = [
            {"role": "student", "content": "question"},
            {"role": "teacher", "content": "answer"},
        ]
        original = ElementPayloadDTO(asks=asks)
        raw = _serialize_payload(original)
        restored = _deserialize_payload(raw)
        assert restored.asks == asks

    def test_payload_asks_deserialization_missing(self):
        from flaskr.service.learn.listen_elements import _deserialize_payload

        raw = '{"audio": null, "previous_visuals": []}'
        restored = _deserialize_payload(raw)
        assert restored.asks is None

    def test_payload_asks_deserialization_invalid_type(self):
        from flaskr.service.learn.listen_elements import _deserialize_payload

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

    def test_load_context_from_payload_asks(self):
        import types
        from flaskr.service.learn.handle_input_ask import _load_ask_context
        from flaskr.service.learn.listen_elements import _serialize_payload
        from flaskr.service.learn.learn_dtos import ElementPayloadDTO

        asks = [
            {"role": "student", "content": "q1"},
            {"role": "teacher", "content": "a1"},
        ]
        payload = ElementPayloadDTO()
        anchor = types.SimpleNamespace(
            content_text="anchor text",
            payload=_serialize_payload(payload),
        )
        ask_element = types.SimpleNamespace(
            payload=_serialize_payload(ElementPayloadDTO(asks=asks)),
        )
        result = _load_ask_context(anchor, ask_element, 10)
        assert result is not None
        assert result[0] == {"role": "assistant", "content": "anchor text"}
        assert result[1] == {"role": "user", "content": "q1"}
        assert result[2] == {"role": "assistant", "content": "a1"}

    def test_load_context_fallback_to_none(self):
        import types
        from flaskr.service.learn.handle_input_ask import _load_ask_context
        from flaskr.service.learn.listen_elements import _serialize_payload
        from flaskr.service.learn.learn_dtos import ElementPayloadDTO

        payload = ElementPayloadDTO()
        anchor = types.SimpleNamespace(
            content_text="text",
            payload=_serialize_payload(payload),
        )
        ask_element = types.SimpleNamespace(
            payload=_serialize_payload(ElementPayloadDTO()),
        )
        result = _load_ask_context(anchor, ask_element, 10)
        assert result is None

    def test_load_context_none_element(self):
        from flaskr.service.learn.handle_input_ask import _load_ask_context

        assert _load_ask_context(None, None, 10) is None

    def test_load_context_truncation(self):
        import types
        from flaskr.service.learn.handle_input_ask import _load_ask_context
        from flaskr.service.learn.listen_elements import _serialize_payload
        from flaskr.service.learn.learn_dtos import ElementPayloadDTO

        asks = [
            {"role": "student", "content": f"q{i}"}
            if i % 2 == 0
            else {"role": "teacher", "content": f"a{i}"}
            for i in range(20)
        ]
        payload = ElementPayloadDTO()
        anchor = types.SimpleNamespace(
            content_text="anchor",
            payload=_serialize_payload(payload),
        )
        ask_element = types.SimpleNamespace(
            payload=_serialize_payload(ElementPayloadDTO(asks=asks)),
        )
        result = _load_ask_context(anchor, ask_element, 4)
        assert result is not None
        # anchor content + last 4 asks entries
        assert len(result) == 5


class TestHandleAskAdapter:
    """Tests for ListenElementRunAdapter._handle_ask()."""

    def test_handle_ask_appends_student_to_payload(self, app):
        import json
        from flaskr.service.learn.listen_elements import (
            ListenElementRunAdapter,
            _serialize_payload,
        )
        from flaskr.service.learn.learn_dtos import (
            GeneratedType,
            RunMarkdownFlowDTO,
            ElementPayloadDTO,
        )
        from flaskr.service.learn.models import LearnGeneratedElement
        from flaskr.dao import db

        with app.app_context():
            adapter = ListenElementRunAdapter(
                app, shifu_bid="s1", outline_bid="o1", user_bid="u1"
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
            assert "asks" in payload
            assert len(payload["asks"]) == 1
            assert payload["asks"][0]["role"] == "student"
            assert payload["asks"][0]["content"] == "user question here"

    def test_handle_ask_emits_ask_element(self, app):
        from flaskr.service.learn.listen_elements import (
            ListenElementRunAdapter,
            _serialize_payload,
        )
        from flaskr.service.learn.learn_dtos import (
            ElementType,
            GeneratedType,
            RunMarkdownFlowDTO,
            ElementPayloadDTO,
        )
        from flaskr.service.learn.models import LearnGeneratedElement
        from flaskr.dao import db

        with app.app_context():
            adapter = ListenElementRunAdapter(
                app, shifu_bid="s1", outline_bid="o1", user_bid="u1"
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
            assert len(result) == 1
            assert result[0].content.element_type == ElementType.ASK
            assert result[0].content.payload.anchor_element_bid == "anchor_elem_2"

    def test_handle_ask_sets_anchor_bid_state(self, app):
        from flaskr.service.learn.listen_elements import (
            ListenElementRunAdapter,
            _serialize_payload,
        )
        from flaskr.service.learn.learn_dtos import (
            GeneratedType,
            RunMarkdownFlowDTO,
            ElementPayloadDTO,
        )
        from flaskr.service.learn.models import LearnGeneratedElement
        from flaskr.dao import db

        with app.app_context():
            adapter = ListenElementRunAdapter(
                app, shifu_bid="s1", outline_bid="o1", user_bid="u1"
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
