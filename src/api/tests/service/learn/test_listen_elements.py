import json
import types

import pytest


def _require_app(app):
    if app is None:
        pytest.skip("App fixture disabled")


def test_get_listen_element_record_returns_latest_elements_and_events(app):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.learn_dtos import VariableUpdateDTO
    from flaskr.service.learn.listen_elements import get_listen_element_record
    from flaskr.service.learn.models import LearnGeneratedElement, LearnProgressRecord
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

    user_bid = "user-listen-elements"
    shifu_bid = "shifu-listen-elements"
    outline_bid = "outline-listen-elements"
    progress_bid = "progress-listen-elements"
    generated_block_bid = "generated-listen-elements"
    element_bid = "element-listen-001"

    partial_payload = json.dumps(
        {
            "audio": None,
            "previous_visuals": [
                {
                    "visual_type": "img",
                    "content": "https://example.com/partial.png",
                }
            ],
        }
    )
    final_payload = json.dumps(
        {
            "audio": {
                "position": 0,
                "audio_url": "https://example.com/final.mp3",
                "audio_bid": "audio-listen-001",
                "duration_ms": 900,
            },
            "previous_visuals": [
                {
                    "visual_type": "img",
                    "content": "https://example.com/final.png",
                }
            ],
        }
    )

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
        partial = LearnGeneratedElement(
            element_bid=element_bid,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            generated_block_bid=generated_block_bid,
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            run_session_bid="run-listen-1",
            run_event_seq=1,
            event_type="element",
            role="teacher",
            element_index=7,
            element_type="sandbox",
            element_type_code=102,
            change_type="render",
            target_element_bid="",
            is_navigable=1,
            is_final=0,
            content_text="partial",
            payload=partial_payload,
            status=1,
        )
        final = LearnGeneratedElement(
            element_bid=element_bid,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            generated_block_bid=generated_block_bid,
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            run_session_bid="run-listen-1",
            run_event_seq=2,
            event_type="element",
            role="teacher",
            element_index=7,
            element_type="sandbox",
            element_type_code=102,
            change_type="render",
            target_element_bid="",
            is_navigable=1,
            is_final=1,
            content_text="final",
            payload=final_payload,
            status=1,
        )
        audio_complete_event = LearnGeneratedElement(
            element_bid="",
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            generated_block_bid=generated_block_bid,
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            run_session_bid="run-listen-1",
            run_event_seq=3,
            event_type="audio_complete",
            role="teacher",
            element_index=7,
            element_type="",
            element_type_code=0,
            change_type="",
            target_element_bid="",
            is_navigable=0,
            is_final=1,
            content_text=json.dumps(
                {
                    "position": 0,
                    "audio_url": "https://example.com/final.mp3",
                    "audio_bid": "audio-listen-001",
                    "duration_ms": 900,
                }
            ),
            payload="",
            status=1,
        )
        variable_update_event = LearnGeneratedElement(
            element_bid="",
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            generated_block_bid=generated_block_bid,
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            run_session_bid="run-listen-1",
            run_event_seq=4,
            event_type="variable_update",
            role="teacher",
            element_index=7,
            element_type="",
            element_type_code=0,
            change_type="",
            target_element_bid="",
            is_navigable=0,
            is_final=1,
            content_text=json.dumps(
                {
                    "variable_name": "sys_user_nickname",
                    "variable_value": "Alice",
                }
            ),
            payload="",
            status=1,
        )
        break_event = LearnGeneratedElement(
            element_bid="",
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            generated_block_bid=generated_block_bid,
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            run_session_bid="run-listen-1",
            run_event_seq=5,
            event_type="break",
            role="teacher",
            element_index=7,
            element_type="",
            element_type_code=0,
            change_type="",
            target_element_bid="",
            is_navigable=0,
            is_final=1,
            content_text="",
            payload="",
            status=1,
        )
        db.session.add_all(
            [
                progress,
                partial,
                final,
                audio_complete_event,
                variable_update_event,
                break_event,
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

        assert len(result.elements) == 1
        assert result.events is None
        element = result.elements[0]
        assert element.element_bid == element_bid
        assert element.is_final is True
        assert element.content_text == "final"
        assert element.payload is not None
        assert element.payload.audio is not None
        assert element.payload.audio.audio_url == "https://example.com/final.mp3"

        result_with_events = get_listen_element_record(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
            preview_mode=False,
            include_non_navigable=True,
        )

        assert result_with_events.events is not None
        assert [event.type for event in result_with_events.events] == [
            "element",
            "element",
            "variable_update",
            "break",
        ]
        final_event = result_with_events.events[1]
        assert final_event.run_event_seq == 2
        assert final_event.content.is_final is True
        assert isinstance(result_with_events.events[2].content, VariableUpdateDTO)
        assert result_with_events.events[2].content.variable_name == "sys_user_nickname"


def test_get_listen_element_record_merges_patch_audio_fields_into_target_snapshot(app):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.listen_elements import get_listen_element_record
    from flaskr.service.learn.models import LearnGeneratedElement, LearnProgressRecord
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

    user_bid = "user-listen-patch-audio"
    shifu_bid = "shifu-listen-patch-audio"
    outline_bid = "outline-listen-patch-audio"
    progress_bid = "progress-listen-patch-audio"
    generated_block_bid = "generated-listen-patch-audio"
    element_bid = "element-listen-patch-audio"

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
        original = LearnGeneratedElement(
            element_bid=element_bid,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            generated_block_bid=generated_block_bid,
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            run_session_bid="run-listen-patch-audio",
            run_event_seq=1,
            event_type="element",
            role="teacher",
            element_index=0,
            element_type="text",
            element_type_code=112,
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
            content_text="Narration",
            payload=json.dumps({"audio": None, "previous_visuals": []}),
            status=1,
        )
        patch = LearnGeneratedElement(
            element_bid="element-listen-patch-audio-patch-1",
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            generated_block_bid=generated_block_bid,
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            run_session_bid="run-listen-patch-audio",
            run_event_seq=2,
            event_type="element",
            role="teacher",
            element_index=0,
            element_type="text",
            element_type_code=112,
            change_type="render",
            target_element_bid=element_bid,
            is_renderable=1,
            is_new=0,
            is_marker=0,
            sequence_number=2,
            is_speakable=1,
            audio_url="",
            audio_segments=json.dumps(
                [
                    {
                        "position": 0,
                        "segment_index": 0,
                        "audio_data": "patch-audio-segment",
                        "duration_ms": 180,
                        "is_final": False,
                    }
                ]
            ),
            is_navigable=1,
            is_final=0,
            content_text="Narration",
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

        assert len(result.elements) == 1
        element = result.elements[0]
        assert element.element_bid == element_bid
        assert element.content_text == "Narration"
        assert element.is_speakable is True
        assert element.audio_segments == [
            {
                "position": 0,
                "segment_index": 0,
                "audio_data": "patch-audio-segment",
                "duration_ms": 180,
                "is_final": False,
            }
        ]


def test_get_listen_element_record_returns_all_persisted_elements_across_progress_records(
    app, monkeypatch
):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.learn_dtos import ElementType
    from flaskr.service.learn.listen_elements import get_listen_element_record
    from flaskr.service.learn.models import LearnGeneratedElement, LearnProgressRecord
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

    user_bid = "user-listen-all-persisted-elements"
    shifu_bid = "shifu-listen-all-persisted-elements"
    outline_bid = "outline-listen-all-persisted-elements"
    content_progress_bid = "progress-listen-content"
    interaction_progress_bid = "progress-listen-interaction"

    with app.app_context():
        LearnGeneratedElement.query.delete()
        LearnProgressRecord.query.delete()
        db.session.commit()

        monkeypatch.setattr(
            "flaskr.service.learn.listen_elements.get_learn_record",
            lambda *args, **kwargs: pytest.fail(
                "persisted element query should not fall back to legacy records"
            ),
        )

        content_progress = LearnProgressRecord(
            progress_record_bid=content_progress_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            user_bid=user_bid,
            status=LEARN_STATUS_IN_PROGRESS,
            block_position=0,
        )
        interaction_progress = LearnProgressRecord(
            progress_record_bid=interaction_progress_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            user_bid=user_bid,
            status=LEARN_STATUS_IN_PROGRESS,
            block_position=1,
        )
        content_element = LearnGeneratedElement(
            element_bid="el_persisted_content",
            progress_record_bid=content_progress_bid,
            user_bid=user_bid,
            generated_block_bid="generated-content-1",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            run_session_bid="run-listen-content",
            run_event_seq=1,
            event_type="element",
            role="teacher",
            element_index=0,
            element_type="text",
            element_type_code=112,
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
            content_text="Lesson content",
            payload=json.dumps({"audio": None, "previous_visuals": []}),
            status=1,
        )
        interaction_element = LearnGeneratedElement(
            element_bid="el_only_interaction",
            progress_record_bid=interaction_progress_bid,
            user_bid=user_bid,
            generated_block_bid="generated-interaction-1",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            run_session_bid="run-listen-interaction",
            run_event_seq=1,
            event_type="element",
            role="ui",
            element_index=0,
            element_type="interaction",
            element_type_code=105,
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
            content_text="Choose one",
            payload=json.dumps({"audio": None, "previous_visuals": []}),
            status=1,
        )
        db.session.add_all(
            [
                content_progress,
                interaction_progress,
                content_element,
                interaction_element,
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

        assert len(result.elements) == 2
        assert result.elements[0].element_type == ElementType.TEXT
        assert result.elements[0].content_text == "Lesson content"
        assert result.elements[1].element_type == ElementType.INTERACTION
        assert result.elements[1].content_text == "Choose one"
        assert result.elements[1].is_renderable is False


def test_get_listen_element_record_keeps_block_order_when_run_sessions_reset_indexes(
    app, monkeypatch
):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.learn_dtos import (
        BlockType,
        LikeStatus,
    )
    from flaskr.service.learn.legacy_record_builder import (
        LegacyGeneratedBlockRecord,
        LegacyLearnRecord,
    )
    from flaskr.service.learn.listen_elements import get_listen_element_record
    from flaskr.service.learn.models import LearnGeneratedElement, LearnProgressRecord
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

    user_bid = "user-listen-block-order"
    shifu_bid = "shifu-listen-block-order"
    outline_bid = "outline-listen-block-order"
    progress_bid = "progress-listen-block-order"

    with app.app_context():
        LearnGeneratedElement.query.delete()
        LearnProgressRecord.query.delete()
        db.session.commit()

        monkeypatch.setattr(
            "flaskr.service.learn.listen_elements.build_legacy_record_for_progress",
            lambda *args, **kwargs: LegacyLearnRecord(
                records=[
                    LegacyGeneratedBlockRecord(
                        "generated-block-first",
                        "First block content",
                        LikeStatus.NONE,
                        BlockType.CONTENT,
                        "",
                    ),
                    LegacyGeneratedBlockRecord(
                        "generated-block-second",
                        "Second block content",
                        LikeStatus.NONE,
                        BlockType.CONTENT,
                        "",
                    ),
                ]
            ),
        )
        monkeypatch.setattr(
            "flaskr.service.learn.listen_elements.get_learn_record",
            lambda *args, **kwargs: pytest.fail(
                "persisted element query should not fall back to legacy records"
            ),
        )

        progress = LearnProgressRecord(
            progress_record_bid=progress_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            user_bid=user_bid,
            status=LEARN_STATUS_IN_PROGRESS,
            block_position=0,
        )
        first_element = LearnGeneratedElement(
            element_bid="element-block-first",
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            generated_block_bid="generated-block-first",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            run_session_bid="run-session-old",
            run_event_seq=5,
            event_type="element",
            role="teacher",
            element_index=5,
            element_type="text",
            element_type_code=213,
            change_type="render",
            target_element_bid="",
            is_renderable=1,
            is_new=1,
            is_marker=0,
            sequence_number=5,
            is_speakable=0,
            audio_url="",
            audio_segments="[]",
            is_navigable=1,
            is_final=1,
            content_text="First block content",
            payload=json.dumps({"audio": None, "previous_visuals": []}),
            status=1,
        )
        second_element = LearnGeneratedElement(
            element_bid="element-block-second",
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            generated_block_bid="generated-block-second",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            run_session_bid="run-session-new",
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
            content_text="Second block content",
            payload=json.dumps({"audio": None, "previous_visuals": []}),
            status=1,
        )
        db.session.add_all([progress, first_element, second_element])
        db.session.commit()

        result = get_listen_element_record(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
            preview_mode=False,
        )

        assert [item.generated_block_bid for item in result.elements] == [
            "generated-block-first",
            "generated-block-second",
        ]
        assert [item.content_text for item in result.elements] == [
            "First block content",
            "Second block content",
        ]


def test_get_listen_element_record_ignores_rows_from_inactive_generated_blocks(app):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.learn_dtos import ElementType
    from flaskr.service.learn.listen_elements import get_listen_element_record
    from flaskr.service.learn.models import (
        LearnGeneratedBlock,
        LearnGeneratedElement,
        LearnProgressRecord,
    )
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

    user_bid = "user-listen-ignore-inactive-blocks"
    shifu_bid = "shifu-listen-ignore-inactive-blocks"
    outline_bid = "outline-listen-ignore-inactive-blocks"
    progress_bid = "progress-listen-ignore-inactive-blocks"

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
            block_position=1,
        )
        active_interaction_block = LearnGeneratedBlock(
            generated_block_bid="generated-interaction-active",
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            block_bid="block-interaction-active",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            type=1,
            role=2,
            generated_content="",
            position=0,
            block_content_conf="?[Pick one//pick]",
            status=1,
        )
        stale_interaction_block = LearnGeneratedBlock(
            generated_block_bid="generated-interaction-stale",
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            block_bid="block-interaction-stale",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            type=1,
            role=2,
            generated_content="",
            position=0,
            block_content_conf="?[Pick one//pick]",
            status=0,
        )
        active_content_block = LearnGeneratedBlock(
            generated_block_bid="generated-content-active",
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            block_bid="block-content-active",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            type=0,
            role=2,
            generated_content="Fresh narration",
            position=1,
            block_content_conf="Fresh narration",
            status=1,
        )
        stale_content_block = LearnGeneratedBlock(
            generated_block_bid="generated-content-stale",
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            block_bid="block-content-stale",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            type=0,
            role=2,
            generated_content="Stale narration",
            position=1,
            block_content_conf="Stale narration",
            status=0,
        )
        active_interaction_row = LearnGeneratedElement(
            element_bid="el-interaction-active",
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            generated_block_bid="generated-interaction-active",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            run_session_bid="run-active",
            run_event_seq=1,
            event_type="element",
            role="ui",
            element_index=0,
            element_type=ElementType.INTERACTION.value,
            element_type_code=205,
            change_type="render",
            target_element_bid="",
            is_renderable=0,
            is_new=1,
            is_marker=1,
            sequence_number=1,
            is_speakable=0,
            audio_url="",
            audio_segments="[]",
            is_navigable=0,
            is_final=1,
            content_text="?[Pick one//pick]",
            payload=json.dumps({"audio": None, "previous_visuals": []}),
            status=1,
        )
        stale_interaction_row = LearnGeneratedElement(
            element_bid="el-interaction-stale",
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            generated_block_bid="generated-interaction-stale",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            run_session_bid="run-stale",
            run_event_seq=2,
            event_type="element",
            role="ui",
            element_index=0,
            element_type=ElementType.INTERACTION.value,
            element_type_code=205,
            change_type="render",
            target_element_bid="",
            is_renderable=0,
            is_new=1,
            is_marker=1,
            sequence_number=2,
            is_speakable=0,
            audio_url="",
            audio_segments="[]",
            is_navigable=0,
            is_final=1,
            content_text="?[Pick one//pick]",
            payload=json.dumps({"audio": None, "previous_visuals": []}),
            status=1,
        )
        active_content_row = LearnGeneratedElement(
            element_bid="el-content-active",
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            generated_block_bid="generated-content-active",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            run_session_bid="run-active",
            run_event_seq=3,
            event_type="element",
            role="teacher",
            element_index=1,
            element_type=ElementType.TEXT.value,
            element_type_code=213,
            change_type="render",
            target_element_bid="",
            is_renderable=0,
            is_new=1,
            is_marker=0,
            sequence_number=3,
            is_speakable=1,
            audio_url="",
            audio_segments="[]",
            is_navigable=1,
            is_final=1,
            content_text="Fresh narration",
            payload=json.dumps({"audio": None, "previous_visuals": []}),
            status=1,
        )
        stale_content_row = LearnGeneratedElement(
            element_bid="el-content-stale",
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            generated_block_bid="generated-content-stale",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            run_session_bid="run-stale",
            run_event_seq=4,
            event_type="element",
            role="teacher",
            element_index=1,
            element_type=ElementType.TEXT.value,
            element_type_code=213,
            change_type="render",
            target_element_bid="",
            is_renderable=0,
            is_new=1,
            is_marker=0,
            sequence_number=4,
            is_speakable=1,
            audio_url="",
            audio_segments="[]",
            is_navigable=1,
            is_final=1,
            content_text="Stale narration",
            payload=json.dumps({"audio": None, "previous_visuals": []}),
            status=1,
        )
        db.session.add_all(
            [
                progress,
                active_interaction_block,
                stale_interaction_block,
                active_content_block,
                stale_content_block,
                active_interaction_row,
                stale_interaction_row,
                active_content_row,
                stale_content_row,
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

    assert [item.element_bid for item in result.elements] == [
        "el-interaction-active",
        "el-content-active",
    ]
    assert [item.content_text for item in result.elements] == [
        "?[Pick one//pick]",
        "Fresh narration",
    ]


def test_get_listen_element_record_dedupes_older_progress_records_with_same_block_position(
    app, monkeypatch
):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.listen_elements import get_listen_element_record
    from flaskr.service.learn.models import LearnGeneratedElement, LearnProgressRecord
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

    user_bid = "user-listen-dedupe-progress"
    shifu_bid = "shifu-listen-dedupe-progress"
    outline_bid = "outline-listen-dedupe-progress"
    older_progress_bid = "progress-listen-older"
    latest_progress_bid = "progress-listen-latest"

    with app.app_context():
        LearnGeneratedElement.query.delete()
        LearnProgressRecord.query.delete()
        db.session.commit()

        monkeypatch.setattr(
            "flaskr.service.learn.listen_elements.get_learn_record",
            lambda *args, **kwargs: pytest.fail(
                "persisted element query should not fall back to legacy records"
            ),
        )

        older_progress = LearnProgressRecord(
            progress_record_bid=older_progress_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            user_bid=user_bid,
            status=LEARN_STATUS_IN_PROGRESS,
            block_position=0,
        )
        latest_progress = LearnProgressRecord(
            progress_record_bid=latest_progress_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            user_bid=user_bid,
            status=LEARN_STATUS_IN_PROGRESS,
            block_position=0,
        )
        db.session.add_all([older_progress, latest_progress])
        db.session.flush()

        older_element = LearnGeneratedElement(
            element_bid="el_progress_older",
            progress_record_bid=older_progress_bid,
            user_bid=user_bid,
            generated_block_bid="generated-progress-older",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            run_session_bid="run-progress-older",
            run_event_seq=1,
            event_type="element",
            role="teacher",
            element_index=0,
            element_type="text",
            element_type_code=112,
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
            content_text="Older content should be hidden",
            payload=json.dumps({"audio": None, "previous_visuals": []}),
            status=1,
        )
        latest_element = LearnGeneratedElement(
            element_bid="el_progress_latest",
            progress_record_bid=latest_progress_bid,
            user_bid=user_bid,
            generated_block_bid="generated-progress-latest",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            run_session_bid="run-progress-latest",
            run_event_seq=1,
            event_type="element",
            role="teacher",
            element_index=0,
            element_type="text",
            element_type_code=112,
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
            content_text="Latest content should remain",
            payload=json.dumps({"audio": None, "previous_visuals": []}),
            status=1,
        )
        db.session.add_all([older_element, latest_element])
        db.session.commit()

        result = get_listen_element_record(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
            preview_mode=False,
        )

        assert len(result.elements) == 1
        assert result.elements[0].content_text == "Latest content should remain"
        assert result.elements[0].generated_block_bid == "generated-progress-latest"


def test_get_listen_element_record_includes_persisted_rows_missing_progress_bid(
    app, monkeypatch
):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.const import ROLE_TEACHER
    from flaskr.service.learn.legacy_record_builder import LegacyLearnRecord
    from flaskr.service.learn.listen_elements import get_listen_element_record
    from flaskr.service.learn.models import (
        LearnGeneratedBlock,
        LearnGeneratedElement,
        LearnProgressRecord,
    )
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

    user_bid = "user-listen-missing-progress-bid"
    shifu_bid = "shifu-listen-missing-progress-bid"
    outline_bid = "outline-listen-missing-progress-bid"
    progress_bid = "progress-listen-missing-progress-bid"
    orphan_block_bid = "generated-orphan-persisted"
    attached_block_bid = "generated-attached-persisted"

    with app.app_context():
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
        orphan_block = LearnGeneratedBlock(
            generated_block_bid=orphan_block_bid,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            block_bid="block-orphan-persisted",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            type=0,
            role=ROLE_TEACHER,
            generated_content="legacy should not be needed here",
            position=0,
            block_content_conf="",
            status=1,
        )
        attached_block = LearnGeneratedBlock(
            generated_block_bid=attached_block_bid,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            block_bid="block-attached-persisted",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            type=0,
            role=ROLE_TEACHER,
            generated_content="legacy should not be needed here either",
            position=1,
            block_content_conf="",
            status=1,
        )
        orphan_element = LearnGeneratedElement(
            element_bid="element-orphan-persisted",
            progress_record_bid="",
            user_bid=user_bid,
            generated_block_bid=orphan_block_bid,
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            run_session_bid="run-listen-missing-progress-bid",
            run_event_seq=10,
            event_type="element",
            role="teacher",
            element_index=0,
            element_type="text",
            element_type_code=112,
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
            content_text="Persisted row with blank progress_record_bid",
            payload=json.dumps({"audio": None, "previous_visuals": []}),
            status=1,
        )
        attached_element = LearnGeneratedElement(
            element_bid="element-attached-persisted",
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            generated_block_bid=attached_block_bid,
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            run_session_bid="run-listen-missing-progress-bid",
            run_event_seq=11,
            event_type="element",
            role="teacher",
            element_index=1,
            element_type="text",
            element_type_code=112,
            change_type="render",
            target_element_bid="",
            is_renderable=1,
            is_new=1,
            is_marker=0,
            sequence_number=2,
            is_speakable=0,
            audio_url="",
            audio_segments="[]",
            is_navigable=1,
            is_final=1,
            content_text="Persisted row with linked progress_record_bid",
            payload=json.dumps({"audio": None, "previous_visuals": []}),
            status=1,
        )
        db.session.add_all(
            [
                progress,
                orphan_block,
                attached_block,
                orphan_element,
                attached_element,
            ]
        )
        db.session.commit()

        monkeypatch.setattr(
            "flaskr.service.learn.listen_elements.build_legacy_record_for_progress",
            lambda *args, **kwargs: LegacyLearnRecord(records=[]),
        )
        monkeypatch.setattr(
            "flaskr.service.learn.listen_elements.get_learn_record",
            lambda *args, **kwargs: pytest.fail(
                "persisted rows should satisfy the record query without legacy fallback"
            ),
        )

        result = get_listen_element_record(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
            preview_mode=False,
        )

        assert len(result.elements) == 2
        contents = {item.content_text for item in result.elements}
        assert contents == {
            "Persisted row with blank progress_record_bid",
            "Persisted row with linked progress_record_bid",
        }


def test_listen_run_persists_content_block_before_element_rows(app):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.context_v2 import (
        BlockType as MarkdownFlowBlockType,
        RunScriptContextV2,
        RunScriptInfo,
        RunType,
    )
    from flaskr.service.learn.listen_elements import ListenElementRunAdapter
    from flaskr.service.learn.llmsetting import LLMSettings
    from flaskr.service.learn.models import (
        LearnGeneratedBlock,
        LearnGeneratedElement,
        LearnProgressRecord,
    )
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

    user_bid = "user-listen-run-content-progress"
    shifu_bid = "shifu-listen-run-content-progress"
    outline_bid = "outline-listen-run-content-progress"
    progress_bid = "progress-listen-run-content-progress"

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
        db.session.add(progress)
        db.session.commit()

        ctx = RunScriptContextV2.__new__(RunScriptContextV2)
        ctx.app = app
        ctx._trace_args = {}
        ctx._trace = types.SimpleNamespace(update=lambda **kwargs: None)
        ctx._outline_item_info = types.SimpleNamespace(
            bid=outline_bid,
            shifu_bid=shifu_bid,
            position=0,
            title="Listen Content Progress",
        )
        ctx._shifu_info = types.SimpleNamespace(use_learner_language=False)
        ctx._user_info = types.SimpleNamespace(user_id=user_bid, mobile="", email="")
        ctx._preview_mode = False
        ctx._struct = None
        ctx._is_paid = True
        ctx._run_type = RunType.OUTPUT
        ctx._can_continue = True
        ctx._input_type = "normal"
        ctx._input = None
        ctx._last_position = -1
        ctx._listen = False
        ctx._element_index_cursor = 0
        ctx._current_attend = progress
        ctx._get_current_attend = types.MethodType(
            lambda self, current_outline_bid: progress, ctx
        )
        ctx._get_next_outline_item = types.MethodType(lambda self: [], ctx)
        ctx.get_llm_settings = types.MethodType(
            lambda self, current_outline_bid: LLMSettings(
                model="fake",
                temperature=0.0,
            ),
            ctx,
        )
        ctx.get_system_prompt = types.MethodType(
            lambda self, current_outline_bid: None,
            ctx,
        )
        ctx._get_run_script_info = types.MethodType(
            lambda self, attend, is_ask=False: RunScriptInfo(
                attend=attend,
                outline_bid=attend.outline_item_bid,
                block_position=attend.block_position,
                mdflow="doc",
            ),
            ctx,
        )

        class DummyBlock:
            def __init__(self, block_type, content, index):
                self.block_type = block_type
                self.content = content
                self.index = index

        class DummyLLMResult:
            def __init__(self, content):
                self.content = content

        visual_mode_calls = []

        class FakeMarkdownFlow:
            def __init__(self, *args, **kwargs):
                self.blocks = [
                    DummyBlock(
                        MarkdownFlowBlockType.CONTENT,
                        "Persisted content block",
                        0,
                    )
                ]

            def set_visual_mode(self, visual_mode):
                visual_mode_calls.append(visual_mode)

            def set_output_language(self, *_args, **_kwargs):
                return self

            def get_all_blocks(self):
                return self.blocks

            def get_block(self, block_index):
                return self.blocks[block_index]

            def process(
                self, block_index, mode, variables=None, context=None, user_input=None
            ):
                block = self.blocks[block_index]

                def _gen():
                    yield DummyLLMResult(block.content)

                return _gen()

        adapter = ListenElementRunAdapter(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
        )

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(
                "flaskr.service.learn.context_v2.MarkdownFlow",
                FakeMarkdownFlow,
            )
            monkeypatch.setattr(
                "flaskr.service.learn.context_v2.get_user_profiles",
                lambda *args, **kwargs: {},
            )
            monkeypatch.setattr(
                "flaskr.service.learn.context_v2.get_profile_item_definition_list",
                lambda *args, **kwargs: [],
            )
            monkeypatch.setattr(
                RunScriptContextV2,
                "_should_stream_tts",
                lambda self: False,
            )
            streamed = list(adapter.process(ctx.run_inner(app)))

        rows = (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.run_session_bid == adapter.run_session_bid,
                LearnGeneratedElement.event_type == "element",
                LearnGeneratedElement.deleted == 0,
                LearnGeneratedElement.status == 1,
            )
            .order_by(
                LearnGeneratedElement.run_event_seq.asc(),
                LearnGeneratedElement.id.asc(),
            )
            .all()
        )

    assert [item.type for item in streamed] == ["element", "done"]
    assert visual_mode_calls
    assert all(visual_mode is True for visual_mode in visual_mode_calls)
    assert rows
    assert {row.progress_record_bid for row in rows} == {progress_bid}
    assert {row.content_text for row in rows} == {"Persisted content block"}


def test_run_inner_emits_next_text_before_finalizing_previous_tts(app):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.context_v2 import (
        LLMSettings,
        RunScriptContextV2,
        RunScriptInfo,
        RunType,
        BlockType as MarkdownFlowBlockType,
    )
    from flaskr.service.learn.learn_dtos import (
        AudioCompleteDTO,
        GeneratedType,
        RunMarkdownFlowDTO,
    )
    from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

    user_bid = "user-stream-text-before-tts"
    shifu_bid = "shifu-stream-text-before-tts"
    outline_bid = "outline-stream-text-before-tts"
    progress_bid = "progress-stream-text-before-tts"

    with app.app_context():
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
        db.session.add(progress)
        db.session.commit()

        ctx = RunScriptContextV2.__new__(RunScriptContextV2)
        ctx.app = app
        ctx._trace_args = {}
        ctx._trace = types.SimpleNamespace(update=lambda **kwargs: None)
        ctx._trace_root_span = None
        ctx._outline_item_info = types.SimpleNamespace(
            bid=outline_bid,
            shifu_bid=shifu_bid,
            position=0,
            title="Stream Text Before TTS",
        )
        ctx._shifu_info = types.SimpleNamespace(use_learner_language=False)
        ctx._user_info = types.SimpleNamespace(user_id=user_bid, mobile="", email="")
        ctx._preview_mode = False
        ctx._struct = None
        ctx._is_paid = True
        ctx._run_type = RunType.OUTPUT
        ctx._can_continue = True
        ctx._input_type = "normal"
        ctx._input = None
        ctx._last_position = -1
        ctx._listen = True
        ctx._element_index_cursor = 0
        ctx._current_attend = progress
        ctx._get_current_attend = types.MethodType(
            lambda self, current_outline_bid: progress, ctx
        )
        ctx._get_next_outline_item = types.MethodType(lambda self: [], ctx)
        ctx.get_llm_settings = types.MethodType(
            lambda self, current_outline_bid: LLMSettings(
                model="fake",
                temperature=0.0,
            ),
            ctx,
        )
        ctx.get_system_prompt = types.MethodType(
            lambda self, current_outline_bid: None,
            ctx,
        )
        ctx._get_run_script_info = types.MethodType(
            lambda self, attend, is_ask=False: RunScriptInfo(
                attend=attend,
                outline_bid=attend.outline_item_bid,
                block_position=attend.block_position,
                mdflow="doc",
            ),
            ctx,
        )
        ctx._should_stream_tts = types.MethodType(lambda self: True, ctx)

        class DummyBlock:
            def __init__(self, block_type, content, index):
                self.block_type = block_type
                self.content = content
                self.index = index

        class DummyFormattedElement:
            def __init__(self, content, type_, number):
                self.content = content
                self.type = type_
                self.number = number

        class DummyLLMResult:
            def __init__(self, content, stream_number):
                self.content = ""
                self.formatted_elements = [
                    DummyFormattedElement(content, "text", stream_number)
                ]

        class FakeMarkdownFlow:
            def __init__(self, *args, **kwargs):
                self.blocks = [
                    DummyBlock(
                        MarkdownFlowBlockType.CONTENT,
                        "First text.Second text.",
                        0,
                    )
                ]

            def set_visual_mode(self, *_args, **_kwargs):
                pass

            def set_output_language(self, *_args, **_kwargs):
                return self

            def get_all_blocks(self):
                return self.blocks

            def get_block(self, block_index):
                return self.blocks[block_index]

            def process(
                self, block_index, mode, variables=None, context=None, user_input=None
            ):
                def _gen():
                    yield DummyLLMResult("First text.", 0)
                    yield DummyLLMResult("Second text.", 1)

                return _gen()

        class FakeTtsProcessor:
            next_element_index = 0

            def __init__(self, generated_block_bid, position):
                self.generated_block_bid = generated_block_bid
                self.position = position

            def process_chunk(self, chunk):
                if False:
                    yield chunk

            def finalize(self, *, commit=True):
                yield RunMarkdownFlowDTO(
                    outline_bid=outline_bid,
                    generated_block_bid=self.generated_block_bid,
                    type=GeneratedType.AUDIO_COMPLETE,
                    content=AudioCompleteDTO(
                        audio_url=f"https://example.com/audio-{self.position}.mp3",
                        audio_bid=f"audio-{self.position}",
                        duration_ms=100,
                        position=self.position,
                        stream_element_number=self.position,
                        stream_element_type="text",
                    ),
                )

        def fake_create_tts_processor(
            self,
            generated_block_bid,
            *,
            shifu_bid="",
            position=0,
            stream_element_number=None,
            stream_element_type=None,
        ):
            return FakeTtsProcessor(generated_block_bid, position)

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(
                "flaskr.service.learn.context_v2.MarkdownFlow",
                FakeMarkdownFlow,
            )
            monkeypatch.setattr(
                "flaskr.service.learn.context_v2.get_user_profiles",
                lambda *args, **kwargs: {},
            )
            monkeypatch.setattr(
                "flaskr.service.learn.context_v2.get_profile_item_definition_list",
                lambda *args, **kwargs: [],
            )
            monkeypatch.setattr(
                RunScriptContextV2,
                "_try_create_tts_processor",
                fake_create_tts_processor,
            )
            events = list(ctx.run_inner(app))

    assert [event.type for event in events[:3]] == [
        GeneratedType.CONTENT,
        GeneratedType.CONTENT,
        GeneratedType.AUDIO_COMPLETE,
    ]
    assert events[0].content == "First text."
    assert events[1].content == "Second text."


def test_listen_run_persists_exception_gate_block_before_element_rows(app):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.context_v2 import RunScriptContextV2
    from flaskr.service.learn.exceptions import PaidException
    from flaskr.service.learn.listen_elements import ListenElementRunAdapter
    from flaskr.service.learn.models import (
        LearnGeneratedBlock,
        LearnGeneratedElement,
        LearnProgressRecord,
    )
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

    user_bid = "user-listen-run-paid-gate"
    shifu_bid = "shifu-listen-run-paid-gate"
    outline_bid = "outline-listen-run-paid-gate"
    progress_bid = "progress-listen-run-paid-gate"

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
            block_position=3,
        )
        db.session.add(progress)
        db.session.commit()

        ctx = RunScriptContextV2.__new__(RunScriptContextV2)
        ctx.app = app
        ctx._can_continue = True
        ctx._user_info = types.SimpleNamespace(user_id=user_bid, mobile="", email="")
        ctx._outline_item_info = types.SimpleNamespace(
            bid=outline_bid,
            shifu_bid=shifu_bid,
        )
        ctx._current_attend = progress
        ctx._emit_feedback_before_exception_gate = types.MethodType(
            lambda self: iter(()),
            ctx,
        )

        def _raise_paid(self, current_app):
            raise PaidException()
            yield  # pragma: no cover

        ctx.run_inner = types.MethodType(_raise_paid, ctx)

        adapter = ListenElementRunAdapter(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
        )
        streamed = list(adapter.process(ctx.run(app)))

        rows = (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.run_session_bid == adapter.run_session_bid,
                LearnGeneratedElement.event_type == "element",
                LearnGeneratedElement.deleted == 0,
                LearnGeneratedElement.status == 1,
            )
            .order_by(
                LearnGeneratedElement.run_event_seq.asc(),
                LearnGeneratedElement.id.asc(),
            )
            .all()
        )
        generated_blocks = (
            LearnGeneratedBlock.query.filter(
                LearnGeneratedBlock.progress_record_bid == progress_bid,
                LearnGeneratedBlock.outline_item_bid == outline_bid,
                LearnGeneratedBlock.deleted == 0,
                LearnGeneratedBlock.status == 1,
            )
            .order_by(LearnGeneratedBlock.id.asc())
            .all()
        )

    assert [item.type for item in streamed] == ["element"]
    assert rows
    assert {row.progress_record_bid for row in rows} == {progress_bid}
    assert len(generated_blocks) == 1
    assert rows[0].generated_block_bid == generated_blocks[0].generated_block_bid


def test_get_record_api_returns_element_payload_by_default(app):
    _require_app(app)

    from flask import request

    from flaskr.dao import db
    from flaskr.service.learn.models import LearnGeneratedElement, LearnProgressRecord
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

    user_bid = "user-record-api-elements"
    shifu_bid = "shifu-record-api-elements"
    outline_bid = "outline-record-api-elements"
    progress_bid = "progress-record-api-elements"
    generated_block_bid = "generated-record-api-elements"
    element_bid = "element-record-api-001"

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
        final = LearnGeneratedElement(
            element_bid=element_bid,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            generated_block_bid=generated_block_bid,
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            run_session_bid="run-record-api-1",
            run_event_seq=2,
            event_type="element",
            role="teacher",
            element_index=3,
            element_type="sandbox",
            element_type_code=102,
            change_type="render",
            target_element_bid="",
            is_navigable=1,
            is_final=1,
            content_text="final",
            payload=json.dumps({"audio": None, "previous_visuals": []}),
            status=1,
        )
        db.session.add_all([progress, final])
        db.session.commit()

    with app.test_request_context(
        f"/api/learn/shifu/{shifu_bid}/records/{outline_bid}?include_non_navigable=true"
    ):
        request.user = types.SimpleNamespace(mobile="", user_id=user_bid)
        response = app.view_functions["get_record_api"](shifu_bid, outline_bid)

    payload = json.loads(response)

    assert payload["code"] == 0
    assert "records" not in payload["data"]
    assert "slides" not in payload["data"]
    assert "interaction" not in payload["data"]
    assert len(payload["data"]["elements"]) == 1
    assert payload["data"]["elements"][0]["element_bid"] == element_bid
    assert payload["data"]["events"][0]["type"] == "element"


def test_listen_element_adapter_retires_fallback_once_visual_element_arrives(app):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.const import ROLE_TEACHER
    from flaskr.service.learn.learn_dtos import (
        AudioCompleteDTO,
        GeneratedType,
        RunMarkdownFlowDTO,
    )
    from flaskr.service.learn.listen_elements import ListenElementRunAdapter
    from flaskr.service.learn.models import LearnGeneratedBlock, LearnGeneratedElement
    from flaskr.service.tts.pipeline import build_av_segmentation_contract

    user_bid = "user-listen-adapter"
    shifu_bid = "shifu-listen-adapter"
    outline_bid = "outline-listen-adapter"
    progress_bid = "progress-listen-adapter"
    generated_block_bid = "generated-listen-adapter"
    raw_content = "![img](https://example.com/visual.png)"
    av_contract = build_av_segmentation_contract(raw_content, generated_block_bid)

    with app.app_context():
        LearnGeneratedBlock.query.delete()
        db.session.commit()

        block = LearnGeneratedBlock(
            generated_block_bid=generated_block_bid,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            block_bid="block-listen-adapter",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            type=0,
            role=ROLE_TEACHER,
            generated_content=raw_content,
            position=0,
            block_content_conf="",
            status=1,
        )
        db.session.add(block)
        db.session.commit()

        adapter = ListenElementRunAdapter(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
        )

        events = [
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content=raw_content,
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_COMPLETE,
                content=AudioCompleteDTO(
                    audio_url="https://example.com/audio.mp3",
                    audio_bid="audio-listen-adapter",
                    duration_ms=1000,
                    position=0,
                    av_contract=av_contract,
                ),
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.BREAK,
                content="",
            ),
        ]

        streamed = list(adapter.process(events))
        assert [item.type for item in streamed] == [
            "element",
            "element",
            "element",  # retire notification (is_new=false, is_renderable=false)
            "element",  # final visual element with correct type
            "done",
        ]

        audio_patch_evt = streamed[1]
        assert audio_patch_evt.content.element_bid == streamed[0].content.element_bid
        assert audio_patch_evt.content.target_element_bid in ("", None)
        assert audio_patch_evt.content.audio_url == "https://example.com/audio.mp3"
        assert audio_patch_evt.content.is_final is True

        # Verify the retire notification element
        retire_evt = streamed[2]
        assert retire_evt.content.is_new is True
        assert retire_evt.content.is_renderable is False
        assert retire_evt.content.is_final is True
        fallback_element_bid = streamed[0].content.element_bid

        active_rows = LearnGeneratedElement.query.filter(
            LearnGeneratedElement.run_session_bid == adapter.run_session_bid,
            LearnGeneratedElement.generated_block_bid == generated_block_bid,
            LearnGeneratedElement.deleted == 0,
            LearnGeneratedElement.status == 1,
        ).all()
        active_element_bids = {
            row.element_bid for row in active_rows if row.event_type == "element"
        }

        visual_element_bid = next(
            row.element_bid
            for row in active_rows
            if row.event_type == "element" and row.element_bid != fallback_element_bid
        )
        assert visual_element_bid
        assert fallback_element_bid not in active_element_bids


def test_listen_element_adapter_retires_matching_active_rows_by_primary_key(app):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.learn_dtos import (
        ElementChangeType,
        ElementDTO,
        ElementType,
    )
    from flaskr.service.learn.listen_elements import ListenElementRunAdapter
    from flaskr.service.learn.models import LearnGeneratedElement

    user_bid = "user-listen-retire-active-rows"
    shifu_bid = "shifu-listen-retire-active-rows"
    outline_bid = "outline-listen-retire-active-rows"
    generated_block_bid = "generated-listen-retire-active-rows"
    base_element_bid = "element-base"

    with app.app_context():
        LearnGeneratedElement.query.delete()
        db.session.commit()

        adapter = ListenElementRunAdapter(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
        )

        rows = [
            LearnGeneratedElement(
                element_bid=base_element_bid,
                progress_record_bid="",
                user_bid=user_bid,
                generated_block_bid=generated_block_bid,
                outline_item_bid=outline_bid,
                shifu_bid=shifu_bid,
                run_session_bid=adapter.run_session_bid,
                run_event_seq=1,
                event_type="element",
                role="teacher",
                element_index=0,
                element_type=ElementType.TEXT.value,
                element_type_code=0,
                change_type=ElementChangeType.RENDER.value,
                target_element_bid="",
                is_navigable=1,
                is_final=0,
                content_text="base",
                payload=json.dumps({"audio": None, "previous_visuals": []}),
                status=1,
            ),
            LearnGeneratedElement(
                element_bid="legacy-patch",
                progress_record_bid="",
                user_bid=user_bid,
                generated_block_bid=generated_block_bid,
                outline_item_bid=outline_bid,
                shifu_bid=shifu_bid,
                run_session_bid=adapter.run_session_bid,
                run_event_seq=2,
                event_type="element",
                role="teacher",
                element_index=0,
                element_type=ElementType.TEXT.value,
                element_type_code=0,
                change_type=ElementChangeType.RENDER.value,
                target_element_bid=base_element_bid,
                is_navigable=1,
                is_final=0,
                content_text="legacy patch",
                payload=json.dumps({"audio": None, "previous_visuals": []}),
                status=1,
            ),
            LearnGeneratedElement(
                element_bid="other-element",
                progress_record_bid="",
                user_bid=user_bid,
                generated_block_bid=generated_block_bid,
                outline_item_bid=outline_bid,
                shifu_bid=shifu_bid,
                run_session_bid=adapter.run_session_bid,
                run_event_seq=3,
                event_type="element",
                role="teacher",
                element_index=1,
                element_type=ElementType.TEXT.value,
                element_type_code=0,
                change_type=ElementChangeType.RENDER.value,
                target_element_bid="",
                is_navigable=1,
                is_final=0,
                content_text="other",
                payload=json.dumps({"audio": None, "previous_visuals": []}),
                status=1,
            ),
        ]
        db.session.add_all(rows)
        db.session.commit()

        adapter._persist_element(
            ElementDTO(
                event_type="element",
                element_bid=base_element_bid,
                generated_block_bid=generated_block_bid,
                element_index=0,
                role="teacher",
                element_type=ElementType.TEXT,
                element_type_code=0,
                change_type=ElementChangeType.RENDER,
                is_renderable=True,
                is_new=False,
                is_marker=False,
                is_navigable=1,
                is_final=False,
                content="updated",
                payload=None,
            )
        )

        persisted_rows = (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.run_session_bid == adapter.run_session_bid,
                LearnGeneratedElement.generated_block_bid == generated_block_bid,
                LearnGeneratedElement.deleted == 0,
            )
            .order_by(LearnGeneratedElement.id.asc())
            .all()
        )

    assert len(persisted_rows) == 4

    status_by_identity = {
        (row.element_bid, row.target_element_bid or ""): row.status
        for row in persisted_rows
    }
    assert status_by_identity[(base_element_bid, "")] == 0
    assert status_by_identity[("legacy-patch", base_element_bid)] == 0
    assert status_by_identity[("other-element", "")] == 1
    assert status_by_identity[(base_element_bid, base_element_bid)] == 1

    latest_row = persisted_rows[-1]
    assert latest_row.element_bid == base_element_bid
    assert latest_row.target_element_bid == base_element_bid
    assert latest_row.content_text == "updated"


def test_listen_adapter_finalizes_visuals_and_text_as_independent_elements(app):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.const import ROLE_TEACHER
    from flaskr.service.learn.learn_dtos import (
        AudioCompleteDTO,
        AudioSegmentDTO,
        ElementType,
        GeneratedType,
        RunMarkdownFlowDTO,
    )
    from flaskr.service.learn.listen_elements import ListenElementRunAdapter
    from flaskr.service.learn.models import LearnGeneratedBlock, LearnGeneratedElement
    from flaskr.service.tts.pipeline import build_av_segmentation_contract

    user_bid = "user-listen-final-text"
    shifu_bid = "shifu-listen-final-text"
    outline_bid = "outline-listen-final-text"
    progress_bid = "progress-listen-final-text"
    generated_block_bid = "generated-listen-final-text"
    raw_content = (
        "<svg><text>Chart</text></svg>\n\n"
        "After svg.\n\n"
        "<div>Question card</div>\n\n"
        "After html."
    )
    av_contract = build_av_segmentation_contract(raw_content, generated_block_bid)

    with app.app_context():
        LearnGeneratedBlock.query.delete()
        db.session.commit()

        block = LearnGeneratedBlock(
            generated_block_bid=generated_block_bid,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            block_bid="block-listen-final-text",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            type=0,
            role=ROLE_TEACHER,
            generated_content=raw_content,
            position=0,
            block_content_conf="",
            status=1,
        )
        db.session.add(block)
        db.session.commit()

        adapter = ListenElementRunAdapter(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
        )

        events = [
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content=raw_content,
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_SEGMENT,
                content=AudioSegmentDTO(
                    position=0,
                    segment_index=0,
                    audio_data="segment-0",
                    duration_ms=350,
                    is_final=False,
                    av_contract=av_contract,
                ),
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_COMPLETE,
                content=AudioCompleteDTO(
                    audio_url="https://example.com/audio-0.mp3",
                    audio_bid="audio-final-text-0",
                    duration_ms=700,
                    position=0,
                    av_contract=av_contract,
                ),
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_SEGMENT,
                content=AudioSegmentDTO(
                    position=1,
                    segment_index=0,
                    audio_data="segment-1",
                    duration_ms=400,
                    is_final=True,
                    av_contract=av_contract,
                ),
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_COMPLETE,
                content=AudioCompleteDTO(
                    audio_url="https://example.com/audio-1.mp3",
                    audio_bid="audio-final-text-1",
                    duration_ms=800,
                    position=1,
                    av_contract=av_contract,
                ),
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.BREAK,
                content="",
            ),
        ]

        streamed = list(adapter.process(events))
        final_elements = [
            item.content
            for item in streamed
            if item.type == "element" and item.content.is_final
        ]
        assert [item.element_type.value for item in final_elements[-4:]] == [
            "svg",
            "text",
            "html",
            "text",
        ]
        assert [item.is_new for item in final_elements[-4:]] == [True, True, True, True]
        assert final_elements[-3].target_element_bid in ("", None)
        assert final_elements[-1].target_element_bid in ("", None)
        assert final_elements[-4].is_marker is True
        assert final_elements[-4].is_renderable is True
        assert final_elements[-4].content_text == ""
        assert final_elements[-3].is_marker is False
        assert final_elements[-3].is_renderable is False
        assert final_elements[-3].is_speakable is True
        assert final_elements[-3].content_text == "After svg."
        assert final_elements[-3].audio_url == "https://example.com/audio-0.mp3"
        assert final_elements[-3].audio_segments == [
            {
                "position": 0,
                "segment_index": 0,
                "audio_data": "segment-0",
                "duration_ms": 350,
                "is_final": True,
            }
        ]
        assert final_elements[-2].is_marker is True
        assert final_elements[-2].is_renderable is True
        assert final_elements[-2].content_text == ""
        assert final_elements[-1].is_marker is False
        assert final_elements[-1].is_renderable is False
        assert final_elements[-1].is_speakable is True
        assert final_elements[-1].content_text == "After html."
        assert final_elements[-1].audio_url == "https://example.com/audio-1.mp3"
        assert final_elements[-1].audio_segments == [
            {
                "position": 1,
                "segment_index": 0,
                "audio_data": "segment-1",
                "duration_ms": 400,
                "is_final": True,
            }
        ]
        assert final_elements[-4].payload is not None
        assert final_elements[-4].payload.previous_visuals[0].visual_type == "svg"
        assert final_elements[-3].payload is not None
        assert final_elements[-3].payload.previous_visuals == []

        persisted_rows = (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.run_session_bid == adapter.run_session_bid,
                LearnGeneratedElement.event_type == "element",
                LearnGeneratedElement.deleted == 0,
                LearnGeneratedElement.status == 1,
            )
            .order_by(
                LearnGeneratedElement.element_index.asc(),
                LearnGeneratedElement.run_event_seq.asc(),
            )
            .all()
        )
        assert [row.element_type for row in persisted_rows] == [
            ElementType.SVG.value,
            ElementType.TEXT.value,
            ElementType.HTML.value,
            ElementType.TEXT.value,
        ]
        assert persisted_rows[0].is_marker == 1
        assert persisted_rows[0].is_renderable == 1
        assert persisted_rows[0].content_text == ""
        assert persisted_rows[1].is_marker == 0
        assert persisted_rows[1].is_renderable == 0
        assert persisted_rows[1].is_speakable == 1
        assert persisted_rows[1].content_text == "After svg."
        assert persisted_rows[1].audio_url == "https://example.com/audio-0.mp3"
        assert json.loads(persisted_rows[1].audio_segments) == [
            {
                "position": 0,
                "segment_index": 0,
                "audio_data": "",
                "duration_ms": 350,
                "is_final": True,
            }
        ]
        assert persisted_rows[2].is_marker == 1
        assert persisted_rows[2].is_renderable == 1
        assert persisted_rows[2].content_text == ""
        assert persisted_rows[3].is_marker == 0
        assert persisted_rows[3].is_renderable == 0
        assert persisted_rows[3].is_speakable == 1
        assert persisted_rows[3].content_text == "After html."
        assert persisted_rows[3].audio_url == "https://example.com/audio-1.mp3"
        assert json.loads(persisted_rows[3].audio_segments) == [
            {
                "position": 1,
                "segment_index": 0,
                "audio_data": "",
                "duration_ms": 400,
                "is_final": True,
            }
        ]
        assert (
            json.loads(persisted_rows[0].payload)["previous_visuals"][0]["visual_type"]
            == "svg"
        )
        assert json.loads(persisted_rows[1].payload)["previous_visuals"] == []


