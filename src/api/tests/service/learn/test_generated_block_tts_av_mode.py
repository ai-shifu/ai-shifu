import pytest


def _require_app(app):
    if app is None:
        pytest.skip("App fixture disabled")


def test_stream_generated_block_audio_av_mode_persists_positions(app, monkeypatch):
    _require_app(app)

    from flaskr.dao import db
    from flaskr.service.learn.learn_dtos import GeneratedType
    from flaskr.service.learn.learn_funcs import stream_generated_block_audio
    from flaskr.service.learn.models import LearnGeneratedBlock
    from flaskr.service.tts.models import LearnGeneratedAudio

    user_bid = "user-1"
    shifu_bid = "shifu-1"
    generated_block_bid = "gen-1"

    with app.app_context():
        db.session.query(LearnGeneratedAudio).delete()
        db.session.query(LearnGeneratedBlock).delete()
        db.session.commit()

        block = LearnGeneratedBlock(
            generated_block_bid=generated_block_bid,
            progress_record_bid="progress-1",
            user_bid=user_bid,
            block_bid="block-1",
            outline_item_bid="outline-1",
            shifu_bid=shifu_bid,
            type=1,
            role=1,
            generated_content="First.\n\n<svg><text>v</text></svg>\n\nSecond.",
            position=0,
            block_content_conf="",
            status=1,
        )
        db.session.add(block)
        db.session.commit()

    monkeypatch.setattr(
        "flaskr.service.learn.learn_funcs._resolve_shifu_tts_settings",
        lambda *_args, **_kwargs: (
            "minimax",
            "test-model",
            type(
                "Voice",
                (),
                {
                    "voice_id": "voice",
                    "speed": 1.0,
                    "pitch": 0,
                    "emotion": "",
                    "volume": 1.0,
                },
            )(),
            type("Audio", (), {"format": "mp3", "sample_rate": 24000})(),
        ),
    )

    def _fake_yield_tts_segments(*, text, **_kwargs):
        # Yield one provider-safe segment per speakable segment.
        yield (0, b"fake-audio", 123, text, 1, 1)

    monkeypatch.setattr(
        "flaskr.service.learn.learn_funcs._yield_tts_segments",
        _fake_yield_tts_segments,
    )
    monkeypatch.setattr(
        "flaskr.service.learn.learn_funcs.concat_audio_best_effort",
        lambda parts: b"".join(parts),
    )
    monkeypatch.setattr(
        "flaskr.service.learn.learn_funcs.get_audio_duration_ms",
        lambda *_args, **_kwargs: 1000,
    )

    def _fake_upload(_app, _audio_bytes, audio_bid):
        return (f"https://example.com/{audio_bid}.mp3", "test-bucket")

    monkeypatch.setattr(
        "flaskr.service.learn.learn_funcs.upload_audio_to_oss",
        _fake_upload,
    )
    monkeypatch.setattr(
        "flaskr.service.learn.learn_funcs.record_tts_usage",
        lambda *_args, **_kwargs: None,
    )

    events = list(
        stream_generated_block_audio(
            app,
            shifu_bid=shifu_bid,
            generated_block_bid=generated_block_bid,
            user_bid=user_bid,
            preview_mode=False,
            av_mode=True,
        )
    )

    complete_positions = [
        event.content.position
        for event in events
        if event.type == GeneratedType.AUDIO_COMPLETE
    ]
    segment_positions = [
        event.content.position
        for event in events
        if event.type == GeneratedType.AUDIO_SEGMENT
    ]

    assert complete_positions == [0, 1]
    assert segment_positions == [0, 1]

    with app.app_context():
        records = (
            LearnGeneratedAudio.query.filter(
                LearnGeneratedAudio.generated_block_bid == generated_block_bid,
                LearnGeneratedAudio.user_bid == user_bid,
                LearnGeneratedAudio.shifu_bid == shifu_bid,
                LearnGeneratedAudio.deleted == 0,
            )
            .order_by(LearnGeneratedAudio.position.asc())
            .all()
        )
        assert [r.position for r in records] == [0, 1]
        assert all(r.oss_url for r in records)
