"""
High-level TTS pipeline helpers.

This module provides a top-level, provider-agnostic pipeline that:
1) preprocesses text for TTS,
2) splits long text into safe segments,
3) synthesizes all segments via the unified TTS client,
4) concatenates audio, uploads to OSS, and returns a playable URL.
"""

from __future__ import annotations

import html
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from flask import Flask

from flaskr.common.config import get_config
from flaskr.api.tts import (
    synthesize_text,
    is_tts_configured,
    get_default_voice_settings,
    get_default_audio_settings,
    VoiceSettings,
    AudioSettings,
)
from flaskr.service.tts import preprocess_for_tts
from flaskr.service.tts.audio_utils import (
    concat_audio_best_effort,
    get_audio_duration_ms,
)
from flaskr.service.tts.tts_handler import upload_audio_to_oss
from flaskr.common.log import AppLoggerProxy
from flaskr.service.metering import UsageContext, record_tts_usage
from flaskr.util.uuid import generate_id


logger = AppLoggerProxy(logging.getLogger(__name__))


_DEFAULT_SENTENCE_ENDINGS = set(".!?。！？；;")


def _split_by_sentence_and_newline(text: str) -> list[str]:
    """
    Split text into small units using newlines and sentence-ending punctuation.

    This is intentionally conservative and avoids provider-specific assumptions.
    """
    units: list[str] = []
    for raw_line in (text or "").replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        start = 0
        for idx, ch in enumerate(line):
            if ch in _DEFAULT_SENTENCE_ENDINGS:
                end = idx + 1
                piece = line[start:end].strip()
                if piece:
                    units.append(piece)
                start = end

        tail = line[start:].strip()
        if tail:
            units.append(tail)

    return units


def _split_text_by_max_chars(units: Sequence[str], max_chars: int) -> list[str]:
    if max_chars <= 0:
        raise ValueError("max_chars must be > 0")

    segments: list[str] = []
    current = ""
    for unit in units:
        unit = (unit or "").strip()
        if not unit:
            continue

        if not current:
            if len(unit) <= max_chars:
                current = unit
                continue
            # Unit itself is too long; hard-split.
            for i in range(0, len(unit), max_chars):
                segments.append(unit[i : i + max_chars])
            current = ""
            continue

        candidate = f"{current} {unit}".strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            segments.append(current)
            if len(unit) <= max_chars:
                current = unit
            else:
                for i in range(0, len(unit), max_chars):
                    segments.append(unit[i : i + max_chars])
                current = ""

    if current:
        segments.append(current)

    return segments


def _split_text_by_max_bytes(
    segments: Sequence[str],
    *,
    max_bytes: int,
    encoding: str,
) -> list[str]:
    """
    Ensure every segment stays within max bytes for a given encoding.

    This is mainly required for providers like Baidu which enforce byte limits.
    """
    if max_bytes <= 0:
        raise ValueError("max_bytes must be > 0")

    output: list[str] = []
    for segment in segments:
        segment = (segment or "").strip()
        if not segment:
            continue

        try:
            if len(segment.encode(encoding, errors="replace")) <= max_bytes:
                output.append(segment)
                continue
        except LookupError:
            # Unknown encoding; fall back to char-based behavior.
            output.append(segment)
            continue

        buf = ""
        for ch in segment:
            candidate = f"{buf}{ch}"
            if len(candidate.encode(encoding, errors="replace")) <= max_bytes:
                buf = candidate
                continue

            if buf:
                output.append(buf.strip())
            buf = ch

        if buf.strip():
            output.append(buf.strip())

    return output


def split_text_for_tts(
    text: str,
    *,
    provider_name: str,
    max_segment_chars: Optional[int] = None,
) -> list[str]:
    """
    Split text into segments suitable for unified TTS synthesis.

    - Applies `preprocess_for_tts` (removes markdown/code/SVG, etc).
    - Splits by newline and sentence endings.
    - Packs units into segments with a configurable maximum character size.
    - Applies provider-specific byte constraints when needed.
    """
    cleaned = preprocess_for_tts(text or "")
    if not cleaned:
        return []

    configured_max = get_config("TTS_MAX_SEGMENT_CHARS") or 300
    max_chars = int(max_segment_chars or configured_max or 300)
    units = _split_by_sentence_and_newline(cleaned)
    segments = _split_text_by_max_chars(units, max_chars=max_chars)

    # Provider-specific byte constraints
    if (provider_name or "").strip().lower() == "baidu":
        # Baidu requires <= 1024 bytes in GBK encoding.
        segments = _split_text_by_max_bytes(segments, max_bytes=1024, encoding="gbk")
    elif (provider_name or "").strip().lower() == "volcengine_http":
        # Volcengine HTTP v1/tts requires <= 1024 bytes in UTF-8 encoding.
        segments = _split_text_by_max_bytes(segments, max_bytes=1024, encoding="utf-8")

    return [s for s in segments if s and s.strip()]