def test_listen_adapter_finalizes_fallback_text_with_embedded_audio(app):
    _require_app(app)

    from flaskr.service.learn.learn_dtos import (
        AudioCompleteDTO,
        AudioSegmentDTO,
        ElementType,
        GeneratedType,
        RunMarkdownFlowDTO,
    )
    from flaskr.service.learn.listen_elements import ListenElementRunAdapter
    from flaskr.service.learn.models import LearnGeneratedElement

    user_bid = "user-listen-fallback-audio"
    shifu_bid = "shifu-listen-fallback-audio"
    outline_bid = "outline-listen-fallback-audio"
    generated_block_bid = "generated-listen-fallback-audio"

    with app.app_context():
        adapter = ListenElementRunAdapter(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
        )

        events = [
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content="Fallback narration.",
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_SEGMENT,
                content=AudioSegmentDTO(
                    position=0,
                    segment_index=0,
                    audio_data="fallback-segment",
                    duration_ms=280,
                    is_final=True,
                ),
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_COMPLETE,
                content=AudioCompleteDTO(
                    audio_url="https://example.com/fallback-audio.mp3",
                    audio_bid="audio-fallback-0",
                    duration_ms=280,
                    position=0,
                ),
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.BREAK,
                content="",
            ),
        ]

        streamed = list(adapter.process(events))
        final_elements = [
            item.content
            for item in streamed
            if item.type == "element" and item.content.is_final and item.content.is_new
        ]
        assert len(final_elements) == 1
        assert final_elements[0].content_text == "Fallback narration."

        persisted_rows = (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.run_session_bid == adapter.run_session_bid,
                LearnGeneratedElement.event_type == "element",
                LearnGeneratedElement.deleted == 0,
                LearnGeneratedElement.status == 1,
            )
            .order_by(
                LearnGeneratedElement.run_event_seq.desc(),
                LearnGeneratedElement.id.desc(),
            )
            .all()
        )
        assert persisted_rows
        final_row = persisted_rows[0]
        assert final_row.element_type == ElementType.TEXT.value
        assert final_row.is_renderable == 0
        assert final_row.content_text == "Fallback narration."
        assert final_row.is_speakable == 1
        assert final_row.audio_url == "https://example.com/fallback-audio.mp3"
        assert json.loads(final_row.audio_segments) == [
            {
                "position": 0,
                "segment_index": 0,
                "audio_data": "",
                "duration_ms": 280,
                "is_final": True,
            }
        ]
        payload = json.loads(final_row.payload)
        assert payload["audio"]["audio_bid"] == "audio-fallback-0"
        assert payload["previous_visuals"] == []


