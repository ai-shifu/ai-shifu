"""
Audio Processing Utilities.

This module provides audio concatenation and processing functions using pydub/ffmpeg.
"""

import io
import logging
from typing import List, Sequence

logger = logging.getLogger(__name__)

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


def concat_audio_mp3(segments: List[bytes], output_format: str = "mp3") -> bytes:
    """
    Concatenate multiple MP3 audio segments into a single audio file.

    Args:
        segments: List of audio data bytes (MP3 format)
        output_format: Output format (default: mp3)

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

    for i, segment_data in enumerate(segments):
        try:
            # Load audio segment from bytes
            segment_io = io.BytesIO(segment_data)
            segment = AudioSegment.from_mp3(segment_io)

            if combined is None:
                combined = segment
            else:
                # Add small crossfade for smoother transitions (50ms)
                combined = combined.append(segment, crossfade=50)

        except Exception as e:
            logger.error(f"Error processing audio segment {i}: {e}")
            # Try to continue with remaining segments
            continue

    if combined is None:
        raise ValueError("Failed to concatenate audio segments")

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
