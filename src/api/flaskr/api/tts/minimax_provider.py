"""
Minimax TTS Provider.

This module provides TTS synthesis using Minimax's Text-to-Speech API (t2a_v2).
"""

import logging
import json
import requests
from dataclasses import dataclass, field
from typing import Iterator, Optional, Dict, Any, List
from urllib.parse import urlencode

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


logger = AppLoggerProxy(logging.getLogger(__name__))

# Minimax TTS API endpoint
MINIMAX_TTS_API_URL = "https://api.minimaxi.com/v1/t2a_v2"

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


@dataclass
class MinimaxHTTPStreamChunk:
    """One parsed MiniMax HTTP streaming response event."""

    audio_data: bytes = b""
    is_final: bool = False
    duration_ms: int = 0
    sample_rate: int = 24000
    format: str = "mp3"
    word_count: int = 0
    subtitles: List[Dict[str, Any]] = field(default_factory=list)
    extra_info: Dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""


def _build_minimax_tts_url() -> str:
    group_id = get_config("MINIMAX_GROUP_ID")
    if not group_id:
        return MINIMAX_TTS_API_URL
    return f"{MINIMAX_TTS_API_URL}?{urlencode({'GroupId': group_id})}"


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


def _fetch_minimax_subtitle_file(url: str) -> List[Dict[str, Any]]:
    if not url:
        return []
    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        logger.debug("Failed to fetch MiniMax subtitle file", exc_info=True)
        return []

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("subtitles", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict) and isinstance(value.get("subtitles"), list):
                return [
                    item
                    for item in value.get("subtitles", [])
                    if isinstance(item, dict)
                ]
    return []


def _looks_like_subtitle_item(value: Dict[str, Any]) -> bool:
    if not str(value.get("text", "") or "").strip():
        return False
    return any(
        key in value
        for key in (
            "time_begin",
            "time_end",
            "start_ms",
            "end_ms",
            "start_time",
            "end_time",
            "begin",
            "end",
        )
    )


def _collect_subtitle_items(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        if _looks_like_subtitle_item(value):
            return [value]
        for key in ("subtitles", "subtitle", "data"):
            items = _collect_subtitle_items(value.get(key))
            if items:
                return items
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        return _fetch_minimax_subtitle_file(value)
    return []


def _extract_minimax_subtitles(message: Dict[str, Any]) -> List[Dict[str, Any]]:
    for container in (
        message.get("data"),
        message.get("extra_info"),
        message,
    ):
        if not isinstance(container, dict):
            continue
        for key in ("subtitles", "subtitle"):
            subtitles = _collect_subtitle_items(container.get(key))
            if subtitles:
                return subtitles
        for key in ("subtitle_file", "subtitle_url", "subtitles_url"):
            subtitles = _collect_subtitle_items(container.get(key))
            if subtitles:
                return subtitles
    return []


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

    def stream_synthesize(
        self,
        text: str,
        voice_settings: Optional[VoiceSettings] = None,
        audio_settings: Optional[AudioSettings] = None,
        model: Optional[str] = None,
    ) -> Iterator[MinimaxHTTPStreamChunk]:
        """
        Synthesize text with MiniMax HTTP streaming.

        The returned audio chunks are raw MiniMax MP3 stream bytes. Callers that
        expose chunks to browser playback must repackage them into independently
        decodable audio segments before sending them to the frontend.
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        api_key = get_config("MINIMAX_API_KEY")
        if not api_key:
            raise ValueError("MINIMAX_API_KEY is not configured")

        tts_model = _resolve_minimax_model(model)
        voice_settings = voice_settings or self.get_default_voice_settings()
        audio_settings = audio_settings or self.get_default_audio_settings()

        payload = {
            "model": tts_model,
            "text": text,
            "stream": True,
            "stream_options": {
                "exclude_aggregated_audio": True,
            },
            "voice_setting": _build_minimax_voice_setting(
                voice_settings,
                model=tts_model,
            ),
            "audio_setting": audio_settings.to_dict(),
            "subtitle_enable": True,
            "aigc_watermark": False,
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "Authorization": f"Bearer {api_key}",
        }

        acquire_tts_rpm_slot(
            provider="minimax",
            api_key=api_key,
            rpm_limit=_coerce_int_config("MINIMAX_TTS_RPM_LIMIT", 0),
            max_wait_seconds=_coerce_float_config(
                "MINIMAX_TTS_QUEUE_MAX_WAIT_SECONDS", 10.0
            ),
        )

        logger.debug(
            "Calling MiniMax HTTP streaming TTS with model=%s, text_length=%s",
            tts_model,
            len(text),
        )
        response = requests.post(
            _build_minimax_tts_url(),
            json=payload,
            headers=headers,
            stream=True,
            timeout=(10, 90),
        )
        response.raise_for_status()

        for raw_line in response.iter_lines(decode_unicode=True):
            line = str(raw_line or "").strip()
            if not line:
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
            if line == "[DONE]":
                break

            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "Invalid MiniMax HTTP streaming JSON response"
                ) from exc

            _ensure_minimax_base_resp(message, "MiniMax HTTP streaming error")
            data = message.get("data") or {}
            extra_info = message.get("extra_info") or {}
            audio_hex = data.get("audio") or ""
            try:
                audio_data = bytes.fromhex(audio_hex) if audio_hex else b""
            except ValueError as exc:
                raise ValueError("Invalid MiniMax HTTP streaming audio hex") from exc

            status = int(data.get("status") or 0)
            is_final = status == 2 or bool(extra_info) or bool(message.get("is_final"))
            subtitles = _extract_minimax_subtitles(message)
            yield MinimaxHTTPStreamChunk(
                audio_data=audio_data,
                is_final=is_final,
                duration_ms=int(extra_info.get("audio_length") or 0),
                sample_rate=int(
                    extra_info.get("audio_sample_rate")
                    or audio_settings.sample_rate
                    or 24000
                ),
                format=str(
                    extra_info.get("audio_format") or audio_settings.format or "mp3"
                ),
                word_count=int(extra_info.get("usage_characters") or 0),
                subtitles=subtitles,
                extra_info=extra_info,
                trace_id=str(message.get("trace_id") or ""),
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
        tts_model = _resolve_minimax_model(model)

        if not api_key:
            raise ValueError("MINIMAX_API_KEY is not configured")

        if not voice_settings:
            voice_settings = self.get_default_voice_settings()

        if not audio_settings:
            audio_settings = self.get_default_audio_settings()

        # Build voice setting dict for Minimax API
        voice_setting_dict = _build_minimax_voice_setting(
            voice_settings,
            model=tts_model,
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

        response = requests.post(
            _build_minimax_tts_url(), json=payload, headers=headers, timeout=60
        )
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
