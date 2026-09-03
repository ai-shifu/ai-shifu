"""Request-scoped synthesis strategies for the streaming TTS processor.

Some providers synthesize one whole mdflow text element per request instead
of sentence-sized segments, either because the request itself streams audio
(MiniMax HTTP streaming) or because the provider returns word timestamps that
only line up for a single request (Volcengine bidirectional WebSocket). Those
paths used to live inline in ``StreamingTTSProcessor``; they are now strategy
objects selected through the provider's ``request_scoped_stream`` capability
and handed the processor whose shared helpers, buffers, and usage context they
drive.

Collaborators such as ``logger``, ``time``, ``MinimaxTTSProvider``, and the
audio duration/export helpers are resolved through the streaming module at
call time because the existing test suites patch them there.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from flaskr.service.tts import resolve_tts_billable_chars
from flaskr.service.tts.subtitle_utils import normalize_subtitle_cues

if TYPE_CHECKING:
    from collections.abc import Generator
    from types import ModuleType

    from flaskr.api.tts.minimax_provider import MinimaxTTSProvider
    from flaskr.service.learn.learn_dtos import RunMarkdownFlowDTO
    from flaskr.service.tts.streaming_tts import StreamingTTSProcessor

_MINIMAX_HTTP_STREAM_SEGMENT_TARGET_MS = 1500
_MINIMAX_HTTP_STREAM_MAX_CHARS = 9500


def _streaming() -> ModuleType:
    # Imported lazily: the streaming module imports this one, and the tests
    # patch collaborators on the streaming module namespace.
    from flaskr.service.tts import streaming_tts

    return streaming_tts


@dataclass
class _MinimaxFallbackAudio:
    audio_data: bytes
    duration_ms: int
    word_count: int
    usage_characters: int
    audio_format: str


class RequestScopedSynthesisStrategy(Protocol):
    """Synthesize one whole text element per request at processor finalize time."""

    def finalize(
        self,
        processor: StreamingTTSProcessor,
        *,
        raw_text: str,
        cleaned_text: str,
        cleaned_text_length: int,
        commit: bool,
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        """Yield audio events for the buffered element and complete the audio."""
        ...


class MinimaxHttpStreamStrategy:
    """MiniMax HTTP streaming: chunked requests with provider subtitle cues."""

    def _split_minimax_http_stream_text(
        self, processor: StreamingTTSProcessor, text: str
    ) -> list[str]:
        parts: list[str] = []
        current = ""
        for unit in processor._sentence_units_for_tts(text):
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
    def _minimax_subtitle_text(raw_item: dict[str, object]) -> str:
        for key in ("text", "content", "sentence"):
            text = str(raw_item.get(key, "") or "").strip()
            if text:
                return text
        return ""

    @staticmethod
    def _minimax_subtitle_time_ms(
        raw_item: dict[str, object],
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
                return round(float(raw_value))
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
        processor: StreamingTTSProcessor,
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
            normalized_text = processor._normalize_subtitle_compare_text(key[0])
            matching_index = None
            for index in range(search_start, len(target)):
                target_text = processor._normalize_subtitle_compare_text(
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

    def _build_minimax_provider_subtitle_cues(
        self,
        processor: StreamingTTSProcessor,
        *,
        request_subtitles: list[dict[str, object]],
        subtitle_offset_ms: int,
    ) -> list[dict[str, object]]:
        return normalize_subtitle_cues(
            self._minimax_subtitles_to_cues(
                processor,
                request_subtitles,
                offset_ms=subtitle_offset_ms,
            )
        )

    def _minimax_subtitles_to_cues(
        self,
        processor: StreamingTTSProcessor,
        subtitles: list[dict[str, Any]],
        *,
        offset_ms: int = 0,
    ) -> list[dict[str, object]]:
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
                    "segment_index": 0,
                    "position": processor.position,
                }
            )
        return cues

    def _scale_minimax_cues_to_live_request(
        self,
        processor: StreamingTTSProcessor,
        subtitle_cues: list[dict[str, Any]],
        *,
        provider_offset_ms: int,
        live_offset_ms: int,
        live_request_end_ms: int,
    ) -> list[dict[str, object]]:
        normalized_cues = normalize_subtitle_cues(subtitle_cues)
        if not normalized_cues or live_request_end_ms <= 0:
            return []

        safe_provider_offset_ms = max(int(provider_offset_ms or 0), 0)
        safe_live_offset_ms = max(int(live_offset_ms or 0), 0)
        safe_live_request_end_ms = max(int(live_request_end_ms or 0), 0)
        source_end_ms = max(
            processor._subtitle_cues_end_ms(normalized_cues) - safe_provider_offset_ms,
            0,
        )
        if source_end_ms <= 0:
            source_end_ms = safe_live_request_end_ms
        scale = safe_live_request_end_ms / source_end_ms if source_end_ms > 0 else 1.0

        live_cues: list[dict[str, Any]] = []
        for cue in normalized_cues:
            text = processor._subtitle_cue_text(cue)
            if not text:
                continue
            source_start_ms = max(
                int(cue.get("start_ms", 0) or 0) - safe_provider_offset_ms,
                0,
            )
            source_cue_end_ms = max(
                int(cue.get("end_ms", source_start_ms) or source_start_ms)
                - safe_provider_offset_ms,
                source_start_ms,
            )
            start_ms = min(
                round(source_start_ms * scale),
                safe_live_request_end_ms,
            )
            end_ms = min(
                round(source_cue_end_ms * scale),
                safe_live_request_end_ms,
            )
            live_cues.append(
                {
                    "text": text,
                    "start_ms": safe_live_offset_ms + max(start_ms, 0),
                    "end_ms": safe_live_offset_ms + max(end_ms, start_ms),
                    "segment_index": int(cue.get("segment_index", 0) or 0),
                    "position": processor.position,
                }
            )
        return live_cues

    def _merge_minimax_live_request_cues(
        self,
        processor: StreamingTTSProcessor,
        previous_live_cues: list[dict[str, Any]],
        incoming_live_cues: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        previous = normalize_subtitle_cues(previous_live_cues)
        incoming = normalize_subtitle_cues(incoming_live_cues)
        if not previous:
            return incoming
        if not incoming:
            return previous

        frozen_prefix = [dict(cue) for cue in previous[:-1]]
        previous_tail = dict(previous[-1])
        incoming_tail_index: int | None = None

        if len(incoming) >= len(previous):
            candidate_index = len(previous) - 1
            candidate = incoming[candidate_index]
            if processor._subtitle_cue_text(candidate) == processor._subtitle_cue_text(
                previous_tail
            ):
                incoming_tail_index = candidate_index

        if incoming_tail_index is None:
            for index in range(max(len(frozen_prefix), 0), len(incoming)):
                candidate = incoming[index]
                if processor._subtitle_cue_text(
                    candidate
                ) == processor._subtitle_cue_text(previous_tail):
                    incoming_tail_index = index
                    break

        if incoming_tail_index is None:
            previous_end_ms = int(previous_tail.get("end_ms", 0) or 0)
            remaining = [
                dict(cue)
                for cue in incoming
                if int(cue.get("end_ms", 0) or 0) > previous_end_ms
            ]
            return [dict(cue) for cue in previous] + remaining

        tail_candidate = incoming[incoming_tail_index]
        previous_tail["end_ms"] = max(
            int(previous_tail.get("end_ms", 0) or 0),
            int(tail_candidate.get("end_ms", 0) or 0),
        )
        remaining = [dict(cue) for cue in incoming[incoming_tail_index + 1 :]]
        return [*frozen_prefix, previous_tail, *remaining]

    def _normalize_minimax_live_request_cues(
        self,
        processor: StreamingTTSProcessor,
        live_cues: list[dict[str, Any]],
        *,
        live_offset_ms: int,
        live_request_end_ms: int,
    ) -> list[dict[str, object]]:
        normalized_cues = normalize_subtitle_cues(live_cues)
        if not normalized_cues:
            return []

        timeline_start_ms = max(int(live_offset_ms or 0), 0)
        timeline_end_ms = timeline_start_ms + max(int(live_request_end_ms or 0), 0)
        if timeline_end_ms <= timeline_start_ms:
            return []

        bounded: list[dict[str, Any]] = []
        last_end_ms = timeline_start_ms
        for cue in normalized_cues:
            text = processor._subtitle_cue_text(cue)
            if not text:
                continue
            start_ms = max(int(cue.get("start_ms", 0) or 0), timeline_start_ms)
            end_ms = max(int(cue.get("end_ms", start_ms) or start_ms), start_ms)
            start_ms = max(start_ms, last_end_ms)
            if start_ms >= timeline_end_ms:
                continue
            end_ms = min(max(end_ms, start_ms + 1), timeline_end_ms)
            bounded.append(
                {
                    "text": text,
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "segment_index": int(cue.get("segment_index", 0) or 0),
                    "position": processor.position,
                }
            )
            last_end_ms = end_ms

        if bounded:
            bounded[-1]["start_ms"] = min(
                int(bounded[-1].get("start_ms", 0) or 0),
                max(timeline_end_ms - 1, timeline_start_ms),
            )
            bounded[-1]["end_ms"] = timeline_end_ms
        return normalize_subtitle_cues(bounded)

    def _build_minimax_live_request_subtitle_cues(
        self,
        processor: StreamingTTSProcessor,
        subtitle_cues: list[dict[str, Any]],
        *,
        provider_offset_ms: int,
        live_offset_ms: int,
        live_request_end_ms: int,
        previous_live_cues: list[dict[str, object]] | None = None,
    ) -> list[dict[str, object]]:
        incoming_live_cues = self._scale_minimax_cues_to_live_request(
            processor,
            subtitle_cues,
            provider_offset_ms=provider_offset_ms,
            live_offset_ms=live_offset_ms,
            live_request_end_ms=live_request_end_ms,
        )
        merged_live_cues = self._merge_minimax_live_request_cues(
            processor,
            previous_live_cues or [],
            incoming_live_cues,
        )
        return self._normalize_minimax_live_request_cues(
            processor,
            merged_live_cues,
            live_offset_ms=live_offset_ms,
            live_request_end_ms=live_request_end_ms,
        )

    def _synthesize_minimax_complete_fallback(
        self,
        processor: StreamingTTSProcessor,
        provider: MinimaxTTSProvider,
        *,
        request_text: str,
        request_format: str,
        request_index: int,
    ) -> _MinimaxFallbackAudio | None:
        try:
            result = provider.synthesize(
                text=request_text,
                voice_settings=processor.voice_settings,
                audio_settings=processor.audio_settings,
                model=processor.tts_model,
            )
        except Exception as exc:
            _streaming().logger.warning(
                "MiniMax complete synthesis fallback failed. request_index=%s, "
                "text_length=%s, error=%s",
                request_index,
                len(request_text or ""),
                exc,
            )
            _streaming().logger.debug(
                "MiniMax complete synthesis fallback traceback", exc_info=True
            )
            return None

        audio_data = result.audio_data or b""
        audio_format = (
            result.format or request_format or processor.audio_settings.format or "mp3"
        )
        decoded_duration_ms = _streaming().try_get_audio_duration_ms(
            audio_data,
            audio_format=audio_format,
        )
        if decoded_duration_ms is None or decoded_duration_ms <= 0:
            _streaming().logger.warning(
                "MiniMax complete synthesis fallback returned undecodable audio. "
                "request_index=%s, bytes=%s, format=%s",
                request_index,
                len(audio_data),
                audio_format,
            )
            return None

        return _MinimaxFallbackAudio(
            audio_data=audio_data,
            duration_ms=int(result.duration_ms or decoded_duration_ms or 0),
            word_count=int(result.word_count or 0),
            usage_characters=int(getattr(result, "usage_characters", 0) or 0),
            audio_format=audio_format,
        )

    def finalize(
        self,
        processor: StreamingTTSProcessor,
        *,
        raw_text: str,
        cleaned_text: str,
        cleaned_text_length: int,
        commit: bool,
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        """Stream the element through chunked MiniMax HTTP requests."""
        request_texts = self._split_minimax_http_stream_text(processor, cleaned_text)
        if not processor._enabled or not request_texts:
            return

        provider = _streaming().MinimaxTTSProvider()
        live_subtitle_cues: list[dict[str, Any]] = []
        final_subtitle_cues: list[dict[str, Any]] = []
        subtitle_offset_ms = 0
        live_offset_ms = 0

        from flaskr.service.tts.tts_usage_recorder import record_tts_segment_usage

        for request_index, request_text in enumerate(request_texts):
            if _streaming()._should_skip_non_speakable_tts_text(
                request_text, processor.tts_provider
            ):
                _streaming()._log_skipped_non_speakable_tts_text(
                    segment_index=request_index,
                    text=request_text,
                    tts_provider=processor.tts_provider,
                    tts_model=processor.tts_model,
                )
                continue

            request_started_at = _streaming().time.monotonic()
            audio_chunks: list[bytes] = []
            source_emitted_ms = 0
            live_request_emitted_ms = 0
            request_duration_ms = 0
            request_word_count = 0
            request_usage_characters = 0
            request_format = processor.audio_settings.format or "mp3"
            request_subtitles: list[dict[str, Any]] = []
            request_final_subtitle_cues: list[dict[str, Any]] = []
            request_final_subtitle_cues_are_provider = False
            request_live_subtitle_cues: list[dict[str, Any]] = []

            for chunk in provider.stream_synthesize(
                text=request_text,
                voice_settings=processor.voice_settings,
                audio_settings=processor.audio_settings,
                model=processor.tts_model,
            ):
                if chunk.audio_data:
                    audio_chunks.append(chunk.audio_data)
                if chunk.format:
                    request_format = chunk.format
                if chunk.is_final:
                    request_duration_ms = int(chunk.duration_ms or request_duration_ms)
                    request_word_count = int(chunk.word_count or request_word_count)
                    request_usage_characters = int(
                        getattr(chunk, "usage_characters", 0)
                        or request_usage_characters
                    )
                if chunk.subtitles:
                    self._extend_unique_minimax_subtitles(
                        processor,
                        request_subtitles,
                        chunk.subtitles,
                    )

                accumulated_audio = b"".join(audio_chunks)
                if not accumulated_audio:
                    continue

                progressive_request_subtitle_cues = (
                    self._build_minimax_provider_subtitle_cues(
                        processor,
                        request_subtitles=request_subtitles,
                        subtitle_offset_ms=subtitle_offset_ms,
                    )
                )
                request_subtitle_coverage_end_ms = max(
                    processor._subtitle_cues_end_ms(progressive_request_subtitle_cues)
                    - int(subtitle_offset_ms or 0),
                    0,
                )

                if chunk.is_final:
                    if request_duration_ms <= 0:
                        decoded_duration_ms = _streaming().try_get_audio_duration_ms(
                            accumulated_audio,
                            audio_format=request_format or "mp3",
                        )
                        if decoded_duration_ms is not None:
                            request_duration_ms = int(decoded_duration_ms or 0)
                    if progressive_request_subtitle_cues and (
                        processor._subtitle_cues_cover_text(
                            progressive_request_subtitle_cues,
                            request_text,
                        )
                    ):
                        request_final_subtitle_cues = progressive_request_subtitle_cues
                        request_final_subtitle_cues_are_provider = True
                        target_end_ms = max(
                            request_subtitle_coverage_end_ms, source_emitted_ms
                        )
                    else:
                        if progressive_request_subtitle_cues:
                            _streaming().logger.debug(
                                "MiniMax subtitles did not cover full request text; "
                                "using fallback cues. request_index=%s, subtitles=%s",
                                request_index,
                                len(progressive_request_subtitle_cues),
                            )
                        request_final_subtitle_cues = (
                            processor._build_minimax_fallback_subtitle_cues(
                                request_text,
                                duration_ms=int(
                                    request_duration_ms
                                    or source_emitted_ms
                                    or live_request_emitted_ms
                                    or 0
                                ),
                                offset_ms=subtitle_offset_ms,
                            )
                        )
                        target_end_ms = max(
                            int(request_duration_ms or 0), source_emitted_ms
                        )
                    event_request_subtitle_cues = request_final_subtitle_cues
                else:
                    if not progressive_request_subtitle_cues:
                        continue
                    target_end_ms = request_subtitle_coverage_end_ms
                    event_request_subtitle_cues = progressive_request_subtitle_cues

                if target_end_ms <= source_emitted_ms:
                    continue

                audio_piece = b""
                piece_duration_ms = 0
                audio_piece, piece_duration_ms = (
                    _streaming().export_audio_range_best_effort(
                        accumulated_audio,
                        start_ms=source_emitted_ms,
                        end_ms=target_end_ms,
                        input_format=request_format or "mp3",
                        output_format=processor.audio_settings.format or "mp3",
                    )
                )

                if (
                    not chunk.is_final
                    and piece_duration_ms < _MINIMAX_HTTP_STREAM_SEGMENT_TARGET_MS
                ):
                    continue

                if (
                    not audio_piece
                    and chunk.is_final
                    and source_emitted_ms == 0
                    and target_end_ms >= int(request_duration_ms or 0)
                ):
                    decoded_duration_ms = _streaming().try_get_audio_duration_ms(
                        accumulated_audio,
                        audio_format=request_format or "mp3",
                    )
                    if decoded_duration_ms is not None and decoded_duration_ms > 0:
                        audio_piece = accumulated_audio
                        piece_duration_ms = int(
                            request_duration_ms or decoded_duration_ms
                        )
                    else:
                        _streaming().logger.warning(
                            "MiniMax HTTP stream produced undecodable final audio; "
                            "will try complete synthesis fallback. request_index=%s, "
                            "bytes=%s, format=%s, trace_id=%s",
                            request_index,
                            len(accumulated_audio or b""),
                            request_format or "mp3",
                            getattr(chunk, "trace_id", ""),
                        )

                if not audio_piece or piece_duration_ms <= 0:
                    continue

                source_emitted_ms = max(source_emitted_ms, int(target_end_ms or 0))
                live_request_emitted_ms += int(piece_duration_ms or 0)
                request_live_subtitle_cues = (
                    self._build_minimax_live_request_subtitle_cues(
                        processor,
                        event_request_subtitle_cues,
                        provider_offset_ms=subtitle_offset_ms,
                        live_offset_ms=live_offset_ms,
                        live_request_end_ms=live_request_emitted_ms,
                        previous_live_cues=request_live_subtitle_cues,
                    )
                )
                progressive_subtitle_cues = normalize_subtitle_cues(
                    list(live_subtitle_cues or []) + request_live_subtitle_cues
                )
                _segment_index, event = processor._store_stream_audio_segment(
                    audio_data=audio_piece,
                    duration_ms=piece_duration_ms,
                    text=request_text,
                    subtitle_cues=progressive_subtitle_cues,
                )
                yield event

            fallback_audio: _MinimaxFallbackAudio | None = None
            if live_request_emitted_ms <= 0:
                fallback_audio = self._synthesize_minimax_complete_fallback(
                    processor,
                    provider,
                    request_text=request_text,
                    request_format=request_format,
                    request_index=request_index,
                )
                if fallback_audio is not None:
                    request_duration_ms = int(fallback_audio.duration_ms or 0)
                    if fallback_audio.word_count:
                        request_word_count = int(fallback_audio.word_count or 0)
                    if fallback_audio.usage_characters:
                        request_usage_characters = int(
                            fallback_audio.usage_characters or 0
                        )

            if request_duration_ms <= 0:
                request_duration_ms = source_emitted_ms or live_request_emitted_ms
            if request_word_count:
                processor._word_count_total += request_word_count
            processor._output_char_total += resolve_tts_billable_chars(
                request_text,
                request_usage_characters,
            )
            if not request_final_subtitle_cues:
                request_subtitle_cues = self._minimax_subtitles_to_cues(
                    processor,
                    request_subtitles,
                    offset_ms=subtitle_offset_ms,
                )
                if request_subtitle_cues and processor._subtitle_cues_cover_text(
                    request_subtitle_cues,
                    request_text,
                ):
                    request_final_subtitle_cues = request_subtitle_cues
                    request_final_subtitle_cues_are_provider = True
                else:
                    if request_subtitle_cues:
                        _streaming().logger.debug(
                            "MiniMax subtitles did not cover full request text; "
                            "using fallback cues. request_index=%s, subtitles=%s",
                            request_index,
                            len(request_subtitle_cues),
                        )
                    request_final_subtitle_cues = (
                        processor._build_minimax_fallback_subtitle_cues(
                            request_text,
                            duration_ms=int(
                                request_duration_ms
                                or source_emitted_ms
                                or live_request_emitted_ms
                                or 0
                            ),
                            offset_ms=subtitle_offset_ms,
                        )
                    )
            if (
                fallback_audio is not None
                and not request_final_subtitle_cues_are_provider
            ):
                request_final_subtitle_cues = (
                    processor._build_minimax_fallback_subtitle_cues(
                        request_text,
                        duration_ms=int(fallback_audio.duration_ms or 0),
                        offset_ms=subtitle_offset_ms,
                    )
                )
            if fallback_audio is not None and live_request_emitted_ms <= 0:
                live_request_emitted_ms = int(fallback_audio.duration_ms or 0)
                request_live_subtitle_cues = (
                    self._build_minimax_live_request_subtitle_cues(
                        processor,
                        request_final_subtitle_cues,
                        provider_offset_ms=subtitle_offset_ms,
                        live_offset_ms=live_offset_ms,
                        live_request_end_ms=live_request_emitted_ms,
                    )
                )
                progressive_subtitle_cues = normalize_subtitle_cues(
                    list(live_subtitle_cues or []) + request_live_subtitle_cues
                )
                _segment_index, event = processor._store_stream_audio_segment(
                    audio_data=fallback_audio.audio_data,
                    duration_ms=fallback_audio.duration_ms,
                    text=request_text,
                    subtitle_cues=progressive_subtitle_cues,
                )
                yield event
            final_subtitle_cues.extend(request_final_subtitle_cues)
            if not request_live_subtitle_cues and live_request_emitted_ms > 0:
                request_live_subtitle_cues = (
                    self._build_minimax_live_request_subtitle_cues(
                        processor,
                        request_final_subtitle_cues,
                        provider_offset_ms=subtitle_offset_ms,
                        live_offset_ms=live_offset_ms,
                        live_request_end_ms=live_request_emitted_ms,
                    )
                )
            live_subtitle_cues = normalize_subtitle_cues(
                list(live_subtitle_cues or []) + request_live_subtitle_cues
            )
            live_offset_ms += int(live_request_emitted_ms or 0)
            request_subtitle_end_ms = processor._subtitle_cues_end_ms(
                request_final_subtitle_cues
            )
            if request_subtitle_end_ms > subtitle_offset_ms:
                subtitle_offset_ms = request_subtitle_end_ms
            else:
                subtitle_offset_ms += int(request_duration_ms or source_emitted_ms or 0)

            record_tts_segment_usage(
                app=processor.app,
                usage_context=processor.usage_context,
                provider=processor.tts_provider or "",
                model=processor.tts_model or "",
                segment_text=request_text,
                word_count=request_word_count,
                duration_ms=int(request_duration_ms or 0),
                latency_ms=int(
                    (_streaming().time.monotonic() - request_started_at) * 1000
                ),
                voice_settings=processor.voice_settings,
                audio_settings=processor.audio_settings,
                is_stream=True,
                parent_usage_bid=processor._usage_parent_bid,
                segment_index=request_index,
                usage_characters=request_usage_characters,
            )

        with processor._lock:
            all_segments = list(processor._all_audio_data)

        yield from processor._yield_audio_complete_from_segments(
            all_segments=all_segments,
            raw_text=raw_text,
            cleaned_text=cleaned_text,
            cleaned_text_length=cleaned_text_length,
            subtitle_cues=final_subtitle_cues,
            event_subtitle_cues=live_subtitle_cues,
            commit=commit,
        )


class VolcengineTimestampStreamStrategy:
    """Volcengine WebSocket: one request whose word timestamps become subtitles."""

    def finalize(
        self,
        processor: StreamingTTSProcessor,
        *,
        raw_text: str,
        cleaned_text: str,
        cleaned_text_length: int,
        commit: bool,
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        """Synthesize the whole element in one request and reuse its timestamps."""
        request_text = (cleaned_text or "").strip()
        if not processor._enabled or not request_text:
            return
        if _streaming()._should_skip_non_speakable_tts_text(
            request_text, processor.tts_provider
        ):
            _streaming()._log_skipped_non_speakable_tts_text(
                segment_index=0,
                text=request_text,
                tts_provider=processor.tts_provider,
                tts_model=processor.tts_model,
            )
            return

        request_started_at = _streaming().time.monotonic()
        result = processor._synthesize_text_with_retry(
            text=request_text,
            voice_settings=processor.voice_settings,
            audio_settings=processor.audio_settings,
            tts_model=processor.tts_model,
            tts_provider=processor.tts_provider,
            segment_index=0,
        )
        if not result.audio_data:
            _streaming().logger.warning("Volcengine timestamp stream returned no audio")
            return

        request_duration_ms = int(result.duration_ms or 0)
        if request_duration_ms <= 0:
            request_duration_ms = _streaming().get_audio_duration_ms(
                result.audio_data,
                audio_format=result.format or processor.audio_settings.format or "mp3",
            )
        request_word_count = int(result.word_count or 0)
        request_usage_characters = int(getattr(result, "usage_characters", 0) or 0)
        if request_word_count:
            processor._word_count_total += request_word_count
        processor._output_char_total += resolve_tts_billable_chars(
            request_text,
            request_usage_characters,
        )

        provider_subtitle_cues = processor._apply_subtitle_context(
            list(getattr(result, "subtitle_cues", []) or [])
        )
        if provider_subtitle_cues and processor._subtitle_cues_cover_text(
            provider_subtitle_cues,
            request_text,
        ):
            final_subtitle_cues = provider_subtitle_cues
        else:
            if provider_subtitle_cues:
                _streaming().logger.debug(
                    "Volcengine subtitles did not cover full request text; "
                    "using fallback cues. subtitles=%s",
                    len(provider_subtitle_cues),
                )
            final_subtitle_cues = processor._build_minimax_fallback_subtitle_cues(
                request_text,
                duration_ms=int(request_duration_ms or 0),
            )
            final_subtitle_cues = processor._apply_subtitle_context(final_subtitle_cues)

        _segment_index, event = processor._store_stream_audio_segment(
            audio_data=result.audio_data,
            duration_ms=int(request_duration_ms or 0),
            text=request_text,
            subtitle_cues=final_subtitle_cues,
        )
        yield event

        from flaskr.service.tts.tts_usage_recorder import record_tts_segment_usage

        record_tts_segment_usage(
            app=processor.app,
            usage_context=processor.usage_context,
            provider=processor.tts_provider or "",
            model=processor.tts_model or "",
            segment_text=request_text,
            word_count=request_word_count,
            duration_ms=int(request_duration_ms or 0),
            latency_ms=int((_streaming().time.monotonic() - request_started_at) * 1000),
            voice_settings=processor.voice_settings,
            audio_settings=processor.audio_settings,
            is_stream=True,
            parent_usage_bid=processor._usage_parent_bid,
            segment_index=0,
            usage_characters=request_usage_characters,
        )

        with processor._lock:
            all_segments = list(processor._all_audio_data)

        yield from processor._yield_audio_complete_from_segments(
            all_segments=all_segments,
            raw_text=raw_text,
            cleaned_text=cleaned_text,
            cleaned_text_length=cleaned_text_length,
            subtitle_cues=final_subtitle_cues,
            event_subtitle_cues=final_subtitle_cues,
            commit=commit,
        )
