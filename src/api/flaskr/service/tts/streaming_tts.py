"""
Streaming TTS Processor with async synthesis.

This module provides real-time TTS synthesis during content streaming.
- First sentence is synthesized immediately for instant feedback
- Subsequent text is batched at ~300 chars at sentence boundaries
- TTS synthesis runs in background threads to avoid blocking content streaming
"""

import re
import base64
import logging
import uuid
import threading
import time
from typing import Generator, Optional, List, Dict
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, Future

from flask import Flask

from flaskr.dao import db
from flaskr.api.tts import (
    synthesize_text,
    is_tts_configured,
    VoiceSettings,
    AudioSettings,
    get_default_voice_settings,
    get_default_audio_settings,
)
from flaskr.service.tts import preprocess_for_tts
from flaskr.service.tts import preprocess_for_tts_with_boundaries
from flaskr.service.tts import TTS_VISUAL_BOUNDARY_TOKEN
from flaskr.service.tts.audio_utils import (
    concat_audio_best_effort,
    get_audio_duration_ms,
    is_audio_processing_available,
)
from flaskr.service.tts.pipeline import split_text_for_tts
from flaskr.service.tts.tts_handler import upload_audio_to_oss
from flaskr.common.log import AppLoggerProxy
from flaskr.service.tts.models import (
    LearnGeneratedAudio,
    AUDIO_STATUS_COMPLETED,
)
from flaskr.service.metering import UsageContext, record_tts_usage
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PROD
from flaskr.util.uuid import generate_id
from flaskr.service.learn.learn_dtos import (
    RunMarkdownFlowDTO,
    GeneratedType,
    AudioSegmentDTO,
    AudioCompleteDTO,
)


logger = AppLoggerProxy(logging.getLogger(__name__))

# Sentence ending patterns
SENTENCE_ENDINGS = re.compile(r"[.!?。！？；;]")

# Global thread pool for TTS synthesis
_tts_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tts_")


@dataclass
class TTSSegment:
    """A segment of text to be synthesized."""

    index: int
    position: int
    text: str
    audio_data: Optional[bytes] = None
    duration_ms: int = 0
    word_count: int = 0
    latency_ms: int = 0
    error: Optional[str] = None
    is_ready: bool = False


