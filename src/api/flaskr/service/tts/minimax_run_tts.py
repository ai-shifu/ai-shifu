"""MiniMax RUN-level HTTP streaming TTS selection."""

from __future__ import annotations

from flaskr.api.tts import get_provider_capabilities
from flaskr.api.tts.base import REQUEST_SCOPED_STREAM_MINIMAX_HTTP
from flaskr.common.config import get_config


def should_use_minimax_http_stream(tts_provider: str) -> bool:
    """Return whether RUN streaming should use MiniMax HTTP streaming TTS.

    An empty provider keeps the historical auto-detection behavior: MiniMax is
    the first auto-detected provider, so its HTTP stream is used whenever its
    credentials are present.
    """
    normalized = (tts_provider or "").strip().lower()
    if normalized == "default":
        normalized = ""
    if (
        normalized
        and get_provider_capabilities(normalized).request_scoped_stream
        != REQUEST_SCOPED_STREAM_MINIMAX_HTTP
    ):
        return False
    return bool(get_config("MINIMAX_API_KEY"))
