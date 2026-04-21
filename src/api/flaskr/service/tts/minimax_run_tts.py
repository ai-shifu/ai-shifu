"""MiniMax RUN-level HTTP streaming TTS selection."""

from __future__ import annotations

from flaskr.common.config import get_config


def should_use_minimax_http_stream(tts_provider: str) -> bool:
    """Return whether RUN streaming should use MiniMax HTTP streaming TTS."""
    normalized = (tts_provider or "").strip().lower()
    if normalized == "default":
        normalized = ""
    if normalized and normalized != "minimax":
        return False
    return bool(get_config("MINIMAX_API_KEY"))