def test_listen_adapter_handles_mdflow_stream_metadata_without_av_contract(app):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.const import ROLE_TEACHER
    from flaskr.service.learn.learn_dtos import (
        AudioCompleteDTO,
        AudioSegmentDTO,
        ElementType,
        GeneratedType,
        RunMarkdownFlowDTO,
    )
    from flaskr.service.learn.listen_elements import (
        ListenElementRunAdapter,
        get_listen_element_record,
    )
    from flaskr.service.learn.models import (
        LearnGeneratedBlock,
        LearnGeneratedElement,
        LearnProgressRecord,
    )
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

    user_bid = "user-listen-mdflow-stream"
    shifu_bid = "shifu-listen-mdflow-stream"
    outline_bid = "outline-listen-mdflow-stream"
    progress_bid = "progress-listen-mdflow-stream"
    generated_block_bid = "generated-listen-mdflow-stream"

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
        block = LearnGeneratedBlock(
            generated_block_bid=generated_block_bid,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            block_bid="block-listen-mdflow-stream",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            type=0,
            role=ROLE_TEACHER,
            generated_content="![img](https://example.com/visual.png)\ncaption line\n",
            position=0,
            block_content_conf="",
            status=1,
        )
        db.session.add_all([progress, block])
        db.session.commit()

        adapter = ListenElementRunAdapter(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
        )

        first_content = RunMarkdownFlowDTO(
            outline_bid=outline_bid,
            generated_block_bid=generated_block_bid,
            type=GeneratedType.CONTENT,
            content="![img](https://example.com/visual.png)\n",
        ).set_mdflow_stream_parts(
            [("![img](https://example.com/visual.png)\n", "img", 0)]
        )
        second_content = RunMarkdownFlowDTO(
            outline_bid=outline_bid,
            generated_block_bid=generated_block_bid,
            type=GeneratedType.CONTENT,
            content="caption line\n",
        ).set_mdflow_stream_parts([("caption line\n", "img", 0)])

        events = [
            first_content,
            second_content,
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_SEGMENT,
                content=AudioSegmentDTO(
                    position=0,
                    segment_index=0,
                    audio_data="stream-segment-0",
                    duration_ms=240,
                    is_final=False,
                ),
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_SEGMENT,
                content=AudioSegmentDTO(
                    position=0,
                    segment_index=1,
                    audio_data="stream-segment-1",
                    duration_ms=260,
                    is_final=False,
                ),
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_COMPLETE,
                content=AudioCompleteDTO(
                    audio_url="https://example.com/stream-audio.mp3",
                    audio_bid="audio-stream-1",
                    duration_ms=900,
                    position=0,
                ),
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.BREAK,
                content="",
            ),
        ]

        streamed = list(adapter.process(events))
        assert [item.type for item in streamed] == [
            "element",
            "element",
            "element",
            "done",
        ]

        first_element = streamed[0].content
        patch_element = streamed[1].content
        final_audio_segment_patch = streamed[2].content
        assert first_element.is_new is True
        assert first_element.element_type == ElementType.IMG
        assert "_" not in first_element.element_bid
        assert patch_element.is_new is True
        assert len(patch_element.element_bid) <= 64
        assert patch_element.element_bid == first_element.element_bid
        assert "_" not in patch_element.element_bid
        assert patch_element.target_element_bid in ("", None)
        assert final_audio_segment_patch.is_new is True
        assert final_audio_segment_patch.element_bid == first_element.element_bid
        assert final_audio_segment_patch.target_element_bid in ("", None)
        assert final_audio_segment_patch.audio_url == ""
        assert final_audio_segment_patch.is_final is True
        assert final_audio_segment_patch.audio_segments == []
        result = get_listen_element_record(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
            preview_mode=False,
        )

        assert len(result.elements) == 1
        element = result.elements[0]
        assert element.element_bid == first_element.element_bid
        assert element.element_type == ElementType.IMG
        assert element.is_new is True
        assert element.is_final is True
        assert element.is_marker is True
        assert element.audio_url == ""
        assert element.audio_segments == []
        assert element.content_text.endswith("caption line\n")
        assert element.payload is not None
        assert len(element.payload.previous_visuals) == 1
        assert element.payload.previous_visuals[0].visual_type == "img"
        assert element.payload.previous_visuals[0].content == ""

        result_with_events = get_listen_element_record(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
            preview_mode=False,
            include_non_navigable=True,
        )

        assert result_with_events.events is not None
        replay_event_types = [item.type for item in result_with_events.events]
        assert "audio_segment" not in replay_event_types
        assert replay_event_types.count("element") >= 1
        assert "audio_complete" not in replay_event_types
        assert "break" in replay_event_types
        replay_audio_patches = [
            item.content
            for item in result_with_events.events
            if item.type == "element"
            and item.content.audio_segments
            and not item.content.audio_url
            and not item.content.is_final
        ]
        assert replay_audio_patches == []

        persisted_rows = (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.generated_block_bid == generated_block_bid,
                LearnGeneratedElement.event_type == "element",
                LearnGeneratedElement.deleted == 0,
                LearnGeneratedElement.status == 1,
            )
            .order_by(LearnGeneratedElement.id.asc())
            .all()
        )
        persisted_segments = [
            json.loads(row.audio_segments or "[]")
            for row in persisted_rows
            if row.audio_segments and row.audio_segments != "[]"
        ]
        assert persisted_segments == []


