import types

import pytest
from flask import request


def _require_app(app):
    if app is None:
        pytest.skip("App fixture disabled")


def test_get_learn_record_includes_slides_and_audio_slide_ids(app):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.learn_funcs import get_learn_record
    from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS
    from flaskr.service.shifu.consts import BLOCK_TYPE_MDCONTENT_VALUE
    from flaskr.service.tts.models import (
        AUDIO_STATUS_COMPLETED,
        LearnGeneratedAudio,
    )

    user_bid = "user-slide-1"
    shifu_bid = "shifu-slide-1"
    outline_bid = "outline-slide-1"
    progress_bid = "progress-slide-1"
    generated_block_bid = "generated-slide-1"

    with app.app_context():
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
            block_bid="block-slide-1",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            type=BLOCK_TYPE_MDCONTENT_VALUE,
            role=1,
            generated_content="Before.\n\n<svg><text>v</text></svg>\n\nAfter.",
            position=0,
            block_content_conf="",
            status=1,
        )
        audio_0 = LearnGeneratedAudio(
            audio_bid="audio-slide-0",
            generated_block_bid=generated_block_bid,
            position=0,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            oss_url="https://example.com/audio-0.mp3",
            duration_ms=500,
            status=AUDIO_STATUS_COMPLETED,
        )
        audio_1 = LearnGeneratedAudio(
            audio_bid="audio-slide-1",
            generated_block_bid=generated_block_bid,
            position=1,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            oss_url="https://example.com/audio-1.mp3",
            duration_ms=600,
            status=AUDIO_STATUS_COMPLETED,
        )
        db.session.add_all([progress, block, audio_0, audio_1])
        db.session.commit()

    with app.test_request_context():
        request.user = types.SimpleNamespace(mobile="", user_id=user_bid)
        result = get_learn_record(
            app=app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
            preview_mode=False,
        )

    assert result.slides is not None
    assert len(result.slides) == 2
    assert [slide.slide_index for slide in result.slides] == [0, 1]
    assert result.slides[0].is_placeholder is True
    assert result.slides[1].visual_kind == "svg"

    assert len(result.records) == 1
    record = result.records[0]
    assert record.audio_url is None
    assert record.audios is not None
    assert [audio.position for audio in record.audios] == [0, 1]

    slide_ids = {slide.slide_id for slide in result.slides}
    assert all(audio.slide_id for audio in record.audios)
    assert all(audio.slide_id in slide_ids for audio in record.audios)
