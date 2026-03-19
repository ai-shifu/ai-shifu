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
            if row.event_type == "element"
            and row.element_bid != f"el_{generated_block_bid}"
        )
        assert visual_element_bid
        assert f"el_{generated_block_bid}" not in active_element_bids


def test_listen_adapter_handles_mdflow_stream_metadata_without_av_contract(app):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.const import ROLE_TEACHER
    from flaskr.service.learn.learn_dtos import (
        AudioCompleteDTO,
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
            "audio_complete",
            "element",
            "break",
        ]

        first_element = streamed[0].content
        patch_element = streamed[1].content
        final_element = streamed[3].content

        assert first_element.is_new is True
        assert first_element.element_type == ElementType.MD_IMG
        assert patch_element.is_new is False
        assert patch_element.target_element_bid == first_element.element_bid
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
        assert element.audio_url == "https://example.com/stream-audio.mp3"
        assert element.content_text.endswith("caption line\n")
        assert element.payload is not None
        assert len(element.payload.previous_visuals) == 1
        assert element.payload.previous_visuals[0].visual_type == "md_img"
        assert element.payload.previous_visuals[0].content.startswith("![img]")


def test_build_listen_elements_from_legacy_record_without_visuals(app):
    _require_app(app)

    from flaskr.service.learn.learn_dtos import (
        AudioCompleteDTO,
        BlockType,
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

    assert len(result.elements) == 2

    first, second = result.elements

    assert first.generated_block_bid == generated_block_bid
    assert first.element_index == 0
    assert first.content_text == "Before intro."
    assert first.payload is not None
    assert first.payload.audio is not None
    assert first.payload.audio.audio_bid == "audio-legacy-0"
    assert first.payload.previous_visuals == []

    assert second.generated_block_bid == generated_block_bid
    assert second.element_index == 1
    assert second.content_text == "After chart."
    assert second.payload is not None
    assert second.payload.audio is not None
    assert second.payload.audio.audio_bid == "audio-legacy-1"
    assert len(second.payload.previous_visuals) == 1
    assert second.payload.previous_visuals[0].visual_type == "svg"
    assert second.payload.previous_visuals[0].content.startswith("<svg")


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
    assert result.elements_built == 2
    assert result.inserted_rows == 2
    assert result.run_session_bid.startswith(f"backfill_{progress_bid}_")

    assert [row.run_event_seq for row in rows] == [1, 2]
    assert [row.content_text for row in rows] == ["Before intro.", "After chart."]
    assert all(row.event_type == "element" for row in rows)
    assert all(row.is_final == 1 for row in rows)  # DB model uses int

    payload_1 = json.loads(rows[1].payload)
    assert payload_1["audio"]["audio_bid"] == "audio-backfill-1-final"
    assert payload_1["previous_visuals"][0]["visual_type"] == "svg"
    assert payload_1["previous_visuals"][0]["content"].startswith("<svg")


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
