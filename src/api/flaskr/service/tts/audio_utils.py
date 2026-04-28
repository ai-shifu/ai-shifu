"""
Audio Processing Utilities.

This module provides audio concatenation and processing functions using pydub/ffmpeg.
"""

import io
import logging
from dataclasses import dataclass
from typing import List, Optional, Sequence

from flaskr.common.log import AppLoggerProxy

logger = AppLoggerProxy(logging.getLogger(__name__))
# Sentence-level TTS segments should concatenate without overlap by default.
# Crossfading sentence boundaries can clip or duplicate phonemes, which is
# especially noticeable in Chinese playback.
DEFAULT_CROSSFADE_MS = 0
_MP3_128K_BYTES_PER_MS = 16


@dataclass(frozen=True)
class AudioAssemblyResult:
    """Final audio selected for upload after validating it can be decoded."""

    audio_data: bytes
    duration_ms: int
    source_segment_count: int
    included_segment_indices: tuple[int, ...]
    used_fallback: bool = False
    fallback_reason: str = ""

    @property
    def segment_count(self) -> int:
        return len(self.included_segment_indices)

    @property
    def is_complete(self) -> bool:
        return self.segment_count == self.source_segment_count


# Try to import pydub, which wraps ffmpeg
try:
    from pydub import AudioSegment

    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    logger.warning("pydub is not installed. Audio concatenation will not be available.")


def is_audio_processing_available() -> bool:
    """Check if audio processing is available."""
    return PYDUB_AVAILABLE


def _estimate_audio_duration_ms(audio_data: bytes) -> int:
    return int(len(audio_data or b"") / _MP3_128K_BYTES_PER_MS)


def _probe_audio_duration_ms(audio_data: bytes, format: str = "mp3") -> int | None:
    if not audio_data:
        return None
    if not PYDUB_AVAILABLE:
        return None

    try:
        audio_io = io.BytesIO(audio_data)
        audio = AudioSegment.from_file(audio_io, format=format)
        return len(audio)
    except Exception:
        return None


def _resolve_result_duration_ms(
    *,
    audio_data: bytes,
    probed_duration_ms: int | None = None,
    preferred_duration_ms: int | None = None,
    format: str = "mp3",
) -> int:
    if preferred_duration_ms is not None and preferred_duration_ms > 0:
        return int(preferred_duration_ms)
    if probed_duration_ms is not None:
        return int(probed_duration_ms)
    return get_audio_duration_ms(audio_data, format=format)


def concat_audio_mp3(
    segments: List[bytes],
    output_format: str = "mp3",
    crossfade_ms: int = DEFAULT_CROSSFADE_MS,
) -> bytes:
    """
    Concatenate multiple MP3 audio segments into a single audio file.

    Args:
        segments: List of audio data bytes (MP3 format)
        output_format: Output format (default: mp3)
        crossfade_ms: Overlap to apply between adjacent segments. Defaults to 0
            for TTS so sentence boundaries remain intact.

    Returns:
        Concatenated audio data as bytes

    Raises:
        ImportError: If pydub is not available
        ValueError: If no segments provided
    """
    if not PYDUB_AVAILABLE:
        raise ImportError(
            "pydub is required for audio concatenation. "
            "Install it with: pip install pydub"
        )

    if not segments:
        raise ValueError("No audio segments to concatenate")

    if len(segments) == 1:
        return segments[0]

    logger.info(f"Concatenating {len(segments)} audio segments")

    # Initialize combined audio
    combined = None
    failed_segments: list[int] = []

    for i, segment_data in enumerate(segments):
        try:
            # Load audio segment from bytes
            segment_io = io.BytesIO(segment_data)
            segment = AudioSegment.from_mp3(segment_io)

            if combined is None:
                combined = segment
            else:
                # Keep crossfade short enough for both segments to avoid pydub
                # errors when callers explicitly opt into overlap.
                safe_crossfade_ms = min(
                    max(int(crossfade_ms or 0), 0),
                    len(combined),
                    len(segment),
                )
                if safe_crossfade_ms > 0:
                    combined = combined.append(segment, crossfade=safe_crossfade_ms)
                else:
                    combined = combined.append(segment)

        except Exception as e:
            failed_segments.append(i)
            logger.warning(
                "Error processing audio segment %s (%s bytes): %s",
                i,
                len(segment_data or b""),
                e,
            )

    if combined is None:
        raise ValueError("Failed to concatenate audio segments")

    if failed_segments:
        failed_segment_list = ", ".join(str(index) for index in failed_segments)
        raise ValueError(f"Failed to decode audio segments: {failed_segment_list}")

    # Export to bytes
    output_io = io.BytesIO()
    combined.export(output_io, format=output_format, bitrate="128k")
    output_data = output_io.getvalue()

    logger.info(
        f"Audio concatenation complete: "
        f"{len(segments)} segments -> {len(output_data)} bytes"
    )

    return output_data


def concat_audio_best_effort(
    segments: Sequence[bytes], output_format: str = "mp3"
) -> bytes:
    """
    Concatenate audio segments into upload-safe bytes.

    Falls back to the first decodable segment instead of raw byte-joining MP3
    files, which can produce invalid uploaded audio.
    """
    return assemble_audio_for_upload(segments, output_format=output_format).audio_data


