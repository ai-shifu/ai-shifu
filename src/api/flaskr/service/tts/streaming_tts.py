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
import os
from typing import Generator, Optional, List, Dict, Iterable
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
from flaskr.service.tts.sandbox_split import split_text_by_sandbox_boundaries
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
    text: str
    audio_data: Optional[bytes] = None
    duration_ms: int = 0
    word_count: int = 0
    latency_ms: int = 0
    error: Optional[str] = None
    is_ready: bool = False


class _StreamingTTSPart:
    """
    Streaming TTS state for a single audio part (identified by `position`).

    This class reuses the original StreamingTTSProcessor segmentation behavior
    (first sentence ASAP, then batch by `max_segment_chars` at sentence boundaries).
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
        position: int,
        max_segment_chars: int,
        tts_provider: str,
        tts_model: str,
        voice_settings: VoiceSettings,
        audio_settings: AudioSettings,
        usage_scene: int,
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
        self.voice_settings = voice_settings
        self.audio_settings = audio_settings
        self.usage_scene = usage_scene

        self._buffer = ""
        self._processed_text_offset = 0
        self._first_sentence_done = False
        self._segment_index = 0
        self._audio_bid = uuid.uuid4().hex
        self._usage_parent_bid = generate_id(app)
        self._word_count_total = 0

        self.usage_context = UsageContext(
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            progress_record_bid=progress_record_bid,
            generated_block_bid=generated_block_bid,
            audio_bid=self._audio_bid,
            usage_scene=usage_scene,
        )

        self._completed_segments: Dict[int, TTSSegment] = {}
        self._pending_futures: List[Future] = []
        self._next_yield_index = 0
        self._lock = threading.Lock()

        # List of (index, audio_data, duration_ms)
        self._all_audio_data: List[tuple] = []

        self._closed = False
        self._cleaned_text_length = 0

    @property
    def audio_bid(self) -> str:
        return self._audio_bid

    @property
    def cleaned_text_length(self) -> int:
        return int(self._cleaned_text_length or 0)

    @property
    def word_count_total(self) -> int:
        return int(self._word_count_total or 0)

    @property
    def usage_parent_bid(self) -> str:
        return self._usage_parent_bid

    @property
    def raw_text(self) -> str:
        return self._buffer

    @property
    def segment_count(self) -> int:
        return int(self._segment_index or 0)

    @property
    def has_audio(self) -> bool:
        return bool(self._all_audio_data)

    def append_text(self, delta: str) -> Generator[RunMarkdownFlowDTO, None, None]:
        if not delta:
            yield from self._yield_ready_segments()
            return
        if self._closed:
            # Ignore late text for closed parts (should not happen).
            yield from self._yield_ready_segments()
            return

        self._buffer += delta
        self._try_submit_tts_task()
        yield from self._yield_ready_segments()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True

        # Submit any remaining buffer content as a final segment.
        if self._buffer:
            try:
                full_text = preprocess_for_tts(self._buffer)
            except Exception:
                full_text = ""

            self._cleaned_text_length = len(full_text or "")
            if self._processed_text_offset > len(full_text):
                self._processed_text_offset = len(full_text)

            remaining_text = (full_text or "")[self._processed_text_offset :].strip()
            if remaining_text and len(remaining_text) >= 2:
                self._submit_tts_task(remaining_text)

    def wait_for_futures(self) -> None:
        # Wait for all pending TTS tasks to complete.
        for future in self._pending_futures:
            try:
                future.result(timeout=60)  # Max 60s per segment
            except Exception as exc:
                logger.error(f"TTS future failed: {exc}")

    def yield_ready_segments(self) -> Generator[RunMarkdownFlowDTO, None, None]:
        yield from self._yield_ready_segments()

    def _try_submit_tts_task(self) -> None:
        if not self._buffer:
            return

        processable_text = preprocess_for_tts(self._buffer)
        if not processable_text:
            return

        if self._processed_text_offset > len(processable_text):
            self._processed_text_offset = len(processable_text)

        remaining_text = processable_text[self._processed_text_offset :]
        if not remaining_text:
            return

        leading_ws = len(remaining_text) - len(remaining_text.lstrip())
        if leading_ws:
            self._processed_text_offset += leading_ws
            remaining_text = remaining_text[leading_ws:]

        if len(remaining_text) < 2:
            return

        text_to_synthesize: Optional[str] = None
        consume_len = 0

        if not self._first_sentence_done:
            match = SENTENCE_ENDINGS.search(remaining_text)
            if match:
                consume_len = match.end()
                candidate = remaining_text[:consume_len]
                text_to_synthesize = candidate.strip()
                if text_to_synthesize and len(text_to_synthesize) >= 2:
                    self._first_sentence_done = True
        else:
            if len(remaining_text) >= self.max_segment_chars:
                chunk = remaining_text[: self.max_segment_chars]
                matches = list(SENTENCE_ENDINGS.finditer(chunk))
                consume_len = matches[-1].end() if matches else len(chunk)
                candidate = remaining_text[:consume_len]
                text_to_synthesize = candidate.strip()

        if consume_len:
            self._processed_text_offset += consume_len

        if text_to_synthesize:
            self._submit_tts_task(text_to_synthesize)

    def _submit_tts_task(self, text: str) -> None:
        with self._lock:
            segment_index = self._segment_index
            self._segment_index += 1

        segment = TTSSegment(index=segment_index, text=text)
        logger.info(
            f"Submitting TTS task pos={self.position} seg={segment_index}: "
            f"{len(text)} chars, provider={self.tts_provider or '(unset)'}"
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
                    f"TTS segment pos={self.position} seg={segment.index} synthesized: "
                    f"text_len={len(segment.text)}, duration={segment.duration_ms}ms"
                )
            except Exception as exc:
                logger.error(
                    f"TTS segment pos={self.position} seg={segment.index} failed: {exc}"
                )
                segment.error = str(exc)
                segment.is_ready = True

            with self._lock:
                self._completed_segments[segment.index] = segment

        return segment

    def _yield_ready_segments(self) -> Generator[RunMarkdownFlowDTO, None, None]:
        while True:
            with self._lock:
                if self._next_yield_index not in self._completed_segments:
                    break

                segment = self._completed_segments.pop(self._next_yield_index)
                self._next_yield_index += 1

                if segment.audio_data and not segment.error:
                    self._all_audio_data.append(
                        (segment.index, segment.audio_data, segment.duration_ms)
                    )

                is_final = bool(
                    self._closed and self._next_yield_index >= self._segment_index
                )

            if segment.audio_data and not segment.error:
                base64_audio = base64.b64encode(segment.audio_data).decode("utf-8")
                yield RunMarkdownFlowDTO(
                    outline_bid=self.outline_bid,
                    generated_block_bid=self.generated_block_bid,
                    type=GeneratedType.AUDIO_SEGMENT,
                    content=AudioSegmentDTO(
                        position=self.position,
                        segment_index=segment.index,
                        audio_data=base64_audio,
                        duration_ms=segment.duration_ms,
                        is_final=is_final,
                    ),
                )


class StreamingTTSProcessor:
    """
    Sandbox-aware Streaming TTS Processor.

    In listen/audiovisual mode, generated markdown may contain sandbox elements
    (SVG/mermaid/images/etc). We split the stream into multiple audio parts by
    sandbox boundaries and synthesize each part independently with a 0-based
    `position`.

    Each part keeps the existing long-text splitting behavior, while the
    frontend controls pacing by playing `position`-aligned audio for sandbox
    slides.
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
        self.max_segment_chars = int(max_segment_chars or 300)
        self.tts_provider = tts_provider
        self.tts_model = tts_model
        self._usage_scene = usage_scene

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

        self._enabled = is_tts_configured(tts_provider)
        if not self._enabled:
            logger.warning(
                f"TTS is not configured for provider '{tts_provider or '(unset)'}', streaming TTS disabled"
            )

        # Raw markdown buffer used for sandbox boundary detection.
        self._raw_buffer = ""
        self._raw_parts: list[str] = []

        # Active parts (closed parts remain here until finalize uploads them).
        self._parts: list[_StreamingTTSPart] = []

        # Current open part (receives new text).
        self._position_cursor = 0
        self._open_part: Optional[_StreamingTTSPart] = None

    def _new_part(self) -> _StreamingTTSPart:
        return _StreamingTTSPart(
            app=self.app,
            generated_block_bid=self.generated_block_bid,
            outline_bid=self.outline_bid,
            progress_record_bid=self.progress_record_bid,
            user_bid=self.user_bid,
            shifu_bid=self.shifu_bid,
            position=self._position_cursor,
            max_segment_chars=self.max_segment_chars,
            tts_provider=self.tts_provider,
            tts_model=self.tts_model,
            voice_settings=self.voice_settings,
            audio_settings=self.audio_settings,
            usage_scene=self._usage_scene,
        )

    def _iter_parts_in_order(self) -> Iterable[_StreamingTTSPart]:
        return sorted(self._parts, key=lambda p: int(p.position or 0))

    def process_chunk(self, chunk: str) -> Generator[RunMarkdownFlowDTO, None, None]:
        if not self._enabled:
            return

        # Always try to drain any ready segments (even if chunk is empty).
        if not chunk:
            for part in self._iter_parts_in_order():
                yield from part.yield_ready_segments()
            return

        self._raw_buffer += chunk
        new_parts = split_text_by_sandbox_boundaries(self._raw_buffer)

        if not self._raw_parts:
            # First chunk: initialize open part and feed the current tail.
            self._open_part = self._new_part()
            self._parts.append(self._open_part)
            if new_parts:
                yield from self._open_part.append_text(new_parts[-1])
            self._raw_parts = new_parts
            # Drain any other ready segments.
            for part in self._iter_parts_in_order():
                if part is not self._open_part:
                    yield from part.yield_ready_segments()
            return

        prev_parts = self._raw_parts
        prev_tail = prev_parts[-1] if prev_parts else ""

        if len(new_parts) <= len(prev_parts):
            # No new sandbox boundary finalized; only the tail may have grown.
            new_tail = new_parts[-1] if new_parts else ""
            delta = ""
            if new_tail.startswith(prev_tail):
                delta = new_tail[len(prev_tail) :]
            else:
                # Best-effort fallback: do not replay; only append the non-common suffix.
                common_len = len(os.path.commonprefix([prev_tail, new_tail]))  # type: ignore[name-defined]
                delta = new_tail[common_len:]

            if self._open_part:
                yield from self._open_part.append_text(delta)

            self._raw_parts = new_parts
            for part in self._iter_parts_in_order():
                if part is self._open_part:
                    continue
                yield from part.yield_ready_segments()
            return

        # One or more sandbox boundaries finalized; close the previous open part and
        # start new parts for each newly created raw section.
        old_len = len(prev_parts)
        new_len = len(new_parts)

        if self._open_part:
            closed_text = new_parts[old_len - 1] if (old_len - 1) < new_len else ""
            delta = ""
            if closed_text.startswith(prev_tail):
                delta = closed_text[len(prev_tail) :]
            elif prev_tail.startswith(closed_text):
                delta = ""
            else:
                common_len = len(os.path.commonprefix([prev_tail, closed_text]))  # type: ignore[name-defined]
                delta = closed_text[common_len:]
            yield from self._open_part.append_text(delta)
            self._open_part.close()

            # If the part has no segments at all, drop it without advancing position.
            if self._open_part.segment_count <= 0 and not self._open_part.has_audio:
                try:
                    self._parts.remove(self._open_part)
                except ValueError:
                    pass
            else:
                self._position_cursor += 1

        # Create and close intermediate fully-bounded parts.
        for raw_idx in range(old_len, max(new_len - 1, old_len)):
            part_text = new_parts[raw_idx] if raw_idx < len(new_parts) else ""
            if part_text is None:
                part_text = ""
            part = self._new_part()
            self._parts.append(part)
            if part_text:
                yield from part.append_text(part_text)
            part.close()
            if part.segment_count <= 0 and not part.has_audio:
                self._parts.remove(part)
            else:
                self._position_cursor += 1

        # New open tail part.
        self._open_part = self._new_part()
        self._parts.append(self._open_part)
        tail_text = new_parts[-1] if new_parts else ""
        if tail_text:
            yield from self._open_part.append_text(tail_text)

        self._raw_parts = new_parts

        # Drain ready segments for all parts.
        for part in self._iter_parts_in_order():
            if part is self._open_part:
                continue
            yield from part.yield_ready_segments()

    def finalize(
        self, *, commit: bool = True
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        if not self._enabled:
            return

        # Close the open part (submit remaining text as final segment).
        if self._open_part:
            self._open_part.close()

        logger.info(
            f"TTS finalize called: enabled={self._enabled}, "
            f"parts={len(self._parts)}, "
            f"position_cursor={self._position_cursor}"
        )

        # Wait for all pending TTS tasks and yield remaining segments.
        for part in self._iter_parts_in_order():
            part.wait_for_futures()
            yield from part.yield_ready_segments()

        upload_parts = [p for p in self._iter_parts_in_order() if p.has_audio]
        if not upload_parts:
            return

        # Upload/persist per part (ordered by position).
        from flaskr.service.tts.tts_handler import upload_audio_to_oss

        last_position = upload_parts[-1].position

        for part in upload_parts:
            raw_text = part.raw_text
            try:
                cleaned_text = preprocess_for_tts(raw_text or "")
            except Exception:
                cleaned_text = ""

            # Sort by segment index and concatenate.
            segments = list(part._all_audio_data)  # noqa: SLF001 - internal for finalize
            segments.sort(key=lambda x: x[0])
            audio_data_list = [s[1] for s in segments]

            logger.info(
                f"TTS finalize: position={part.position} "
                f"segments={len(audio_data_list)} "
                f"audio_processing_available={is_audio_processing_available()}"
            )

            final_audio = concat_audio_best_effort(audio_data_list)
            final_duration_ms = get_audio_duration_ms(final_audio)
            file_size = len(final_audio)

            oss_url, bucket_name = upload_audio_to_oss(
                self.app, final_audio, part.audio_bid
            )

            audio_record = LearnGeneratedAudio(
                audio_bid=part.audio_bid,
                generated_block_bid=self.generated_block_bid,
                position=part.position,
                progress_record_bid=self.progress_record_bid,
                user_bid=self.user_bid,
                shifu_bid=self.shifu_bid,
                oss_url=oss_url,
                oss_bucket=bucket_name,
                oss_object_key=f"tts-audio/{part.audio_bid}.mp3",
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
                text_length=part.cleaned_text_length,
                segment_count=len(audio_data_list),
                status=AUDIO_STATUS_COMPLETED,
            )
            db.session.add(audio_record)
            if commit:
                db.session.commit()
            else:
                db.session.flush()

            record_tts_usage(
                self.app,
                part.usage_context,
                usage_bid=part.usage_parent_bid,
                provider=self.tts_provider or "",
                model=self.tts_model or "",
                is_stream=True,
                input=len(raw_text or ""),
                output=len(cleaned_text or ""),
                total=len(cleaned_text or ""),
                word_count=part.word_count_total,
                duration_ms=int(final_duration_ms or 0),
                latency_ms=0,
                record_level=0,
                parent_usage_bid="",
                segment_index=0,
                segment_count=len(audio_data_list),
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

            yield RunMarkdownFlowDTO(
                outline_bid=self.outline_bid,
                generated_block_bid=self.generated_block_bid,
                type=GeneratedType.AUDIO_COMPLETE,
                content=AudioCompleteDTO(
                    position=part.position,
                    audio_url=oss_url,
                    audio_bid=part.audio_bid,
                    duration_ms=final_duration_ms,
                    is_last=bool(part.position == last_position),
                ),
            )

    def finalize_preview(self) -> Generator[RunMarkdownFlowDTO, None, None]:
        # Keep API parity; preview flows currently do not use streaming TTS.
        if not self._enabled:
            return

        if self._open_part:
            self._open_part.close()

        for part in self._iter_parts_in_order():
            part.wait_for_futures()
            yield from part.yield_ready_segments()

        parts_with_audio = [p for p in self._iter_parts_in_order() if p.has_audio]
        if not parts_with_audio:
            return

        # Yield a completion marker per part (no OSS URL in preview mode).
        last_position = parts_with_audio[-1].position
        for part in parts_with_audio:
            total_duration_ms = sum(seg[2] for seg in part._all_audio_data)  # noqa: SLF001
            yield RunMarkdownFlowDTO(
                outline_bid=self.outline_bid,
                generated_block_bid=self.generated_block_bid,
                type=GeneratedType.AUDIO_COMPLETE,
                content=AudioCompleteDTO(
                    position=part.position,
                    audio_url="",
                    audio_bid=part.audio_bid,
                    duration_ms=total_duration_ms,
                    is_last=bool(part.position == last_position),
                ),
            )
