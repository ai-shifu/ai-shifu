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
from typing import Any, Generator, Optional, List, Dict
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
from flaskr.service.tts.audio_utils import (
    concat_audio_best_effort,
    get_audio_duration_ms,
    is_audio_processing_available,
)
from flaskr.common.log import AppLoggerProxy
from flaskr.service.tts.models import (
    LearnGeneratedAudio,
    AUDIO_STATUS_COMPLETED,
)
from flaskr.service.metering import UsageContext
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PROD
from flaskr.util.uuid import generate_id
from flaskr.service.learn.learn_dtos import (
    RunMarkdownFlowDTO,
    GeneratedType,
    AudioSegmentDTO,
    AudioCompleteDTO,
    NewSlideDTO,
)
from flaskr.service.learn.listen_slide_builder import build_listen_slides_for_block
from flaskr.service.tts.pipeline import (
    build_av_segmentation_contract,
    _AV_IMG_TAG_PATTERN,
    _AV_MARKDOWN_IMAGE_PATTERN,
    _AV_SANDBOX_START_PATTERN,
    _AV_SVG_OPEN_PATTERN,
    _AV_IFRAME_OPEN_PATTERN,
    _AV_IFRAME_CLOSE_PATTERN,
    _AV_TABLE_OPEN_PATTERN,
    _AV_TABLE_CLOSE_PATTERN,
    _AV_VIDEO_OPEN_PATTERN,
    _AV_VIDEO_CLOSE_PATTERN,
    _find_first_match_outside_fence,
    _find_html_block_end_with_complete,
    _extract_speakable_text_from_sandbox_html,
    _get_fence_ranges,
    _find_markdown_table_block,
    _rewind_fixed_marker_start,
    _extend_fixed_marker_end,
)


logger = AppLoggerProxy(logging.getLogger(__name__))

# Sentence ending patterns
SENTENCE_ENDINGS = re.compile(r"[.!?。！？；;]")
_AV_MARKDOWN_IMAGE_START_PATTERN = re.compile(r"!\[")

# Global thread pool for TTS synthesis
_tts_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tts_")


