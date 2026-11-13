"""Check the registry and capability declarations against expected behavior."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.api import tts as tts_api
from flaskr.api.tts.base import (
    REQUEST_SCOPED_STREAM_MINIMAX_HTTP,
    REQUEST_SCOPED_STREAM_VOLCENGINE_TIMESTAMP,
    BaseTTSProvider,
    ProviderCapabilities,
)
from flaskr.service.tts import minimax_run_tts, pipeline, streaming_tts, validation

if TYPE_CHECKING:
    import pytest

GOLDEN_REGISTRY_ORDER = (
    "minimax",
    "volcengine",
    "baidu",
    "aliyun",
    "tencent",
    "tencent_texttovoice",
    "elevenlabs",
    "gemini",
)
GOLDEN_AUTO_DETECT = ("minimax", "volcengine", "baidu", "aliyun")
GOLDEN_REQUIRES_MODEL = {
    "minimax",
    "volcengine",
    "tencent_texttovoice",
    "elevenlabs",
    "gemini",
}
GOLDEN_REQUIRES_LISTED_VOICE = {"elevenlabs", "gemini"}
GOLDEN_EMPTY_AUDIO_RETRY = {
    "elevenlabs",
    "gemini",
    "tencent",
    "tencent_texttovoice",
    "volcengine",
}
GOLDEN_NON_SPEAKABLE_SKIP = {
    "elevenlabs",
    "gemini",
    "minimax",
    "tencent",
    "tencent_texttovoice",
    "volcengine",
}
GOLDEN_CONFIG_REQUIRES_CONFIGURED = {"elevenlabs", "gemini"}
GOLDEN_CONFIG_REQUIRES_ALLOWED_MODEL = {"elevenlabs", "gemini"}
GOLDEN_SEGMENT_BYTES = {"baidu": (1024, "gbk")}


def _names_where(predicate: object) -> set[str]:
    return {
        name
        for name in tts_api.list_provider_names()
        if predicate(tts_api.get_provider_capabilities(name))
    }


def test_registry_order_and_names_match_golden() -> None:
    assert tts_api.list_provider_names() == GOLDEN_REGISTRY_ORDER
    assert set(tts_api._PROVIDER_REGISTRY) == set(GOLDEN_REGISTRY_ORDER)


def test_every_provider_declares_capabilities_explicitly() -> None:
    for name in tts_api.list_provider_names():
        provider_cls = tts_api._PROVIDER_REGISTRY[name]
        assert "capabilities" in provider_cls.__dict__, name
        assert isinstance(provider_cls.capabilities, ProviderCapabilities)
    assert BaseTTSProvider.capabilities == ProviderCapabilities()


def test_auto_detect_order_matches_golden() -> None:
    assert tts_api._AUTO_DETECT_PROVIDER_PRIORITY == GOLDEN_AUTO_DETECT
    assert tts_api._auto_detectable_provider_names() == GOLDEN_AUTO_DETECT
    assert [
        name
        for name, _cls in tts_api._iter_provider_classes(include_explicit_only=False)
    ] == list(GOLDEN_AUTO_DETECT)


def test_validation_sets_match_golden() -> None:
    assert set(validation.SUPPORTED_TTS_PROVIDERS) == set(GOLDEN_REGISTRY_ORDER)
    assert set(validation.PROVIDERS_REQUIRING_MODEL) == GOLDEN_REQUIRES_MODEL
    assert set(validation.PROVIDERS_REQUIRING_LISTED_VOICE) == (
        GOLDEN_REQUIRES_LISTED_VOICE
    )
    assert _names_where(lambda c: c.requires_model) == GOLDEN_REQUIRES_MODEL
    assert (
        _names_where(lambda c: c.requires_listed_voice) == GOLDEN_REQUIRES_LISTED_VOICE
    )


def test_config_exposure_sets_match_golden() -> None:
    assert set(tts_api._CONFIG_REQUIRES_CONFIGURED_PROVIDER) == (
        GOLDEN_CONFIG_REQUIRES_CONFIGURED
    )
    assert set(tts_api._CONFIG_REQUIRES_ALLOWED_MODEL) == (
        GOLDEN_CONFIG_REQUIRES_ALLOWED_MODEL
    )


def test_streaming_empty_audio_retry_matches_golden() -> None:
    error = ValueError("No audio data received from provider")
    retrying = {
        name
        for name in GOLDEN_REGISTRY_ORDER
        if streaming_tts._is_retryable_empty_audio_error(error, name)
    }
    assert retrying == GOLDEN_EMPTY_AUDIO_RETRY
    # The auto-detected (empty) provider stays retryable; unknown names do not.
    assert streaming_tts._is_retryable_empty_audio_error(error, "") is True
    assert streaming_tts._is_retryable_empty_audio_error(error, "unknown") is False
    assert (
        streaming_tts._is_retryable_empty_audio_error(ValueError("boom"), "gemini")
        is False
    )


def test_streaming_non_speakable_skip_matches_golden() -> None:
    skipping = {
        name
        for name in GOLDEN_REGISTRY_ORDER
        if streaming_tts._should_skip_non_speakable_tts_text("---", name)
    }
    assert skipping == GOLDEN_NON_SPEAKABLE_SKIP
    assert streaming_tts._should_skip_non_speakable_tts_text("hello", "gemini") is False
    assert streaming_tts._should_skip_non_speakable_tts_text("---", "") is False


def test_request_scoped_streams_match_golden(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _names_where(
        lambda c: c.request_scoped_stream == REQUEST_SCOPED_STREAM_VOLCENGINE_TIMESTAMP
    ) == {"volcengine"}
    assert _names_where(
        lambda c: c.request_scoped_stream == REQUEST_SCOPED_STREAM_MINIMAX_HTTP
    ) == {"minimax"}
    assert streaming_tts._should_use_volcengine_timestamp_stream("volcengine") is True
    assert streaming_tts._should_use_volcengine_timestamp_stream("VOLCENGINE ") is True
    assert streaming_tts._should_use_volcengine_timestamp_stream("minimax") is False

    monkeypatch.setattr(minimax_run_tts, "get_config", lambda _key, *_a: "key")
    assert minimax_run_tts.should_use_minimax_http_stream("minimax") is True
    assert minimax_run_tts.should_use_minimax_http_stream("") is True
    assert minimax_run_tts.should_use_minimax_http_stream("default") is True
    assert minimax_run_tts.should_use_minimax_http_stream("volcengine") is False
    monkeypatch.setattr(minimax_run_tts, "get_config", lambda _key, *_a: "")
    assert minimax_run_tts.should_use_minimax_http_stream("minimax") is False


def test_segment_byte_limits_match_golden(monkeypatch: pytest.MonkeyPatch) -> None:
    declared = {
        name: (caps.segment_max_bytes, caps.segment_encoding)
        for name in GOLDEN_REGISTRY_ORDER
        for caps in [tts_api.get_provider_capabilities(name)]
        if caps.segment_max_bytes
    }
    assert declared == GOLDEN_SEGMENT_BYTES

    monkeypatch.setattr(pipeline, "get_config", lambda _key, *_a: 300)
    long_cjk = "中" * 600  # 1200 GBK bytes, no sentence ends
    assert all(
        len(seg.encode("gbk")) <= 1024
        for seg in pipeline.split_text_for_tts(long_cjk, provider_name="baidu")
    )
    unconstrained = pipeline.split_text_for_tts(long_cjk, provider_name="aliyun")
    assert unconstrained == pipeline.split_text_for_tts(
        long_cjk, provider_name="unknown"
    )


def test_unknown_provider_gets_conservative_defaults() -> None:
    assert tts_api.get_provider_capabilities("nope") == ProviderCapabilities()
    assert tts_api.get_provider_capabilities("") == ProviderCapabilities()
    assert tts_api.get_provider_capabilities("default") == ProviderCapabilities()