def test_listen_adapter_marks_non_text_after_text_as_new_in_stream(app):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.const import ROLE_TEACHER
    from flaskr.service.learn.learn_dtos import (
        ElementType,
        GeneratedType,
        RunMarkdownFlowDTO,
    )
    from flaskr.service.learn.listen_elements import ListenElementRunAdapter
    from flaskr.service.learn.models import (
        LearnGeneratedBlock,
        LearnGeneratedElement,
        LearnProgressRecord,
    )
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

    user_bid = "user-listen-is-new-rule"
    shifu_bid = "shifu-listen-is-new-rule"
    outline_bid = "outline-listen-is-new-rule"
    progress_bid = "progress-listen-is-new-rule"
    generated_block_bid = "generated-listen-is-new-rule"

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
        block = LearnGeneratedBlock(
            generated_block_bid=generated_block_bid,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            block_bid="block-listen-is-new-rule",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            type=0,
            role=ROLE_TEACHER,
            generated_content="Intro<div>Card</div>Tail",
            position=0,
            block_content_conf="",
            status=1,
        )
        db.session.add_all([progress, block])
        db.session.commit()

        adapter = ListenElementRunAdapter(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
        )

        events = [
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content="Intro",
            ).set_mdflow_stream_parts([("Intro", "text", 0)]),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content=" more",
            ).set_mdflow_stream_parts([(" more", "text", 0)]),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content="<div>",
            ).set_mdflow_stream_parts([("<div>", "html", 1)]),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content="Card</div>",
            ).set_mdflow_stream_parts([("Card</div>", "html", 1)]),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content="Tail",
            ).set_mdflow_stream_parts([("Tail", "text", 2)]),
        ]

        streamed = list(adapter.process(events))
        assert [item.type for item in streamed] == [
            "element",
            "element",
            "done",
            "element",
            "element",
            "done",
            "element",
        ]
        element_events = [item.content for item in streamed if item.type == "element"]

        assert [item.element_type for item in element_events] == [
            ElementType.TEXT,
            ElementType.TEXT,
            ElementType.HTML,
            ElementType.HTML,
            ElementType.TEXT,
        ]
        assert [item.is_new for item in element_events] == [
            True,
            True,
            True,
            True,
            True,
        ]
        assert element_events[1].target_element_bid in ("", None)
        assert element_events[2].target_element_bid in ("", None)
        assert element_events[3].target_element_bid in ("", None)
        assert element_events[4].target_element_bid in ("", None)