@dataclass(frozen=True)
class SynthesizeToOssResult:
    provider: str
    model: str
    voice_id: str
    language: str
    segment_count: int
    duration_ms: int
    audio_url: str
    elapsed_seconds: float

    def to_html_audio(self) -> str:
        """Return an embeddable HTML audio player snippet."""
        url = html.escape(self.audio_url, quote=True)
        return f'<audio controls preload="none" src="{url}"></audio>'


def synthesize_long_text_to_oss(
    app: Flask,
    *,
    text: str,
    provider_name: str,
    model: str = "",
    voice_id: str = "",
    language: str = "",
    max_segment_chars: Optional[int] = None,
    max_workers: int = 4,
    sleep_between_segments: float = 0.0,
    audio_bid: Optional[str] = None,
    voice_settings: Optional[VoiceSettings] = None,
    audio_settings: Optional[AudioSettings] = None,
    usage_context: Optional[UsageContext] = None,
    parent_usage_bid: Optional[str] = None,
) -> SynthesizeToOssResult:
    """
    Synthesize a long text, upload the final audio to OSS, and return URL + metrics.

    Notes:
    - Uses the unified TTS client (`flaskr.api.tts.synthesize_text`).
    - Segments are synthesized in parallel (bounded by `max_workers`).
    - Final output is uploaded as an MP3 file for browser playback.
    """
    provider = (provider_name or "").strip().lower()
    if not provider:
        raise ValueError("TTS provider is required")

    if not is_tts_configured(provider):
        raise ValueError(f"TTS provider is not configured: {provider}")

    segments = split_text_for_tts(
        text,
        provider_name=provider,
        max_segment_chars=max_segment_chars,
    )
    if not segments:
        raise ValueError("No speakable text after preprocessing")

    cleaned_text = preprocess_for_tts(text or "")
    raw_length = len(text or "")
    cleaned_length = len(cleaned_text or "")
    usage_parent_bid = ""
    usage_metadata: Optional[dict] = None
    total_word_count = 0
    if usage_context is not None:
        usage_parent_bid = parent_usage_bid or generate_id(app)

    if voice_settings is None:
        voice_settings = get_default_voice_settings(provider)
    if voice_id:
        voice_settings.voice_id = voice_id

    if audio_settings is None:
        audio_settings = get_default_audio_settings(provider)
    # Force MP3 for OSS playback and consistent file naming.
    audio_settings.format = "mp3"
    if usage_context is not None:
        usage_metadata = {
            "voice_id": voice_settings.voice_id or "",
            "speed": voice_settings.speed,
            "pitch": voice_settings.pitch,
            "emotion": voice_settings.emotion,
            "volume": voice_settings.volume,
            "format": audio_settings.format or "mp3",
            "sample_rate": audio_settings.sample_rate or 24000,
        }

    start = time.monotonic()
    max_workers = max(1, int(max_workers or 1))
    sleep_between_segments = float(sleep_between_segments or 0.0)
    if sleep_between_segments < 0:
        raise ValueError("sleep_between_segments must be >= 0")

    if max_workers == 1:
        audio_parts: list[bytes] = []
        with app.app_context():
            for index, segment_text in enumerate(segments):
                segment_start = time.monotonic()
                result = synthesize_text(
                    text=segment_text,
                    voice_settings=voice_settings,
                    audio_settings=audio_settings,
                    model=(model or "").strip() or None,
                    provider_name=provider,
                )
                audio_parts.append(result.audio_data)
                if usage_context is not None:
                    segment_length = len(segment_text or "")
                    total_word_count += int(result.word_count or 0)
                    latency_ms = int((time.monotonic() - segment_start) * 1000)
                    record_tts_usage(
                        app,
                        usage_context,
                        provider=provider,
                        model=(model or "").strip(),
                        is_stream=False,
                        input=segment_length,
                        output=segment_length,
                        total=segment_length,
                        word_count=int(result.word_count or 0),
                        duration_ms=int(result.duration_ms or 0),
                        latency_ms=latency_ms,
                        record_level=1,
                        parent_usage_bid=usage_parent_bid,
                        segment_index=index,
                        segment_count=0,
                        extra=usage_metadata,
                    )
                if sleep_between_segments and index < len(segments) - 1:
                    time.sleep(sleep_between_segments)
    else:
        if sleep_between_segments:
            logger.info(
                "sleep_between_segments is ignored when max_workers > 1 (provider=%s)",
                provider,
            )
        audio_parts = [b""] * len(segments)
        segment_map = {idx: segment for idx, segment in enumerate(segments)}

        def _synthesize_in_app_context(segment_text: str):
            with app.app_context():
                return synthesize_text(
                    text=segment_text,
                    voice_settings=voice_settings,
                    audio_settings=audio_settings,
                    model=(model or "").strip() or None,
                    provider_name=provider,
                )

        with ThreadPoolExecutor(
            max_workers=min(max_workers, len(segments))
        ) as executor:
            future_map = {
                executor.submit(
                    _synthesize_in_app_context,
                    segment_text,
                ): index
                for index, segment_text in enumerate(segments)
            }

            for future in as_completed(future_map):
                index = future_map[future]
                result = future.result()
                audio_parts[index] = result.audio_data
                if usage_context is not None:
                    segment_text = segment_map.get(index, "")
                    segment_length = len(segment_text or "")
                    total_word_count += int(result.word_count or 0)
                    record_tts_usage(
                        app,
                        usage_context,
                        provider=provider,
                        model=(model or "").strip(),
                        is_stream=False,
                        input=segment_length,
                        output=segment_length,
                        total=segment_length,
                        word_count=int(result.word_count or 0),
                        duration_ms=int(result.duration_ms or 0),
                        latency_ms=0,
                        record_level=1,
                        parent_usage_bid=usage_parent_bid,
                        segment_index=index,
                        segment_count=0,
                        extra=usage_metadata,
                    )

    final_audio = concat_audio_best_effort(audio_parts)
    if not final_audio:
        raise ValueError("No audio data produced")

    duration_ms = get_audio_duration_ms(final_audio, format="mp3")

    audio_bid = (audio_bid or "").strip() or uuid.uuid4().hex
    with app.app_context():
        audio_url, _bucket = upload_audio_to_oss(app, final_audio, audio_bid)

    elapsed = time.monotonic() - start

    if usage_context is not None:
        record_tts_usage(
            app,
            usage_context,
            usage_bid=usage_parent_bid,
            provider=provider,
            model=(model or "").strip(),
            is_stream=False,
            input=raw_length,
            output=cleaned_length,
            total=cleaned_length,
            word_count=total_word_count,
            duration_ms=int(duration_ms or 0),
            latency_ms=0,
            record_level=0,
            parent_usage_bid="",
            segment_index=0,
            segment_count=len(segments),
            extra=usage_metadata,
        )

    return SynthesizeToOssResult(
        provider=provider,
        model=(model or "").strip(),
        voice_id=voice_settings.voice_id or voice_id or "",
        language=language,
        segment_count=len(segments),
        duration_ms=duration_ms,
        audio_url=audio_url,
        elapsed_seconds=elapsed,
    )


