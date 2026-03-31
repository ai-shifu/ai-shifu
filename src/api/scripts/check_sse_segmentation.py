#!/usr/bin/env python3
"""
Replay generated blocks through AVStreamingTTSProcessor with tiny SSE chunks.

This script is intended for regression checks against real generated block
content exported from MySQL. It compares:

1. Expected speakable segments from split_av_speakable_segments(raw_text)
2. Observed speakable segments produced when AVStreamingTTSProcessor receives
   the same content incrementally as simulated SSE chunks

The input file is expected to contain one JSON object per line with a
base64-encoded generated_content payload.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from unittest.mock import MagicMock

os.environ.setdefault("SKIP_LOAD_DOTENV", "1")
os.environ.setdefault("SKIP_APP_AUTOCREATE", "1")
os.environ.setdefault("SKIP_DB_MIGRATIONS_FOR_TESTS", "1")

from flask_sqlalchemy import SQLAlchemy

from flaskr import dao

if dao.db is None:
    dao.db = SQLAlchemy()

from flaskr.service.tts.pipeline import split_av_speakable_segments
from flaskr.service.tts import streaming_tts as streaming_tts_module


DEFAULT_CHUNK_SIZES = (1, 2, 3, 5, 8, 13)
VISUAL_LEAK_PATTERN = re.compile(
    r"(<svg\b|</svg>|!\[|<img\b|<iframe\b|<video\b|<table\b|```)",
    flags=re.IGNORECASE,
)


@dataclass
class BlockSample:
    id: int
    generated_block_bid: str
    created_at: str
    position: int
    content_len: int
    generated_content: str


@dataclass
class AnalysisResult:
    sample: BlockSample
    expected_segments: list[str]
    observed_segments: list[str]
    issues: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check SSE segmentation against exported generate blocks."
    )
    parser.add_argument(
        "--input",
        default="/tmp/latest_generate_blocks_b64.jsonl",
        help="Path to JSONL exported from MySQL",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of records to analyze",
    )
    parser.add_argument(
        "--chunk-sizes",
        default="1,2,3,5,8,13",
        help="Comma-separated chunk sizes used cyclically to simulate SSE",
    )
    parser.add_argument(
        "--show",
        type=int,
        default=10,
        help="Maximum number of abnormal samples to print",
    )
    return parser.parse_args()


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _iter_chunks(text: str, chunk_sizes: tuple[int, ...]) -> Iterable[str]:
    if not text:
        return
    idx = 0
    size_idx = 0
    while idx < len(text):
        size = max(int(chunk_sizes[size_idx % len(chunk_sizes)]), 1)
        yield text[idx : idx + size]
        idx += size
        size_idx += 1


def _load_samples(path: Path, limit: int) -> list[BlockSample]:
    samples: list[BlockSample] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            payload = line.strip()
            if not payload:
                continue
            obj = json.loads(payload)
            content = base64.b64decode(obj["generated_content_b64"]).decode("utf-8")
            samples.append(
                BlockSample(
                    id=int(obj["id"]),
                    generated_block_bid=str(obj["generated_block_bid"]),
                    created_at=str(obj["created_at"]),
                    position=int(obj["position"]),
                    content_len=int(obj["content_len"]),
                    generated_content=content,
                )
            )
            if len(samples) >= limit:
                break
    return samples


def _simulate_observed_segments(
    sample: BlockSample,
    chunk_sizes: tuple[int, ...],
) -> list[str]:
    captured_by_position: dict[int, list[str]] = {}

    class CaptureStreamingTTSProcessor:
        def __init__(self, **kwargs):
            self.position = int(kwargs.get("position", 0) or 0)
            self._parts: list[str] = []

        def process_chunk(self, chunk):
            if chunk:
                self._parts.append(chunk)
            return
            yield

        def finalize(self, commit=True):
            _ = commit
            text = "".join(self._parts).strip()
            if text:
                captured_by_position.setdefault(self.position, []).append(text)
            return
            yield

    original_cls = streaming_tts_module.StreamingTTSProcessor
    streaming_tts_module.StreamingTTSProcessor = CaptureStreamingTTSProcessor
    try:
        processor = streaming_tts_module.AVStreamingTTSProcessor(
            app=MagicMock(config={}),
            generated_block_bid=sample.generated_block_bid,
            outline_bid="test-outline",
            progress_record_bid="test-progress",
            user_bid="test-user",
            shifu_bid="test-shifu",
            tts_provider="minimax",
            tts_model="speech-01",
        )
        for chunk in _iter_chunks(sample.generated_content, chunk_sizes):
            list(processor.process_chunk(chunk))
        list(processor.finalize(commit=False))
    finally:
        streaming_tts_module.StreamingTTSProcessor = original_cls

    observed_segments: list[str] = []
    for position in sorted(captured_by_position):
        merged = "".join(captured_by_position[position]).strip()
        if merged:
            observed_segments.append(merged)
    return observed_segments


def _detect_issues(
    expected_segments: list[str], observed_segments: list[str]
) -> list[str]:
    issues: list[str] = []
    if len(expected_segments) != len(observed_segments):
        issues.append(
            f"segment_count_mismatch expected={len(expected_segments)} observed={len(observed_segments)}"
        )

    for idx, (expected, observed) in enumerate(
        zip(expected_segments, observed_segments), start=1
    ):
        if expected != observed:
            if _normalize_text(expected) == _normalize_text(observed):
                issues.append(f"segment_{idx}_whitespace_only_diff")
            else:
                issues.append(f"segment_{idx}_text_mismatch")
        if VISUAL_LEAK_PATTERN.search(observed):
            issues.append(f"segment_{idx}_visual_marker_leak")

    if len(observed_segments) > len(expected_segments):
        for idx, observed in enumerate(
            observed_segments[len(expected_segments) :],
            start=len(expected_segments) + 1,
        ):
            if VISUAL_LEAK_PATTERN.search(observed):
                issues.append(f"segment_{idx}_visual_marker_leak")

    return issues


def _preview(text: str, width: int = 160) -> str:
    one_line = text.replace("\n", "\\n")
    if len(one_line) <= width:
        return one_line
    return one_line[: width - 3] + "..."


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    chunk_sizes = (
        tuple(int(part.strip()) for part in args.chunk_sizes.split(",") if part.strip())
        or DEFAULT_CHUNK_SIZES
    )

    samples = _load_samples(input_path, limit=args.limit)
    if not samples:
        raise SystemExit("No samples loaded")

    abnormal: list[AnalysisResult] = []
    speakable_count = 0
    empty_count = 0

    for sample in samples:
        expected_segments = split_av_speakable_segments(sample.generated_content)
        observed_segments = _simulate_observed_segments(sample, chunk_sizes)
        if expected_segments:
            speakable_count += 1
        else:
            empty_count += 1

        issues = _detect_issues(expected_segments, observed_segments)
        if issues:
            abnormal.append(
                AnalysisResult(
                    sample=sample,
                    expected_segments=expected_segments,
                    observed_segments=observed_segments,
                    issues=issues,
                )
            )

    print(
        f"Analyzed {len(samples)} blocks with chunk_sizes={chunk_sizes}. "
        f"Speakable={speakable_count}, empty={empty_count}, abnormal={len(abnormal)}."
    )

    if not abnormal:
        return 0

    for item in abnormal[: args.show]:
        sample = item.sample
        print(
            "\n--- "
            f"id={sample.id} generated_block_bid={sample.generated_block_bid} "
            f"created_at={sample.created_at} content_len={sample.content_len}"
        )
        print("issues:", ", ".join(item.issues))
        print(
            f"expected_count={len(item.expected_segments)} "
            f"observed_count={len(item.observed_segments)}"
        )
        for idx, expected in enumerate(item.expected_segments[:3], start=1):
            print(f"expected[{idx}]: {_preview(expected)}")
        for idx, observed in enumerate(item.observed_segments[:3], start=1):
            print(f"observed[{idx}]: {_preview(observed)}")

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
