"""
TTS usage recording helpers.

Provides utility functions to record TTS usage with consistent metadata construction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask
    from flaskr.service.metering import UsageContext
    from flaskr.api.tts import VoiceSettings, AudioSettings

from flaskr.service.metering import record_tts_usage


def build_tts_metadata(
    voice_settings: "VoiceSettings",
    audio_settings: "AudioSettings",
) -> dict:
    """
    Build metadata dict from voice and audio settings.

    Args:
        voice_settings: TTS voice configuration
        audio_settings: TTS audio configuration

    Returns:
        Metadata dict with voice and audio parameters
    """
    return {
        "voice_id": voice_settings.voice_id or "",
        "speed": voice_settings.speed,
        "pitch": voice_settings.pitch,
        "emotion": voice_settings.emotion,
        "volume": voice_settings.volume,
        "format": audio_settings.format or "mp3",
        "sample_rate": audio_settings.sample_rate or 24000,
    }


def record_tts_segment_usage(
    app: "Flask",
    usage_context: "UsageContext",
    provider: str,
    model: str,
    segment_text: str,
    word_count: int,
    duration_ms: int,
    latency_ms: int,
    voice_settings: "VoiceSettings",
    audio_settings: "AudioSettings",
    is_stream: bool,
    parent_usage_bid: str,
    segment_index: int,
) -> None:
    """
    Record TTS usage for a single segment.

    This is a segment-level recording (record_level=1) used during streaming synthesis.

    Args:
        app: Flask application instance
        usage_context: Usage context for metering
        provider: TTS provider name
        model: TTS model name
        segment_text: The text that was synthesized
        word_count: Number of words in the segment
        duration_ms: Audio duration in milliseconds
        latency_ms: Synthesis latency in milliseconds
        voice_settings: TTS voice configuration
        audio_settings: TTS audio configuration
        is_stream: Whether this is a streaming request
        parent_usage_bid: Parent usage record ID for aggregation
        segment_index: Index of this segment in the sequence
    """
    segment_length = len(segment_text or "")
    extra = build_tts_metadata(voice_settings, audio_settings)

    record_tts_usage(
        app,
        usage_context,
        provider=provider,
        model=model,
        is_stream=is_stream,
        input=segment_length,
        output=segment_length,
        total=segment_length,
        word_count=word_count,
        duration_ms=duration_ms,
        latency_ms=latency_ms,
        record_level=1,
        parent_usage_bid=parent_usage_bid,
        segment_index=segment_index,
        segment_count=0,
        extra=extra,
    )


def record_tts_aggregated_usage(
    app: "Flask",
    usage_context: "UsageContext",
    usage_bid: str,
    provider: str,
    model: str,
    raw_text: str,
    cleaned_text: str,
    total_word_count: int,
    duration_ms: int,
    segment_count: int,
    voice_settings: "VoiceSettings",
    audio_settings: "AudioSettings",
    is_stream: bool = True,
) -> None:
    """
    Record aggregated TTS usage for all segments.

    This is an aggregated recording (record_level=0) used after all segments
    have been synthesized.

    Args:
        app: Flask application instance
        usage_context: Usage context for metering
        usage_bid: Usage record ID for this aggregation
        provider: TTS provider name
        model: TTS model name
        raw_text: Original input text (before preprocessing)
        cleaned_text: Cleaned text (after preprocessing)
        total_word_count: Total word count across all segments
        duration_ms: Total audio duration in milliseconds
        segment_count: Number of segments synthesized
        voice_settings: TTS voice configuration
        audio_settings: TTS audio configuration
        is_stream: Whether this is a streaming request
    """
    extra = build_tts_metadata(voice_settings, audio_settings)

    record_tts_usage(
        app,
        usage_context,
        usage_bid=usage_bid,
        provider=provider,
        model=model,
        is_stream=is_stream,
        input=len(raw_text or ""),
        output=len(cleaned_text or ""),
        total=len(cleaned_text or ""),
        word_count=total_word_count,
        duration_ms=int(duration_ms or 0),
        latency_ms=0,
        record_level=0,
        parent_usage_bid="",
        segment_index=0,
        segment_count=segment_count,
        extra=extra,
    )