def test_listen_adapter_keeps_html_stream_as_single_element_on_break(app):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.const import ROLE_TEACHER
    from flaskr.service.learn.learn_dtos import (
        ElementType,
        GeneratedType,
        RunMarkdownFlowDTO,
    )
    from flaskr.service.learn.listen_elements import (
        ListenElementRunAdapter,
        get_listen_element_record,
    )
    from flaskr.service.learn.models import (
        LearnGeneratedBlock,
        LearnGeneratedElement,
        LearnProgressRecord,
    )
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

    user_bid = "user-listen-html-single-on-break"
    shifu_bid = "shifu-listen-html-single-on-break"
    outline_bid = "outline-listen-html-single-on-break"
    progress_bid = "progress-listen-html-single-on-break"
    generated_block_bid = "generated-listen-html-single-on-break"

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
        block = LearnGeneratedBlock(
            generated_block_bid=generated_block_bid,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            block_bid="block-listen-html-single-on-break",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            type=0,
            role=ROLE_TEACHER,
            generated_content="",
            position=0,
            block_content_conf="",
            status=1,
        )
        db.session.add_all([progress, block])
        db.session.commit()

        adapter = ListenElementRunAdapter(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
        )

        events = [
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content="<div>",
            ).set_mdflow_stream_parts([("<div>", "html", 0)]),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content="Card</div>",
            ).set_mdflow_stream_parts([("Card</div>", "html", 0)]),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.BREAK,
                content="",
            ),
        ]

        streamed = list(adapter.process(events))
        html_events = [
            item.content
            for item in streamed
            if item.type == "element" and item.content.element_type == ElementType.HTML
        ]

        assert len(html_events) == 3
        assert [item.is_new for item in html_events] == [True, True, True]
        assert html_events[0].target_element_bid in ("", None)
        assert html_events[1].target_element_bid in ("", None)
        assert html_events[2].target_element_bid in ("", None)
        assert len({item.element_bid for item in html_events}) == 1

        result = get_listen_element_record(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
            preview_mode=False,
        )

        assert len(result.elements) == 1
        assert result.elements[0].element_type == ElementType.HTML
        assert result.elements[0].is_new is True


def test_listen_adapter_marks_type_switch_as_new_when_stream_number_reused(app):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.const import ROLE_TEACHER
    from flaskr.service.learn.learn_dtos import (
        ElementType,
        GeneratedType,
        RunMarkdownFlowDTO,
    )
    from flaskr.service.learn.listen_elements import ListenElementRunAdapter
    from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

    user_bid = "user-listen-stream-switch"
    shifu_bid = "shifu-listen-stream-switch"
    outline_bid = "outline-listen-stream-switch"
    progress_bid = "progress-listen-stream-switch"
    generated_block_bid = "generated-listen-stream-switch"

    with app.app_context():
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
            block_bid="block-listen-stream-switch",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            type=0,
            role=ROLE_TEACHER,
            generated_content="",
            position=0,
            block_content_conf="",
            status=1,
        )
        db.session.add_all([progress, block])
        db.session.commit()

        adapter = ListenElementRunAdapter(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
        )

        events = [
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content="Before image",
            ).set_mdflow_stream_parts([("Before image", "text", 0)]),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content="https://example.com/step.png",
            ).set_mdflow_stream_parts([("https://example.com/step.png", "img", 0)]),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content="After image",
            ).set_mdflow_stream_parts([("After image", "text", 0)]),
        ]

        streamed = list(adapter.process(events))
        assert [item.type for item in streamed] == [
            "element",
            "done",
            "element",
            "done",
            "element",
        ]
        element_events = [item.content for item in streamed if item.type == "element"]

        assert [item.element_type for item in element_events] == [
            ElementType.TEXT,
            ElementType.IMG,
            ElementType.TEXT,
        ]
        assert [item.is_new for item in element_events] == [True, True, True]
        assert [item.target_element_bid for item in element_events] == [
            None,
            None,
            None,
        ]
        assert len({item.element_bid for item in element_events}) == 3


def test_listen_adapter_marks_reentered_image_slot_as_new_after_text(app):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.const import ROLE_TEACHER
    from flaskr.service.learn.learn_dtos import (
        ElementType,
        GeneratedType,
        RunMarkdownFlowDTO,
    )
    from flaskr.service.learn.listen_elements import ListenElementRunAdapter
    from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

    user_bid = "user-listen-reenter-image-slot"
    shifu_bid = "shifu-listen-reenter-image-slot"
    outline_bid = "outline-listen-reenter-image-slot"
    progress_bid = "progress-listen-reenter-image-slot"
    generated_block_bid = "generated-listen-reenter-image-slot"

    with app.app_context():
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
            block_bid="block-listen-reenter-image-slot",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            type=0,
            role=ROLE_TEACHER,
            generated_content="",
            position=0,
            block_content_conf="",
            status=1,
        )
        db.session.add_all([progress, block])
        db.session.commit()

        adapter = ListenElementRunAdapter(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
        )

        events = [
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content="![img](https://example.com/first.png)\n",
            ).set_mdflow_stream_parts(
                [("![img](https://example.com/first.png)\n", "img", 0)]
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content="Between images\n",
            ).set_mdflow_stream_parts([("Between images\n", "text", 1)]),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content="![img](https://example.com/second.png)\n",
            ).set_mdflow_stream_parts(
                [("![img](https://example.com/second.png)\n", "img", 0)]
            ),
        ]

        streamed = list(adapter.process(events))
        element_events = [item.content for item in streamed if item.type == "element"]

        assert [item.element_type for item in element_events] == [
            ElementType.IMG,
            ElementType.TEXT,
            ElementType.IMG,
        ]
        assert [item.is_new for item in element_events] == [True, True, True]
        assert element_events[0].target_element_bid in ("", None)
        assert element_events[2].target_element_bid in ("", None)
        assert element_events[0].element_bid != element_events[2].element_bid


def test_audio_segments_stick_to_first_target_element_without_av_contract(app):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.const import ROLE_TEACHER
    from flaskr.service.learn.learn_dtos import (
        AudioCompleteDTO,
        AudioSegmentDTO,
        ElementType,
        GeneratedType,
        RunMarkdownFlowDTO,
    )
    from flaskr.service.learn.listen_elements import ListenElementRunAdapter
    from flaskr.service.learn.models import (
        LearnGeneratedBlock,
        LearnGeneratedElement,
        LearnProgressRecord,
    )
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

    user_bid = "user-audio-target-binding"
    shifu_bid = "shifu-audio-target-binding"
    outline_bid = "outline-audio-target-binding"
    progress_bid = "progress-audio-target-binding"
    generated_block_bid = "generated-audio-target-binding"

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
        block = LearnGeneratedBlock(
            generated_block_bid=generated_block_bid,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            block_bid="block-audio-target-binding",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            type=0,
            role=ROLE_TEACHER,
            generated_content="",
            position=0,
            block_content_conf="",
            status=1,
        )
        db.session.add_all([progress, block])
        db.session.commit()

        adapter = ListenElementRunAdapter(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
        )

        events = [
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content="<div>Intro visual</div>\n",
            ).set_mdflow_stream_parts([("<div>Intro visual</div>\n", "html", 0)]),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content="Narration text\n",
            ).set_mdflow_stream_parts([("Narration text\n", "text", 1)]),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_SEGMENT,
                content=AudioSegmentDTO(
                    position=0,
                    segment_index=0,
                    audio_data="bound-segment-0",
                    duration_ms=180,
                    is_final=False,
                ),
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content="<div>Follow-up visual</div>\n",
            ).set_mdflow_stream_parts([("<div>Follow-up visual</div>\n", "html", 2)]),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_SEGMENT,
                content=AudioSegmentDTO(
                    position=0,
                    segment_index=1,
                    audio_data="bound-segment-1",
                    duration_ms=190,
                    is_final=False,
                ),
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_COMPLETE,
                content=AudioCompleteDTO(
                    audio_url="https://example.com/bound-audio.mp3",
                    audio_bid="bound-audio-0",
                    duration_ms=370,
                    position=0,
                ),
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.BREAK,
                content="",
            ),
        ]

        streamed = list(adapter.process(events))
        element_events = [item.content for item in streamed if item.type == "element"]

        text_elements = [
            item for item in element_events if item.element_type == ElementType.TEXT
        ]
        html_elements = [
            item for item in element_events if item.element_type == ElementType.HTML
        ]
        assert len(text_elements) >= 3
        assert len(html_elements) == 4

        text_element_bid = text_elements[0].element_bid
        assert text_elements[1].element_bid == text_element_bid
        assert text_elements[1].audio_segments == [
            {
                "position": 0,
                "segment_index": 0,
                "audio_data": "bound-segment-0",
                "duration_ms": 180,
                "is_final": False,
            }
        ]
        assert text_elements[2].element_bid == text_element_bid
        assert text_elements[2].audio_segments == [
            {
                "position": 0,
                "segment_index": 1,
                "audio_data": "bound-segment-1",
                "duration_ms": 190,
                "is_final": False,
            }
        ]
        audio_complete_text = next(
            item
            for item in text_elements
            if item.audio_url == "https://example.com/bound-audio.mp3"
            and item.element_bid == text_element_bid
        )
        assert audio_complete_text.element_bid == text_element_bid
        assert audio_complete_text.target_element_bid in ("", None)
        assert audio_complete_text.is_final is True
        assert audio_complete_text.audio_segments == [
            {
                "position": 0,
                "segment_index": 0,
                "audio_data": "bound-segment-0",
                "duration_ms": 180,
                "is_final": False,
            },
            {
                "position": 0,
                "segment_index": 1,
                "audio_data": "bound-segment-1",
                "duration_ms": 190,
                "is_final": True,
            },
        ]

        intro_html = next(
            item
            for item in html_elements
            if item.is_new and "Intro visual" in (item.content_text or "")
        )
        follow_up_html = next(
            item
            for item in html_elements
            if item.is_new and "Follow-up visual" in (item.content_text or "")
        )
        assert len({item.element_bid for item in html_elements}) == 2
        assert [item.is_new for item in html_elements] == [True, True, True, True]
        assert intro_html.target_element_bid in ("", None)
        assert follow_up_html.target_element_bid in ("", None)
        assert follow_up_html.element_bid != intro_html.element_bid
        assert "Intro visual" not in (follow_up_html.content_text or "")
        assert follow_up_html.audio_segments == []
        assert follow_up_html.audio_url == ""
        assert follow_up_html.is_speakable is False
        assert any(
            item.is_new
            and item.element_bid == intro_html.element_bid
            and "Intro visual" in (item.content_text or "")
            for item in html_elements
        )
        assert any(
            item.is_new
            and item.element_bid == follow_up_html.element_bid
            and "Follow-up visual" in (item.content_text or "")
            for item in html_elements
        )

        persisted_text_rows = (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.generated_block_bid == generated_block_bid,
                LearnGeneratedElement.event_type == "element",
                LearnGeneratedElement.element_type == ElementType.TEXT.value,
                LearnGeneratedElement.deleted == 0,
                LearnGeneratedElement.status == 1,
            )
            .order_by(LearnGeneratedElement.run_event_seq.asc())
            .all()
        )
        text_rows_with_audio = [
            row
            for row in persisted_text_rows
            if row.audio_segments and row.audio_segments != "[]"
        ]
        assert len(text_rows_with_audio) == 1
        assert (
            text_rows_with_audio[0].audio_url == "https://example.com/bound-audio.mp3"
        )
        assert text_rows_with_audio[0].is_final == 1
        assert json.loads(text_rows_with_audio[0].audio_segments) == [
            {
                "position": 0,
                "segment_index": 0,
                "audio_data": "",
                "duration_ms": 180,
                "is_final": False,
            },
            {
                "position": 0,
                "segment_index": 1,
                "audio_data": "",
                "duration_ms": 190,
                "is_final": True,
            },
        ]


