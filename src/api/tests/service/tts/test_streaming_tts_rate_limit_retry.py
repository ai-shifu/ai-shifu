"""Provider throttling must be retried with backoff, not fail the segment.

Tencent large-model TTS returns ``LimitExceeded.AccessLimit`` for whole
bursts of concurrent segments; a burst previously lost every throttled
segment's audio. Throttled calls now retry with a staggered backoff.
"""

import types

import pytest

from flaskr.service.tts import streaming_tts
from flaskr.service.tts.streaming_tts import (
    _RATE_LIMIT_RETRY_MAX_ATTEMPTS,
    _is_retryable_rate_limit_error,
)

_TENCENT_MESSAGE = (
    "Tencent TextToVoice error LimitExceeded.AccessLimit: Your request is "
    "too frequently. Please try again later"
)


@pytest.mark.parametrize(
    "message,expected",
    [
        (_TENCENT_MESSAGE, True),
        ("HTTP 429 Too many requests", True),
        ("provider rate limit reached", True),
        ("Tencent TextToVoice error AuthFailure: bad secret", False),
        ("No audio data received", False),
    ],
)
def test_rate_limit_detector(message, expected):
    assert _is_retryable_rate_limit_error(ValueError(message)) is expected


def _run_retry(monkeypatch, outcomes, segment_index=0):
    calls = []
    sleeps = []

    def _fake_synthesize_text(**kwargs):
        calls.append(kwargs)
        outcome = outcomes[min(len(calls) - 1, len(outcomes) - 1)]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(streaming_tts, "synthesize_text", _fake_synthesize_text)
    monkeypatch.setattr(streaming_tts.time, "sleep", sleeps.append)

    generator = object.__new__(streaming_tts.StreamingTTSProcessor)
    result = streaming_tts.StreamingTTSProcessor._synthesize_text_with_retry(
        generator,
        text="hello",
        voice_settings=None,
        audio_settings=None,
        tts_provider="tencent_texttovoice",
        tts_model="large-model",
        segment_index=segment_index,
    )
    return result, calls, sleeps


def test_throttled_segment_retries_until_success(monkeypatch):
    success = types.SimpleNamespace(audio_data=b"ok")
    result, calls, sleeps = _run_retry(
        monkeypatch,
        [ValueError(_TENCENT_MESSAGE), ValueError(_TENCENT_MESSAGE), success],
    )

    assert result is success
    assert len(calls) == 3
    # Backoff grows per attempt so retrying threads spread out.
    assert len(sleeps) == 2
    assert sleeps[1] > sleeps[0] > 0


def test_throttled_segment_gives_up_after_max_attempts(monkeypatch):
    with pytest.raises(ValueError, match="LimitExceeded"):
        _run_retry(
            monkeypatch,
            [ValueError(_TENCENT_MESSAGE)] * (_RATE_LIMIT_RETRY_MAX_ATTEMPTS + 1),
        )


def test_stagger_depends_on_segment_index(monkeypatch):
    success = types.SimpleNamespace(audio_data=b"ok")
    _, _, sleeps_a = _run_retry(
        monkeypatch, [ValueError(_TENCENT_MESSAGE), success], segment_index=0
    )
    _, _, sleeps_b = _run_retry(
        monkeypatch, [ValueError(_TENCENT_MESSAGE), success], segment_index=1
    )

    assert sleeps_a[0] != sleeps_b[0]


def test_non_retryable_error_still_raises_immediately(monkeypatch):
    with pytest.raises(ValueError, match="AuthFailure"):
        _run_retry(
            monkeypatch,
            [ValueError("Tencent TextToVoice error AuthFailure: bad secret")],
        )