def write_html_report(
    results: Sequence[SynthesizeToOssResult],
    *,
    output_path: str,
    title: str = "TTS Test Report",
) -> str:
    """
    Write an HTML report that contains embeddable <audio> players.

    Returns:
        The absolute output path as a string.
    """
    rows = []
    for item in results:
        rows.append(
            "<tr>"
            f"<td>{html.escape(item.provider)}</td>"
            f"<td>{html.escape(item.model)}</td>"
            f"<td>{html.escape(item.voice_id)}</td>"
            f"<td>{html.escape(item.language)}</td>"
            f"<td>{item.segment_count}</td>"
            f"<td>{item.duration_ms}</td>"
            f"<td>{item.elapsed_seconds:.3f}</td>"
            f"<td>{item.to_html_audio()}</td>"
            "</tr>"
        )

    html_body = f"""<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>{html.escape(title)}</title>
    <style>
      body {{ font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial; margin: 24px; }}
      table {{ border-collapse: collapse; width: 100%; }}
      th, td {{ border: 1px solid #e5e7eb; padding: 8px; vertical-align: top; }}
      th {{ background: #f9fafb; text-align: left; }}
      audio {{ width: 260px; }}
      .muted {{ color: #6b7280; font-size: 12px; }}
    </style>
  </head>
  <body>
    <h1>{html.escape(title)}</h1>
    <p class=\"muted\">Rows: {len(results)}</p>
    <table>
      <thead>
        <tr>
          <th>Provider</th>
          <th>Model</th>
          <th>Voice</th>
          <th>Language</th>
          <th>Segments</th>
          <th>Audio Duration (ms)</th>
          <th>Synthesis Time (s)</th>
          <th>Preview</th>
        </tr>
      </thead>
      <tbody>
        {"".join(rows)}
      </tbody>
    </table>
  </body>
</html>
"""

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_body, encoding="utf-8")
    return str(out.resolve())