@dataclass
class TTSSegment:
    """A segment of text to be synthesized."""

    index: int
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
        position: int = 0,
        voice_id: str = "",
        speed: float = 1.0,
        pitch: int = 0,
        emotion: str = "",
        max_segment_chars: int = 300,
        tts_provider: str = "",
        tts_model: str = "",
        av_contract: Optional[Dict[str, Any]] = None,
        usage_scene: int = BILL_USAGE_SCENE_PROD,
    ):
        self.app = app
        self.generated_block_bid = generated_block_bid
        self.outline_bid = outline_bid
        self.progress_record_bid = progress_record_bid
        self.user_bid = user_bid
        self.shifu_bid = shifu_bid
        self.position = int(position or 0)
        self.max_segment_chars = max_segment_chars
        self.tts_provider = tts_provider
        self.tts_model = tts_model
        self.av_contract = av_contract

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

        # Storage for all yielded audio data (for final concatenation)
        # List of (index, audio_data, duration_ms)
        self._all_audio_data: List[tuple] = []

        # Check if TTS is configured for the specified provider
        self._enabled = is_tts_configured(tts_provider)
        if not self._enabled:
            logger.warning(
                f"TTS is not configured for provider '{tts_provider or '(unset)'}', streaming TTS disabled"
            )

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

        # Preprocess buffer to remove code blocks, SVG, etc.
        processable_text = preprocess_for_tts(self._buffer)
        if not processable_text:
            return

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
            self._submit_tts_task(text_to_synthesize)

    def _submit_tts_task(self, text: str):
        """Submit a TTS synthesis task to the background thread pool."""
        with self._lock:
            segment_index = self._segment_index
            self._segment_index += 1

        segment = TTSSegment(index=segment_index, text=text)

        logger.info(
            f"Submitting TTS task {segment_index}: {len(text)} chars, content={text}, provider={self.tts_provider or '(unset)'}"
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

    def _submit_remaining_text_in_segments(self, remaining_text: str):
        """
        Submit remaining text in segments to avoid burst submission at finalization.

        This ensures the last few segments maintain consistent pacing instead of
        being synthesized and returned almost simultaneously.

        Args:
            remaining_text: The remaining text to be synthesized
        """
        if not remaining_text or len(remaining_text) < 2:
            return

        logger.info(
            f"Submitting remaining text in segments: {len(remaining_text)} chars"
        )

        # Split remaining text at sentence boundaries, similar to normal flow
        while remaining_text and len(remaining_text) >= 2:
            # Determine chunk size (use max_segment_chars as limit)
            chunk_size = min(len(remaining_text), self.max_segment_chars)
            chunk = remaining_text[:chunk_size]

            # Try to find sentence boundary within chunk
            matches = list(SENTENCE_ENDINGS.finditer(chunk))
            if matches:
                # Split at last sentence ending in chunk
                split_pos = matches[-1].end()
            else:
                # No sentence boundary found, use full chunk
                split_pos = chunk_size

            # Extract segment and submit
            segment_text = remaining_text[:split_pos].strip()
            if segment_text and len(segment_text) >= 2:
                self._submit_tts_task(segment_text)
                logger.info(
                    f"Submitted finalize segment: {len(segment_text)} chars, "
                    f"remaining: {len(remaining_text) - split_pos} chars"
                )

            # Update remaining text
            remaining_text = remaining_text[split_pos:].strip()

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

                from flaskr.service.tts.tts_usage_recorder import (
                    record_tts_segment_usage,
                )

                record_tts_segment_usage(
                    app=self.app,
                    usage_context=self.usage_context,
                    provider=tts_provider or "",
                    model=tts_model or "",
                    segment_text=segment.text or "",
                    word_count=segment.word_count,
                    duration_ms=int(segment.duration_ms or 0),
                    latency_ms=segment.latency_ms,
                    voice_settings=self.voice_settings,
                    audio_settings=self.audio_settings,
                    is_stream=True,
                    parent_usage_bid=self._usage_parent_bid,
                    segment_index=segment.index,
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
        segments_yielded = 0
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
                        (segment.index, segment.audio_data, segment.duration_ms)
                    )
                    logger.info(
                        f"TTS stored segment {segment.index} for concatenation, "
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
                        position=self.position,
                        av_contract=self.av_contract,
                    ),
                )

                # Add small delay between yields to prevent burst delivery
                # This ensures segments are delivered at a steady pace
                if segments_yielded > 0:
                    time.sleep(0.1)  # 100ms delay between segment yields
                segments_yielded += 1

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

        # Submit any remaining buffer content in segments to avoid burst
        if self._buffer:
            full_text = preprocess_for_tts(self._buffer)
            if self._processed_text_offset > len(full_text):
                self._processed_text_offset = len(full_text)

            remaining_text = full_text[self._processed_text_offset :].strip()
            # Use segmented submission to maintain consistent pacing
            self._submit_remaining_text_in_segments(remaining_text)
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

        # Sort by index and concatenate
        all_segments.sort(key=lambda x: x[0])
        audio_data_list = [s[1] for s in all_segments]
        total_duration_ms = sum(s[2] for s in all_segments)

        logger.info(
            f"Concatenating {len(audio_data_list)} audio segments, "
            f"total duration: {total_duration_ms}ms"
        )

        try:
            # Concatenate all segments
            logger.info(
                f"TTS finalize: audio_processing_available={is_audio_processing_available()}"
            )
            final_audio = concat_audio_best_effort(audio_data_list)

            final_duration_ms = get_audio_duration_ms(final_audio)
            file_size = len(final_audio)
            logger.info(
                f"TTS finalize: final_audio_size={file_size}, duration={final_duration_ms}ms"
            )

            # Upload to OSS
            from flaskr.service.tts.tts_handler import upload_audio_to_oss

            logger.info(f"TTS finalize: uploading to OSS, audio_bid={self._audio_bid}")
            oss_url, bucket_name = upload_audio_to_oss(
                self.app, final_audio, self._audio_bid
            )
            logger.info(f"TTS finalize: OSS upload complete, url={oss_url}")

            # Save to database - use existing context if available
            logger.info("TTS finalize: saving to database")
            audio_record = LearnGeneratedAudio(
                audio_bid=self._audio_bid,
                generated_block_bid=self.generated_block_bid,
                position=self.position,
                progress_record_bid=self.progress_record_bid,
                user_bid=self.user_bid,
                shifu_bid=self.shifu_bid,
                oss_url=oss_url,
                oss_bucket=bucket_name,
                oss_object_key=f"tts-audio/{self._audio_bid}.mp3",
                duration_ms=final_duration_ms,
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
                status=AUDIO_STATUS_COMPLETED,
            )
            db.session.add(audio_record)
            if commit:
                db.session.commit()
                logger.info("TTS finalize: database commit complete")
            else:
                db.session.flush()
                logger.info("TTS finalize: database flush complete")

            from flaskr.service.tts.tts_usage_recorder import (
                record_tts_aggregated_usage,
            )

            record_tts_aggregated_usage(
                app=self.app,
                usage_context=self.usage_context,
                usage_bid=self._usage_parent_bid,
                provider=self.tts_provider or "",
                model=self.tts_model or "",
                raw_text=raw_text or "",
                cleaned_text=cleaned_text or "",
                total_word_count=self._word_count_total,
                duration_ms=final_duration_ms or 0,
                segment_count=len(audio_data_list),
                voice_settings=self.voice_settings,
                audio_settings=self.audio_settings,
                is_stream=True,
            )

            # Yield completion
            logger.info("TTS finalize: yielding AUDIO_COMPLETE")
            yield RunMarkdownFlowDTO(
                outline_bid=self.outline_bid,
                generated_block_bid=self.generated_block_bid,
                type=GeneratedType.AUDIO_COMPLETE,
                content=AudioCompleteDTO(
                    audio_url=oss_url,
                    audio_bid=self._audio_bid,
                    duration_ms=final_duration_ms,
                    position=self.position,
                    av_contract=self.av_contract,
                ),
            )

            logger.info(
                f"TTS complete: audio_bid={self._audio_bid}, "
                f"segments={len(audio_data_list)}, "
                f"duration={final_duration_ms}ms"
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

        # Submit any remaining buffer content in segments to avoid burst.
        if self._buffer:
            full_text = preprocess_for_tts(self._buffer)
            if self._processed_text_offset > len(full_text):
                self._processed_text_offset = len(full_text)

            remaining_text = full_text[self._processed_text_offset :].strip()
            # Use segmented submission to maintain consistent pacing
            self._submit_remaining_text_in_segments(remaining_text)
            self._buffer = ""

        # Wait for all pending TTS tasks to complete
        for future in self._pending_futures:
            try:
                future.result(timeout=60)
            except Exception as e:
                logger.error(f"TTS preview future failed: {e}")

        # Yield any remaining segments.
        yield from self._yield_ready_segments()

        with self._lock:
            total_duration_ms = sum(seg[2] for seg in self._all_audio_data)
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
                position=self.position,
                av_contract=self.av_contract,
            ),
        )

        cleaned_text = ""
        try:
            cleaned_text = preprocess_for_tts(raw_text or "")
        except Exception:
            cleaned_text = ""

        from flaskr.service.tts.tts_usage_recorder import (
            record_tts_aggregated_usage,
        )

        record_tts_aggregated_usage(
            app=self.app,
            usage_context=self.usage_context,
            usage_bid=self._usage_parent_bid,
            provider=self.tts_provider or "",
            model=self.tts_model or "",
            raw_text=raw_text or "",
            cleaned_text=cleaned_text or "",
            total_word_count=self._word_count_total,
            duration_ms=total_duration_ms or 0,
            segment_count=len(self._all_audio_data),
            voice_settings=self.voice_settings,
            audio_settings=self.audio_settings,
            is_stream=True,
        )


