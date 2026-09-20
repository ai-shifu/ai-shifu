"""Exercise Tencent transport cleanup, malformed streams and synthesis accounting."""

from collections.abc import Iterator
from unittest.mock import Mock

import pytest
import requests
from flaskr.api.tts import tencent_provider as tencent


class StreamingResponse:
    """Provide a finite provider stream and observable connection cleanup."""

    def __init__(self, lines: list, error: Exception | None = None) -> None:
        """Store response lines and an optional HTTP status failure."""
        self.lines = lines
        self.error = error
        self.closed = False

    def raise_for_status(self) -> None:
        if self.error:
            raise self.error

    def iter_lines(self, *, decode_unicode: bool) -> Iterator:
        assert decode_unicode
        yield from self.lines

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> tencent.TencentTTSProvider:
    settings = {
        "TENCENT_TTS_APP_ID": "1234",
        "TENCENT_TTS_SECRET_ID": "test-id",
        "TENCENT_TTS_SECRET_KEY": "test-key",
    }
    monkeypatch.setattr(
        tencent, "get_config", lambda key, default=None: settings.get(key, default)
    )
    return tencent.TencentTTSProvider()


def test_http_error_closes_response_before_propagating(
    provider: tencent.TencentTTSProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    error = requests.HTTPError("provider unavailable")
    response = StreamingResponse([], error=error)
    monkeypatch.setattr(tencent.requests, "post", Mock(return_value=response))
    with pytest.raises(requests.HTTPError, match="provider unavailable"):
        list(provider.stream_synthesize("hello"))
    assert response.closed