def test_late_audio_positions_bind_to_latest_text_without_av_contract(app):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.const import ROLE_TEACHER
    from flaskr.service.learn.learn_dtos import (
        AudioCompleteDTO,
        AudioSegmentDTO,
        ElementType,
        GeneratedType,
        RunMarkdownFlowDTO,
    )
    from flaskr.service.learn.listen_elements import ListenElementRunAdapter
    from flaskr.service.learn.models import (
        LearnGeneratedBlock,
        LearnGeneratedElement,
        LearnProgressRecord,
    )
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

    user_bid = "user-latest-audio-target-binding"
    shifu_bid = "shifu-latest-audio-target-binding"
    outline_bid = "outline-latest-audio-target-binding"
    progress_bid = "progress-latest-audio-target-binding"
    generated_block_bid = "generated-latest-audio-target-binding"

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
        block = LearnGeneratedBlock(
            generated_block_bid=generated_block_bid,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            block_bid="block-latest-audio-target-binding",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            type=0,
            role=ROLE_TEACHER,
            generated_content="",
            position=0,
            block_content_conf="",
            status=1,
        )
        db.session.add_all([progress, block])
        db.session.commit()

        adapter = ListenElementRunAdapter(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
        )

        events = [
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content="First narration.\n",
            ).set_mdflow_stream_parts([("First narration.\n", "text", 0)]),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_SEGMENT,
                content=AudioSegmentDTO(
                    position=0,
                    segment_index=0,
                    audio_data="first-segment-0",
                    duration_ms=180,
                    is_final=False,
                ),
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_COMPLETE,
                content=AudioCompleteDTO(
                    audio_url="https://example.com/first-audio.mp3",
                    audio_bid="first-audio-0",
                    duration_ms=180,
                    position=0,
                ),
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content="<div>Visual gap</div>\n",
            ).set_mdflow_stream_parts([("<div>Visual gap</div>\n", "html", 1)]),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content="Second narration.\n",
            ).set_mdflow_stream_parts([("Second narration.\n", "text", 2)]),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_SEGMENT,
                content=AudioSegmentDTO(
                    position=1,
                    segment_index=0,
                    audio_data="second-segment-0",
                    duration_ms=210,
                    is_final=False,
                ),
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_SEGMENT,
                content=AudioSegmentDTO(
                    position=1,
                    segment_index=1,
                    audio_data="second-segment-1",
                    duration_ms=220,
                    is_final=False,
                ),
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_SEGMENT,
                content=AudioSegmentDTO(
                    position=1,
                    segment_index=2,
                    audio_data="second-segment-2",
                    duration_ms=230,
                    is_final=False,
                ),
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_COMPLETE,
                content=AudioCompleteDTO(
                    audio_url="https://example.com/second-audio.mp3",
                    audio_bid="second-audio-1",
                    duration_ms=210,
                    position=1,
                ),
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.BREAK,
                content="",
            ),
        ]

        streamed = list(adapter.process(events))
        assert streamed[-1].type == "done"
        element_events = [item.content for item in streamed if item.type == "element"]

        rendered_texts = []
        seen_text_bids = set()
        for item in element_events:
            if item.element_type != ElementType.TEXT:
                continue
            if item.element_bid in seen_text_bids:
                continue
            seen_text_bids.add(item.element_bid)
            rendered_texts.append(item)
        assert len(rendered_texts) == 2

        first_text_bid = rendered_texts[0].element_bid
        second_text_bid = rendered_texts[1].element_bid
        assert first_text_bid != second_text_bid

        first_audio_complete = next(
            item
            for item in element_events
            if item.element_type == ElementType.TEXT
            and item.audio_url == "https://example.com/first-audio.mp3"
        )
        assert first_audio_complete.element_bid == first_text_bid
        assert first_audio_complete.target_element_bid in ("", None)
        assert first_audio_complete.is_final is True

        second_audio_segments = [
            item
            for item in element_events
            if item.element_type == ElementType.TEXT
            and item.element_bid == second_text_bid
            and item.audio_segments
            and not item.audio_url
            and item.audio_segments[0]["position"] == 1
        ]
        assert all(
            item.element_bid == second_text_bid for item in second_audio_segments
        )
        assert [item.audio_segments for item in second_audio_segments] == [
            [
                {
                    "position": 1,
                    "segment_index": 0,
                    "audio_data": "second-segment-0",
                    "duration_ms": 210,
                    "is_final": False,
                }
            ],
            [
                {
                    "position": 1,
                    "segment_index": 1,
                    "audio_data": "second-segment-1",
                    "duration_ms": 220,
                    "is_final": False,
                }
            ],
            [
                {
                    "position": 1,
                    "segment_index": 2,
                    "audio_data": "second-segment-2",
                    "duration_ms": 230,
                    "is_final": False,
                }
            ],
        ]

        second_audio_complete = next(
            item
            for item in element_events
            if item.element_type == ElementType.TEXT
            and item.audio_url == "https://example.com/second-audio.mp3"
        )
        assert second_audio_complete.element_bid == second_text_bid
        assert second_audio_complete.target_element_bid in ("", None)
        assert second_audio_complete.is_final is True
        assert second_audio_complete.audio_segments == [
            {
                "position": 1,
                "segment_index": 0,
                "audio_data": "second-segment-0",
                "duration_ms": 210,
                "is_final": False,
            },
            {
                "position": 1,
                "segment_index": 1,
                "audio_data": "second-segment-1",
                "duration_ms": 220,
                "is_final": False,
            },
            {
                "position": 1,
                "segment_index": 2,
                "audio_data": "second-segment-2",
                "duration_ms": 230,
                "is_final": True,
            },
        ]

        assert not any(
            item.element_bid == first_text_bid
            and any(segment["position"] == 1 for segment in (item.audio_segments or []))
            for item in element_events
            if item.element_type == ElementType.TEXT
        )

        persisted_text_rows = (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.generated_block_bid == generated_block_bid,
                LearnGeneratedElement.event_type == "element",
                LearnGeneratedElement.element_type == ElementType.TEXT.value,
                LearnGeneratedElement.deleted == 0,
                LearnGeneratedElement.status == 1,
            )
            .order_by(LearnGeneratedElement.run_event_seq.asc())
            .all()
        )
        second_text_rows_with_audio = [
            row
            for row in persisted_text_rows
            if row.element_bid == second_text_bid
            and row.audio_segments
            and row.audio_segments != "[]"
        ]
        assert second_text_rows_with_audio
        assert all(
            json.loads(row.audio_segments)[0]["position"] == 1
            for row in second_text_rows_with_audio
        )
        assert all(
            row.audio_url == "https://example.com/second-audio.mp3"
            for row in second_text_rows_with_audio
        )
        final_second_text_row = next(
            row
            for row in reversed(second_text_rows_with_audio)
            if row.audio_url == "https://example.com/second-audio.mp3"
        )
        assert json.loads(final_second_text_row.audio_segments) == [
            {
                "position": 1,
                "segment_index": 0,
                "audio_data": "",
                "duration_ms": 210,
                "is_final": False,
            },
            {
                "position": 1,
                "segment_index": 1,
                "audio_data": "",
                "duration_ms": 220,
                "is_final": False,
            },
            {
                "position": 1,
                "segment_index": 2,
                "audio_data": "",
                "duration_ms": 230,
                "is_final": True,
            },
        ]


def test_listen_adapter_binds_buffered_audio_to_text_after_html(app):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.const import ROLE_TEACHER
    from flaskr.service.learn.learn_dtos import (
        AudioCompleteDTO,
        AudioSegmentDTO,
        ElementType,
        GeneratedType,
        RunMarkdownFlowDTO,
    )
    from flaskr.service.learn.listen_elements import ListenElementRunAdapter
    from flaskr.service.learn.models import (
        LearnGeneratedBlock,
        LearnGeneratedElement,
        LearnProgressRecord,
    )
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

    user_bid = "user-audio-after-html"
    shifu_bid = "shifu-audio-after-html"
    outline_bid = "outline-audio-after-html"
    progress_bid = "progress-audio-after-html"
    generated_block_bid = "generated-audio-after-html"

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
        block = LearnGeneratedBlock(
            generated_block_bid=generated_block_bid,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            block_bid="block-audio-after-html",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            type=0,
            role=ROLE_TEACHER,
            generated_content="",
            position=0,
            block_content_conf="",
            status=1,
        )
        db.session.add_all([progress, block])
        db.session.commit()

        adapter = ListenElementRunAdapter(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
        )

        events = [
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content="<div>Choice detail</div>\n",
            ).set_mdflow_stream_parts([("<div>Choice detail</div>\n", "html", 0)]),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_SEGMENT,
                content=AudioSegmentDTO(
                    position=0,
                    segment_index=0,
                    audio_data="late-text-segment",
                    duration_ms=210,
                    is_final=True,
                ),
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content="Narration after click\n",
            ).set_mdflow_stream_parts([("Narration after click\n", "text", 1)]),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_COMPLETE,
                content=AudioCompleteDTO(
                    audio_url="https://example.com/after-click.mp3",
                    audio_bid="after-click-audio-0",
                    duration_ms=210,
                    position=0,
                ),
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.BREAK,
                content="",
            ),
        ]

        streamed = list(adapter.process(events))
        element_events = [item.content for item in streamed if item.type == "element"]

        html_elements = [
            item for item in element_events if item.element_type == ElementType.HTML
        ]
        text_elements = [
            item for item in element_events if item.element_type == ElementType.TEXT
        ]
        assert len({item.element_bid for item in html_elements}) == 1
        assert len(text_elements) >= 2

        html_element = next(item for item in html_elements if not item.is_final)
        assert html_element.audio_segments == []
        assert html_element.audio_url == ""
        assert html_element.is_speakable is False
        assert all(item.audio_segments == [] for item in html_elements)
        assert all(item.audio_url == "" for item in html_elements)

        initial_text = next(
            item
            for item in text_elements
            if item.content_text == "Narration after click\n"
        )
        assert initial_text.audio_segments == [
            {
                "position": 0,
                "segment_index": 0,
                "audio_data": "late-text-segment",
                "duration_ms": 210,
                "is_final": True,
            }
        ]
        assert initial_text.audio_url == ""
        assert initial_text.is_new is True

        final_text = next(
            item
            for item in text_elements
            if item.audio_url == "https://example.com/after-click.mp3"
            and item.is_final is True
        )
        assert final_text.element_bid == initial_text.element_bid
        assert final_text.target_element_bid in ("", None)
        assert final_text.is_final is True
        assert final_text.audio_segments == [
            {
                "position": 0,
                "segment_index": 0,
                "audio_data": "late-text-segment",
                "duration_ms": 210,
                "is_final": True,
            }
        ]

        persisted_rows = (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.generated_block_bid == generated_block_bid,
                LearnGeneratedElement.event_type == "element",
                LearnGeneratedElement.deleted == 0,
                LearnGeneratedElement.status == 1,
            )
            .order_by(LearnGeneratedElement.run_event_seq.asc())
            .all()
        )
        persisted_html_rows = [
            row for row in persisted_rows if row.element_type == ElementType.HTML.value
        ]
        persisted_text_rows = [
            row for row in persisted_rows if row.element_type == ElementType.TEXT.value
        ]
        assert len(persisted_html_rows) == 1
        assert all(
            not row.audio_segments or row.audio_segments == "[]"
            for row in persisted_html_rows
        )
        assert all(row.audio_url == "" for row in persisted_html_rows)
        assert any(
            json.loads(row.audio_segments)
            == [
                {
                    "position": 0,
                    "segment_index": 0,
                    "audio_data": "",
                    "duration_ms": 210,
                    "is_final": True,
                }
            ]
            for row in persisted_text_rows
            if row.audio_segments and row.audio_segments != "[]"
        )
        assert any(
            row.audio_url == "https://example.com/after-click.mp3" and row.is_final == 1
            for row in persisted_text_rows
        )


