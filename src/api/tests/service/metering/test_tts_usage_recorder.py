from __future__ import annotations

from types import SimpleNamespace

from flask import Flask

from flaskr.service.metering import UsageContext, record_tts_usage
from flaskr.service.tts.tts_usage_recorder import (
    record_tts_aggregated_usage,
    record_tts_segment_usage,
)


def _voice_settings():
    return SimpleNamespace(
        voice_id="voice-1",
        speed=1.0,
        pitch=0,
        emotion="",
        volume=1.0,
    )


def _audio_settings():
    return SimpleNamespace(format="mp3", sample_rate=32000)


def test_record_tts_usage_persists_supplied_output_without_provider_mapping(
    monkeypatch,
):
    app = Flask(__name__)
    captured = {}
    enqueued = []

    monkeypatch.setattr(
        "flaskr.service.metering.recorder.generate_id",
        lambda _app: "usage-tts-explicit-output",
    )
    monkeypatch.setattr(
        "flaskr.service.metering.recorder._resolve_billable",
        lambda _app, *, context, usage_scene: 1,
    )
    monkeypatch.setattr(
        "flaskr.service.metering.recorder._persist_usage_record",
        lambda _app, record: captured.setdefault("record", record) or True,
    )
    monkeypatch.setattr(
        "flaskr.service.metering.recorder._enqueue_usage_settlement",
        lambda _app, *, usage_bid: enqueued.append(usage_bid),
    )

    usage_bid = record_tts_usage(
        app,
        UsageContext(user_bid="user-1", shifu_bid="shifu-1"),
        provider="minimax",
        model="speech-2.8-turbo",
        is_stream=True,
        input=12,
        output=7,
        total=7,
        word_count=13,
        duration_ms=1000,
    )

    record = captured["record"]
    assert usage_bid == "usage-tts-explicit-output"
    assert record.input == 12
    assert record.output == 7
    assert record.total == 7
    assert record.word_count == 13
    assert enqueued == ["usage-tts-explicit-output"]


def test_record_tts_segment_usage_uses_usage_characters_for_output(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        "flaskr.service.tts.tts_usage_recorder.record_tts_usage",
        lambda _app, _context, **kwargs: captured.setdefault("kwargs", kwargs),
    )

    record_tts_segment_usage(
        Flask(__name__),
        UsageContext(user_bid="user-1", shifu_bid="shifu-1"),
        provider="minimax",
        model="speech-2.8-turbo",
        segment_text="local text",
        word_count=52,
        usage_characters=26,
        duration_ms=1000,
        latency_ms=12,
        voice_settings=_voice_settings(),
        audio_settings=_audio_settings(),
        is_stream=True,
        parent_usage_bid="usage-parent-1",
        segment_index=0,
    )

    kwargs = captured["kwargs"]
    assert kwargs["input"] == len("local text")
    assert kwargs["output"] == 26
    assert kwargs["total"] == 26
    assert kwargs["word_count"] == 52


def test_record_tts_segment_usage_falls_back_to_local_length(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        "flaskr.service.tts.tts_usage_recorder.record_tts_usage",
        lambda _app, _context, **kwargs: captured.setdefault("kwargs", kwargs),
    )

    record_tts_segment_usage(
        Flask(__name__),
        UsageContext(user_bid="user-1", shifu_bid="shifu-1"),
        provider="volcengine",
        model="seed-tts-2.0",
        segment_text="local text",
        word_count=2,
        usage_characters=0,
        duration_ms=1000,
        latency_ms=12,
        voice_settings=_voice_settings(),
        audio_settings=_audio_settings(),
        is_stream=True,
        parent_usage_bid="usage-parent-1",
        segment_index=0,
    )

    kwargs = captured["kwargs"]
    assert kwargs["output"] == len("local text")
    assert kwargs["total"] == len("local text")
    assert kwargs["word_count"] == 2


def test_record_tts_aggregated_usage_uses_total_usage_characters(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        "flaskr.service.tts.tts_usage_recorder.record_tts_usage",
        lambda _app, _context, **kwargs: captured.setdefault("kwargs", kwargs),
    )

    record_tts_aggregated_usage(
        Flask(__name__),
        UsageContext(user_bid="user-1", shifu_bid="shifu-1"),
        usage_bid="usage-parent-1",
        provider="minimax",
        model="speech-2.8-turbo",
        raw_text="raw text",
        cleaned_text="localtext",
        total_word_count=52,
        total_usage_characters=26,
        duration_ms=1000,
        segment_count=2,
        voice_settings=_voice_settings(),
        audio_settings=_audio_settings(),
        is_stream=True,
    )

    kwargs = captured["kwargs"]
    assert kwargs["input"] == len("raw text")
    assert kwargs["output"] == 26
    assert kwargs["total"] == 26
    assert kwargs["word_count"] == 52