class AVStreamingTTSProcessor:
    """
    Streaming TTS processor that segments audio by AV boundaries (e.g. SVG, fences).

    Each speakable segment (text gap between visual elements) is synthesized as a
    separate audio track, identified by `position` (0-based) within the same
    generated block.

    This processor is intended to be used for Listen Mode RUN SSE so the frontend
    can sync audio playback with visuals without making additional on-demand TTS calls.
    """

    def __init__(
        self,
        *,
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
        slide_index_offset: int = 0,
    ):
        self.app = app
        self.generated_block_bid = generated_block_bid
        self.outline_bid = outline_bid
        self.progress_record_bid = progress_record_bid
        self.user_bid = user_bid
        self.shifu_bid = shifu_bid
        self.voice_id = voice_id
        self.speed = speed
        self.pitch = pitch
        self.emotion = emotion
        self.max_segment_chars = max_segment_chars
        self.tts_provider = tts_provider
        self.tts_model = tts_model
        self.usage_scene = usage_scene
        self.slide_index_offset = int(slide_index_offset or 0)

        self._position_cursor = 0
        self._current_processor: Optional[StreamingTTSProcessor] = None
        self._raw_buffer = ""
        self._raw_full_content = ""
        self._av_contract: Optional[Dict[str, Any]] = None
        self._slide_id_by_position: Dict[int, str] = {}
        self._slides_by_id: Dict[str, NewSlideDTO] = {}
        self._emitted_slide_ids: set[str] = set()
        self._next_slide_index = self.slide_index_offset
        self._current_segment_has_speakable_text = False
        self._run_start_slide_emitted = False
        self._pending_visual_slide: Optional[NewSlideDTO] = None

        # When we hit a non-speakable block boundary (e.g. `<svg>`), we may need to
        # wait for its closing marker before resuming segmentation.
        self._skip_mode: Optional[str] = (
            None
            # 'fence' | 'svg' | 'iframe' | 'video' | 'html_table' | 'md_table' | 'sandbox' | 'md_img'
        )

    def _update_av_contract(self):
        try:
            self._av_contract = build_av_segmentation_contract(
                self._raw_full_content, self.generated_block_bid
            )
        except Exception:
            self._av_contract = None

    def _ensure_processor(self) -> StreamingTTSProcessor:
        if self._current_processor is not None:
            return self._current_processor
        self._current_processor = StreamingTTSProcessor(
            app=self.app,
            generated_block_bid=self.generated_block_bid,
            outline_bid=self.outline_bid,
            progress_record_bid=self.progress_record_bid,
            user_bid=self.user_bid,
            shifu_bid=self.shifu_bid,
            position=self._position_cursor,
            voice_id=self.voice_id,
            speed=self.speed,
            pitch=self.pitch,
            emotion=self.emotion,
            max_segment_chars=self.max_segment_chars,
            tts_provider=self.tts_provider,
            tts_model=self.tts_model,
            av_contract=self._av_contract,
            usage_scene=self.usage_scene,
        )
        self._current_segment_has_speakable_text = False
        return self._current_processor

    def _process_processor_chunk(
        self, processor: StreamingTTSProcessor, chunk: str
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        if (chunk or "").strip():
            self._current_segment_has_speakable_text = True
        yield from self._emit_with_slide_binding(processor.process_chunk(chunk))

    @property
    def next_slide_index(self) -> int:
        return int(self._next_slide_index or self.slide_index_offset)

    @property
    def has_pending_visual_boundary(self) -> bool:
        return bool(self._skip_mode)

    def _segment_type_for_visual_kind(self, visual_kind: str) -> str:
        if visual_kind in {"iframe", "sandbox", "html_table"}:
            return "sandbox"
        return "markdown"

    def _emit_new_slide_event(
        self, slide: NewSlideDTO, *, force: bool = False
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        # NEW_SLIDE is a timeline signal only. The frontend renders visuals from
        # streamed CONTENT chunks, so never include full segment payload here.
        if (slide.segment_content or "") != "":
            slide.segment_content = ""
        if not force and slide.slide_id in self._emitted_slide_ids:
            return
        self._emitted_slide_ids.add(slide.slide_id)
        self.app.logger.info(f"emit new slide: {slide.slide_id}")
        yield RunMarkdownFlowDTO(
            outline_bid=self.outline_bid,
            generated_block_bid=self.generated_block_bid,
            type=GeneratedType.NEW_SLIDE,
            content=slide,
        )

    def emit_run_start_slide(self) -> Generator[RunMarkdownFlowDTO, None, None]:
        if self._run_start_slide_emitted:
            return
        self._run_start_slide_emitted = True
        # Emit a deterministic initial placeholder slide so the frontend has a
        # timeline anchor before the first content chunk/audio event arrives.
        slide = self._build_fallback_slide(self._position_cursor)
        yield from self._emit_new_slide_event(slide)

    def _emit_visual_slide_for_current_position(
        self, *, visual_kind: str, segment_content: str
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        position = int(self._position_cursor or 0)
        _ = segment_content
        slide = NewSlideDTO(
            slide_id=uuid.uuid4().hex,
            generated_block_bid=self.generated_block_bid,
            slide_index=self._next_slide_index,
            audio_position=position,
            visual_kind=visual_kind,
            segment_type=self._segment_type_for_visual_kind(visual_kind),
            # Keep NEW_SLIDE payload lightweight; frontend renders from stream content.
            segment_content="",
            source_span=[],
            is_placeholder=False,
        )
        self._next_slide_index += 1
        self._slide_id_by_position[position] = slide.slide_id
        self._slides_by_id[slide.slide_id] = slide
        yield from self._emit_new_slide_event(slide)

    def _emit_visual_slide_head_for_current_position(
        self, *, visual_kind: str
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        position = int(self._position_cursor or 0)
        existing = self._pending_visual_slide
        if (
            existing is not None
            and int(existing.audio_position or 0) == position
            and (existing.visual_kind or "") == (visual_kind or "")
        ):
            return

        slide = NewSlideDTO(
            slide_id=uuid.uuid4().hex,
            generated_block_bid=self.generated_block_bid,
            slide_index=self._next_slide_index,
            audio_position=position,
            visual_kind=visual_kind,
            segment_type="placeholder",
            segment_content="",
            source_span=[],
            is_placeholder=True,
        )
        self._next_slide_index += 1
        self._slide_id_by_position[position] = slide.slide_id
        self._slides_by_id[slide.slide_id] = slide
        self._pending_visual_slide = slide
        yield from self._emit_new_slide_event(slide)

    def _finalize_pending_visual_slide(
        self, *, visual_kind: str, segment_content: str
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        position = int(self._position_cursor or 0)
        pending = self._pending_visual_slide
        if (
            pending is None
            or int(pending.audio_position or 0) != position
            or (pending.visual_kind or "") != (visual_kind or "")
        ):
            yield from self._emit_visual_slide_for_current_position(
                visual_kind=visual_kind, segment_content=segment_content
            )
            return

        completed = NewSlideDTO(
            slide_id=pending.slide_id,
            generated_block_bid=pending.generated_block_bid,
            slide_index=int(pending.slide_index or 0),
            audio_position=int(pending.audio_position or 0),
            visual_kind=visual_kind,
            segment_type=self._segment_type_for_visual_kind(visual_kind),
            # Keep NEW_SLIDE payload lightweight; frontend renders from stream content.
            segment_content="",
            source_span=list(pending.source_span or []),
            is_placeholder=False,
        )
        self._slides_by_id[completed.slide_id] = completed
        self._pending_visual_slide = None
        yield from self._emit_new_slide_event(completed, force=True)

    def _sync_slide_registry_from_contract(self):
        slides, mapping = build_listen_slides_for_block(
            raw_content=self._raw_full_content,
            generated_block_bid=self.generated_block_bid,
            av_contract=self._av_contract,
            slide_index_offset=self.slide_index_offset,
        )
        if not slides or not mapping:
            return

        slide_by_id = {slide.slide_id: slide for slide in slides}
        for position, candidate_slide_id in sorted(mapping.items()):
            # Allow replacing placeholder slides with finalized slides from contract
            existing_slide_id = self._slide_id_by_position.get(position)
            if existing_slide_id:
                existing_slide = self._slides_by_id.get(existing_slide_id)
                # Skip if we already have a finalized slide for this position
                if existing_slide and not existing_slide.is_placeholder:
                    continue

            slide = slide_by_id.get(candidate_slide_id)
            if slide is None:
                continue
            self._slide_id_by_position[position] = candidate_slide_id
            self._slides_by_id[candidate_slide_id] = slide
            self._next_slide_index = max(
                self._next_slide_index, int(slide.slide_index or 0) + 1
            )

    def _build_fallback_slide(self, position: int) -> NewSlideDTO:
        slide = NewSlideDTO(
            slide_id=uuid.uuid4().hex,
            generated_block_bid=self.generated_block_bid,
            slide_index=self._next_slide_index,
            audio_position=position,
            visual_kind="placeholder",
            segment_type="placeholder",
            segment_content="",
            source_span=[],
            is_placeholder=True,
        )
        self._slide_id_by_position[position] = slide.slide_id
        self._slides_by_id[slide.slide_id] = slide
        self._next_slide_index += 1
        return slide

    def _ensure_slide_for_position(self, position: int) -> NewSlideDTO:
        self._sync_slide_registry_from_contract()

        existing_slide_id = self._slide_id_by_position.get(position)
        if existing_slide_id:
            existing_slide = self._slides_by_id.get(existing_slide_id)
            if existing_slide is not None:
                return existing_slide

        return self._build_fallback_slide(position)

    def _bind_slide_for_audio_event(
        self, event: RunMarkdownFlowDTO
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        if event.type not in {
            GeneratedType.AUDIO_SEGMENT,
            GeneratedType.AUDIO_COMPLETE,
        }:
            yield event
            return

        content = event.content
        position = int(getattr(content, "position", 0) or 0)
        slide = self._ensure_slide_for_position(position)

        if hasattr(content, "slide_id"):
            content.slide_id = slide.slide_id

        if slide.slide_id not in self._emitted_slide_ids:
            yield from self._emit_new_slide_event(slide)

        yield event

    def _emit_with_slide_binding(
        self, events: Generator[RunMarkdownFlowDTO, None, None]
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        for event in events:
            yield from self._bind_slide_for_audio_event(event)

    def _finalize_current(
        self, *, commit: bool
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        if self._current_processor is None:
            return
        did_complete = False
        for event in self._emit_with_slide_binding(
            self._current_processor.finalize(commit=commit)
        ):
            if event.type == GeneratedType.AUDIO_COMPLETE:
                did_complete = True
            yield event
        had_speakable_text = self._current_segment_has_speakable_text
        self._current_processor = None
        self._current_segment_has_speakable_text = False
        if did_complete or had_speakable_text:
            self._position_cursor += 1

    def _find_skip_end(self, raw: str) -> Optional[int]:
        """Find the end position of the current skip mode visual element."""
        from flaskr.service.tts.boundary_strategies import find_boundary_end

        return find_boundary_end(self._skip_mode, raw)

    def _find_next_boundary(self, raw: str) -> Optional[tuple[str, int, int, bool]]:
        """
        Return (kind, start, end, complete) for the earliest AV boundary in `raw`.

        `start` and `end` are indices in `raw`.
        """
        if not raw:
            return None

        fence_ranges = _get_fence_ranges(raw)
        candidates: list[tuple[str, int, int, bool]] = []

        # Fenced blocks are always treated as boundaries (even if unclosed).
        fence_start = raw.find("```")
        if fence_start != -1:
            fence_close = raw.find("```", fence_start + 3)
            if fence_close == -1:
                candidates.append(("fence", fence_start, len(raw), False))
            else:
                candidates.append(("fence", fence_start, fence_close + 3, True))

        svg_match = _find_first_match_outside_fence(
            raw, _AV_SVG_OPEN_PATTERN, fence_ranges
        )
        if svg_match is not None:
            svg_start = svg_match.start()
            svg_close = re.search(r"</svg>", raw[svg_start:], flags=re.IGNORECASE)
            if svg_close:
                candidates.append(
                    (
                        "svg",
                        svg_start,
                        svg_start + svg_close.end(),
                        True,
                    )
                )
            else:
                candidates.append(("svg", svg_start, len(raw), False))

        iframe_match = _find_first_match_outside_fence(
            raw, _AV_IFRAME_OPEN_PATTERN, fence_ranges
        )
        if iframe_match is not None:
            iframe_start = _rewind_fixed_marker_start(raw, iframe_match.start())
            iframe_close = _AV_IFRAME_CLOSE_PATTERN.search(raw, iframe_start)
            if iframe_close:
                iframe_end = _extend_fixed_marker_end(raw, iframe_close.end())
                candidates.append(("iframe", iframe_start, iframe_end, True))
            else:
                candidates.append(("iframe", iframe_start, len(raw), False))

        video_match = _find_first_match_outside_fence(
            raw, _AV_VIDEO_OPEN_PATTERN, fence_ranges
        )
        if video_match is not None:
            video_start = video_match.start()
            video_close = _AV_VIDEO_CLOSE_PATTERN.search(raw[video_start:])
            if video_close:
                candidates.append(
                    (
                        "video",
                        video_start,
                        video_start + video_close.end(),
                        True,
                    )
                )
            else:
                candidates.append(("video", video_start, len(raw), False))

        table_match = _find_first_match_outside_fence(
            raw, _AV_TABLE_OPEN_PATTERN, fence_ranges
        )
        if table_match is not None:
            table_start = table_match.start()
            table_close = _AV_TABLE_CLOSE_PATTERN.search(raw[table_start:])
            if table_close:
                candidates.append(
                    (
                        "html_table",
                        table_start,
                        table_start + table_close.end(),
                        True,
                    )
                )
            else:
                candidates.append(("html_table", table_start, len(raw), False))

        img_match = _find_first_match_outside_fence(
            raw, _AV_IMG_TAG_PATTERN, fence_ranges
        )
        if img_match is not None:
            candidates.append(("img", img_match.start(), img_match.end(), True))

        md_img_match = _find_first_match_outside_fence(
            raw, _AV_MARKDOWN_IMAGE_PATTERN, fence_ranges
        )
        if md_img_match is not None:
            candidates.append(
                ("md_img", md_img_match.start(), md_img_match.end(), True)
            )
        else:
            # Guard against split markdown image tokens in streaming chunks:
            # treat `![...` without a closing `)` as an incomplete visual boundary.
            md_img_start = _find_first_match_outside_fence(
                raw, _AV_MARKDOWN_IMAGE_START_PATTERN, fence_ranges
            )
            if md_img_start is not None:
                start = md_img_start.start()
                image_open = raw.find("](", start + 2)
                if image_open == -1:
                    candidates.append(("md_img", start, len(raw), False))
                else:
                    image_close = raw.find(")", image_open + 2)
                    if image_close == -1:
                        candidates.append(("md_img", start, len(raw), False))

        md_table = _find_markdown_table_block(raw, fence_ranges)
        if md_table is not None:
            start, end, complete = md_table
            candidates.append(("md_table", start, end, complete))

        sandbox_match = _find_first_match_outside_fence(
            raw, _AV_SANDBOX_START_PATTERN, fence_ranges
        )
        if sandbox_match is not None:
            sandbox_start = sandbox_match.start()
            sandbox_end, sandbox_complete = _find_html_block_end_with_complete(
                raw, sandbox_start
            )
            candidates.append(
                (
                    "sandbox",
                    sandbox_start,
                    sandbox_end,
                    sandbox_complete,
                )
            )

        if not candidates:
            return None

        return min(candidates, key=lambda item: item[1])

    def process_chunk(self, chunk: str) -> Generator[RunMarkdownFlowDTO, None, None]:
        if not chunk:
            if self._current_processor is not None:
                yield from self._process_processor_chunk(self._current_processor, "")
            return

        self._raw_full_content += chunk
        self._update_av_contract()
        if self._current_processor is not None:
            self._current_processor.av_contract = self._av_contract
        self._raw_buffer += chunk

        while self._raw_buffer:
            if self._skip_mode:
                skip_kind = self._skip_mode
                skip_end = self._find_skip_end(self._raw_buffer)
                if skip_end is None:
                    break
                skipped = self._raw_buffer[:skip_end]
                self._raw_buffer = self._raw_buffer[skip_end:]
                self._skip_mode = None
                if skip_kind in {
                    "fence",
                    "svg",
                    "iframe",
                    "video",
                    "html_table",
                    "md_table",
                    "sandbox",
                    "md_img",
                }:
                    yield from self._finalize_pending_visual_slide(
                        visual_kind=skip_kind,
                        segment_content=skipped,
                    )
                if skip_kind == "sandbox":
                    injected = _extract_speakable_text_from_sandbox_html(skipped)
                    if injected:
                        processor = self._ensure_processor()
                        yield from self._process_processor_chunk(processor, injected)
                continue

            boundary = self._find_next_boundary(self._raw_buffer)
            if boundary is None:
                # Keep a small tail so we don't lose boundary markers split across chunks,
                # e.g. `<di` + `v ...>` or partial fences/backticks.
                tail_len = 32
                if len(self._raw_buffer) <= tail_len:
                    break

                speakable = self._raw_buffer[:-tail_len]
                self._raw_buffer = self._raw_buffer[-tail_len:]
                if speakable:
                    processor = self._ensure_processor()
                    yield from self._process_processor_chunk(processor, speakable)
                continue

            kind, start, end, complete = boundary
            speakable = self._raw_buffer[:start]
            remainder = self._raw_buffer[start:]
            boundary_len = max(end - start, 0)
            boundary_chunk = remainder[:boundary_len] if boundary_len else ""

            if speakable:
                processor = self._ensure_processor()
                yield from self._process_processor_chunk(processor, speakable)

            # Boundary encountered: finalize the current speakable segment.
            yield from self._finalize_current(commit=False)
            if (
                kind
                in {
                    "fence",
                    "svg",
                    "iframe",
                    "video",
                    "html_table",
                    "md_table",
                    "sandbox",
                    "img",
                    "md_img",
                }
                and complete
                and boundary_chunk
            ):
                yield from self._finalize_pending_visual_slide(
                    visual_kind=kind,
                    segment_content=boundary_chunk,
                )

            # Consume the boundary itself.
            self._raw_buffer = remainder
            if (
                kind
                in {
                    "fence",
                    "svg",
                    "iframe",
                    "video",
                    "html_table",
                    "md_table",
                    "sandbox",
                    "md_img",
                }
                and not complete
            ):
                yield from self._emit_visual_slide_head_for_current_position(
                    visual_kind=kind
                )
                self._skip_mode = kind
                break
            self._raw_buffer = self._raw_buffer[boundary_len:]
            if kind == "sandbox" and boundary_chunk:
                injected = _extract_speakable_text_from_sandbox_html(boundary_chunk)
                if injected:
                    processor = self._ensure_processor()
                    yield from self._process_processor_chunk(processor, injected)

    def finalize(
        self, *, commit: bool = True
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        # Ignore any trailing non-speakable content if we are mid-boundary.
        if self._skip_mode:
            self._raw_buffer = ""
            self._skip_mode = None

        if self._raw_buffer:
            processor = self._ensure_processor()
            yield from self._process_processor_chunk(processor, self._raw_buffer)
            self._raw_buffer = ""

        yield from self._finalize_current(commit=commit)

        # After finalizing all content, re-sync slides from the complete AV contract
        # and emit finalized versions of any placeholder slides.
        self._sync_slide_registry_from_contract()
        for position, slide_id in sorted(self._slide_id_by_position.items()):
            slide = self._slides_by_id.get(slide_id)
            if slide is None:
                continue
            # Emit finalized slides that were created from contract (is_placeholder=False).
            # Skip slides that are still placeholders (no contract data for this position).
            if not slide.is_placeholder and slide_id not in self._emitted_slide_ids:
                yield from self._emit_new_slide_event(slide)

    def finalize_preview(self) -> Generator[RunMarkdownFlowDTO, None, None]:
        if self._skip_mode:
            self._raw_buffer = ""
            self._skip_mode = None

        if self._raw_buffer:
            processor = self._ensure_processor()
            yield from processor.process_chunk(self._raw_buffer)
            self._raw_buffer = ""

        if self._current_processor is None:
            return
        for event in self._current_processor.finalize_preview():
            yield event
        self._current_processor = None
