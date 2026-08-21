"""Verify TTS error mapping behavior."""

import logging
from collections.abc import Iterator

import pytest
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.learn.learn_funcs import _yield_with_tts_error_mapping
from flaskr.service.tts.rpm_gate import TTSRpmQueueTimeoutError


def test_rpm_queue_timeout_maps_to_rate_limited_not_unknown(app, caplog) -> None:
    def _body() -> Iterator[None]:
        message = "TTS RPM queue wait exceeded 10.00s"
        raise TTSRpmQueueTimeoutError(message)
        yield  # pragma: no cover

    with (
        app.app_context(),
        caplog.at_level(logging.WARNING),
        pytest.raises(AppError) as exc_info,
    ):
        list(
            _yield_with_tts_error_mapping(
                app,
                unknown_error_log="AV TTS synthesis failed",
                body=_body,
            )
        )

    # Backpressure surfaces as the dedicated retryable code, not a generic 500.
    assert exc_info.value.code == ERROR_CODE["server.learn.ttsRateLimited"]
    assert exc_info.value.code != ERROR_CODE["server.common.unknownError"]
    # It is not escalated to ERROR (which would page ops via the Feishu handler).
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_unexpected_error_still_maps_to_unknown_error(app, caplog) -> None:
    def _body() -> Iterator[None]:
        message = "tts worker crashed"
        raise RuntimeError(message)
        yield  # pragma: no cover

    with (
        app.app_context(),
        caplog.at_level(logging.ERROR),
        pytest.raises(AppError) as exc_info,
    ):
        list(
            _yield_with_tts_error_mapping(
                app,
                unknown_error_log="AV TTS synthesis failed",
                body=_body,
            )
        )

    assert exc_info.value.code == ERROR_CODE["server.common.unknownError"]
