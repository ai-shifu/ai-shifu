"""MiniMax RUN-level WebSocket TTS orchestration."""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from flaskr.api.tts import AudioSettings, TTSResult, VoiceSettings
from flaskr.api.tts.minimax_provider import MinimaxTTSProvider
from flaskr.common.config import get_config
from flaskr.common.log import AppLoggerProxy
from flaskr.service.tts.rpm_gate import TTSRpmQueueTimeout


logger = AppLoggerProxy(logging.getLogger(__name__))


class MinimaxRunTTSDisabled(RuntimeError):
    """Raised after the MiniMax RUN WebSocket TTS path has been disabled."""


class MinimaxRunTTSManager:
    """Serializes all MiniMax WebSocket TTS sends for one RUN."""

    def __init__(
        self,
        *,
        voice_settings: VoiceSettings,
        audio_settings: AudioSettings,
        model: str = "",
        session_factory: Optional[Callable[[], object]] = None,
    ):
        self._voice_settings = voice_settings
        self._audio_settings = audio_settings
        self._model = model or ""
        self._session_factory = session_factory
        self._session = None
        self._disabled = False
        self._closed = False
        self._lock = threading.RLock()

    @property
    def is_disabled(self) -> bool:
        with self._lock:
            return self._disabled or self._closed

    def synthesize(self, text: str) -> TTSResult:
        """Synthesize one sentence/segment over the RUN WebSocket session."""
        with self._lock:
            if self._disabled or self._closed:
                raise MinimaxRunTTSDisabled("MiniMax RUN TTS is disabled")

            try:
                return self._synthesize_locked(text)
            except TTSRpmQueueTimeout:
                self._disable_locked()
                raise
            except Exception as first_error:
                logger.warning(
                    "MiniMax WebSocket TTS segment failed; reconnecting once: %s",
                    first_error,
                )
                self._close_session_locked()

            try:
                return self._synthesize_locked(text)
            except TTSRpmQueueTimeout:
                self._disable_locked()
                raise
            except Exception as second_error:
                self._disable_locked()
                raise MinimaxRunTTSDisabled(
                    f"MiniMax RUN TTS failed after reconnect: {second_error}"
                ) from second_error

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._close_session_locked()

    def _synthesize_locked(self, text: str) -> TTSResult:
        session = self._ensure_session_locked()
        return session.synthesize_segment(text)

    def _ensure_session_locked(self):
        if self._session is not None:
            return self._session
        session = self._create_session()
        session.open()
        self._session = session
        return session

    def _create_session(self):
        if self._session_factory is not None:
            return self._session_factory()
        return MinimaxTTSProvider().create_websocket_session(
            voice_settings=self._voice_settings,
            audio_settings=self._audio_settings,
            model=self._model,
        )

    def _disable_locked(self) -> None:
        self._disabled = True
        self._close_session_locked()

    def _close_session_locked(self) -> None:
        session = self._session
        self._session = None
        if session is None:
            return
        try:
            session.close()
        except Exception:
            logger.debug("Failed to close MiniMax RUN TTS session", exc_info=True)


def should_use_minimax_run_websocket(tts_provider: str) -> bool:
    """Return whether the RUN streaming path should use MiniMax WebSocket TTS."""
    normalized = (tts_provider or "").strip().lower()
    if normalized == "default":
        normalized = ""
    if normalized and normalized != "minimax":
        return False
    return bool(get_config("MINIMAX_API_KEY"))