class StreamingTTSProcessor:
    """
    Processes text for TTS in real-time during content streaming.

    Uses background threads for TTS synthesis to avoid blocking content streaming.
    """

    def __init__(
        self,
        app: Flask,
        generated_block_bid: str,
        outline_bid: str,
        progress_record_bid: str,
        user_bid: str,
        shifu_bid: str,
        voice_id: str = "",
        speed: float = 1.0,
        pitch: int = 0,
        emotion: str = "",
        max_segment_chars: int = 300,
        tts_provider: str = "",
        tts_model: str = "",
        usage_scene: int = BILL_USAGE_SCENE_PROD,
    ):
        self.app = app
        self.generated_block_bid = generated_block_bid
        self.outline_bid = outline_bid
        self.progress_record_bid = progress_record_bid
        self.user_bid = user_bid
        self.shifu_bid = shifu_bid
        self.max_segment_chars = max_segment_chars
        self.tts_provider = tts_provider
        self.tts_model = tts_model

        # Audio settings - use provider-specific defaults
        self.voice_settings = get_default_voice_settings(tts_provider)
        if voice_id:
            self.voice_settings.voice_id = voice_id
        if speed is not None:
            self.voice_settings.speed = float(speed)
        if pitch is not None:
            self.voice_settings.pitch = int(pitch)
        if emotion:
            self.voice_settings.emotion = emotion
        self.audio_settings = get_default_audio_settings(tts_provider)

        # State
        self._buffer = ""
        self._processed_text_offset = 0
        self._first_sentence_done = False
        self._segment_index = 0
        self._audio_bid = str(uuid.uuid4()).replace("-", "")
        self._current_position = 0
        self._current_position_has_audio = False
        self._usage_parent_bid = generate_id(app)
        self._word_count_total = 0
        self._usage_scene = usage_scene
        self.usage_context = UsageContext(
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            progress_record_bid=progress_record_bid,
            generated_block_bid=generated_block_bid,
            audio_bid=self._audio_bid,
            usage_scene=usage_scene,
        )

        # Thread-safe queue for completed segments
        self._completed_segments: Dict[int, TTSSegment] = {}
        self._pending_futures: List[Future] = []
        self._next_yield_index = 0
        self._lock = threading.Lock()

        # Storage for all yielded audio data.
        # List of (position, index, audio_data, duration_ms)
        self._all_audio_data: List[tuple] = []

        # Check if TTS is configured for the specified provider
        self._enabled = is_tts_configured(tts_provider)
        if not self._enabled:
            logger.warning(
                f"TTS is not configured for provider '{tts_provider or '(unset)'}', streaming TTS disabled"
            )

    def _advance_position_if_needed(self):
        """Advance audio unit position only when current position produced audio."""
        with self._lock:
            if not self._current_position_has_audio:
                return
            self._current_position += 1
            self._current_position_has_audio = False
        self._first_sentence_done = False

    def _submit_text_for_position(self, text: str, position: int):
        """Submit text for synthesis while preserving long-text segmentation."""
        normalized = (text or "").strip()
        if len(normalized) < 2:
            return

        try:
            segments = split_text_for_tts(
                normalized,
                provider_name=self.tts_provider or "",
                max_segment_chars=int(self.max_segment_chars),
            )
        except Exception:
            segments = []

        if not segments:
            segments = [normalized]

        for segment in segments:
            clean_segment = (segment or "").strip()
            if len(clean_segment) < 2:
                continue
            self._submit_tts_task(clean_segment, position=position)

    def process_chunk(self, chunk: str) -> Generator[RunMarkdownFlowDTO, None, None]:
        """
        Process a chunk of streaming content.

        Submits TTS tasks to background threads and yields completed segments.
        """
        if not self._enabled or not chunk:
            # Still check for completed segments
            yield from self._yield_ready_segments()
            return

        self._buffer += chunk

        # Check if we should submit a new TTS task
        self._try_submit_tts_task()

        # Yield any segments that are ready
        yield from self._yield_ready_segments()

    def _try_submit_tts_task(self):
        """Check if we have enough content to submit a TTS task."""
        if not self._buffer:
            return

        # Preprocess buffer while preserving visual boundaries as explicit markers.
        processable_text = preprocess_for_tts_with_boundaries(self._buffer)
        if not processable_text:
            return

        while True:
            # Keep the offset within bounds in case preprocessing shrunk the text.
            if self._processed_text_offset > len(processable_text):
                self._processed_text_offset = len(processable_text)

            remaining_text = processable_text[self._processed_text_offset :]
            if not remaining_text:
                return

            # Skip leading whitespace without producing a segment.
            leading_ws = len(remaining_text) - len(remaining_text.lstrip())
            if leading_ws:
                self._processed_text_offset += leading_ws
                remaining_text = remaining_text[leading_ws:]
                if not remaining_text:
                    return

            # Boundary marker means visual content happened between speech parts.
            if remaining_text.startswith(TTS_VISUAL_BOUNDARY_TOKEN):
                self._processed_text_offset += len(TTS_VISUAL_BOUNDARY_TOKEN)
                self._advance_position_if_needed()
                continue

            boundary_index = remaining_text.find(TTS_VISUAL_BOUNDARY_TOKEN)
            if boundary_index > 0:
                candidate = remaining_text[:boundary_index].strip()
                self._processed_text_offset += boundary_index
                if candidate and len(candidate) >= 2:
                    self._submit_text_for_position(candidate, self._current_position)
                    self._first_sentence_done = True
                # Leave boundary marker for next loop iteration.
                continue

            if len(remaining_text) < 2:
                return

            text_to_synthesize: Optional[str] = None
            consume_len = 0

            if not self._first_sentence_done:
                # Look for first sentence ending
                match = SENTENCE_ENDINGS.search(remaining_text)
                if match:
                    consume_len = match.end()
                    candidate = remaining_text[:consume_len]
                    text_to_synthesize = candidate.strip()
                    if text_to_synthesize and len(text_to_synthesize) >= 2:
                        self._first_sentence_done = True
            else:
                # After first sentence, batch at ~300 chars at sentence boundaries
                if len(remaining_text) >= self.max_segment_chars:
                    chunk = remaining_text[: self.max_segment_chars]
                    matches = list(SENTENCE_ENDINGS.finditer(chunk))

                    if matches:
                        consume_len = matches[-1].end()
                    else:
                        # No sentence boundary, find word/char boundary
                        consume_len = len(chunk)

                    candidate = remaining_text[:consume_len]
                    text_to_synthesize = candidate.strip()

            if consume_len:
                self._processed_text_offset += consume_len

            # Submit TTS task to background thread.
            if text_to_synthesize:
                self._submit_tts_task(
                    text_to_synthesize, position=self._current_position
                )
            return

    def _submit_tts_task(self, text: str, *, position: int):
        """Submit a TTS synthesis task to the background thread pool."""
        with self._lock:
            segment_index = self._segment_index
            self._segment_index += 1
            self._current_position_has_audio = True

        segment = TTSSegment(index=segment_index, position=position, text=text)

        logger.info(
            f"Submitting TTS task {segment_index}: {len(text)} chars, "
            f"position={position}, provider={self.tts_provider or '(unset)'}"
        )

        future = _tts_executor.submit(
            self._synthesize_in_thread,
            segment,
            self.voice_settings,
            self.audio_settings,
            self.tts_provider,
            self.tts_model,
        )
        self._pending_futures.append(future)

    def _synthesize_in_thread(
        self,
        segment: TTSSegment,
        voice_settings: VoiceSettings,
        audio_settings: AudioSettings,
        tts_provider: str = "",
        tts_model: str = "",
    ) -> TTSSegment:
        """Synthesize a segment in a background thread."""
        with self.app.app_context():
            try:
                segment_start = time.monotonic()
                result = synthesize_text(
                    text=segment.text,
                    voice_settings=voice_settings,
                    audio_settings=audio_settings,
                    model=tts_model,
                    provider_name=tts_provider,
                )
                segment.audio_data = result.audio_data
                segment.duration_ms = result.duration_ms
                segment.word_count = int(result.word_count or 0)
                segment.latency_ms = int((time.monotonic() - segment_start) * 1000)
                segment.is_ready = True

                segment_length = len(segment.text or "")
                record_tts_usage(
                    self.app,
                    self.usage_context,
                    provider=tts_provider or "",
                    model=tts_model or "",
                    is_stream=True,
                    input=segment_length,
                    output=segment_length,
                    total=segment_length,
                    word_count=segment.word_count,
                    duration_ms=int(segment.duration_ms or 0),
                    latency_ms=segment.latency_ms,
                    record_level=1,
                    parent_usage_bid=self._usage_parent_bid,
                    segment_index=segment.index,
                    segment_count=0,
                    extra={
                        "voice_id": self.voice_settings.voice_id or "",
                        "speed": self.voice_settings.speed,
                        "pitch": self.voice_settings.pitch,
                        "emotion": self.voice_settings.emotion,
                        "volume": self.voice_settings.volume,
                        "format": self.audio_settings.format or "mp3",
                        "sample_rate": self.audio_settings.sample_rate or 24000,
                    },
                )

                with self._lock:
                    self._word_count_total += segment.word_count

                logger.info(
                    f"TTS segment {segment.index} synthesized: "
                    f"text_len={len(segment.text)}, duration={segment.duration_ms}ms"
                )
            except Exception as e:
                logger.error(f"TTS segment {segment.index} failed: {e}")
                segment.error = str(e)
                segment.is_ready = True

            # Store in completed segments
            with self._lock:
                self._completed_segments[segment.index] = segment

        return segment

    def _yield_ready_segments(self) -> Generator[RunMarkdownFlowDTO, None, None]:
        """Yield segments that are ready in order."""
        while True:
            with self._lock:
                # Check if next segment is ready
                if self._next_yield_index not in self._completed_segments:
                    break

                segment = self._completed_segments.pop(self._next_yield_index)
                self._next_yield_index += 1

                # Store audio data for final concatenation (before popping)
                if segment.audio_data and not segment.error:
                    self._all_audio_data.append(
                        (
                            segment.position,
                            segment.index,
                            segment.audio_data,
                            segment.duration_ms,
                        )
                    )
                    logger.info(
                        f"TTS stored segment {segment.index} for concatenation, "
                        f"position={segment.position}, "
                        f"total stored: {len(self._all_audio_data)}"
                    )

            if segment.audio_data and not segment.error:
                # Encode to base64
                base64_audio = base64.b64encode(segment.audio_data).decode("utf-8")

                yield RunMarkdownFlowDTO(
                    outline_bid=self.outline_bid,
                    generated_block_bid=self.generated_block_bid,
                    type=GeneratedType.AUDIO_SEGMENT,
                    content=AudioSegmentDTO(
                        segment_index=segment.index,
                        audio_data=base64_audio,
                        duration_ms=segment.duration_ms,
                        is_final=False,
                        position=segment.position,
                    ),
                )

    def finalize(
        self, *, commit: bool = True
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        """
        Finalize TTS processing after content streaming is complete.
        """
        raw_text = self._buffer
        cleaned_text = ""
        cleaned_text_length = 0
        try:
            cleaned_text = preprocess_for_tts(self._buffer or "")
            cleaned_text_length = len(cleaned_text)
        except Exception:
            cleaned_text = ""
            cleaned_text_length = 0

        logger.info(
            f"TTS finalize called: enabled={self._enabled}, "
            f"buffer_len={len(self._buffer)}, "
            f"segment_index={self._segment_index}, "
            f"pending_futures={len(self._pending_futures)}, "
            f"all_audio_data={len(self._all_audio_data)}"
        )
        if not self._enabled:
            logger.info("TTS finalize: TTS not enabled, returning early")
            return

        # Submit any remaining buffer content while preserving boundary positions.
        if self._buffer:
            full_text = preprocess_for_tts_with_boundaries(self._buffer)
            if self._processed_text_offset > len(full_text):
                self._processed_text_offset = len(full_text)

            remaining_text = full_text[self._processed_text_offset :]
            if remaining_text:
                parts = remaining_text.split(TTS_VISUAL_BOUNDARY_TOKEN)
                for index, part in enumerate(parts):
                    candidate = (part or "").strip()
                    if candidate and len(candidate) >= 2:
                        self._submit_text_for_position(
                            candidate, self._current_position
                        )
                        self._first_sentence_done = True

                    # Move to next position when there is a boundary marker.
                    if index < len(parts) - 1:
                        self._advance_position_if_needed()
            self._buffer = ""

        # Wait for all pending TTS tasks to complete
        for future in self._pending_futures:
            try:
                future.result(timeout=60)  # Max 60s per segment
            except Exception as e:
                logger.error(f"TTS future failed: {e}")

        # Yield any remaining segments
        yield from self._yield_ready_segments()

        # Use stored audio data from all yielded segments
        with self._lock:
            all_segments = list(self._all_audio_data)
            logger.info(
                f"TTS finalize: _all_audio_data has {len(self._all_audio_data)} segments, "
                f"copying to all_segments"
            )

        if not all_segments:
            logger.warning(
                f"No audio segments to concatenate. "
                f"segment_index={self._segment_index}, "
                f"next_yield_index={self._next_yield_index}, "
                f"completed_segments keys={list(self._completed_segments.keys())}"
            )
            return

        try:
            logger.info(
                f"TTS finalize: audio_processing_available={is_audio_processing_available()}"
            )

            segments_by_position: Dict[int, List[tuple[int, bytes, int]]] = {}
            for position, segment_index, audio_data, duration_ms in all_segments:
                bucket = segments_by_position.setdefault(int(position), [])
                bucket.append((int(segment_index), audio_data, int(duration_ms or 0)))

            completion_payloads: List[tuple[int, str, str, int]] = []
            total_duration_ms = 0
            total_segment_count = 0

            for position in sorted(segments_by_position.keys()):
                ordered_segments = sorted(
                    segments_by_position[position], key=lambda item: item[0]
                )
                audio_data_list = [segment[1] for segment in ordered_segments]
                if not audio_data_list:
                    continue

                final_audio = concat_audio_best_effort(audio_data_list)
                if not final_audio:
                    continue

                position_duration_ms = int(get_audio_duration_ms(final_audio) or 0)
                total_duration_ms += position_duration_ms
                total_segment_count += len(audio_data_list)
                file_size = len(final_audio)

                position_audio_bid = uuid.uuid4().hex
                logger.info(
                    "TTS finalize: uploading position=%s audio_bid=%s",
                    position,
                    position_audio_bid,
                )
                oss_url, bucket_name = upload_audio_to_oss(
                    self.app, final_audio, position_audio_bid
                )

                audio_record = LearnGeneratedAudio(
                    audio_bid=position_audio_bid,
                    generated_block_bid=self.generated_block_bid,
                    progress_record_bid=self.progress_record_bid,
                    user_bid=self.user_bid,
                    shifu_bid=self.shifu_bid,
                    oss_url=oss_url,
                    oss_bucket=bucket_name,
                    oss_object_key=f"tts-audio/{position_audio_bid}.mp3",
                    duration_ms=position_duration_ms,
                    file_size=file_size,
                    voice_id=self.voice_settings.voice_id,
                    voice_settings={
                        "speed": self.voice_settings.speed,
                        "pitch": self.voice_settings.pitch,
                        "emotion": self.voice_settings.emotion,
                        "volume": self.voice_settings.volume,
                    },
                    model=self.tts_model or "",
                    text_length=cleaned_text_length,
                    segment_count=len(audio_data_list),
                    position=position,
                    status=AUDIO_STATUS_COMPLETED,
                )
                db.session.add(audio_record)
                completion_payloads.append(
                    (position, oss_url, position_audio_bid, position_duration_ms)
                )

            if not completion_payloads:
                logger.warning("No completion payloads generated after concatenation")
                return

            if commit:
                db.session.commit()
                logger.info("TTS finalize: database commit complete")
            else:
                db.session.flush()
                logger.info("TTS finalize: database flush complete")

            record_tts_usage(
                self.app,
                self.usage_context,
                usage_bid=self._usage_parent_bid,
                provider=self.tts_provider or "",
                model=self.tts_model or "",
                is_stream=True,
                input=len(raw_text or ""),
                output=len(cleaned_text or ""),
                total=len(cleaned_text or ""),
                word_count=self._word_count_total,
                duration_ms=int(total_duration_ms or 0),
                latency_ms=0,
                record_level=0,
                parent_usage_bid="",
                segment_index=0,
                segment_count=total_segment_count,
                extra={
                    "voice_id": self.voice_settings.voice_id or "",
                    "speed": self.voice_settings.speed,
                    "pitch": self.voice_settings.pitch,
                    "emotion": self.voice_settings.emotion,
                    "volume": self.voice_settings.volume,
                    "format": self.audio_settings.format or "mp3",
                    "sample_rate": self.audio_settings.sample_rate or 24000,
                },
            )

            # Yield completions in position order.
            for position, oss_url, audio_bid, duration_ms in sorted(
                completion_payloads, key=lambda item: item[0]
            ):
                logger.info(
                    "TTS finalize: yielding AUDIO_COMPLETE position=%s audio_bid=%s",
                    position,
                    audio_bid,
                )
                yield RunMarkdownFlowDTO(
                    outline_bid=self.outline_bid,
                    generated_block_bid=self.generated_block_bid,
                    type=GeneratedType.AUDIO_COMPLETE,
                    content=AudioCompleteDTO(
                        audio_url=oss_url,
                        audio_bid=audio_bid,
                        duration_ms=duration_ms,
                        position=position,
                    ),
                )

            logger.info(
                "TTS complete: positions=%s, total_segments=%s, total_duration=%sms",
                len(completion_payloads),
                total_segment_count,
                total_duration_ms,
            )

        except Exception as e:
            import traceback

            logger.error(f"Failed to finalize TTS: {e}\n{traceback.format_exc()}")

    def finalize_preview(self) -> Generator[RunMarkdownFlowDTO, None, None]:
        """
        Finalize TTS processing for preview/debug flows without uploading or persisting.

        The editor preview (learning simulation) only needs streamable segments for
        playback, so we skip OSS upload and database writes to avoid polluting
        learning records.
        """
        logger.info(
            f"TTS preview finalize called: enabled={self._enabled}, "
            f"buffer_len={len(self._buffer)}, "
            f"segment_index={self._segment_index}, "
            f"pending_futures={len(self._pending_futures)}, "
            f"all_audio_data={len(self._all_audio_data)}"
        )
        raw_text = self._buffer
        if not self._enabled:
            return

        # Submit any remaining buffer content.
        if self._buffer:
            full_text = preprocess_for_tts_with_boundaries(self._buffer)
            if self._processed_text_offset > len(full_text):
                self._processed_text_offset = len(full_text)

            remaining_text = full_text[self._processed_text_offset :]
            if remaining_text:
                parts = remaining_text.split(TTS_VISUAL_BOUNDARY_TOKEN)
                for index, part in enumerate(parts):
                    candidate = (part or "").strip()
                    if candidate and len(candidate) >= 2:
                        self._submit_text_for_position(
                            candidate, self._current_position
                        )
                    if index < len(parts) - 1:
                        self._advance_position_if_needed()
            self._buffer = ""

        # Wait for all pending TTS tasks to complete.
        for future in self._pending_futures:
            try:
                future.result(timeout=60)
            except Exception as e:
                logger.error(f"TTS preview future failed: {e}")

        # Yield any remaining segments.
        yield from self._yield_ready_segments()

        with self._lock:
            total_duration_ms = sum(seg[3] for seg in self._all_audio_data)
            has_audio = bool(self._all_audio_data)

        if not has_audio:
            return

        # Yield completion marker (no OSS URL in preview mode).
        yield RunMarkdownFlowDTO(
            outline_bid=self.outline_bid,
            generated_block_bid=self.generated_block_bid,
            type=GeneratedType.AUDIO_COMPLETE,
            content=AudioCompleteDTO(
                audio_url="",
                audio_bid=self._audio_bid,
                duration_ms=total_duration_ms,
            ),
        )

        cleaned_text = ""
        try:
            cleaned_text = preprocess_for_tts(raw_text or "")
        except Exception:
            cleaned_text = ""

        record_tts_usage(
            self.app,
            self.usage_context,
            usage_bid=self._usage_parent_bid,
            provider=self.tts_provider or "",
            model=self.tts_model or "",
            is_stream=True,
            input=len(raw_text or ""),
            output=len(cleaned_text or ""),
            total=len(cleaned_text or ""),
            word_count=self._word_count_total,
            duration_ms=int(total_duration_ms or 0),
            latency_ms=0,
            record_level=0,
            parent_usage_bid="",
            segment_index=0,
            segment_count=len(self._all_audio_data),
            extra={
                "voice_id": self.voice_settings.voice_id or "",
                "speed": self.voice_settings.speed,
                "pitch": self.voice_settings.pitch,
                "emotion": self.voice_settings.emotion,
                "volume": self.voice_settings.volume,
                "format": self.audio_settings.format or "mp3",
                "sample_rate": self.audio_settings.sample_rate or 24000,
            },
        )
