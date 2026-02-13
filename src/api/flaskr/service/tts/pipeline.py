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
import re
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

_AV_SANDBOX_START_PATTERN = re.compile(
    r"<(script|style|link|iframe|html|head|body|meta|title|base|template|div|section|article|main)(?:[\s>/]|$)",
    re.IGNORECASE,
)
_AV_MARKDOWN_IMAGE_PATTERN = re.compile(
    r"!\[[^\]]*\]\([^\)\n]*\)",
    re.IGNORECASE,
)
_AV_IMG_TAG_PATTERN = re.compile(r"<img\b[^>]*?>", re.IGNORECASE)
_AV_SVG_OPEN_PATTERN = re.compile(r"<svg\b", re.IGNORECASE)
_AV_SVG_CLOSE_PATTERN = re.compile(r"</svg>", re.IGNORECASE)
_AV_IFRAME_OPEN_PATTERN = re.compile(r"<iframe\b", re.IGNORECASE)
_AV_IFRAME_CLOSE_PATTERN = re.compile(r"</iframe>", re.IGNORECASE)
_AV_VIDEO_OPEN_PATTERN = re.compile(r"<video\b", re.IGNORECASE)
_AV_VIDEO_CLOSE_PATTERN = re.compile(r"</video>", re.IGNORECASE)
_AV_TABLE_OPEN_PATTERN = re.compile(r"<table\b", re.IGNORECASE)
_AV_TABLE_CLOSE_PATTERN = re.compile(r"</table>", re.IGNORECASE)
_AV_CLOSING_BOUNDARY_PATTERN = re.compile(
    r"</[a-z][^>]*>\s*\n(?=[^\s<])", re.IGNORECASE
)
_AV_MARKDOWN_TABLE_ROW_PATTERN = re.compile(r"^\s*\|.+\|\s*$", re.MULTILINE)

_AV_SPEAKABLE_SANDBOX_ROOT_TAGS = {"div", "section", "article", "main", "template"}
_AV_SPEAKABLE_SANDBOX_HINT_PATTERN = re.compile(r"<(p|li|h[1-6])\b", re.IGNORECASE)


def _get_fence_ranges(raw: str) -> list[tuple[int, int]]:
    """
    Return ranges for triple-backtick fenced blocks: [(start, end), ...].

    If a fence is not closed, the range will extend to the end of the string.
    """
    ranges: list[tuple[int, int]] = []
    if not raw:
        return ranges

    cursor = 0
    while True:
        start = raw.find("```", cursor)
        if start == -1:
            break
        close = raw.find("```", start + 3)
        if close == -1:
            ranges.append((start, len(raw)))
            break
        end = close + 3
        ranges.append((start, end))
        cursor = end

    return ranges


def _is_index_in_ranges(index: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= index < end for start, end in ranges)


def _find_first_match_outside_fence(
    raw: str, pattern: re.Pattern[str], fence_ranges: list[tuple[int, int]]
) -> re.Match[str] | None:
    """
    Find the first regex match whose start index is not inside a fenced block.
    """
    match = pattern.search(raw)
    while match:
        if not _is_index_in_ranges(match.start(), fence_ranges):
            return match
        match = pattern.search(raw, match.end())
    return None


def _find_first_index_outside_fence(
    raw: str, pattern: re.Pattern[str], fence_ranges: list[tuple[int, int]]
) -> int:
    match = _find_first_match_outside_fence(raw, pattern, fence_ranges)
    return -1 if match is None else match.start()


def _find_html_block_end(raw: str, start_index: int) -> int:
    """
    Best-effort end boundary for a sandbox HTML block.

    Mirrors the heuristic used by the frontend `splitContentSegments` utility:
    end at the first closing-tag boundary after `start_index`.
    """
    return _find_html_block_end_with_complete(raw, start_index)[0]


