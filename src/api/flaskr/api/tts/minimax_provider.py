"""
Minimax TTS Provider.

This module provides TTS synthesis using Minimax's Text-to-Speech API (t2a_v2).
"""

import logging
import json
import requests
from typing import Optional, Dict, Any, List

from flaskr.common.config import get_config
from flaskr.common.log import AppLoggerProxy
from flaskr.api.tts.base import (
    BaseTTSProvider,
    TTSResult,
    VoiceSettings,
    AudioSettings,
    ProviderConfig,
    ParamRange,
)
from flaskr.service.tts.rpm_gate import acquire_tts_rpm_slot

try:
    import websocket
except ImportError:  # pragma: no cover - dependency is present in runtime images
    websocket = None


logger = AppLoggerProxy(logging.getLogger(__name__))

# Minimax TTS API endpoint
MINIMAX_TTS_API_URL = "https://api.minimax.chat/v1/t2a_v2"
MINIMAX_TTS_WS_URL = "wss://api.minimaxi.com/ws/v1/t2a_v2"

# Allowed emotion values for Minimax TTS
MINIMAX_ALLOWED_EMOTIONS = [
    "happy",
    "sad",
    "angry",
    "fearful",
    "disgusted",
    "surprised",
    "calm",
    "neutral",
    "fluent",
    "whisper",
]

# Minimax TTS models
MINIMAX_MODELS = [
    {"value": "speech-2.8-turbo", "label": "Speech-2.8-Turbo"},
    {"value": "speech-2.8-hd", "label": "Speech-2.8-HD"},
    {"value": "speech-2.6-turbo", "label": "Speech-2.6-Turbo"},
    {"value": "speech-2.6-hd", "label": "Speech-2.6-HD"},
    {"value": "speech-01-turbo", "label": "Speech-01-Turbo"},
    {"value": "speech-01-hd", "label": "Speech-01-HD"},
    {"value": "speech-02-turbo", "label": "Speech-02-Turbo"},
    {"value": "speech-02-hd", "label": "Speech-02-HD"},
]

# Minimax TTS voices
MINIMAX_VOICES = [
    {"value": "male-qn-qingse", "label": "青涩青年音色"},
    {"value": "male-qn-jingying", "label": "精英青年音色"},
    {"value": "male-qn-badao", "label": "霸道青年音色"},
    {"value": "male-qn-daxuesheng", "label": "青年大学生音色"},
    {"value": "female-shaonv", "label": "少女音色"},
    {"value": "female-yujie", "label": "御姐音色"},
    {"value": "female-chengshu", "label": "成熟女性音色"},
    {"value": "female-tianmei", "label": "甜美女性音色"},
    {"value": "presenter_male", "label": "男性主持人"},
    {"value": "presenter_female", "label": "女性主持人"},
    {"value": "audiobook_male_1", "label": "男性有声书1"},
    {"value": "audiobook_male_2", "label": "男性有声书2"},
    {"value": "audiobook_female_1", "label": "女性有声书1"},
    {"value": "audiobook_female_2", "label": "女性有声书2"},
]

# Minimax emotions for frontend
MINIMAX_EMOTIONS = [
    {"value": "neutral", "label": "中性"},
    {"value": "happy", "label": "开心"},
    {"value": "sad", "label": "悲伤"},
    {"value": "angry", "label": "愤怒"},
    {"value": "fearful", "label": "恐惧"},
    {"value": "disgusted", "label": "厌恶"},
    {"value": "surprised", "label": "惊讶"},
    {"value": "calm", "label": "平静"},
]


def _resolve_minimax_model(model: Optional[str]) -> str:
    valid_models = {m["value"] for m in MINIMAX_MODELS}
    requested_model = (model or "").strip()
    if requested_model and requested_model not in valid_models:
        logger.warning(
            "Ignoring invalid Minimax TTS model: %s (falling back to default)",
            requested_model,
        )
        requested_model = ""
    return requested_model or "speech-01-turbo"


def _build_minimax_voice_setting(
    voice_settings: VoiceSettings,
    *,
    model: str,
    websocket_mode: bool = False,
) -> Dict[str, Any]:
    voice_setting_dict: Dict[str, Any] = {
        "voice_id": voice_settings.voice_id,
        "speed": voice_settings.speed,
        "vol": voice_settings.volume,
    }
    if voice_settings.pitch is not None:
        voice_setting_dict["pitch"] = int(voice_settings.pitch)

    emotion = (voice_settings.emotion or "").strip()
    if not emotion or emotion == "neutral" or emotion not in MINIMAX_ALLOWED_EMOTIONS:
        return voice_setting_dict

    if websocket_mode:
        if model.startswith("speech-2.8") and emotion == "whisper":
            return voice_setting_dict
        voice_setting_dict["emotion"] = emotion
        return voice_setting_dict

    if model.startswith("speech-01"):
        voice_setting_dict["emotion"] = emotion
    return voice_setting_dict


