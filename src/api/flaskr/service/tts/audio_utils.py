"""
Audio Processing Utilities.

This module provides audio concatenation and processing functions using pydub/ffmpeg.
"""

import io
import logging
from typing import List, Optional, Sequence

from flaskr.common.log import AppLoggerProxy

logger = AppLoggerProxy(logging.getLogger(__name__))
# Sentence-level TTS segments should concatenate without overlap by default.
# Crossfading sentence boundaries can clip or duplicate phonemes, which is
# especially noticeable in Chinese playback.
DEFAULT_CROSSFADE_MS = 0

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
    Concatenate audio segments with graceful fallback when processing is unavailable.

    Falls back to raw byte-join if pydub/ffmpeg are not available or fail.
    """
    if not segments:
        return b""
    if len(segments) == 1:
        return segments[0]

    if is_audio_processing_available():
        try:
            return concat_audio_mp3(list(segments), output_format=output_format)
        except Exception as exc:
            logger.warning(
                "Audio concatenation failed; falling back to byte-join: %s", exc
            )

    return b"".join(segments)


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
        return int(len(audio_data) / 16000 * 1000)

    try:
        audio_io = io.BytesIO(audio_data)
        audio = AudioSegment.from_file(audio_io, format=format)
        return len(audio)  # pydub returns duration in ms
    except Exception as e:
        logger.error(f"Error getting audio duration: {e}")
        # Fallback to estimate
        return int(len(audio_data) / 16000 * 1000)
