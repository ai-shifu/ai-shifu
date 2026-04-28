"""
Streaming TTS Processor with async synthesis.

This module provides real-time TTS synthesis during content streaming.
- Generic providers synthesize sentence-by-sentence as boundaries appear
- MiniMax RUN TTS sends one HTTP streaming request per mdflow text element
- TTS synthesis runs in background threads where the provider path supports it
"""

import base64
import logging
import traceback
import uuid
import threading
import time
from typing import Any, Generator, Optional, List, Dict
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, Future

from flask import Flask

from flaskr.api.tts import (
    synthesize_text,
    is_tts_configured,
    VoiceSettings,
    AudioSettings,
    get_default_voice_settings,
    get_default_audio_settings,
)
from flaskr.api.tts.minimax_provider import MinimaxTTSProvider
from flaskr.service.tts import preprocess_for_tts
from flaskr.service.tts.audio_utils import (
    assemble_audio_for_upload,
    export_audio_range_best_effort,
    get_audio_duration_ms,
)
from flaskr.common.log import AppLoggerProxy
from flaskr.service.tts.audio_record_utils import (
    build_completed_audio_record,
    save_audio_record,
)
from flaskr.service.tts.subtitle_utils import (
    append_subtitle_cue,
    normalize_subtitle_cues,
    select_subtitle_cues_for_segments,
)
from flaskr.service.metering import UsageContext
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PROD
from flaskr.util.uuid import generate_id
from flaskr.service.learn.learn_dtos import (
    RunMarkdownFlowDTO,
    GeneratedType,
    AudioSegmentDTO,
    AudioCompleteDTO,
)
from flaskr.service.learn.listen_slide_builder import build_visual_segments_for_block
from flaskr.service.tts.boundary_strategies import find_boundary_end
from flaskr.service.tts.patterns import (
    SENTENCE_ENDINGS,
)
from flaskr.service.tts.pipeline import (
    build_av_segmentation_contract,
    _find_next_av_boundary,
)
from flaskr.service.tts.minimax_run_tts import (
    should_use_minimax_http_stream,
)
from flaskr.service.tts.rpm_gate import TTSRpmQueueTimeout


logger = AppLoggerProxy(logging.getLogger(__name__))

# Global thread pool for TTS synthesis
_tts_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tts_")

