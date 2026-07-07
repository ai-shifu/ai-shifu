import logging

import pytest

from flaskr.service.common.models import AppException, ERROR_CODE
from flaskr.service.learn.learn_funcs import _yield_with_tts_error_mapping
from flaskr.service.tts.rpm_gate import TTSRpmQueueTimeout


def test_rpm_queue_timeout_maps_to_rate_limited_not_unknown(app, caplog):
    def _body():
        raise TTSRpmQueueTimeout("TTS RPM queue wait exceeded 10.00s")
        yield  # pragma: no cover

    with app.app_context():
        with caplog.at_level(logging.WARNING):
            with pytest.raises(AppException) as exc_info:
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


def test_unexpected_error_still_maps_to_unknown_error(app, caplog):
    def _body():
        raise RuntimeError("tts worker crashed")
        yield  # pragma: no cover

    with app.app_context():
        with caplog.at_level(logging.ERROR):
            with pytest.raises(AppException) as exc_info:
                list(
                    _yield_with_tts_error_mapping(
                        app,
                        unknown_error_log="AV TTS synthesis failed",
                        body=_body,
                    )
                )

    assert exc_info.value.code == ERROR_CODE["server.common.unknownError"]
