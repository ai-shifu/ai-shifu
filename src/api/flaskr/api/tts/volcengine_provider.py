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


logger = logging.getLogger(__name__)

# Volcengine TTS WebSocket endpoint
VOLCENGINE_TTS_WS_URL = "wss://openspeech.bytedance.com/api/v3/tts/bidirection"

# Volcengine TTS models
VOLCENGINE_MODELS = [
    {"value": "seed-tts-1.0", "label": "Seed-TTS-1.0"},
    {"value": "seed-tts-2.0", "label": "Seed-TTS-2.0"},
    {"value": "seed-icl-1.0", "label": "Seed-ICL-1.0"},
]

# Volcengine recommended voices
VOLCENGINE_VOICES = [
    {"value": "zh_female_shuangkuaisisi_moon_bigtts", "label": "爽快思思 (女)"},
    {"value": "zh_male_abin_moon_bigtts", "label": "阿斌 (男)"},
    {"value": "zh_female_cancan_mars_bigtts", "label": "灿灿 (女)"},
    {"value": "zh_male_ahu_conversation_wvae_bigtts", "label": "阿虎 (男)"},
    {"value": "zh_female_wanwanxiaohe_moon_bigtts", "label": "弯弯小何 (女)"},
    {"value": "zh_male_shaonian_mars_bigtts", "label": "少年 (男)"},
    {"value": "zh_female_linjie_moon_bigtts", "label": "邻家姐姐 (女)"},
    {"value": "zh_male_yangguang_moon_bigtts", "label": "阳光男声 (男)"},
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

    def _get_credentials(self) -> tuple:
        """
        Get Volcengine TTS credentials.

        Uses ARK_* config as primary, with VOLCENGINE_TTS_* as override.

        Returns:
            tuple: (app_key, access_key, resource_id)
        """
        # App Key: VOLCENGINE_TTS_APP_KEY or ARK_ACCESS_KEY_ID
        app_key = (
            get_config("VOLCENGINE_TTS_APP_KEY")
            or get_config("ARK_ACCESS_KEY_ID")
            or ""
        )

        # Access Key: VOLCENGINE_TTS_ACCESS_KEY or ARK_SECRET_ACCESS_KEY
        access_key = (
            get_config("VOLCENGINE_TTS_ACCESS_KEY")
            or get_config("ARK_SECRET_ACCESS_KEY")
            or ""
        )

        # Resource ID: specific to TTS
        resource_id = get_config("VOLCENGINE_TTS_RESOURCE_ID") or "seed-tts-1.0"

        return app_key, access_key, resource_id

    def is_configured(self) -> bool:
        """Check if Volcengine TTS is properly configured."""
        if not WEBSOCKET_AVAILABLE:
            logger.warning("websocket-client package is not installed")
            return False

        app_key, access_key, resource_id = self._get_credentials()
        return bool(app_key and access_key and resource_id)

    def get_default_voice_settings(self) -> VoiceSettings:
        """Get default voice settings from configuration."""
        return VoiceSettings(
            voice_id=get_config("VOLCENGINE_TTS_VOICE_ID")
            or "zh_female_shuangkuaisisi_moon_bigtts",
            speed=get_config("VOLCENGINE_TTS_SPEED") or 1.0,
            pitch=get_config("VOLCENGINE_TTS_PITCH") or 0,
            emotion=get_config("VOLCENGINE_TTS_EMOTION") or "",
            volume=get_config("VOLCENGINE_TTS_VOLUME") or 1.0,
        )

    def get_default_audio_settings(self) -> AudioSettings:
        """Get default audio settings from configuration."""
        return AudioSettings(
            format=get_config("VOLCENGINE_TTS_FORMAT") or "mp3",
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

        # Get credentials using shared ARK config
        app_key, access_key, resource_id = self._get_credentials()
        # Use provided model, or fall back to config
        tts_model = model or get_config("VOLCENGINE_TTS_MODEL") or ""

        if not app_key or not access_key or not resource_id:
            raise ValueError(
                "Volcengine TTS credentials are not configured. Set ARK_ACCESS_KEY_ID and ARK_SECRET_ACCESS_KEY, or VOLCENGINE_TTS_APP_KEY and VOLCENGINE_TTS_ACCESS_KEY"
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
                model=tts_model,
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
            label="火山引擎",
            speed=ParamRange(min=0.5, max=2.0, step=0.1, default=1.0),
            pitch=ParamRange(min=-12, max=12, step=1, default=0),
            supports_emotion=True,
            models=VOLCENGINE_MODELS,
            voices=VOLCENGINE_VOICES,
            emotions=VOLCENGINE_EMOTIONS,
        )