_VISUAL_SLIDE_KINDS = frozenset(
    {
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
)
_VISUAL_SKIP_KINDS = frozenset(
    {
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
)

# Keep only a short tail when no visual boundary is detected so partial markers
# like `<div`, `<svg`, `![` or fenced code openers can span across chunks
# without delaying speakable text submission more than necessary.
_STREAM_BOUNDARY_GUARD_TAIL_CHARS = 12
_MINIMAX_HTTP_STREAM_SEGMENT_TARGET_MS = 1500
_MINIMAX_HTTP_STREAM_MAX_CHARS = 9500


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
        stream_element_number: int | None = None,
        stream_element_type: str | None = None,
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
        self.stream_element_number = (
            int(stream_element_number) if stream_element_number is not None else None
        )
        normalized_stream_element_type = str(stream_element_type or "").strip().lower()
        self.stream_element_type = normalized_stream_element_type or None
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
        self._use_minimax_http_stream = should_use_minimax_http_stream(tts_provider)

        # State
        self._buffer = ""
        self._raw_offset = 0  # tracks position in raw (unprocessed) buffer
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

        # Storage for all yielded audio data and text (for final concatenation/subtitles)
        # List of (index, audio_data, duration_ms, text)
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
        if self._use_minimax_http_stream:
            # MiniMax HTTP streaming is request-scoped: we send one request for
            # the whole mdflow text element when this processor is finalized.
            return

        # Check if we should submit a new TTS task
        self._try_submit_tts_task()

        # Yield any segments that are ready
        yield from self._yield_ready_segments()

    def drain_ready_segments(self) -> Generator[RunMarkdownFlowDTO, None, None]:
        """Yield already-synthesized segments without submitting new text."""
        yield from self._yield_ready_segments()

    def _try_submit_tts_task(self):
        """Submit all complete sentences currently available in the stream buffer."""
        if not self._buffer:
            return

        # Preprocess only the unprocessed portion of the raw buffer to avoid
        # offset drift caused by markdown constructs (bold, links, etc.)
        # becoming complete as the buffer grows.
        raw_remaining = self._buffer[self._raw_offset :]
        if not raw_remaining:
            return

        processable_text = preprocess_for_tts(raw_remaining)
        if not processable_text:
            return

        # Skip leading whitespace without producing a segment.
        processable_text = processable_text.lstrip()

        if len(processable_text) < 2:
            return

        # Only consume text up to the last complete sentence ending in the
        # currently processable stream window.
        sentence_matches = list(SENTENCE_ENDINGS.finditer(processable_text))
        if not sentence_matches:
            return

        last_match = sentence_matches[-1]
        completed_text = processable_text[: last_match.end()]

        # Advance the raw offset.  We need to find how far into the raw
        # remaining text the last sentence ending corresponds.  Because
        # preprocessing can change text length, we search for the sentence-
        # ending character in the raw text scanning forward.
        self._raw_offset += self._find_raw_consume_len(
            raw_remaining, last_match.end(), processable_text
        )

        self._submit_remaining_text_in_segments(
            completed_text,
            include_trailing_fragment=False,
        )

    @staticmethod
    def _find_raw_consume_len(
        raw_text: str, processed_end: int, processed_text: str
    ) -> int:
        """Map a position in preprocessed text back to the raw buffer.

        Uses binary search: find the smallest raw-text prefix whose
        preprocessed form covers ``processed_text[:processed_end]``.
        This is robust against arbitrary preprocessing transformations
        (bold/italic removal, code-block stripping, etc.).

        Args:
            raw_text: The raw (un-preprocessed) remaining buffer text.
            processed_end: End offset in *processed_text* up to which we
                want to consume.
            processed_text: The fully preprocessed (and lstripped) version
                of *raw_text*.

        Returns:
            Number of characters to consume from *raw_text*.
        """
        target = processed_text[:processed_end]
        # raw text is always >= preprocessed text in length (preprocessing
        # only removes content), so processed_end is a valid lower bound.
        lo, hi = processed_end, len(raw_text)
        best = hi  # worst case: consume everything
        while lo <= hi:
            mid = (lo + hi) // 2
            candidate = preprocess_for_tts(raw_text[:mid]).lstrip()
            if len(candidate) >= len(target) and candidate[: len(target)] == target:
                best = mid
                hi = mid - 1
            else:
                lo = mid + 1
        return best

    def _submit_tts_task(self, text: str):
        """Submit a TTS synthesis task to the background thread pool."""
        with self._lock:
            segment_index = self._segment_index
            self._segment_index += 1

        segment = TTSSegment(index=segment_index, text=text)

        logger.debug(
            f"Submitting TTS task {segment_index}: {len(text)} chars, provider={self.tts_provider or '(unset)'}"
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

    def _submit_remaining_text_in_segments(
        self,
        remaining_text: str,
        *,
        include_trailing_fragment: bool = True,
    ):
        """
        Submit text sentence-by-sentence.

        When ``include_trailing_fragment`` is True, any trailing text without
        sentence-ending punctuation is submitted as one final segment.

        Args:
            remaining_text: The text to be synthesized
            include_trailing_fragment: Whether to submit trailing text that does
                not end with sentence punctuation.
        """
        if not remaining_text or len(remaining_text) < 2:
            return

        logger.debug(
            f"Submitting remaining text in segments: {len(remaining_text)} chars"
        )

        cursor = 0
        for match in SENTENCE_ENDINGS.finditer(remaining_text):
            split_pos = match.end()
            segment_text = remaining_text[cursor:split_pos].strip()
            if segment_text and len(segment_text) >= 2:
                self._submit_tts_task(segment_text)
                logger.debug(
                    f"Submitted finalize segment: {len(segment_text)} chars, "
                    f"remaining: {len(remaining_text) - split_pos} chars"
                )
            cursor = split_pos

        if include_trailing_fragment:
            tail_text = remaining_text[cursor:].strip()
            if tail_text and len(tail_text) >= 2:
                self._submit_tts_task(tail_text)
                logger.debug(
                    f"Submitted finalize trailing fragment: {len(tail_text)} chars"
                )

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

                logger.debug(
                    f"TTS segment {segment.index} synthesized: "
                    f"text_len={len(segment.text)}, duration={segment.duration_ms}ms"
                )
            except TTSRpmQueueTimeout as e:
                self._enabled = False
                logger.warning(
                    "TTS segment %s skipped after RPM queue timeout: %s",
                    segment.index,
                    e,
                )
                segment.error = str(e)
                segment.is_ready = True
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
                        (
                            segment.index,
                            segment.audio_data,
                            segment.duration_ms,
                            segment.text,
                        )
                    )
                    logger.debug(
                        f"TTS stored segment {segment.index} for concatenation, "
                        f"total stored: {len(self._all_audio_data)}"
                    )

            if segment.audio_data and not segment.error:
                subtitle_cues: list[dict[str, Any]] = []
                with self._lock:
                    for (
                        saved_segment_index,
                        _saved_audio_data,
                        saved_duration_ms,
                        saved_segment_text,
                    ) in self._all_audio_data:
                        append_subtitle_cue(
                            subtitle_cues,
                            text=str(saved_segment_text or ""),
                            duration_ms=int(saved_duration_ms or 0),
                            segment_index=int(saved_segment_index or 0),
                            position=self.position,
                        )
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
                        stream_element_number=self.stream_element_number,
                        stream_element_type=self.stream_element_type,
                        av_contract=self.av_contract,
                        subtitle_cues=normalize_subtitle_cues(subtitle_cues),
                    ),
                )

                # Add small delay between yields to prevent burst delivery
                # This ensures segments are delivered at a steady pace
                if segments_yielded > 0:
                    time.sleep(0.1)  # 100ms delay between segment yields
                segments_yielded += 1

    def _yield_audio_segment_event(
        self,
        *,
        segment_index: int,
        audio_data: bytes,
        duration_ms: int,
        is_final: bool = False,
        subtitle_cues: Optional[list[dict[str, Any]]] = None,
    ) -> RunMarkdownFlowDTO:
        base64_audio = base64.b64encode(audio_data).decode("utf-8")
        return RunMarkdownFlowDTO(
            outline_bid=self.outline_bid,
            generated_block_bid=self.generated_block_bid,
            type=GeneratedType.AUDIO_SEGMENT,
            content=AudioSegmentDTO(
                segment_index=segment_index,
                audio_data=base64_audio,
                duration_ms=duration_ms,
                is_final=is_final,
                position=self.position,
                stream_element_number=self.stream_element_number,
                stream_element_type=self.stream_element_type,
                av_contract=self.av_contract,
                subtitle_cues=normalize_subtitle_cues(subtitle_cues or []),
            ),
        )

    def _build_segment_subtitle_cues(
        self, all_segments: list[tuple]
    ) -> list[dict[str, Any]]:
        subtitle_cues: list[dict[str, Any]] = []
        for segment_index, _audio_data, duration_ms, segment_text in all_segments:
            append_subtitle_cue(
                subtitle_cues,
                text=str(segment_text or ""),
                duration_ms=int(duration_ms or 0),
                segment_index=int(segment_index or 0),
                position=self.position,
            )
        return subtitle_cues

    def _sentence_units_for_tts(self, text: str) -> list[str]:
        units: list[str] = []
        cursor = 0
        for match in SENTENCE_ENDINGS.finditer(text or ""):
            split_pos = match.end()
            unit = text[cursor:split_pos].strip()
            if unit:
                units.append(unit)
            cursor = split_pos
        tail = (text or "")[cursor:].strip()
        if tail:
            units.append(tail)
        return units or ([text.strip()] if (text or "").strip() else [])

    def _split_minimax_http_stream_text(self, text: str) -> list[str]:
        parts: list[str] = []
        current = ""
        for unit in self._sentence_units_for_tts(text):
            if len(unit) > _MINIMAX_HTTP_STREAM_MAX_CHARS:
                if current:
                    parts.append(current)
                    current = ""
                for start in range(0, len(unit), _MINIMAX_HTTP_STREAM_MAX_CHARS):
                    chunk = unit[start : start + _MINIMAX_HTTP_STREAM_MAX_CHARS].strip()
                    if chunk:
                        parts.append(chunk)
                continue

            candidate = f"{current}\n{unit}" if current else unit
            if len(candidate) <= _MINIMAX_HTTP_STREAM_MAX_CHARS:
                current = candidate
                continue
            if current:
                parts.append(current)
            current = unit

        if current:
            parts.append(current)
        return parts

    @staticmethod
    def _minimax_subtitle_text(raw_item: dict[str, Any]) -> str:
        for key in ("text", "content", "sentence"):
            text = str(raw_item.get(key, "") or "").strip()
            if text:
                return text
        return ""

    @staticmethod
    def _minimax_subtitle_time_ms(
        raw_item: dict[str, Any],
        keys: tuple[str, ...],
        *,
        default_ms: int = 0,
    ) -> int:
        for key in keys:
            if key not in raw_item:
                continue
            raw_value = raw_item.get(key)
            if raw_value is None or raw_value == "":
                continue
            try:
                return int(round(float(raw_value)))
            except (TypeError, ValueError):
                continue
        return int(default_ms or 0)

    @classmethod
    def _minimax_raw_subtitle_key(cls, raw_item: dict[str, Any]) -> tuple[str, int]:
        text = cls._minimax_subtitle_text(raw_item)
        start_ms = cls._minimax_subtitle_time_ms(
            raw_item,
            ("time_begin", "start_ms", "start_time", "begin_time", "start", "begin"),
        )
        return text, start_ms

    def _extend_unique_minimax_subtitles(
        self,
        target: list[dict[str, Any]],
        incoming: list[dict[str, Any]],
    ) -> None:
        seen_indexes = {
            self._minimax_raw_subtitle_key(item): index
            for index, item in enumerate(target)
        }
        search_start = 0
        for raw_item in incoming or []:
            if not isinstance(raw_item, dict):
                continue
            key = self._minimax_raw_subtitle_key(raw_item)
            if not key[0]:
                continue
            existing_index = seen_indexes.get(key)
            if existing_index is not None:
                target[existing_index] = raw_item
                search_start = max(search_start, existing_index + 1)
                continue
            normalized_text = self._normalize_subtitle_compare_text(key[0])
            matching_index = None
            for index in range(search_start, len(target)):
                target_text = self._normalize_subtitle_compare_text(
                    self._minimax_subtitle_text(target[index])
                )
                if target_text == normalized_text:
                    matching_index = index
                    break
            if matching_index is not None:
                previous_key = self._minimax_raw_subtitle_key(target[matching_index])
                if seen_indexes.get(previous_key) == matching_index:
                    seen_indexes.pop(previous_key, None)
                target[matching_index] = raw_item
                seen_indexes[key] = matching_index
                search_start = matching_index + 1
                continue
            target.append(raw_item)
            seen_indexes[key] = len(target) - 1
            search_start = len(target)

    @staticmethod
    def _normalize_subtitle_compare_text(text: str) -> str:
        return "".join(str(text or "").lower().split())

    def _subtitle_cues_cover_text(
        self,
        subtitle_cues: list[dict[str, Any]],
        text: str,
    ) -> bool:
        normalized_units = [
            self._normalize_subtitle_compare_text(unit)
            for unit in self._sentence_units_for_tts(text)
        ]
        normalized_units = [unit for unit in normalized_units if unit]
        if not normalized_units:
            return bool(subtitle_cues)

        subtitle_blob = self._normalize_subtitle_compare_text(
            "".join(str(cue.get("text", "") or "") for cue in subtitle_cues or [])
        )
        if not subtitle_blob:
            return False
        return all(unit in subtitle_blob for unit in normalized_units)

    def _build_minimax_fallback_subtitle_cues(
        self,
        text: str,
        *,
        duration_ms: int,
        offset_ms: int = 0,
        segment_index: int = 0,
    ) -> list[dict[str, Any]]:
        units = self._sentence_units_for_tts(text)
        units = [unit.strip() for unit in units if unit.strip()]
        if not units:
            return []

        safe_offset_ms = max(int(offset_ms or 0), 0)
        safe_duration_ms = max(int(duration_ms or 0), 0)
        weights = [max(len(unit), 1) for unit in units]
        remaining_duration_ms = safe_duration_ms
        remaining_weight = sum(weights) or 1
        cursor_ms = safe_offset_ms
        cues: list[dict[str, Any]] = []

        for index, unit in enumerate(units):
            if index == len(units) - 1:
                unit_duration_ms = remaining_duration_ms
            elif safe_duration_ms > 0:
                unit_duration_ms = int(
                    round(remaining_duration_ms * weights[index] / remaining_weight)
                )
                unit_duration_ms = max(min(unit_duration_ms, remaining_duration_ms), 0)
            else:
                unit_duration_ms = 0

            end_ms = cursor_ms + unit_duration_ms
            cues.append(
                {
                    "text": unit,
                    "start_ms": cursor_ms,
                    "end_ms": max(end_ms, cursor_ms),
                    "segment_index": int(segment_index or 0),
                    "position": self.position,
                }
            )
            cursor_ms = max(end_ms, cursor_ms)
            remaining_duration_ms = max(remaining_duration_ms - unit_duration_ms, 0)
            remaining_weight = max(remaining_weight - weights[index], 1)

        return cues

    @staticmethod
    def _subtitle_cues_end_ms(subtitle_cues: list[dict[str, Any]]) -> int:
        normalized_cues = normalize_subtitle_cues(subtitle_cues)
        if not normalized_cues:
            return 0
        return max(int(cue.get("end_ms", 0) or 0) for cue in normalized_cues)

    def _build_minimax_provider_subtitle_cues(
        self,
        *,
        request_subtitles: list[dict[str, Any]],
        subtitle_offset_ms: int,
        segment_index: int = 0,
    ) -> list[dict[str, Any]]:
        return normalize_subtitle_cues(
            self._minimax_subtitles_to_cues(
                request_subtitles,
                offset_ms=subtitle_offset_ms,
                segment_index=segment_index,
            )
        )

    def _minimax_subtitles_to_cues(
        self,
        subtitles: list[dict[str, Any]],
        *,
        offset_ms: int = 0,
        segment_index: int = 0,
    ) -> list[dict[str, Any]]:
        cues: list[dict[str, Any]] = []
        for raw_item in subtitles or []:
            if not isinstance(raw_item, dict):
                continue
            text = self._minimax_subtitle_text(raw_item)
            if not text:
                continue
            start_ms = self._minimax_subtitle_time_ms(
                raw_item,
                (
                    "time_begin",
                    "start_ms",
                    "start_time",
                    "begin_time",
                    "start",
                    "begin",
                ),
            )
            end_ms = self._minimax_subtitle_time_ms(
                raw_item,
                ("time_end", "end_ms", "end_time", "finish_time", "end", "finish"),
                default_ms=start_ms,
            )
            start_ms = max(start_ms + int(offset_ms or 0), 0)
            end_ms = max(end_ms + int(offset_ms or 0), start_ms)
            cues.append(
                {
                    "text": text,
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "segment_index": int(segment_index or 0),
                    "position": self.position,
                }
            )
        return cues

    def _store_stream_audio_segment(
        self,
        *,
        audio_data: bytes,
        duration_ms: int,
        text: str,
        subtitle_cues: Optional[list[dict[str, Any]]] = None,
    ) -> tuple[int, RunMarkdownFlowDTO]:
        with self._lock:
            segment_index = self._segment_index
            self._segment_index += 1
            self._all_audio_data.append(
                (
                    segment_index,
                    audio_data,
                    int(duration_ms or 0),
                    text,
                )
            )
        return segment_index, self._yield_audio_segment_event(
            segment_index=segment_index,
            audio_data=audio_data,
            duration_ms=int(duration_ms or 0),
            subtitle_cues=subtitle_cues,
        )

    def _yield_audio_complete_from_segments(
        self,
        *,
        all_segments: list[tuple],
        raw_text: str,
        cleaned_text: str,
        cleaned_text_length: int,
        subtitle_cues: Optional[list[dict[str, Any]]] = None,
        event_subtitle_cues: Optional[list[dict[str, Any]]] = None,
        commit: bool = True,
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        if not all_segments:
            logger.warning(
                "No audio segments to concatenate. segment_index=%s, next_yield_index=%s",
                self._segment_index,
                self._next_yield_index,
            )
            return

        all_segments.sort(key=lambda x: x[0])
        audio_data_list = [s[1] for s in all_segments]
        audio_durations_ms = [int(s[2] or 0) for s in all_segments]
        segment_indices = [int(s[0] or 0) for s in all_segments]
        effective_subtitle_cues = (
            normalize_subtitle_cues(subtitle_cues)
            if subtitle_cues
            else self._build_segment_subtitle_cues(all_segments)
        )
        effective_event_subtitle_cues = (
            normalize_subtitle_cues(event_subtitle_cues)
            if event_subtitle_cues is not None
            else effective_subtitle_cues
        )

        try:
            assembly_result = assemble_audio_for_upload(
                audio_data_list,
                segment_durations_ms=audio_durations_ms,
                segment_indices=segment_indices,
                output_format="mp3",
            )
            final_audio = assembly_result.audio_data
            final_duration_ms = int(assembly_result.duration_ms or 0)
            uploaded_subtitle_cues = select_subtitle_cues_for_segments(
                effective_subtitle_cues,
                assembly_result.included_segment_indices,
                duration_ms=final_duration_ms,
            )
            uploaded_event_subtitle_cues = select_subtitle_cues_for_segments(
                effective_event_subtitle_cues,
                assembly_result.included_segment_indices,
                duration_ms=final_duration_ms,
            )
            if assembly_result.used_fallback:
                logger.warning(
                    "TTS final audio fell back to first decodable segment. "
                    "audio_bid=%s included_segments=%s source_segments=%s",
                    self._audio_bid,
                    assembly_result.included_segment_indices,
                    assembly_result.source_segment_count,
                )
            file_size = len(final_audio)

            from flaskr.service.tts.tts_handler import upload_audio_to_oss

            oss_url, bucket_name = upload_audio_to_oss(
                self.app, final_audio, self._audio_bid
            )

            audio_record = build_completed_audio_record(
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
                audio_format=self.audio_settings.format or "mp3",
                sample_rate=self.audio_settings.sample_rate or 24000,
                voice_settings=self.voice_settings,
                tts_model=self.tts_model or "",
                text_length=cleaned_text_length,
                segment_count=assembly_result.segment_count or len(audio_data_list),
                subtitle_cues=uploaded_subtitle_cues,
            )
            save_audio_record(audio_record, commit=commit)

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
                duration_ms=sum(audio_durations_ms) or final_duration_ms or 0,
                segment_count=len(audio_data_list),
                voice_settings=self.voice_settings,
                audio_settings=self.audio_settings,
                is_stream=True,
            )

            yield RunMarkdownFlowDTO(
                outline_bid=self.outline_bid,
                generated_block_bid=self.generated_block_bid,
                type=GeneratedType.AUDIO_COMPLETE,
                content=AudioCompleteDTO(
                    audio_url=oss_url,
                    audio_bid=self._audio_bid,
                    duration_ms=final_duration_ms,
                    position=self.position,
                    stream_element_number=self.stream_element_number,
                    stream_element_type=self.stream_element_type,
                    av_contract=self.av_contract,
                    subtitle_cues=normalize_subtitle_cues(uploaded_event_subtitle_cues),
                ),
            )

            logger.debug(
                "TTS complete: audio_bid=%s, segments=%s, duration=%sms",
                self._audio_bid,
                len(audio_data_list),
                final_duration_ms,
            )
        except Exception as e:
            logger.error(f"Failed to finalize TTS: {e}\n{traceback.format_exc()}")

    def _finalize_minimax_http_stream(
        self,
        *,
        raw_text: str,
        cleaned_text: str,
        cleaned_text_length: int,
        commit: bool,
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        request_texts = self._split_minimax_http_stream_text(cleaned_text)
        if not self._enabled or not request_texts:
            return

        provider = MinimaxTTSProvider()
        live_subtitle_cues: list[dict[str, Any]] = []
        final_subtitle_cues: list[dict[str, Any]] = []
        subtitle_offset_ms = 0

        from flaskr.service.tts.tts_usage_recorder import record_tts_segment_usage

        for request_index, request_text in enumerate(request_texts):
            request_started_at = time.monotonic()
            audio_chunks: list[bytes] = []
            emitted_ms = 0
            request_duration_ms = 0
            request_word_count = 0
            request_format = self.audio_settings.format or "mp3"
            request_subtitles: list[dict[str, Any]] = []
            request_final_subtitle_cues: list[dict[str, Any]] = []

            for chunk in provider.stream_synthesize(
                text=request_text,
                voice_settings=self.voice_settings,
                audio_settings=self.audio_settings,
                model=self.tts_model,
            ):
                if chunk.audio_data:
                    audio_chunks.append(chunk.audio_data)
                if chunk.format:
                    request_format = chunk.format
                if chunk.is_final:
                    request_duration_ms = int(chunk.duration_ms or request_duration_ms)
                    request_word_count = int(chunk.word_count or request_word_count)
                if chunk.subtitles:
                    self._extend_unique_minimax_subtitles(
                        request_subtitles,
                        chunk.subtitles,
                    )

                accumulated_audio = b"".join(audio_chunks)
                if not accumulated_audio:
                    continue

                progressive_request_subtitle_cues = (
                    self._build_minimax_provider_subtitle_cues(
                        request_subtitles=request_subtitles,
                        subtitle_offset_ms=subtitle_offset_ms,
                        segment_index=request_index,
                    )
                )
                request_subtitle_coverage_end_ms = max(
                    self._subtitle_cues_end_ms(progressive_request_subtitle_cues)
                    - int(subtitle_offset_ms or 0),
                    0,
                )

                if chunk.is_final:
                    if request_duration_ms <= 0:
                        request_duration_ms = get_audio_duration_ms(
                            accumulated_audio,
                            format=request_format or "mp3",
                        )
                    if progressive_request_subtitle_cues and (
                        self._subtitle_cues_cover_text(
                            progressive_request_subtitle_cues,
                            request_text,
                        )
                    ):
                        request_final_subtitle_cues = progressive_request_subtitle_cues
                        target_end_ms = max(
                            request_subtitle_coverage_end_ms, emitted_ms
                        )
                    else:
                        if progressive_request_subtitle_cues:
                            logger.debug(
                                "MiniMax subtitles did not cover full request text; "
                                "using fallback cues. request_index=%s, subtitles=%s",
                                request_index,
                                len(progressive_request_subtitle_cues),
                            )
                        request_final_subtitle_cues = (
                            self._build_minimax_fallback_subtitle_cues(
                                request_text,
                                duration_ms=int(request_duration_ms or emitted_ms or 0),
                                offset_ms=subtitle_offset_ms,
                                segment_index=request_index,
                            )
                        )
                        target_end_ms = max(int(request_duration_ms or 0), emitted_ms)
                    event_request_subtitle_cues = request_final_subtitle_cues
                else:
                    if not progressive_request_subtitle_cues:
                        continue
                    target_end_ms = request_subtitle_coverage_end_ms
                    event_request_subtitle_cues = progressive_request_subtitle_cues

                if target_end_ms <= emitted_ms:
                    continue

                audio_piece = b""
                piece_duration_ms = 0
                audio_piece, piece_duration_ms = export_audio_range_best_effort(
                    accumulated_audio,
                    start_ms=emitted_ms,
                    end_ms=target_end_ms,
                    input_format=request_format or "mp3",
                    output_format=self.audio_settings.format or "mp3",
                )

                if (
                    not chunk.is_final
                    and piece_duration_ms < _MINIMAX_HTTP_STREAM_SEGMENT_TARGET_MS
                ):
                    continue

                if (
                    not audio_piece
                    and chunk.is_final
                    and emitted_ms == 0
                    and target_end_ms >= int(request_duration_ms or 0)
                ):
                    audio_piece = accumulated_audio
                    piece_duration_ms = request_duration_ms or get_audio_duration_ms(
                        audio_piece,
                        format=request_format or "mp3",
                    )

                if not audio_piece or piece_duration_ms <= 0:
                    continue

                emitted_ms += int(piece_duration_ms or 0)
                progressive_subtitle_cues = normalize_subtitle_cues(
                    list(live_subtitle_cues or []) + event_request_subtitle_cues
                )
                _segment_index, event = self._store_stream_audio_segment(
                    audio_data=audio_piece,
                    duration_ms=piece_duration_ms,
                    text=request_text,
                    subtitle_cues=progressive_subtitle_cues,
                )
                yield event

            if request_duration_ms <= 0:
                request_duration_ms = emitted_ms
            if request_word_count:
                self._word_count_total += request_word_count
            if not request_final_subtitle_cues:
                request_subtitle_cues = self._minimax_subtitles_to_cues(
                    request_subtitles,
                    offset_ms=subtitle_offset_ms,
                    segment_index=request_index,
                )
                if request_subtitle_cues and self._subtitle_cues_cover_text(
                    request_subtitle_cues,
                    request_text,
                ):
                    request_final_subtitle_cues = request_subtitle_cues
                else:
                    if request_subtitle_cues:
                        logger.debug(
                            "MiniMax subtitles did not cover full request text; "
                            "using fallback cues. request_index=%s, subtitles=%s",
                            request_index,
                            len(request_subtitle_cues),
                        )
                    request_final_subtitle_cues = (
                        self._build_minimax_fallback_subtitle_cues(
                            request_text,
                            duration_ms=int(request_duration_ms or emitted_ms or 0),
                            offset_ms=subtitle_offset_ms,
                            segment_index=request_index,
                        )
                    )
            final_subtitle_cues.extend(request_final_subtitle_cues)
            live_subtitle_cues = normalize_subtitle_cues(
                list(live_subtitle_cues or []) + request_final_subtitle_cues
            )
            request_subtitle_end_ms = self._subtitle_cues_end_ms(
                request_final_subtitle_cues
            )
            if request_subtitle_end_ms > subtitle_offset_ms:
                subtitle_offset_ms = request_subtitle_end_ms
            else:
                subtitle_offset_ms += int(request_duration_ms or emitted_ms or 0)

            record_tts_segment_usage(
                app=self.app,
                usage_context=self.usage_context,
                provider=self.tts_provider or "",
                model=self.tts_model or "",
                segment_text=request_text,
                word_count=request_word_count,
                duration_ms=int(request_duration_ms or 0),
                latency_ms=int((time.monotonic() - request_started_at) * 1000),
                voice_settings=self.voice_settings,
                audio_settings=self.audio_settings,
                is_stream=True,
                parent_usage_bid=self._usage_parent_bid,
                segment_index=request_index,
            )

        with self._lock:
            all_segments = list(self._all_audio_data)

        yield from self._yield_audio_complete_from_segments(
            all_segments=all_segments,
            raw_text=raw_text,
            cleaned_text=cleaned_text,
            cleaned_text_length=cleaned_text_length,
            subtitle_cues=final_subtitle_cues,
            event_subtitle_cues=live_subtitle_cues,
            commit=commit,
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

        logger.debug(
            f"TTS finalize called: enabled={self._enabled}, "
            f"buffer_len={len(self._buffer)}, "
            f"segment_index={self._segment_index}, "
            f"pending_futures={len(self._pending_futures)}, "
            f"all_audio_data={len(self._all_audio_data)}"
        )
        has_existing_work = bool(
            self._pending_futures or self._completed_segments or self._all_audio_data
        )
        if not self._enabled and not has_existing_work:
            logger.debug("TTS finalize: TTS not enabled, returning early")
            return

        if self._use_minimax_http_stream:
            self._raw_offset = len(self._buffer)
            self._buffer = ""
            yield from self._finalize_minimax_http_stream(
                raw_text=raw_text,
                cleaned_text=cleaned_text.strip(),
                cleaned_text_length=cleaned_text_length,
                commit=commit,
            )
            return

        # Submit any remaining buffer content in segments to avoid burst
        if self._enabled and self._buffer:
            raw_remaining = self._buffer[self._raw_offset :]
            remaining_text = preprocess_for_tts(raw_remaining).strip()
            # Use segmented submission to maintain consistent pacing
            self._submit_remaining_text_in_segments(remaining_text)
            self._raw_offset = len(self._buffer)
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
            logger.debug(
                f"TTS finalize: _all_audio_data has {len(self._all_audio_data)} segments"
            )

        if not all_segments:
            logger.warning(
                f"No audio segments to concatenate. "
                f"segment_index={self._segment_index}, "
                f"next_yield_index={self._next_yield_index}, "
                f"completed_segments keys={list(self._completed_segments.keys())}"
            )
            return

        yield from self._yield_audio_complete_from_segments(
            all_segments=all_segments,
            raw_text=raw_text,
            cleaned_text=cleaned_text,
            cleaned_text_length=cleaned_text_length,
            commit=commit,
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
        element_index_offset: int = 0,
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
        self.element_index_offset = int(element_index_offset or 0)

        self._position_cursor = 0
        self._current_processor: Optional[StreamingTTSProcessor] = None
        self._raw_buffer = ""
        self._raw_full_content = ""
        self._av_contract: Optional[Dict[str, Any]] = None
        self._next_element_index = self.element_index_offset
        self._current_segment_has_speakable_text = False

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
        for event in processor.process_chunk(chunk):
            yield event

    @property
    def next_element_index(self) -> int:
        return int(self._next_element_index or self.element_index_offset)

    @property
    def has_pending_visual_boundary(self) -> bool:
        return bool(self._skip_mode)

    def _refresh_next_element_index_from_contract(self):
        segments, _ = build_visual_segments_for_block(
            app=self.app,
            raw_content=self._raw_full_content,
            generated_block_bid=self.generated_block_bid,
            av_contract=self._av_contract,
            element_index_offset=self.element_index_offset,
        )
        if not segments:
            return
        self._next_element_index = max(
            self._next_element_index,
            max(seg.element_index + 1 for seg in segments),
        )

    def _finalize_current(
        self, *, commit: bool
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        if self._current_processor is None:
            return
        did_complete = False
        for event in self._current_processor.finalize(commit=commit):
            if event.type == GeneratedType.AUDIO_COMPLETE:
                did_complete = True
            yield event
        had_speakable_text = self._current_segment_has_speakable_text
        self._current_processor = None
        self._current_segment_has_speakable_text = False
        if did_complete or had_speakable_text:
            self._position_cursor += 1

    def _find_next_boundary(self, raw: str) -> Optional[tuple[str, int, int, bool]]:
        return _find_next_av_boundary(raw, include_partial_md_image=True)

    def process_chunk(self, chunk: str) -> Generator[RunMarkdownFlowDTO, None, None]:
        if not chunk:
            yield from self.drain_ready_segments()
            return

        self._raw_full_content += chunk
        self._update_av_contract()
        if self._current_processor is not None:
            self._current_processor.av_contract = self._av_contract
        self._raw_buffer += chunk

        while self._raw_buffer:
            if self._skip_mode:
                skip_kind = self._skip_mode
                skip_end = find_boundary_end(skip_kind, self._raw_buffer)
                if skip_end is None:
                    break
                self._raw_buffer = self._raw_buffer[skip_end:]
                self._skip_mode = None
                if skip_kind in _VISUAL_SKIP_KINDS:
                    self._next_element_index += 1
                continue

            boundary = self._find_next_boundary(self._raw_buffer)
            if boundary is None:
                # Keep a small tail so we don't lose boundary markers split across chunks,
                # e.g. `<di` + `v ...>` or partial fences/backticks.
                tail_len = _STREAM_BOUNDARY_GUARD_TAIL_CHARS
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

            if speakable:
                processor = self._ensure_processor()
                yield from self._process_processor_chunk(processor, speakable)

            # Boundary encountered: finalize the current speakable segment.
            yield from self._finalize_current(commit=False)
            if kind in _VISUAL_SLIDE_KINDS and complete and boundary_len > 0:
                self._next_element_index += 1

            # Consume the boundary itself.
            self._raw_buffer = remainder
            if kind in _VISUAL_SKIP_KINDS and not complete:
                self._skip_mode = kind
                break
            self._raw_buffer = self._raw_buffer[boundary_len:]

    def drain_ready_segments(self) -> Generator[RunMarkdownFlowDTO, None, None]:
        """Yield already-ready audio events for the current speakable segment."""
        if self._current_processor is None:
            return
        yield from self._current_processor.drain_ready_segments()

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

        # Refresh cursor from the full contract so next block can continue element index.
        self._refresh_next_element_index_from_contract()
