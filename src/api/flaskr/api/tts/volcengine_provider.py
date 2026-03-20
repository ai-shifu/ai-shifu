"""
Volcengine TTS Provider.

This module provides TTS synthesis using Volcengine's bidirectional
WebSocket TTS API (ByteDance/Doubao).

API Reference:
- WebSocket URL: wss://openspeech.bytedance.com/api/v3/tts/bidirection
- Uses custom binary protocol for frame encoding/decoding
"""

import uuid
import logging
import threading
from typing import Optional, List

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
from flaskr.api.tts.volcengine_protocol import (
    VolcengineProtocol,
    Event,
    MessageType,
)

try:
    import websocket

    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False
    websocket = None


logger = AppLoggerProxy(logging.getLogger(__name__))

# Volcengine TTS WebSocket endpoint
VOLCENGINE_TTS_WS_URL = "wss://openspeech.bytedance.com/api/v3/tts/bidirection"

# Volcengine TTS models
VOLCENGINE_MODELS = [
    # Resource IDs used in the WebSocket handshake header (X-Api-Resource-Id).
    {"value": "seed-tts-1.0", "label": "Seed-TTS-1.0 (resource)"},
    {"value": "seed-tts-2.0", "label": "Seed-TTS-2.0 (resource)"},
    {"value": "seed-icl-1.0", "label": "Seed-ICL-1.0 (resource)"},
]

# Volcengine recommended voices
VOLCENGINE_VOICES = [
    # Seed-TTS 1.0 voices
    {
        "value": "zh_female_shuangkuaisisi_moon_bigtts",
        "label": "[1.0] 爽快思思 (女)",
        "resource_id": "seed-tts-1.0",
    },
    {
        "value": "zh_male_abin_moon_bigtts",
        "label": "[1.0] 阿斌 (男)",
        "resource_id": "seed-tts-1.0",
    },
    {
        "value": "zh_female_cancan_mars_bigtts",
        "label": "[1.0] 灿灿 (女)",
        "resource_id": "seed-tts-1.0",
    },
    {
        "value": "zh_male_ahu_conversation_wvae_bigtts",
        "label": "[1.0] 阿虎 (男)",
        "resource_id": "seed-tts-1.0",
    },
    {
        "value": "zh_female_wanwanxiaohe_moon_bigtts",
        "label": "[1.0] 弯弯小何 (女)",
        "resource_id": "seed-tts-1.0",
    },
    {
        "value": "zh_male_shaonian_mars_bigtts",
        "label": "[1.0] 少年 (男)",
        "resource_id": "seed-tts-1.0",
    },
    {
        "value": "zh_female_linjie_moon_bigtts",
        "label": "[1.0] 邻家姐姐 (女)",
        "resource_id": "seed-tts-1.0",
    },
    {
        "value": "zh_male_yangguang_moon_bigtts",
        "label": "[1.0] 阳光男声 (男)",
        "resource_id": "seed-tts-1.0",
    },
    # Seed-TTS 2.0 voices (examples, extend as needed)
    {
        "value": "zh_female_vv_uranus_bigtts",
        "label": "[2.0] Vivi 2.0 (女)",
        "resource_id": "seed-tts-2.0",
    },
    {
        "value": "zh_female_xiaohe_uranus_bigtts",
        "label": "[2.0] 小何 (女)",
        "resource_id": "seed-tts-2.0",
    },
    {
        "value": "zh_male_m191_uranus_bigtts",
        "label": "[2.0] 云舟 (男)",
        "resource_id": "seed-tts-2.0",
    },
    {
        "value": "zh_male_taocheng_uranus_bigtts",
        "label": "[2.0] 小天 (男)",
        "resource_id": "seed-tts-2.0",
    },
    {
        "value": "zh_male_dayi_saturn_bigtts",
        "label": "[2.0] 大壹 (男)",
        "resource_id": "seed-tts-2.0",
    },
    {
        "value": "zh_female_mizai_saturn_bigtts",
        "label": "[2.0] 黑猫侦探社咪仔 (女)",
        "resource_id": "seed-tts-2.0",
    },
    {
        "value": "zh_female_jitangnv_saturn_bigtts",
        "label": "[2.0] 鸡汤女 (女)",
        "resource_id": "seed-tts-2.0",
    },
    {
        "value": "zh_female_meilinvyou_saturn_bigtts",
        "label": "[2.0] 魅力女友 (女)",
        "resource_id": "seed-tts-2.0",
    },
    {
        "value": "zh_female_santongyongns_saturn_bigtts",
        "label": "[2.0] 流畅女声 (女)",
        "resource_id": "seed-tts-2.0",
    },
    {
        "value": "zh_male_ruyayichen_saturn_bigtts",
        "label": "[2.0] 儒雅逸辰 (男)",
        "resource_id": "seed-tts-2.0",
    },
    {
        "value": "zh_female_xueayi_saturn_bigtts",
        "label": "[2.0] 儿童绘本 (女)",
        "resource_id": "seed-tts-2.0",
    },
    {
        "value": "saturn_zh_female_cancan_tob",
        "label": "[2.0] 知性灿灿 (女)",
        "resource_id": "seed-tts-2.0",
    },
    {
        "value": "saturn_zh_female_keainvsheng_tob",
        "label": "[2.0] 可爱女生 (女)",
        "resource_id": "seed-tts-2.0",
    },
    {
        "value": "saturn_zh_female_tiaopigongzhu_tob",
        "label": "[2.0] 调皮公主 (女)",
        "resource_id": "seed-tts-2.0",
    },
    {
        "value": "saturn_zh_male_shuanglangshaonian_tob",
        "label": "[2.0] 爽朗少年 (男)",
        "resource_id": "seed-tts-2.0",
    },
    {
        "value": "saturn_zh_male_tiancaitongzhuo_tob",
        "label": "[2.0] 天才同桌 (男)",
        "resource_id": "seed-tts-2.0",
    },
]