def _find_html_block_end_with_complete(raw: str, start_index: int) -> tuple[int, bool]:
    """
    Best-effort end boundary for a sandbox HTML block.

    Returns: (end, complete)

    `complete` is True when we can confidently identify the end boundary even if
    it ends at the end of the buffer (common in streaming).
    """
    if not raw:
        return (0, False)
    if start_index < 0 or start_index >= len(raw):
        return (len(raw), False)

    # 1) Primary heuristic: match a closing-tag boundary that is followed by
    # non-tag, non-whitespace text (mirrors markdown-flow-ui).
    for match in _AV_CLOSING_BOUNDARY_PATTERN.finditer(raw):
        if match.start() <= start_index:
            continue
        return (match.end(), True)

    # 2) Fallback: when the HTML block ends at EOF or before another tag, the
    # closingBoundary heuristic may fail. Attempt to find the matching root
    # closing tag for common container tags, accounting for nesting.
    head = raw[start_index:].lstrip()
    if not head.startswith("<"):
        return (len(raw), False)

    tag_match = re.match(r"<([a-z0-9-]+)\b", head, flags=re.IGNORECASE)
    if not tag_match:
        return (len(raw), False)

    tag = (tag_match.group(1) or "").lower()
    match_offset = raw[start_index:].find("<")
    root_start = start_index if match_offset <= 0 else start_index + match_offset

    if tag in {"script", "style"}:
        close = re.search(rf"</{tag}\s*>", raw[root_start:], flags=re.IGNORECASE)
        if not close:
            return (len(raw), False)
        return (root_start + close.end(), True)

    if tag not in {
        "div",
        "section",
        "article",
        "main",
        "template",
        "html",
        "head",
        "body",
    }:
        return (len(raw), False)

    token_pattern = re.compile(rf"</?{re.escape(tag)}\b", flags=re.IGNORECASE)
    depth = 0
    cursor = root_start
    while True:
        match = token_pattern.search(raw, cursor)
        if not match:
            return (len(raw), False)

        token = raw[match.start() : match.end()]
        if token.startswith("</"):
            depth -= 1
            if depth <= 0:
                gt = raw.find(">", match.end())
                if gt == -1:
                    return (len(raw), False)
                end = gt + 1
                end = _extend_fixed_marker_end(raw, end)
                return (end, True)
        else:
            depth += 1

        cursor = match.end()


def _extract_speakable_text_from_sandbox_html(raw: str) -> str:
    """
    Extract speakable text from a sandbox HTML block.

    By default, sandbox blocks are treated as visual boundaries (not spoken).

    Listen Mode requirement: sandbox HTML content must never be narrated, even
    if it contains textual tags like <p>/<li>/<h*>.
    """
    return ""


def _find_svg_block_end(raw: str, start_index: int) -> int:
    close = _AV_SVG_CLOSE_PATTERN.search(raw, start_index)
    if not close:
        return len(raw)
    return close.end()


def _rewind_fixed_marker_start(raw: str, start_index: int) -> int:
    """
    If `raw` contains a MarkdownFlow fixed marker prefix on the same line as a
    visual tag (e.g. `=== <iframe ...`), rewind start to include the marker.
    """
    if not raw or start_index <= 0:
        return start_index

    line_start = raw.rfind("\n", 0, start_index)
    line_start = 0 if line_start == -1 else line_start + 1
    prefix = raw[line_start:start_index]
    stripped = prefix.strip()
    if not stripped:
        return start_index

    # Fixed markers look like: === / !=== / !=== ...
    chars = set(stripped)
    if chars.issubset({"=", "!"}) and stripped.count("=") >= 3:
        return line_start
    return start_index


def _extend_fixed_marker_end(raw: str, end_index: int) -> int:
    """
    If `raw` contains a trailing fixed marker suffix on the same line as a
    visual close tag (e.g. `</iframe> ===`), extend end to include it (and one
    trailing newline if present).
    """
    if not raw or end_index <= 0 or end_index >= len(raw):
        return end_index

    nl = raw.find("\n", end_index)
    line_end = len(raw) if nl == -1 else nl
    tail = raw[end_index:line_end]
    if not tail:
        return end_index

    if re.fullmatch(r"[\s!=]*", tail) and ("=" in tail or "!" in tail):
        return len(raw) if nl == -1 else nl + 1
    return end_index


def _find_iframe_block_end(raw: str, start_index: int) -> int:
    close = _AV_IFRAME_CLOSE_PATTERN.search(raw, start_index)
    if not close:
        return len(raw)
    return _extend_fixed_marker_end(raw, close.end())


def _find_video_block_end(raw: str, start_index: int) -> int:
    close = _AV_VIDEO_CLOSE_PATTERN.search(raw, start_index)
    if not close:
        return len(raw)
    return close.end()


def _find_table_block_end(raw: str, start_index: int) -> int:
    close = _AV_TABLE_CLOSE_PATTERN.search(raw, start_index)
    if not close:
        return len(raw)
    return close.end()


def _find_markdown_table_block(
    raw: str, fence_ranges: list[tuple[int, int]]
) -> tuple[int, int, bool] | None:
    """
    Find the first Markdown table block outside fences.

    Returns: (start, end, complete)
    """
    if not raw:
        return None

    for match in _AV_MARKDOWN_TABLE_ROW_PATTERN.finditer(raw):
        if _is_index_in_ranges(match.start(), fence_ranges):
            continue

        line = match.group(0) or ""
        leading_ws = len(line) - len(line.lstrip())
        table_start = match.start() + leading_ws

        cursor = table_start
        while cursor < len(raw):
            nl = raw.find("\n", cursor)
            line_end = len(raw) if nl == -1 else nl
            line_text = raw[cursor:line_end]
            if line_text.strip().startswith("|"):
                if nl == -1:
                    # Buffer ends while still inside the table block.
                    return (table_start, len(raw), False)
                cursor = nl + 1
                continue

            # Table ended at the first non-table line.
            return (table_start, cursor, True)

        return (table_start, len(raw), False)

    return None


