import json
import types

import pytest


def _require_app(app):
    if app is None:
        pytest.skip("App fixture disabled")


def test_get_listen_element_record_returns_latest_elements_and_events(app):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.learn_dtos import AudioCompleteDTO, VariableUpdateDTO
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
            "audio_complete",
            "variable_update",
            "break",
        ]
        final_event = result_with_events.events[1]
        assert final_event.run_event_seq == 2
        assert final_event.content.is_final is True
        assert isinstance(result_with_events.events[2].content, AudioCompleteDTO)
        assert result_with_events.events[2].content.audio_bid == "audio-listen-001"
        assert isinstance(result_with_events.events[3].content, VariableUpdateDTO)
        assert result_with_events.events[3].content.variable_name == "sys_user_nickname"


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
            "audio_complete",
            "element",  # retire notification (is_new=false, is_renderable=false)
            "element",  # final visual element with correct type
            "break",
        ]

        # Verify the retire notification element
        retire_evt = streamed[2]
        assert retire_evt.content.is_new is False
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


def test_listen_adapter_finalizes_visuals_and_text_as_independent_elements(app):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.const import ROLE_TEACHER
    from flaskr.service.learn.learn_dtos import (
        AudioCompleteDTO,
        AudioSegmentDTO,
        GeneratedType,
        RunMarkdownFlowDTO,
    )
    from flaskr.service.learn.listen_elements import ListenElementRunAdapter
    from flaskr.service.learn.models import LearnGeneratedBlock
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
            if item.type == "element" and item.content.is_final and item.content.is_new
        ]

        assert [item.element_type.value for item in final_elements] == [
            "svg",
            "text",
            "html",
            "text",
        ]
        assert final_elements[0].is_marker is True
        assert final_elements[0].is_renderable is True
        assert final_elements[0].content_text == ""
        assert final_elements[1].is_marker is False
        assert final_elements[1].is_renderable is False
        assert final_elements[1].is_speakable is True
        assert final_elements[1].content_text == "After svg."
        assert final_elements[1].audio_url == "https://example.com/audio-0.mp3"
        assert final_elements[1].audio_segments == [
            {
                "position": 0,
                "segment_index": 0,
                "audio_data": "segment-0",
                "duration_ms": 350,
                "is_final": False,
            }
        ]
        assert final_elements[1].payload is not None
        assert final_elements[1].payload.audio is not None
        assert final_elements[1].payload.audio.audio_bid == "audio-final-text-0"
        assert final_elements[2].is_marker is True
        assert final_elements[2].is_renderable is True
        assert final_elements[2].content_text == ""
        assert final_elements[3].is_marker is False
        assert final_elements[3].is_renderable is False
        assert final_elements[3].is_speakable is True
        assert final_elements[3].content_text == "After html."
        assert final_elements[3].audio_url == "https://example.com/audio-1.mp3"
        assert final_elements[3].audio_segments == [
            {
                "position": 1,
                "segment_index": 0,
                "audio_data": "segment-1",
                "duration_ms": 400,
                "is_final": True,
            }
        ]
        assert final_elements[0].payload is not None
        assert final_elements[0].payload.previous_visuals[0].visual_type == "svg"
        assert final_elements[1].payload is not None
        assert final_elements[1].payload.previous_visuals == []


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
        final_element = final_elements[0]
        assert final_element.element_type == ElementType.TEXT
        assert final_element.is_renderable is False
        assert final_element.content_text == "Fallback narration."
        assert final_element.is_speakable is True
        assert final_element.audio_url == "https://example.com/fallback-audio.mp3"
        assert final_element.audio_segments == [
            {
                "position": 0,
                "segment_index": 0,
                "audio_data": "fallback-segment",
                "duration_ms": 280,
                "is_final": True,
            }
        ]
        assert final_element.payload is not None
        assert final_element.payload.audio is not None
        assert final_element.payload.audio.audio_bid == "audio-fallback-0"
        assert final_element.payload.previous_visuals == []


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
            "audio_complete",
            "element",
            "break",
        ]

        first_element = streamed[0].content
        patch_element = streamed[1].content
        audio_patch_element = streamed[2].content
        final_element = streamed[4].content

        assert first_element.is_new is True
        assert first_element.element_type == ElementType.MD_IMG
        assert "_" not in first_element.element_bid
        assert patch_element.is_new is False
        assert len(patch_element.element_bid) <= 64
        assert patch_element.element_bid != first_element.element_bid
        assert "_" not in patch_element.element_bid
        assert patch_element.target_element_bid == first_element.element_bid
        assert audio_patch_element.is_new is False
        assert len(audio_patch_element.element_bid) <= 64
        assert audio_patch_element.element_bid != first_element.element_bid
        assert "_" not in audio_patch_element.element_bid
        assert audio_patch_element.target_element_bid == first_element.element_bid
        assert audio_patch_element.audio_segments == [
            {
                "position": 0,
                "segment_index": 0,
                "audio_data": "stream-segment-0",
                "duration_ms": 240,
                "is_final": False,
            }
        ]
        assert final_element.is_new is False
        assert final_element.is_final is True
        assert final_element.target_element_bid == first_element.element_bid

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
        assert element.element_type == ElementType.MD_IMG
        assert element.is_final is True
        assert element.is_marker is True
        assert element.audio_url == "https://example.com/stream-audio.mp3"
        assert element.audio_segments == [
            {
                "position": 0,
                "segment_index": 0,
                "audio_data": "stream-segment-0",
                "duration_ms": 240,
                "is_final": False,
            }
        ]
        assert element.content_text.endswith("caption line\n")
        assert element.payload is not None
        assert len(element.payload.previous_visuals) == 1
        assert element.payload.previous_visuals[0].visual_type == "md_img"
        assert element.payload.previous_visuals[0].content.startswith("![img]")

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
        assert "audio_complete" in replay_event_types
        assert "break" in replay_event_types
        replay_audio_patch = next(
            item.content
            for item in result_with_events.events
            if item.type == "element" and item.content.audio_segments
        )
        assert replay_audio_patch.audio_segments == [
            {
                "position": 0,
                "segment_index": 0,
                "audio_data": "stream-segment-0",
                "duration_ms": 240,
                "is_final": False,
            }
        ]


def test_build_listen_elements_from_legacy_record_interleaves_visuals_and_text(app):
    _require_app(app)

    from flaskr.service.learn.learn_dtos import (
        AudioCompleteDTO,
        BlockType,
        ElementType,
        GeneratedBlockDTO,
        LearnRecordDTO,
        LikeStatus,
    )
    from flaskr.service.learn.listen_elements import (
        build_listen_elements_from_legacy_record,
    )
    from flaskr.service.tts.pipeline import build_av_segmentation_contract

    raw_content = "Before intro.\n\n<svg><text>Chart</text></svg>\n\nAfter chart."
    generated_block_bid = "generated-legacy-elements"
    av_contract = build_av_segmentation_contract(raw_content, generated_block_bid)
    legacy_record = LearnRecordDTO(
        records=[
            GeneratedBlockDTO(
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
                av_contract=av_contract,
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


def test_backfill_learn_generated_elements_for_progress_persists_clean_elements(app):
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
    assert rows[1].content_text == "Plain text only."