def test_audio_stream_number_binding_overrides_position_guessing(app):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.const import ROLE_TEACHER
    from flaskr.service.learn.learn_dtos import (
        AudioCompleteDTO,
        AudioSegmentDTO,
        ElementType,
        GeneratedType,
        RunMarkdownFlowDTO,
    )
    from flaskr.service.learn.listen_elements import ListenElementRunAdapter
    from flaskr.service.learn.models import (
        LearnGeneratedBlock,
        LearnGeneratedElement,
        LearnProgressRecord,
    )
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

    user_bid = "user-audio-stream-number-binding"
    shifu_bid = "shifu-audio-stream-number-binding"
    outline_bid = "outline-audio-stream-number-binding"
    progress_bid = "progress-audio-stream-number-binding"
    generated_block_bid = "generated-audio-stream-number-binding"

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
        block = LearnGeneratedBlock(
            generated_block_bid=generated_block_bid,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            block_bid="block-audio-stream-number-binding",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            type=0,
            role=ROLE_TEACHER,
            generated_content="",
            position=0,
            block_content_conf="",
            status=1,
        )
        db.session.add_all([progress, block])
        db.session.commit()

        adapter = ListenElementRunAdapter(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
        )

        events = [
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content="# Intro\n",
            ).set_mdflow_stream_parts([("# Intro\n", "title", 0)]),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content="First narration\n",
            ).set_mdflow_stream_parts([("First narration\n", "text", 1)]),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content="## Details\n",
            ).set_mdflow_stream_parts([("## Details\n", "title", 2)]),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content="Second narration\n",
            ).set_mdflow_stream_parts([("Second narration\n", "text", 3)]),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_SEGMENT,
                content=AudioSegmentDTO(
                    position=0,
                    stream_element_number=3,
                    stream_element_type="text",
                    segment_index=0,
                    audio_data="second-segment-0",
                    duration_ms=210,
                    is_final=False,
                ),
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_COMPLETE,
                content=AudioCompleteDTO(
                    audio_url="https://example.com/second-stream.mp3",
                    audio_bid="second-stream-audio",
                    duration_ms=210,
                    position=0,
                    stream_element_number=3,
                    stream_element_type="text",
                ),
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_SEGMENT,
                content=AudioSegmentDTO(
                    position=1,
                    stream_element_number=1,
                    stream_element_type="text",
                    segment_index=0,
                    audio_data="first-segment-0",
                    duration_ms=180,
                    is_final=False,
                ),
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_COMPLETE,
                content=AudioCompleteDTO(
                    audio_url="https://example.com/first-stream.mp3",
                    audio_bid="first-stream-audio",
                    duration_ms=180,
                    position=1,
                    stream_element_number=1,
                    stream_element_type="text",
                ),
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.BREAK,
                content="",
            ),
        ]

        streamed = list(adapter.process(events))
        element_events = [item.content for item in streamed if item.type == "element"]
        text_events = [
            item for item in element_events if item.element_type == ElementType.TEXT
        ]

        first_text_final = next(
            item
            for item in text_events
            if item.is_final is True and item.content_text == "First narration\n"
        )
        second_text_final = next(
            item
            for item in text_events
            if item.is_final is True and item.content_text == "Second narration\n"
        )

        assert first_text_final.audio_url == "https://example.com/first-stream.mp3"
        assert first_text_final.audio_segments == [
            {
                "position": 1,
                "segment_index": 0,
                "audio_data": "first-segment-0",
                "duration_ms": 180,
                "is_final": True,
            }
        ]
        assert second_text_final.audio_url == "https://example.com/second-stream.mp3"
        assert second_text_final.audio_segments == [
            {
                "position": 0,
                "segment_index": 0,
                "audio_data": "second-segment-0",
                "duration_ms": 210,
                "is_final": True,
            }
        ]


def test_html_only_stream_does_not_absorb_audio_without_av_contract(app):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.const import ROLE_TEACHER
    from flaskr.service.learn.learn_dtos import (
        AudioCompleteDTO,
        AudioSegmentDTO,
        ElementType,
        GeneratedType,
        RunMarkdownFlowDTO,
    )
    from flaskr.service.learn.listen_elements import ListenElementRunAdapter
    from flaskr.service.learn.models import (
        LearnGeneratedBlock,
        LearnGeneratedElement,
        LearnProgressRecord,
    )
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

    user_bid = "user-html-only-audio"
    shifu_bid = "shifu-html-only-audio"
    outline_bid = "outline-html-only-audio"
    progress_bid = "progress-html-only-audio"
    generated_block_bid = "generated-html-only-audio"

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
        block = LearnGeneratedBlock(
            generated_block_bid=generated_block_bid,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            block_bid="block-html-only-audio",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            type=0,
            role=ROLE_TEACHER,
            generated_content="",
            position=0,
            block_content_conf="",
            status=1,
        )
        db.session.add_all([progress, block])
        db.session.commit()

        adapter = ListenElementRunAdapter(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
        )

        events = [
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content="<div>Narration after click</div>\n",
            ).set_mdflow_stream_parts(
                [("<div>Narration after click</div>\n", "html", 0)]
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
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
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_COMPLETE,
                content=AudioCompleteDTO(
                    audio_url="https://example.com/html-only.mp3",
                    audio_bid="html-only-audio-0",
                    duration_ms=210,
                    position=0,
                ),
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.BREAK,
                content="",
            ),
        ]

        streamed = list(adapter.process(events))
        element_events = [item.content for item in streamed if item.type == "element"]
        html_elements = [
            item for item in element_events if item.element_type == ElementType.HTML
        ]
        text_elements = [
            item for item in element_events if item.element_type == ElementType.TEXT
        ]

        assert len(html_elements) == 2
        assert text_elements == []
        assert all(item.audio_segments == [] for item in html_elements)
        assert all(item.audio_url == "" for item in html_elements)
        assert all(item.is_speakable is False for item in html_elements)

        persisted_rows = (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.generated_block_bid == generated_block_bid,
                LearnGeneratedElement.event_type == "element",
                LearnGeneratedElement.deleted == 0,
                LearnGeneratedElement.status == 1,
            )
            .order_by(LearnGeneratedElement.run_event_seq.asc())
            .all()
        )
        persisted_html_rows = [
            row for row in persisted_rows if row.element_type == ElementType.HTML.value
        ]

        assert len(persisted_html_rows) == 1
        assert all(
            not row.audio_segments or row.audio_segments == "[]"
            for row in persisted_html_rows
        )
        assert all(row.audio_url == "" for row in persisted_html_rows)


def test_duplicate_audio_segment_events_are_deduplicated_in_run_state(app):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.const import ROLE_TEACHER
    from flaskr.service.learn.learn_dtos import (
        AudioCompleteDTO,
        AudioSegmentDTO,
        ElementType,
        GeneratedType,
        RunMarkdownFlowDTO,
    )
    from flaskr.service.learn.listen_elements import ListenElementRunAdapter
    from flaskr.service.learn.models import (
        LearnGeneratedBlock,
        LearnGeneratedElement,
        LearnProgressRecord,
    )
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

    user_bid = "user-dup-audio-segment"
    shifu_bid = "shifu-dup-audio-segment"
    outline_bid = "outline-dup-audio-segment"
    progress_bid = "progress-dup-audio-segment"
    generated_block_bid = "generated-dup-audio-segment"

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
        block = LearnGeneratedBlock(
            generated_block_bid=generated_block_bid,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            block_bid="block-dup-audio-segment",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            type=0,
            role=ROLE_TEACHER,
            generated_content="",
            position=0,
            block_content_conf="",
            status=1,
        )
        db.session.add_all([progress, block])
        db.session.commit()

        adapter = ListenElementRunAdapter(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
        )

        duplicate_segment = AudioSegmentDTO(
            position=0,
            stream_element_number=1,
            stream_element_type="text",
            segment_index=0,
            audio_data="segment-0",
            duration_ms=180,
            is_final=False,
        )

        events = [
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content="Narration\n",
            ).set_mdflow_stream_parts([("Narration\n", "text", 1)]),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_SEGMENT,
                content=duplicate_segment,
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_SEGMENT,
                content=AudioSegmentDTO(
                    position=0,
                    stream_element_number=1,
                    stream_element_type="text",
                    segment_index=0,
                    audio_data="segment-0",
                    duration_ms=180,
                    is_final=False,
                ),
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_COMPLETE,
                content=AudioCompleteDTO(
                    audio_url="https://example.com/segment-0.mp3",
                    audio_bid="audio-segment-0",
                    duration_ms=180,
                    position=0,
                    stream_element_number=1,
                    stream_element_type="text",
                ),
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.BREAK,
                content="",
            ),
        ]

        streamed = list(adapter.process(events))
        element_events = [item.content for item in streamed if item.type == "element"]
        text_final = next(
            item
            for item in element_events
            if item.element_type == ElementType.TEXT and item.is_final is True
        )

        assert text_final.audio_segments == [
            {
                "position": 0,
                "segment_index": 0,
                "audio_data": "segment-0",
                "duration_ms": 180,
                "is_final": True,
            }
        ]

        persisted_row = (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.generated_block_bid == generated_block_bid,
                LearnGeneratedElement.event_type == "element",
                LearnGeneratedElement.element_type == ElementType.TEXT.value,
                LearnGeneratedElement.deleted == 0,
                LearnGeneratedElement.status == 1,
                LearnGeneratedElement.is_final == 1,
            )
            .order_by(LearnGeneratedElement.run_event_seq.desc())
            .first()
        )

        assert persisted_row is not None
        assert json.loads(persisted_row.audio_segments) == [
            {
                "position": 0,
                "segment_index": 0,
                "audio_data": "",
                "duration_ms": 180,
                "is_final": True,
            }
        ]


def test_listen_adapter_streams_subtitle_cues_on_audio_segment_patch(app):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.const import ROLE_TEACHER
    from flaskr.service.learn.learn_dtos import (
        AudioSegmentDTO,
        ElementType,
        GeneratedType,
        RunMarkdownFlowDTO,
    )
    from flaskr.service.learn.listen_elements import ListenElementRunAdapter
    from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

    user_bid = "user-stream-segment-subtitles"
    shifu_bid = "shifu-stream-segment-subtitles"
    outline_bid = "outline-stream-segment-subtitles"
    progress_bid = "progress-stream-segment-subtitles"
    generated_block_bid = "generated-stream-segment-subtitles"

    with app.app_context():
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
            block_bid="block-stream-segment-subtitles",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            type=0,
            role=ROLE_TEACHER,
            generated_content="",
            position=0,
            block_content_conf="",
            status=1,
        )
        db.session.add_all([progress, block])
        db.session.commit()

        adapter = ListenElementRunAdapter(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
        )

        events = [
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content="Narration subtitle stream.\n",
            ).set_mdflow_stream_parts([("Narration subtitle stream.\n", "text", 1)]),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
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
                            "text": "Narration subtitle stream.",
                            "start_ms": 0,
                            "end_ms": 180,
                            "segment_index": 0,
                            "position": 0,
                        }
                    ],
                ),
            ),
        ]

        streamed = list(adapter.process(events))
        text_events = [
            item.content
            for item in streamed
            if item.type == "element" and item.content.element_type == ElementType.TEXT
        ]

        assert len(text_events) == 2
        segment_patch = text_events[-1]
        assert segment_patch.payload is not None
        assert segment_patch.payload.audio is not None
        assert [cue.text for cue in segment_patch.payload.audio.subtitle_cues] == [
            "Narration subtitle stream."
        ]
        assert segment_patch.payload.audio.duration_ms == 180
        assert segment_patch.audio_segments == [
            {
                "position": 0,
                "segment_index": 0,
                "audio_data": "segment-0",
                "duration_ms": 180,
                "is_final": False,
                "subtitle_cues": [
                    {
                        "text": "Narration subtitle stream.",
                        "start_ms": 0,
                        "end_ms": 180,
                        "segment_index": 0,
                        "position": 0,
                    }
                ],
            }
        ]


def test_build_listen_elements_from_legacy_record_interleaves_visuals_and_text(app):
    _require_app(app)

    from flaskr.service.learn.learn_dtos import (
        AudioCompleteDTO,
        BlockType,
        ElementType,
        LikeStatus,
    )
    from flaskr.service.learn.legacy_record_builder import (
        LegacyGeneratedBlockRecord,
        LegacyLearnRecord,
    )
    from flaskr.service.learn.listen_elements import (
        build_listen_elements_from_legacy_record,
    )

    raw_content = "Before intro.\n\n<svg><text>Chart</text></svg>\n\nAfter chart."
    generated_block_bid = "generated-legacy-elements"
    legacy_record = LegacyLearnRecord(
        records=[
            LegacyGeneratedBlockRecord(
                generated_block_bid=generated_block_bid,
                content=raw_content,
                like_status=LikeStatus.NONE,
                block_type=BlockType.CONTENT,
                user_input="",
                audios=[
                    AudioCompleteDTO(
                        position=0,
                        audio_url="https://example.com/audio-0.mp3",
                        audio_bid="audio-legacy-0",
                        duration_ms=800,
                    ),
                    AudioCompleteDTO(
                        position=1,
                        audio_url="https://example.com/audio-1.mp3",
                        audio_bid="audio-legacy-1",
                        duration_ms=900,
                    ),
                ],
            )
        ]
    )

    result = build_listen_elements_from_legacy_record(app, legacy_record)

    assert len(result.elements) == 3

    first, second, third = result.elements

    assert first.generated_block_bid == generated_block_bid
    assert first.element_index == 0
    assert first.element_type == ElementType.TEXT
    assert first.content_text == "Before intro."
    assert first.payload is not None
    assert first.payload.audio is not None
    assert first.payload.audio.audio_bid == "audio-legacy-0"
    assert first.payload.previous_visuals == []
    assert first.is_renderable is False
    assert first.is_speakable is True
    assert first.is_marker is False
    assert first.audio_url == "https://example.com/audio-0.mp3"
    assert first.audio_segments == []

    assert second.generated_block_bid == generated_block_bid
    assert second.element_index == 1
    assert second.element_type == ElementType.SVG
    assert second.is_renderable is True
    assert second.is_marker is True
    assert second.content_text == ""
    assert second.payload is not None
    assert second.payload.audio is None
    assert len(second.payload.previous_visuals) == 1
    assert second.payload.previous_visuals[0].visual_type == "svg"
    assert second.payload.previous_visuals[0].content.startswith("<svg")

    assert third.generated_block_bid == generated_block_bid
    assert third.element_index == 2
    assert third.element_type == ElementType.TEXT
    assert third.content_text == "After chart."
    assert third.payload is not None
    assert third.payload.audio is not None
    assert third.payload.audio.audio_bid == "audio-legacy-1"
    assert third.payload.previous_visuals == []
    assert third.is_renderable is False
    assert third.is_speakable is True
    assert third.is_marker is False
    assert third.audio_url == "https://example.com/audio-1.mp3"
    assert third.audio_segments == []