def _coerce_int_config(name: str, default: int) -> int:
    try:
        return int(get_config(name) or default)
    except (TypeError, ValueError):
        return default


def _coerce_float_config(name: str, default: float) -> float:
    try:
        return float(get_config(name) or default)
    except (TypeError, ValueError):
        return default


class MinimaxWebSocketTTSSession:
    """A single MiniMax WebSocket TTS task session."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        voice_settings: VoiceSettings,
        audio_settings: AudioSettings,
        rpm_limit: int,
        queue_max_wait_seconds: float,
        connect_timeout_seconds: float = 10.0,
        receive_timeout_seconds: float = 60.0,
    ):
        if websocket is None:
            raise ValueError("websocket-client is required for MiniMax WebSocket TTS")
        if not api_key:
            raise ValueError("MINIMAX_API_KEY is not configured")

        self._api_key = api_key
        self._model = _resolve_minimax_model(model)
        self._voice_settings = voice_settings
        self._audio_settings = audio_settings
        self._rpm_limit = int(rpm_limit or 0)
        self._queue_max_wait_seconds = float(queue_max_wait_seconds or 0)
        self._connect_timeout_seconds = float(connect_timeout_seconds or 10.0)
        self._receive_timeout_seconds = float(receive_timeout_seconds or 60.0)
        self._ws = None
        self._started = False

    def open(self) -> None:
        """Open the socket and send `task_start` after acquiring the RPM gate."""
        if self._started and self._ws is not None:
            return

        headers = [
            "Content-Type: application/json",
            f"Authorization: Bearer {self._api_key}",
        ]
        self._ws = websocket.create_connection(
            MINIMAX_TTS_WS_URL,
            header=headers,
            timeout=self._connect_timeout_seconds,
        )
        self._ws.settimeout(self._receive_timeout_seconds)

        connected = self._recv_json()
        self._ensure_event(connected, "connected_success")

        self._acquire_gate()
        self._send_json(
            {
                "event": "task_start",
                "model": self._model,
                "voice_setting": _build_minimax_voice_setting(
                    self._voice_settings,
                    model=self._model,
                    websocket_mode=True,
                ),
                "audio_setting": self._audio_settings.to_dict(),
            }
        )
        started = self._recv_json()
        self._ensure_event(started, "task_started")
        self._started = True

    def synthesize_segment(self, text: str) -> TTSResult:
        """Send one `task_continue` and collect all returned audio chunks."""
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")
        if not self._started or self._ws is None:
            self.open()

        self._acquire_gate()
        self._send_json({"event": "task_continue", "text": text})

        audio_chunks: list[bytes] = []
        extra_info: Dict[str, Any] = {}
        while True:
            message = self._recv_json()
            event = message.get("event")
            if event and event != "task_continued":
                raise ValueError(f"Unexpected MiniMax WebSocket event: {event}")

            data = message.get("data") or {}
            audio_hex = data.get("audio")
            if audio_hex:
                audio_chunks.append(bytes.fromhex(audio_hex))
            if message.get("extra_info"):
                extra_info = message.get("extra_info") or {}
            if message.get("is_final"):
                break

        audio_data = b"".join(audio_chunks)
        if not audio_data:
            raise ValueError("No audio data in MiniMax WebSocket response")

        duration_ms = int(extra_info.get("audio_length") or 0)
        sample_rate = int(
            extra_info.get("audio_sample_rate")
            or self._audio_settings.sample_rate
            or 24000
        )
        audio_format = str(
            extra_info.get("audio_format") or self._audio_settings.format or "mp3"
        )
        word_count = int(extra_info.get("usage_characters") or 0)

        logger.info(
            "MiniMax WebSocket TTS segment completed: duration=%sms, size=%s bytes, usage_characters=%s",
            duration_ms,
            len(audio_data),
            word_count,
        )
        return TTSResult(
            audio_data=audio_data,
            duration_ms=duration_ms,
            sample_rate=sample_rate,
            format=audio_format,
            word_count=word_count,
        )

    def close(self) -> None:
        """Finish the MiniMax task and close the socket."""
        ws = self._ws
        self._ws = None
        self._started = False
        if ws is None:
            return
        try:
            ws.settimeout(10)
            ws.send(json.dumps({"event": "task_finish"}, ensure_ascii=False))
            message = self._recv_json_from(ws)
            if message.get("event"):
                self._ensure_event(message, "task_finished")
        except Exception:
            logger.debug(
                "MiniMax WebSocket task_finish failed during close", exc_info=True
            )
        finally:
            try:
                ws.close()
            except Exception:
                logger.debug("MiniMax WebSocket close failed", exc_info=True)

    def _acquire_gate(self) -> None:
        acquire_tts_rpm_slot(
            provider="minimax",
            api_key=self._api_key,
            rpm_limit=self._rpm_limit,
            max_wait_seconds=self._queue_max_wait_seconds,
        )

    def _send_json(self, payload: Dict[str, Any]) -> None:
        if self._ws is None:
            raise ValueError("MiniMax WebSocket is not connected")
        self._ws.send(json.dumps(payload, ensure_ascii=False))

    def _recv_json(self) -> Dict[str, Any]:
        if self._ws is None:
            raise ValueError("MiniMax WebSocket is not connected")
        return self._recv_json_from(self._ws)

    def _recv_json_from(self, ws) -> Dict[str, Any]:
        raw = ws.recv()
        if not raw:
            raise ValueError("Empty MiniMax WebSocket response")
        try:
            message = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid MiniMax WebSocket JSON response") from exc

        if message.get("event") == "task_failed":
            raise ValueError(
                _format_minimax_error(message, "MiniMax WebSocket task failed")
            )
        _ensure_minimax_base_resp(message, "MiniMax WebSocket error")
        return message

    @staticmethod
    def _ensure_event(message: Dict[str, Any], expected_event: str) -> None:
        actual_event = message.get("event")
        if actual_event != expected_event:
            raise ValueError(
                f"Unexpected MiniMax WebSocket event: expected={expected_event}, actual={actual_event}"
            )


def _ensure_minimax_base_resp(message: Dict[str, Any], prefix: str) -> None:
    base_resp = message.get("base_resp") or {}
    status_code = int(base_resp.get("status_code") or 0)
    if status_code != 0:
        raise ValueError(_format_minimax_error(message, prefix))


def _format_minimax_error(message: Dict[str, Any], prefix: str) -> str:
    base_resp = message.get("base_resp") or {}
    status_code = base_resp.get("status_code", "unknown")
    status_msg = base_resp.get("status_msg", "Unknown error")
    trace_id = message.get("trace_id") or ""
    trace_suffix = f", trace_id={trace_id}" if trace_id else ""
    return f"{prefix}: {status_code} - {status_msg}{trace_suffix}"


class MinimaxTTSProvider(BaseTTSProvider):
    """TTS provider using Minimax API."""

    @property
    def provider_name(self) -> str:
        return "MiniMax"

    def is_configured(self) -> bool:
        """Check if Minimax TTS is properly configured."""
        api_key = get_config("MINIMAX_API_KEY")
        return bool(api_key)

    def get_default_voice_settings(self) -> VoiceSettings:
        """Get default voice settings.

        Notes:
        - Per-Shifu voice settings are stored in the database.
        - This method only provides a provider-level fallback when callers do not
          specify a voice_id/speed/pitch/emotion.
        """
        return VoiceSettings(
            voice_id="male-qn-qingse",
            speed=1.0,
            pitch=0,
            emotion="",
            volume=1.0,
        )

    def get_default_audio_settings(self) -> AudioSettings:
        """Get default audio settings from configuration."""
        return AudioSettings(
            format="mp3",
            sample_rate=get_config("MINIMAX_TTS_SAMPLE_RATE") or 24000,
            bitrate=get_config("MINIMAX_TTS_BITRATE") or 128000,
            channel=1,
        )

    def get_supported_emotions(self) -> List[str]:
        """Get list of supported emotions."""
        return MINIMAX_ALLOWED_EMOTIONS

    def synthesize(
        self,
        text: str,
        voice_settings: Optional[VoiceSettings] = None,
        audio_settings: Optional[AudioSettings] = None,
        model: Optional[str] = None,
    ) -> TTSResult:
        """
        Synthesize text to speech using Minimax TTS.

        Args:
            text: Text to synthesize
            voice_settings: Voice settings (optional)
            audio_settings: Audio settings (optional)
            model: TTS model name (optional, defaults to config)

        Returns:
            TTSResult with audio data and metadata

        Raises:
            ValueError: If synthesis fails
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        # Call API with hex output format
        result = self._call_api(
            text=text,
            voice_settings=voice_settings,
            audio_settings=audio_settings,
            output_format="hex",
            model=model,
        )

        # Extract audio data
        data = result.get("data", {})
        audio_hex = data.get("audio")

        if not audio_hex:
            raise ValueError("No audio data in API response")

        # Decode hex to bytes
        audio_data = bytes.fromhex(audio_hex)

        # Extract metadata
        extra_info = result.get("extra_info", {})
        duration_ms = extra_info.get("audio_length", 0)
        sample_rate = extra_info.get("audio_sample_rate", 24000)
        audio_format = extra_info.get("audio_format", "mp3")
        word_count = extra_info.get("usage_characters", 0)

        logger.info(
            f"Minimax TTS synthesis completed: duration={duration_ms}ms, "
            f"size={len(audio_data)} bytes, usage_characters={word_count}, extra_info={extra_info}"
        )

        return TTSResult(
            audio_data=audio_data,
            duration_ms=duration_ms,
            sample_rate=sample_rate,
            format=audio_format,
            word_count=word_count,
        )

    def _call_api(
        self,
        text: str,
        voice_settings: Optional[VoiceSettings] = None,
        audio_settings: Optional[AudioSettings] = None,
        output_format: str = "hex",
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Call Minimax TTS API.

        Args:
            text: Text to synthesize
            voice_settings: Voice settings (default from config)
            audio_settings: Audio settings (default from config)
            output_format: Output format - "hex" or "url"
            model: TTS model name (optional, defaults to config)

        Returns:
            API response dictionary

        Raises:
            ValueError: If API key is not configured
            requests.RequestException: If API call fails
        """
        api_key = get_config("MINIMAX_API_KEY")
        group_id = get_config("MINIMAX_GROUP_ID")
        tts_model = _resolve_minimax_model(model)

        if not api_key:
            raise ValueError("MINIMAX_API_KEY is not configured")

        if not voice_settings:
            voice_settings = self.get_default_voice_settings()

        if not audio_settings:
            audio_settings = self.get_default_audio_settings()

        # Build API URL with group ID if provided
        url = MINIMAX_TTS_API_URL
        if group_id:
            url = f"{url}?GroupId={group_id}"

        # Build voice setting dict for Minimax API
        voice_setting_dict = _build_minimax_voice_setting(
            voice_settings,
            model=tts_model,
            websocket_mode=False,
        )

        # Build request payload
        payload = {
            "model": tts_model,
            "text": text,
            "stream": False,
            "voice_setting": voice_setting_dict,
            "audio_setting": audio_settings.to_dict(),
            "output_format": output_format,
            "subtitle_enable": False,
            "aigc_watermark": False,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        logger.debug(
            f"Calling Minimax TTS API with model={tts_model}, text_length={len(text)}"
        )

        response = requests.post(url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()

        result = response.json()

        # Check for API errors
        base_resp = result.get("base_resp", {})
        status_code = base_resp.get("status_code", 0)
        if status_code != 0:
            status_msg = base_resp.get("status_msg", "Unknown error")
            logger.error(f"Minimax TTS API error: {status_code} - {status_msg}")
            raise ValueError(f"Minimax TTS API error: {status_code} - {status_msg}")

        return result

    def create_websocket_session(
        self,
        *,
        voice_settings: Optional[VoiceSettings] = None,
        audio_settings: Optional[AudioSettings] = None,
        model: Optional[str] = None,
    ) -> MinimaxWebSocketTTSSession:
        """Create one WebSocket TTS task session for RUN streaming."""
        api_key = get_config("MINIMAX_API_KEY")
        if not api_key:
            raise ValueError("MINIMAX_API_KEY is not configured")
        return MinimaxWebSocketTTSSession(
            api_key=api_key,
            model=_resolve_minimax_model(model),
            voice_settings=voice_settings or self.get_default_voice_settings(),
            audio_settings=audio_settings or self.get_default_audio_settings(),
            rpm_limit=_coerce_int_config("MINIMAX_TTS_RPM_LIMIT", 0),
            queue_max_wait_seconds=_coerce_float_config(
                "MINIMAX_TTS_QUEUE_MAX_WAIT_SECONDS", 10.0
            ),
        )

    def get_provider_config(self) -> ProviderConfig:
        """Get Minimax provider configuration for frontend."""
        return ProviderConfig(
            name="MiniMax",
            label="MiniMax",
            speed=ParamRange(min=0.5, max=2.0, step=0.1, default=1.0),
            pitch=ParamRange(min=-12, max=12, step=1, default=0),
            supports_emotion=True,
            models=MINIMAX_MODELS,
            voices=MINIMAX_VOICES,
            emotions=MINIMAX_EMOTIONS,
        )