def assemble_audio_for_upload(
    segments: Sequence[bytes],
    *,
    segment_durations_ms: Optional[Sequence[int]] = None,
    segment_indices: Optional[Sequence[int]] = None,
    input_format: str = "mp3",
    output_format: str = "mp3",
) -> AudioAssemblyResult:
    """
    Build uploadable audio and validate the selected bytes are decodable.

    Multi-segment MP3s must be decoded and re-exported before upload. If that
    fails, return the first decodable segment rather than uploading a raw
    byte-join. If no segment can be decoded, raise ``ValueError``.
    """
    source_segment_count = len(segments or [])
    segment_index_values = list(segment_indices or range(source_segment_count))

    def _segment_index_for_position(position: int) -> int:
        if position < len(segment_index_values):
            return int(segment_index_values[position] or 0)
        return position

    indexed_segments = [
        (_segment_index_for_position(index), segment_data)
        for index, segment_data in enumerate(segments or [])
        if segment_data
    ]
    if not indexed_segments:
        raise ValueError("No audio data produced")
    if not PYDUB_AVAILABLE:
        raise ValueError("Audio processing is required to validate TTS output")

    duration_by_index: dict[int, int] = {}
    if segment_durations_ms is not None:
        duration_by_index = {
            _segment_index_for_position(index): max(int(duration_ms or 0), 0)
            for index, duration_ms in enumerate(segment_durations_ms)
        }

    if len(indexed_segments) == 1:
        index, segment_data = indexed_segments[0]
        probed_duration_ms = _probe_audio_duration_ms(segment_data, format=input_format)
        if probed_duration_ms is None:
            raise ValueError("No decodable audio segments to upload")
        return AudioAssemblyResult(
            audio_data=segment_data,
            duration_ms=_resolve_result_duration_ms(
                audio_data=segment_data,
                probed_duration_ms=probed_duration_ms,
                preferred_duration_ms=duration_by_index.get(index),
                format=input_format,
            ),
            source_segment_count=source_segment_count,
            included_segment_indices=(index,),
        )

    segment_payloads = [segment_data for _index, segment_data in indexed_segments]
    try:
        final_audio = concat_audio_mp3(segment_payloads, output_format=output_format)
        probed_duration_ms = _probe_audio_duration_ms(final_audio, format=output_format)
        if probed_duration_ms is None:
            raise ValueError("Concatenated audio failed validation")
        return AudioAssemblyResult(
            audio_data=final_audio,
            duration_ms=int(probed_duration_ms),
            source_segment_count=source_segment_count,
            included_segment_indices=tuple(index for index, _data in indexed_segments),
        )
    except Exception as exc:
        fallback_reason = str(exc)
        logger.warning(
            "Audio assembly failed; trying first decodable segment fallback. "
            "segments=%s error_type=%s",
            len(indexed_segments),
            type(exc).__name__,
        )
        logger.debug("Audio assembly failure details: %s", exc, exc_info=True)

    for index, segment_data in indexed_segments:
        probed_duration_ms = _probe_audio_duration_ms(segment_data, format=input_format)
        if probed_duration_ms is None:
            continue
        return AudioAssemblyResult(
            audio_data=segment_data,
            duration_ms=_resolve_result_duration_ms(
                audio_data=segment_data,
                probed_duration_ms=probed_duration_ms,
                preferred_duration_ms=duration_by_index.get(index),
                format=input_format,
            ),
            source_segment_count=source_segment_count,
            included_segment_indices=(index,),
            used_fallback=True,
            fallback_reason=fallback_reason,
        )

    raise ValueError("No decodable audio segments to upload")


def export_audio_range_best_effort(
    audio_data: bytes,
    *,
    start_ms: int = 0,
    end_ms: Optional[int] = None,
    input_format: str = "mp3",
    output_format: str = "mp3",
) -> tuple[bytes, int]:
    """
    Export a time range from an encoded audio blob as a standalone audio file.

    Returns ``(audio_bytes, duration_ms)``. If pydub/ffmpeg cannot decode the
    range, returns ``(b"", 0)`` except for the full-audio fallback, where the
    original bytes are returned.
    """
    if not audio_data:
        return b"", 0

    safe_start_ms = max(int(start_ms or 0), 0)
    safe_end_ms = int(end_ms) if end_ms is not None else None

    if is_audio_processing_available():
        try:
            audio_io = io.BytesIO(audio_data)
            audio = AudioSegment.from_file(audio_io, format=input_format)
            start = min(safe_start_ms, len(audio))
            end = (
                len(audio)
                if safe_end_ms is None
                else min(max(safe_end_ms, start), len(audio))
            )
            sliced = audio[start:end]
            if len(sliced) <= 0:
                return b"", 0
            output_io = io.BytesIO()
            sliced.export(output_io, format=output_format, bitrate="128k")
            return output_io.getvalue(), len(sliced)
        except Exception as exc:
            logger.debug("Audio range export failed: %s", exc, exc_info=True)

    if safe_start_ms == 0 and safe_end_ms is None:
        return audio_data, get_audio_duration_ms(audio_data, format=input_format)
    return b"", 0


def get_audio_duration_ms(audio_data: bytes, format: str = "mp3") -> int:
    """
    Get duration of audio data in milliseconds.

    Args:
        audio_data: Audio data bytes
        format: Audio format (default: mp3)

    Returns:
        Duration in milliseconds
    """
    if not PYDUB_AVAILABLE:
        # Rough estimate based on bitrate (128kbps for MP3)
        # 128kbps = 16KB/s, so duration = size_bytes / 16000 * 1000
        return _estimate_audio_duration_ms(audio_data)

    try:
        audio_io = io.BytesIO(audio_data)
        audio = AudioSegment.from_file(audio_io, format=format)
        return len(audio)  # pydub returns duration in ms
    except Exception as e:
        logger.warning(
            "Audio duration probe failed; using bitrate estimate. "
            "format=%s bytes=%s error_type=%s",
            format,
            len(audio_data or b""),
            type(e).__name__,
        )
        logger.debug("Audio duration probe details: %s", e, exc_info=True)
        # Fallback to estimate
        return _estimate_audio_duration_ms(audio_data)