# Volcengine emotions
VOLCENGINE_EMOTIONS = [
    {"value": "", "label": "默认"},
    {"value": "happy", "label": "开心"},
    {"value": "sad", "label": "悲伤"},
    {"value": "angry", "label": "愤怒"},
]


class VolcengineTTSProvider(BaseTTSProvider):
    """TTS provider using Volcengine bidirectional WebSocket API."""

    def __init__(self):
        self._protocol = VolcengineProtocol()
        self._lock = threading.Lock()

    @property
    def provider_name(self) -> str:
        return "volcengine"

    def _infer_resource_id_for_voice(self, voice_id: str) -> str:
        """Infer Volcengine resource ID from a known voice ID."""
        voice_id = (voice_id or "").strip()
        if not voice_id:
            return ""

        for voice in VOLCENGINE_VOICES:
            if voice.get("value") == voice_id:
                return (voice.get("resource_id") or "").strip()

        return ""

    def _get_credentials(self, resource_id: str = "") -> tuple[str, str, str]:
        """
        Get Volcengine TTS credentials.

        Uses VOLCENGINE_TTS_* config for authentication.

        Notes:
        - VOLCENGINE_TTS_APP_KEY and VOLCENGINE_TTS_ACCESS_KEY are also used by
          the HTTP v1/tts provider. Keeping the same vars avoids duplicated
          secrets across providers.
        - ARK_* fallback is kept for backward compatibility with legacy
          deployments, but VOLCENGINE_TTS_* is preferred.

        Returns:
            tuple: (app_key, access_key, resource_id)
        """
        app_key = (get_config("VOLCENGINE_TTS_APP_KEY") or "").strip()
        access_key = (get_config("VOLCENGINE_TTS_ACCESS_KEY") or "").strip()

        # Backward compatibility: historically Volcengine WebSocket TTS used ARK_*.
        # Prefer VOLCENGINE_TTS_* to avoid coupling TTS auth with LLM auth.
        if not app_key:
            app_key = (get_config("ARK_ACCESS_KEY_ID") or "").strip()
        if not access_key:
            access_key = (get_config("ARK_SECRET_ACCESS_KEY") or "").strip()

        # Resource ID (X-Api-Resource-Id) is required in the WebSocket handshake.
        # The `model` argument is treated as a resource ID for this provider.
        resource_id = (resource_id or "").strip() or "seed-tts-1.0"

        return app_key, access_key, resource_id

    def is_configured(self) -> bool:
        """Check if Volcengine TTS is properly configured."""
        if not WEBSOCKET_AVAILABLE:
            logger.warning("websocket-client package is not installed")
            return False

        app_key, access_key, _resource_id = self._get_credentials()
        return bool(app_key and access_key)

    def get_default_voice_settings(self) -> VoiceSettings:
        """Get default voice settings.

        Notes:
        - Per-Shifu voice settings are stored in the database.
        - This method only provides a provider-level fallback.
        """
        return VoiceSettings(
            voice_id="zh_female_shuangkuaisisi_moon_bigtts",
            speed=1.0,
            pitch=0,
            emotion="",
            volume=1.0,
        )

    def get_default_audio_settings(self) -> AudioSettings:
        """Get default audio settings from configuration."""
        return AudioSettings(
            # This project uploads and serves audio as MP3 (see `upload_audio_to_oss`).
            format="mp3",
            sample_rate=get_config("VOLCENGINE_TTS_SAMPLE_RATE") or 24000,
            bitrate=get_config("VOLCENGINE_TTS_BITRATE") or 128000,
            channel=1,
        )

    def get_supported_voices(self) -> List[dict]:
        """Get list of supported voices."""
        return VOLCENGINE_VOICES

    def synthesize(
        self,
        text: str,
        voice_settings: Optional[VoiceSettings] = None,
        audio_settings: Optional[AudioSettings] = None,
        model: Optional[str] = None,
    ) -> TTSResult:
        """
        Synthesize text to speech using Volcengine TTS.

        Args:
            text: Text to synthesize
            voice_settings: Voice settings (optional)
            audio_settings: Audio settings (optional)

        Returns:
            TTSResult with audio data and metadata

        Raises:
            ValueError: If synthesis fails
        """
        if not WEBSOCKET_AVAILABLE:
            raise ValueError(
                "websocket-client package is not installed. Install with: pip install websocket-client"
            )

        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        if not voice_settings:
            voice_settings = self.get_default_voice_settings()

        if not audio_settings:
            audio_settings = self.get_default_audio_settings()

        # Resource ID for handshake comes from `model` (provider-specific semantics).
        app_key, access_key, resource_id = self._get_credentials(
            resource_id=model or ""
        )
        inferred_resource_id = self._infer_resource_id_for_voice(
            voice_settings.voice_id
        )
        if inferred_resource_id and inferred_resource_id != resource_id:
            logger.info(
                "Volcengine voice implies resource id; overriding requested resource id (%s -> %s)",
                resource_id,
                inferred_resource_id,
            )
            resource_id = inferred_resource_id
        # Optional model version for req_params.model is intentionally not
        # configured via env; use provider defaults.
        model_version = ""

        if not app_key or not access_key or not resource_id:
            raise ValueError(
                "Volcengine TTS credentials are not configured. "
                "Set VOLCENGINE_TTS_APP_KEY and VOLCENGINE_TTS_ACCESS_KEY."
            )

        # Generate unique IDs
        connect_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4()).replace("-", "")

        # Collect audio data
        audio_chunks: List[bytes] = []
        error_message: Optional[str] = None
        connection_established = threading.Event()
        session_finished = threading.Event()
        total_duration_ms = 0

        # Create WebSocket connection
        ws_headers = {
            "X-Api-App-Key": app_key,
            "X-Api-Access-Key": access_key,
            "X-Api-Resource-Id": resource_id,
            "X-Api-Connect-Id": connect_id,
        }

        protocol = VolcengineProtocol()

        def on_message(ws, message):
            nonlocal error_message, total_duration_ms

            try:
                if isinstance(message, bytes):
                    frame = protocol.decode_frame(message)

                    if frame.event == Event.CONNECTION_STARTED:
                        logger.debug(f"Connection started: {frame.connection_id}")
                        connection_established.set()

                    elif frame.event == Event.CONNECTION_FAILED:
                        error_message = f"Connection failed: {frame.payload}"
                        logger.error(error_message)
                        connection_established.set()
                        session_finished.set()

                    elif frame.event == Event.SESSION_STARTED:
                        logger.debug(f"Session started: {frame.session_id}")

                    elif frame.event == Event.SESSION_FINISHED:
                        logger.debug(f"Session finished: {frame.session_id}")
                        # Extract usage info if available
                        if isinstance(frame.payload, dict):
                            usage = frame.payload.get("usage", {})
                            if usage:
                                logger.info(f"TTS usage: {usage}")
                        session_finished.set()

                    elif frame.event == Event.SESSION_FAILED:
                        error_message = f"Session failed: {frame.payload}"
                        logger.error(error_message)
                        session_finished.set()

                    elif frame.event == Event.TTS_RESPONSE:
                        # Audio data received
                        if frame.payload and isinstance(frame.payload, bytes):
                            audio_chunks.append(frame.payload)
                            logger.debug(
                                f"Received audio chunk: {len(frame.payload)} bytes"
                            )

                    elif frame.event == Event.TTS_SENTENCE_START:
                        logger.debug(f"Sentence start: {frame.payload}")

                    elif frame.event == Event.TTS_SENTENCE_END:
                        logger.debug(f"Sentence end: {frame.payload}")
                        # Extract duration if available
                        if isinstance(frame.payload, dict):
                            duration = frame.payload.get("res_params", {}).get(
                                "duration_ms", 0
                            )
                            total_duration_ms += duration

                    elif frame.message_type == MessageType.ERROR_INFORMATION:
                        error_message = f"Error {frame.error_code}: {frame.payload}"
                        logger.error(error_message)
                        session_finished.set()

            except Exception as e:
                logger.error(f"Error processing message: {e}")
                error_message = str(e)
                session_finished.set()

        def on_error(ws, error):
            nonlocal error_message
            error_message = str(error)
            logger.error(f"WebSocket error: {error}")
            connection_established.set()
            session_finished.set()

        def on_close(ws, close_status_code, close_msg):
            logger.debug(f"WebSocket closed: {close_status_code} - {close_msg}")
            connection_established.set()
            session_finished.set()

        def on_open(ws):
            logger.debug("WebSocket opened, sending StartConnection")
            # Send StartConnection
            ws.send(
                protocol.encode_start_connection(), opcode=websocket.ABNF.OPCODE_BINARY
            )

        # Create and run WebSocket
        ws = websocket.WebSocketApp(
            VOLCENGINE_TTS_WS_URL,
            header=ws_headers,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open,
        )

        # Run WebSocket in a separate thread
        ws_thread = threading.Thread(
            target=ws.run_forever, kwargs={"skip_utf8_validation": True}
        )
        ws_thread.daemon = True
        ws_thread.start()

        try:
            # Wait for connection to be established
            if not connection_established.wait(timeout=10):
                raise ValueError("Timeout waiting for connection")

            if error_message:
                raise ValueError(error_message)

            # Send StartSession
            logger.debug(f"Sending StartSession with speaker={voice_settings.voice_id}")
            start_session_frame = protocol.encode_start_session(
                session_id=session_id,
                speaker=voice_settings.voice_id,
                audio_format=audio_settings.format,
                sample_rate=audio_settings.sample_rate,
                speed=voice_settings.speed,
                pitch=voice_settings.pitch,
                volume=voice_settings.volume,
                emotion=voice_settings.emotion,
                model=model_version,
            )
            ws.send(start_session_frame, opcode=websocket.ABNF.OPCODE_BINARY)

            # Small delay to ensure session is started
            import time

            time.sleep(0.1)

            # Send TaskRequest with text
            logger.debug(f"Sending TaskRequest with text length={len(text)}")
            task_request_frame = protocol.encode_task_request(session_id, text)
            ws.send(task_request_frame, opcode=websocket.ABNF.OPCODE_BINARY)

            # Send FinishSession
            logger.debug("Sending FinishSession")
            finish_session_frame = protocol.encode_finish_session(session_id)
            ws.send(finish_session_frame, opcode=websocket.ABNF.OPCODE_BINARY)

            # Wait for session to finish
            if not session_finished.wait(timeout=60):
                raise ValueError("Timeout waiting for TTS synthesis")

            if error_message:
                raise ValueError(error_message)

            # Send FinishConnection
            ws.send(
                protocol.encode_finish_connection(), opcode=websocket.ABNF.OPCODE_BINARY
            )

        finally:
            # Close WebSocket
            ws.close()
            ws_thread.join(timeout=5)

        if not audio_chunks:
            raise ValueError("No audio data received")

        # Combine audio chunks
        audio_data = b"".join(audio_chunks)

        # Estimate duration if not provided
        if total_duration_ms == 0:
            # Estimate based on audio size (rough approximation for MP3)
            # Assuming 128kbps = 16KB/s
            bytes_per_ms = (audio_settings.bitrate / 8) / 1000
            total_duration_ms = (
                int(len(audio_data) / bytes_per_ms) if bytes_per_ms > 0 else 0
            )

        logger.info(
            f"Volcengine TTS synthesis completed: duration={total_duration_ms}ms, "
            f"size={len(audio_data)} bytes, chunks={len(audio_chunks)}"
        )

        return TTSResult(
            audio_data=audio_data,
            duration_ms=total_duration_ms,
            sample_rate=audio_settings.sample_rate,
            format=audio_settings.format,
            word_count=len(text),
        )

    def get_provider_config(self) -> ProviderConfig:
        """Get Volcengine provider configuration for frontend."""
        return ProviderConfig(
            name="volcengine",
            label="火山引擎大模型",
            speed=ParamRange(min=0.5, max=2.0, step=0.1, default=1.0),
            pitch=ParamRange(min=-12, max=12, step=1, default=0),
            supports_emotion=True,
            models=VOLCENGINE_MODELS,
            voices=VOLCENGINE_VOICES,
            emotions=VOLCENGINE_EMOTIONS,
        )