def test_build_listen_elements_from_legacy_record_prefers_persisted_visual_elements(
    app,
):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.learn_dtos import (
        AudioCompleteDTO,
        BlockType,
        ElementType,
        LikeStatus,
    )
    from flaskr.service.learn.legacy_record_builder import (
        LegacyGeneratedBlockRecord,
        LegacyLearnRecord,
    )
    from flaskr.service.learn.listen_elements import (
        build_listen_elements_from_legacy_record,
    )
    from flaskr.service.learn.models import LearnGeneratedElement

    generated_block_bid = "generated-legacy-persisted-visual"
    visual_markdown = "![img](https://example.com/visual.png)"
    visual_payload = json.dumps(
        {
            "audio": None,
            "previous_visuals": [
                {
                    "visual_type": "img",
                    "content": visual_markdown,
                }
            ],
        }
    )

    with app.app_context():
        LearnGeneratedElement.query.filter(
            LearnGeneratedElement.generated_block_bid == generated_block_bid
        ).delete()
        db.session.commit()

        db.session.add_all(
            [
                LearnGeneratedElement(
                    element_bid="el-legacy-visual-text-1",
                    progress_record_bid="progress-legacy-visual",
                    user_bid="user-legacy-visual",
                    generated_block_bid=generated_block_bid,
                    outline_item_bid="outline-legacy-visual",
                    shifu_bid="shifu-legacy-visual",
                    run_session_bid="run-legacy-visual",
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
                    content_text="Before image.",
                    payload='{"audio": null, "previous_visuals": []}',
                    deleted=0,
                    status=1,
                ),
                LearnGeneratedElement(
                    element_bid="el-legacy-visual-marker",
                    progress_record_bid="progress-legacy-visual",
                    user_bid="user-legacy-visual",
                    generated_block_bid=generated_block_bid,
                    outline_item_bid="outline-legacy-visual",
                    shifu_bid="shifu-legacy-visual",
                    run_session_bid="run-legacy-visual",
                    run_event_seq=2,
                    event_type="element",
                    role="teacher",
                    element_index=1,
                    element_type="img",
                    element_type_code=204,
                    change_type="render",
                    target_element_bid="",
                    is_renderable=1,
                    is_new=1,
                    is_marker=1,
                    sequence_number=2,
                    is_speakable=0,
                    audio_url="",
                    audio_segments="[]",
                    is_navigable=1,
                    is_final=1,
                    content_text="",
                    payload=visual_payload,
                    deleted=0,
                    status=0,
                ),
                LearnGeneratedElement(
                    element_bid="el-legacy-visual-marker",
                    progress_record_bid="progress-legacy-visual",
                    user_bid="user-legacy-visual",
                    generated_block_bid=generated_block_bid,
                    outline_item_bid="outline-legacy-visual",
                    shifu_bid="shifu-legacy-visual",
                    run_session_bid="run-legacy-visual",
                    run_event_seq=3,
                    event_type="element",
                    role="teacher",
                    element_index=1,
                    element_type="img",
                    element_type_code=204,
                    change_type="render",
                    target_element_bid="el-legacy-visual-marker",
                    is_renderable=1,
                    is_new=0,
                    is_marker=1,
                    sequence_number=3,
                    is_speakable=0,
                    audio_url="",
                    audio_segments="[]",
                    is_navigable=1,
                    is_final=1,
                    content_text="",
                    payload=visual_payload,
                    deleted=0,
                    status=1,
                ),
                LearnGeneratedElement(
                    element_bid="el-legacy-visual-text-2",
                    progress_record_bid="progress-legacy-visual",
                    user_bid="user-legacy-visual",
                    generated_block_bid=generated_block_bid,
                    outline_item_bid="outline-legacy-visual",
                    shifu_bid="shifu-legacy-visual",
                    run_session_bid="run-legacy-visual",
                    run_event_seq=4,
                    event_type="element",
                    role="teacher",
                    element_index=2,
                    element_type="text",
                    element_type_code=213,
                    change_type="render",
                    target_element_bid="",
                    is_renderable=0,
                    is_new=1,
                    is_marker=0,
                    sequence_number=4,
                    is_speakable=1,
                    audio_url="",
                    audio_segments="[]",
                    is_navigable=1,
                    is_final=1,
                    content_text="After image.",
                    payload='{"audio": null, "previous_visuals": []}',
                    deleted=0,
                    status=1,
                ),
            ]
        )
        db.session.commit()

    legacy_record = LegacyLearnRecord(
        records=[
            LegacyGeneratedBlockRecord(
                generated_block_bid=generated_block_bid,
                content=f"Before image.\n\n{visual_markdown}\n\nAfter image.",
                like_status=LikeStatus.NONE,
                block_type=BlockType.CONTENT,
                user_input="",
                audios=[
                    AudioCompleteDTO(
                        position=0,
                        audio_url="https://example.com/legacy-visual-0.mp3",
                        audio_bid="audio-legacy-visual-0",
                        duration_ms=320,
                    ),
                    AudioCompleteDTO(
                        position=1,
                        audio_url="https://example.com/legacy-visual-1.mp3",
                        audio_bid="audio-legacy-visual-1",
                        duration_ms=410,
                    ),
                ],
            )
        ]
    )

    result = build_listen_elements_from_legacy_record(app, legacy_record)

    assert len(result.elements) == 3
    assert [element.element_type for element in result.elements] == [
        ElementType.TEXT,
        ElementType.IMG,
        ElementType.TEXT,
    ]
    assert [element.content_text for element in result.elements] == [
        "Before image.",
        "![img](https://example.com/visual.png)",
        "After image.",
    ]
    assert [element.is_new for element in result.elements] == [True, True, True]
    assert [element.element_index for element in result.elements] == [0, 1, 2]
    assert result.elements[1].target_element_bid in ("", None)
    assert result.elements[1].payload is not None
    assert result.elements[1].payload.previous_visuals[0].visual_type == "img"
    assert result.elements[1].payload.previous_visuals[0].content == ""
    assert [element.audio_url for element in result.elements] == [
        "https://example.com/legacy-visual-0.mp3",
        "",
        "https://example.com/legacy-visual-1.mp3",
    ]


def test_build_listen_elements_from_legacy_record_keeps_interaction_user_input(app):
    _require_app(app)

    from flaskr.service.learn.learn_dtos import (
        BlockType,
        LikeStatus,
    )
    from flaskr.service.learn.legacy_record_builder import (
        LegacyGeneratedBlockRecord,
        LegacyLearnRecord,
    )
    from flaskr.service.learn.listen_elements import (
        build_listen_elements_from_legacy_record,
    )

    legacy_record = LegacyLearnRecord(
        records=[
            LegacyGeneratedBlockRecord(
                generated_block_bid="generated-interaction-legacy",
                content="?[Agree//agree][Disagree//disagree]",
                like_status=LikeStatus.NONE,
                block_type=BlockType.INTERACTION,
                user_input="agree",
            )
        ]
    )

    result = build_listen_elements_from_legacy_record(app, legacy_record)

    assert len(result.elements) == 1
    element = result.elements[0]
    assert element.is_renderable is False
    assert element.payload is not None
    assert element.payload.user_input == "agree"


def test_backfill_learn_generated_elements_for_progress_persists_clean_elements(app):
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

    user_bid = "user-backfill-elements"
    shifu_bid = "shifu-backfill-elements"
    outline_bid = "outline-backfill-elements"
    progress_bid = "progress-backfill-elements"
    generated_block_bid = "generated-backfill-elements"
    raw_content = "Before intro.\n\n<svg><text>Chart</text></svg>\n\nAfter chart."

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
        stale_block = LearnGeneratedBlock(
            generated_block_bid=generated_block_bid,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            block_bid="block-backfill-stale",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            type=BLOCK_TYPE_MDCONTENT_VALUE,
            role=ROLE_TEACHER,
            generated_content="stale content should be ignored",
            position=0,
            block_content_conf="",
            status=1,
        )
        final_block = LearnGeneratedBlock(
            generated_block_bid=generated_block_bid,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            block_bid="block-backfill-final",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            type=BLOCK_TYPE_MDCONTENT_VALUE,
            role=ROLE_TEACHER,
            generated_content=raw_content,
            position=0,
            block_content_conf="",
            status=1,
        )
        empty_block = LearnGeneratedBlock(
            generated_block_bid="generated-backfill-empty",
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            block_bid="block-backfill-empty",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            type=BLOCK_TYPE_MDCONTENT_VALUE,
            role=ROLE_TEACHER,
            generated_content="   ",
            position=1,
            block_content_conf="",
            status=1,
        )
        audio_0 = LearnGeneratedAudio(
            audio_bid="audio-backfill-0",
            generated_block_bid=generated_block_bid,
            position=0,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            oss_url="https://example.com/backfill-0.mp3",
            duration_ms=500,
            status=AUDIO_STATUS_COMPLETED,
        )
        audio_1_stale = LearnGeneratedAudio(
            audio_bid="audio-backfill-1-stale",
            generated_block_bid=generated_block_bid,
            position=1,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            oss_url="https://example.com/backfill-1-stale.mp3",
            duration_ms=700,
            status=AUDIO_STATUS_COMPLETED,
        )
        audio_1_final = LearnGeneratedAudio(
            audio_bid="audio-backfill-1-final",
            generated_block_bid=generated_block_bid,
            position=1,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            oss_url="https://example.com/backfill-1-final.mp3",
            duration_ms=900,
            status=AUDIO_STATUS_COMPLETED,
        )
        orphan_audio = LearnGeneratedAudio(
            audio_bid="audio-backfill-orphan",
            generated_block_bid="generated-backfill-orphan",
            position=0,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            oss_url="https://example.com/backfill-orphan.mp3",
            duration_ms=300,
            status=AUDIO_STATUS_COMPLETED,
        )
        db.session.add_all(
            [
                progress,
                stale_block,
                final_block,
                empty_block,
                audio_0,
                audio_1_stale,
                audio_1_final,
                orphan_audio,
            ]
        )
        db.session.commit()

        result = backfill_learn_generated_elements_for_progress(app, progress_bid)

        rows = (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.progress_record_bid == progress_bid,
                LearnGeneratedElement.deleted == 0,
                LearnGeneratedElement.status == 1,
            )
            .order_by(
                LearnGeneratedElement.run_event_seq.asc(),
                LearnGeneratedElement.id.asc(),
            )
            .all()
        )

    assert result.generated_blocks_total == 3
    assert result.duplicate_blocks_skipped == 1
    assert result.audio_records_total == 4
    assert result.duplicate_audios_skipped == 1
    assert result.orphan_audios_skipped == 1
    assert result.skipped_empty_blocks == 1
    assert result.elements_built == 3
    assert result.inserted_rows == 3
    assert result.run_session_bid.startswith(f"backfill_{progress_bid}_")

    assert [row.run_event_seq for row in rows] == [1, 2, 3]
    assert [row.element_type for row in rows] == ["text", "svg", "text"]
    assert [row.content_text for row in rows] == ["Before intro.", "", "After chart."]
    assert all(row.event_type == "element" for row in rows)
    assert all(row.is_final == 1 for row in rows)  # DB model uses int

    payload_1 = json.loads(rows[1].payload)
    assert payload_1["audio"] is None
    assert payload_1["previous_visuals"][0]["visual_type"] == "svg"
    assert payload_1["previous_visuals"][0]["content"].startswith("<svg")

    payload_2 = json.loads(rows[2].payload)
    assert payload_2["audio"]["audio_bid"] == "audio-backfill-1-final"
    assert payload_2["previous_visuals"] == []


def test_backfill_learn_generated_elements_for_progress_overwrite_replaces_active_rows(
    app,
):
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

    user_bid = "user-backfill-overwrite"
    shifu_bid = "shifu-backfill-overwrite"
    outline_bid = "outline-backfill-overwrite"
    progress_bid = "progress-backfill-overwrite"
    generated_block_bid = "generated-backfill-overwrite"

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
        block = LearnGeneratedBlock(
            generated_block_bid=generated_block_bid,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            block_bid="block-backfill-overwrite",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            type=BLOCK_TYPE_MDCONTENT_VALUE,
            role=ROLE_TEACHER,
            generated_content="Plain text only.",
            position=0,
            block_content_conf="",
            status=1,
        )
        existing_row = LearnGeneratedElement(
            element_bid="legacy-element",
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            generated_block_bid=generated_block_bid,
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            run_session_bid="legacy-run",
            run_event_seq=1,
            event_type="element",
            role="teacher",
            element_index=0,
            element_type="sandbox",
            element_type_code=102,
            change_type="render",
            target_element_bid="",
            is_navigable=1,
            is_final=1,
            content_text="legacy",
            payload=json.dumps({"audio": None, "previous_visuals": []}),
            status=1,
        )
        db.session.add_all([progress, block, existing_row])
        db.session.commit()

        skipped = backfill_learn_generated_elements_for_progress(app, progress_bid)
        assert skipped.skipped_existing is True
        assert skipped.existing_active_rows == 1

        overwritten = backfill_learn_generated_elements_for_progress(
            app,
            progress_bid,
            overwrite=True,
        )

        rows = (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.progress_record_bid == progress_bid,
                LearnGeneratedElement.deleted == 0,
            )
            .order_by(LearnGeneratedElement.id.asc())
            .all()
        )

    assert overwritten.skipped_existing is False
    assert overwritten.overwritten_rows == 1
    assert overwritten.inserted_rows == 1

    assert len(rows) == 2
    assert rows[0].status == 0
    assert rows[0].content_text == "legacy"
    assert rows[1].status == 1
    assert rows[1].generated_block_bid == generated_block_bid


def test_backfill_learn_generated_elements_for_progress_overwrite_dry_run_rebuilds_without_stale_rows(
    app,
):
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

    user_bid = "user-backfill-overwrite-dry-run"
    shifu_bid = "shifu-backfill-overwrite-dry-run"
    outline_bid = "outline-backfill-overwrite-dry-run"
    progress_bid = "progress-backfill-overwrite-dry-run"
    generated_block_bid = "generated-backfill-overwrite-dry-run"

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
        block = LearnGeneratedBlock(
            generated_block_bid=generated_block_bid,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            block_bid="block-backfill-overwrite-dry-run",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            type=BLOCK_TYPE_MDCONTENT_VALUE,
            role=ROLE_TEACHER,
            generated_content="Before intro.\n\n```svg\n<svg><rect /></svg>\n```\n\nAfter chart.",
            position=0,
            block_content_conf="",
            status=1,
        )
        existing_row = LearnGeneratedElement(
            element_bid="legacy-element-dry-run",
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            generated_block_bid=generated_block_bid,
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            run_session_bid="legacy-run",
            run_event_seq=1,
            event_type="element",
            role="teacher",
            element_index=0,
            element_type="text",
            element_type_code=213,
            change_type="render",
            target_element_bid="",
            is_navigable=1,
            is_final=1,
            content_text="legacy",
            payload=json.dumps({"audio": None, "previous_visuals": []}),
            status=1,
        )
        db.session.add_all([progress, block, existing_row])
        db.session.commit()

        preview = backfill_learn_generated_elements_for_progress(
            app,
            progress_bid,
            overwrite=True,
            dry_run=True,
        )

        rows = (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.progress_record_bid == progress_bid,
                LearnGeneratedElement.deleted == 0,
            )
            .order_by(LearnGeneratedElement.id.asc())
            .all()
        )

    assert preview.dry_run is True
    assert preview.existing_active_rows == 1
    assert preview.overwritten_rows == 0
    assert preview.inserted_rows == 3
    assert preview.elements_built == 3
    assert len(rows) == 1
    assert rows[0].status == 1
    assert rows[0].content_text == "legacy"