def build_av_segmentation_contract(raw: str, block_bid: str = "") -> dict:
    """
    Build a shared AV segmentation contract used by backend and frontend.

    Contract shape:
    - visual_boundaries[]: {kind, position, block_bid, source_span}
    - speakable_segments[]: {position, text, after_visual_kind, block_bid, source_span}
    """
    visual_boundaries: list[dict] = []
    speakable_segments: list[dict] = []

    if not raw or not raw.strip():
        return {
            "visual_boundaries": visual_boundaries,
            "speakable_segments": speakable_segments,
        }

    def _append_speakable(
        *,
        text: str,
        start_offset: int,
        end_offset: int,
        after_visual_kind: str,
    ):
        cleaned = (text or "").strip()
        if not cleaned:
            return
        speakable_segments.append(
            {
                "position": len(speakable_segments),
                "text": cleaned,
                "after_visual_kind": after_visual_kind,
                "block_bid": block_bid or "",
                "source_span": [int(start_offset), int(end_offset)],
            }
        )

    def _split(text: str, base_offset: int, after_visual_kind: str):
        if not text or not text.strip():
            return

        fence_ranges = _get_fence_ranges(text)
        candidates: list[tuple[str, int, int]] = []

        if fence_ranges:
            start, end = fence_ranges[0]
            candidates.append(("fence", start, end))

        svg_start = _find_first_index_outside_fence(
            text, _AV_SVG_OPEN_PATTERN, fence_ranges
        )
        if svg_start != -1:
            candidates.append(("svg", svg_start, _find_svg_block_end(text, svg_start)))

        iframe_match = _find_first_match_outside_fence(
            text, _AV_IFRAME_OPEN_PATTERN, fence_ranges
        )
        if iframe_match is not None:
            iframe_start = _rewind_fixed_marker_start(text, iframe_match.start())
            candidates.append(
                ("iframe", iframe_start, _find_iframe_block_end(text, iframe_start))
            )

        video_match = _find_first_match_outside_fence(
            text, _AV_VIDEO_OPEN_PATTERN, fence_ranges
        )
        if video_match is not None:
            video_start = video_match.start()
            candidates.append(
                ("video", video_start, _find_video_block_end(text, video_start))
            )

        table_match = _find_first_match_outside_fence(
            text, _AV_TABLE_OPEN_PATTERN, fence_ranges
        )
        if table_match is not None:
            table_start = table_match.start()
            candidates.append(
                ("html_table", table_start, _find_table_block_end(text, table_start))
            )

        img_match = _find_first_match_outside_fence(
            text, _AV_IMG_TAG_PATTERN, fence_ranges
        )
        if img_match is not None:
            candidates.append(("img", img_match.start(), img_match.end()))

        md_img_match = _find_first_match_outside_fence(
            text, _AV_MARKDOWN_IMAGE_PATTERN, fence_ranges
        )
        if md_img_match is not None:
            candidates.append(("md_img", md_img_match.start(), md_img_match.end()))

        md_table = _find_markdown_table_block(text, fence_ranges)
        if md_table is not None:
            start, end, _complete = md_table
            candidates.append(("md_table", start, end))

        sandbox_match = _find_first_match_outside_fence(
            text, _AV_SANDBOX_START_PATTERN, fence_ranges
        )
        if sandbox_match is not None:
            sandbox_start = sandbox_match.start()
            sandbox_end, _complete = _find_html_block_end_with_complete(
                text, sandbox_start
            )
            candidates.append(("sandbox", sandbox_start, sandbox_end))

        if not candidates:
            _append_speakable(
                text=text,
                start_offset=base_offset,
                end_offset=base_offset + len(text),
                after_visual_kind=after_visual_kind,
            )
            return

        kind, start, end = min(candidates, key=lambda item: item[1])
        if end <= start:
            _append_speakable(
                text=text,
                start_offset=base_offset,
                end_offset=base_offset + len(text),
                after_visual_kind=after_visual_kind,
            )
            return

        _append_speakable(
            text=text[:start],
            start_offset=base_offset,
            end_offset=base_offset + start,
            after_visual_kind=after_visual_kind,
        )
        visual_boundaries.append(
            {
                "kind": kind,
                "position": len(visual_boundaries),
                "block_bid": block_bid or "",
                "source_span": [int(base_offset + start), int(base_offset + end)],
            }
        )
        _split(text[end:], base_offset + end, kind)

    _split(raw, 0, "")

    return {
        "visual_boundaries": visual_boundaries,
        "speakable_segments": speakable_segments,
    }


def split_av_speakable_segments(raw: str) -> list[str]:
    """
    Split raw Markdown/HTML content into ordered speakable segments for AV sync.

    The output segments correspond to "text" gaps between visual blocks such as
    SVG, images, fenced code/mermaid blocks, and sandbox HTML blocks.
    """
    contract = build_av_segmentation_contract(raw)
    return [
        segment.get("text", "").strip()
        for segment in contract.get("speakable_segments", [])
        if (segment.get("text", "") or "").strip()
    ]


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
