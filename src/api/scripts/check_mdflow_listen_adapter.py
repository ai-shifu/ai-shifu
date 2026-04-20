#!/usr/bin/env python3
"""
Replay exported generated blocks through markdown-flow 0.2.55 StreamFormatter
and the listen-mode element adapter.

This script validates the new internal chain:

1. markdown-flow 0.2.55 StreamFormatter produces incremental element parts
2. parts are attached to RunMarkdownFlowDTO via private metadata
3. ListenElementRunAdapter consumes those parts without falling back to the
   legacy text-only element path

It can run in two modes:

- stream_only: validate finalized stream elements without AV segmentation
- stream_with_av: validate the same stream path plus AV finalization
"""

from __future__ import annotations

import argparse
import base64
import importlib
import json
import os
import shutil
import sys
import tempfile
from collections import Counter, OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

os.environ.setdefault("SKIP_LOAD_DOTENV", "1")
os.environ.setdefault("SKIP_APP_AUTOCREATE", "1")
os.environ.setdefault("SKIP_DB_MIGRATIONS_FOR_TESTS", "1")

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.mysql import BIGINT, LONGTEXT
from sqlalchemy.ext.compiler import compiles

from flaskr import dao

if dao.db is None:
    dao.db = SQLAlchemy()


@compiles(LONGTEXT, "sqlite")
def _compile_longtext_sqlite(_type, _compiler, **_kw):
    return "TEXT"


@compiles(BIGINT, "sqlite")
def _compile_bigint_sqlite(_type, _compiler, **_kw):
    return "INTEGER"


DEFAULT_CHUNK_SIZES = (1, 2, 3, 5, 8, 13)
DEFAULT_MDFLOW_ROOT = "/tmp/mdflow255"


@dataclass
class BlockSample:
    id: int
    generated_block_bid: str
    shifu_bid: str
    outline_item_bid: str
    progress_record_bid: str
    created_at: str
    position: int
    content_len: int
    generated_content: str


@dataclass
class ExpectedStreamElement:
    number: int
    stream_type: str
    content_text: str


@dataclass
class AnalysisResult:
    mode: str
    sample: BlockSample
    issues: list[str]
    expected_count: int
    observed_count: int
    final_types: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check markdown-flow 0.2.55 stream parts against ListenElementRunAdapter."
    )
    parser.add_argument(
        "--input",
        default="/tmp/latest_generate_blocks_b64.jsonl",
        help="Path to JSONL exported from generated blocks",
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
    parser.add_argument(
        "--mode",
        choices=("both", "stream_only", "stream_with_av"),
        default="both",
        help="Validation mode",
    )
    parser.add_argument(
        "--mdflow-root",
        default=DEFAULT_MDFLOW_ROOT,
        help="Filesystem root containing markdown-flow 0.2.55 package files",
    )
    return parser.parse_args()


def _preview(text: str, width: int = 160) -> str:
    one_line = (text or "").replace("\n", "\\n")
    if len(one_line) <= width:
        return one_line
    return one_line[: width - 3] + "..."


def _iter_chunks(text: str, chunk_sizes: tuple[int, ...]) -> Iterable[str]:
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
                    shifu_bid=str(obj.get("shifu_bid") or "test-shifu"),
                    outline_item_bid=str(
                        obj.get("outline_item_bid") or "test-outline-item"
                    ),
                    progress_record_bid=str(
                        obj.get("progress_record_bid") or "test-progress"
                    ),
                    created_at=str(obj.get("created_at") or ""),
                    position=int(obj.get("position") or 0),
                    content_len=int(obj.get("content_len") or len(content)),
                    generated_content=content,
                )
            )
            if len(samples) >= limit:
                break
    return samples


def _bootstrap_mdflow(mdflow_root: str):
    root = Path(mdflow_root)
    init_file = root / "markdown_flow" / "__init__.py"
    if not init_file.exists():
        raise SystemExit(
            f"markdown-flow root not found or incomplete: {root}. "
            "Expected markdown_flow/__init__.py"
        )

    sys.path.insert(0, str(root))
    for name in list(sys.modules):
        if name == "markdown_flow" or name.startswith("markdown_flow."):
            sys.modules.pop(name, None)

    markdown_flow = importlib.import_module("markdown_flow")
    if not hasattr(markdown_flow, "StreamFormatter"):
        raise SystemExit(
            f"markdown-flow loaded from {markdown_flow.__file__} "
            "does not expose StreamFormatter"
        )
    return markdown_flow


def _make_app() -> tuple[Flask, str]:
    temp_dir = tempfile.mkdtemp(prefix="ai-shifu-mdflow-listen-")
    db_path = Path(temp_dir) / "test.db"
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    dao.init_db(app)

    # Import models after db initialization so metadata is registered.
    from flaskr.service.learn.models import (  # noqa: F401
        LearnGeneratedBlock,
        LearnGeneratedElement,
        LearnProgressRecord,
    )

    with app.app_context():
        dao.db.create_all()
    return app, temp_dir


def _format_stream_parts(
    content: str,
    chunk_sizes: tuple[int, ...],
    stream_formatter_cls,
) -> list[tuple[str, str, int]]:
    formatter = stream_formatter_cls()
    parts: list[tuple[str, str, int]] = []

    for chunk in _iter_chunks(content, chunk_sizes):
        for item in formatter.process(chunk):
            parts.append(
                (str(item.content or ""), str(item.type or ""), int(item.number))
            )
    for item in formatter.flush():
        parts.append((str(item.content or ""), str(item.type or ""), int(item.number)))
    return parts


def _group_expected_stream_elements(
    parts: list[tuple[str, str, int]],
) -> list[ExpectedStreamElement]:
    grouped: "OrderedDict[int, ExpectedStreamElement]" = OrderedDict()
    for content, stream_type, number in parts:
        if not content or not stream_type:
            continue
        existing = grouped.get(number)
        if existing is None:
            grouped[number] = ExpectedStreamElement(
                number=number,
                stream_type=stream_type,
                content_text=content,
            )
            continue
        existing.content_text += content
    return list(grouped.values())


def _reset_tables(app: Flask) -> None:
    from flaskr.service.learn.models import (
        LearnGeneratedBlock,
        LearnGeneratedElement,
        LearnProgressRecord,
    )

    with app.app_context():
        LearnGeneratedElement.query.delete()
        LearnGeneratedBlock.query.delete()
        LearnProgressRecord.query.delete()
        dao.db.session.commit()


def _seed_sample(app: Flask, sample: BlockSample, *, suffix: str) -> dict[str, str]:
    from flaskr.service.learn.const import ROLE_TEACHER
    from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS

    block_bid = f"{sample.generated_block_bid}_{suffix}"
    progress_bid = f"{sample.progress_record_bid}_{suffix}"
    shifu_bid = sample.shifu_bid or f"shifu-{sample.id}"
    outline_bid = sample.outline_item_bid or f"outline-{sample.id}"
    user_bid = f"user-{sample.id}-{suffix}"

    with app.app_context():
        progress = LearnProgressRecord(
            progress_record_bid=progress_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            user_bid=user_bid,
            status=LEARN_STATUS_IN_PROGRESS,
            block_position=int(sample.position or 0),
        )
        block = LearnGeneratedBlock(
            generated_block_bid=block_bid,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            block_bid=f"block-{sample.id}-{suffix}",
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            type=0,
            role=ROLE_TEACHER,
            generated_content=sample.generated_content,
            position=int(sample.position or 0),
            block_content_conf="",
            status=1,
        )
        dao.db.session.add_all([progress, block])
        dao.db.session.commit()

    return {
        "generated_block_bid": block_bid,
        "progress_record_bid": progress_bid,
        "shifu_bid": shifu_bid,
        "outline_bid": outline_bid,
        "user_bid": user_bid,
    }


def _build_stream_events(
    *,
    outline_bid: str,
    generated_block_bid: str,
    parts: list[tuple[str, str, int]],
) -> list[object]:
    from flaskr.service.learn.learn_dtos import GeneratedType, RunMarkdownFlowDTO

    events: list[object] = []
    for content, stream_type, number in parts:
        events.append(
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content=content,
            ).set_mdflow_stream_parts([(content, stream_type, number)])
        )
    return events


def _append_audio_complete_events(
    *,
    events: list[object],
    outline_bid: str,
    generated_block_bid: str,
    raw_content: str,
) -> None:
    from flaskr.service.learn.learn_dtos import (
        AudioCompleteDTO,
        GeneratedType,
        RunMarkdownFlowDTO,
    )
    from flaskr.service.tts.pipeline import build_av_segmentation_contract

    av_contract = build_av_segmentation_contract(raw_content, generated_block_bid)
    speakable_segments = av_contract.get("speakable_segments") or []
    for seg in speakable_segments:
        if not isinstance(seg, dict):
            continue
        try:
            position = int(seg.get("position", 0))
        except (TypeError, ValueError):
            continue
        events.append(
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_COMPLETE,
                content=AudioCompleteDTO(
                    audio_url=f"https://example.invalid/audio/{generated_block_bid}/{position}.mp3",
                    audio_bid=f"audio-{generated_block_bid}-{position}",
                    duration_ms=1000,
                    position=position,
                    av_contract=av_contract,
                ),
            )
        )


def _append_terminal_events(
    *,
    events: list[object],
    outline_bid: str,
    generated_block_bid: str,
) -> None:
    from flaskr.service.learn.learn_dtos import GeneratedType, RunMarkdownFlowDTO

    events.extend(
        [
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.BREAK,
                content="",
            ),
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.DONE,
                content="",
            ),
        ]
    )


def _expected_visual_segment_count(raw_content: str, generated_block_bid: str) -> int:
    from flaskr.service.learn.listen_slide_builder import (
        VisualSegment,
        build_visual_segments_for_block,
    )
    from flaskr.service.learn.listen_source_span_utils import (
        normalize_source_span,
        slice_source_by_span,
    )
    from flaskr.service.tts.pipeline import build_av_segmentation_contract

    av_contract = build_av_segmentation_contract(raw_content, generated_block_bid)
    visual_segments, _ = build_visual_segments_for_block(
        raw_content=raw_content,
        generated_block_bid=generated_block_bid,
        av_contract=av_contract,
        element_index_offset=0,
    )
    if visual_segments:
        return len(visual_segments)

    visual_boundaries = av_contract.get("visual_boundaries") or []
    fallback_segments: list[VisualSegment] = []
    next_index = 0
    for boundary in visual_boundaries:
        if not isinstance(boundary, dict):
            continue
        source_span = normalize_source_span(boundary.get("source_span"))
        if not source_span:
            continue
        visual_kind = str(boundary.get("kind", "") or "")
        if not visual_kind:
            continue
        fallback_segments.append(
            VisualSegment(
                segment_id=f"fallback-{next_index}",
                generated_block_bid=generated_block_bid,
                element_index=next_index,
                audio_position=int(boundary.get("position", 0) or 0),
                visual_kind=visual_kind,
                segment_type="sandbox"
                if visual_kind in {"iframe", "sandbox", "html_table"}
                else "markdown",
                segment_content=slice_source_by_span(raw_content, source_span),
                source_span=source_span,
                is_placeholder=False,
            )
        )
        next_index += 1
    return len(fallback_segments)


def _analyze_stream_only(
    app: Flask,
    sample: BlockSample,
    parts: list[tuple[str, str, int]],
) -> AnalysisResult:
    from flaskr.service.learn.listen_elements import (
        ListenElementRunAdapter,
        _element_type_from_mdflow_stream,
        get_listen_element_record,
    )
    from flaskr.service.learn.models import LearnGeneratedElement

    _reset_tables(app)
    seeded = _seed_sample(app, sample, suffix="stream-only")
    events = _build_stream_events(
        outline_bid=seeded["outline_bid"],
        generated_block_bid=seeded["generated_block_bid"],
        parts=parts,
    )
    _append_terminal_events(
        events=events,
        outline_bid=seeded["outline_bid"],
        generated_block_bid=seeded["generated_block_bid"],
    )

    expected = _group_expected_stream_elements(parts)
    issues: list[str] = []

    with app.app_context():
        adapter = ListenElementRunAdapter(
            app,
            shifu_bid=seeded["shifu_bid"],
            outline_bid=seeded["outline_bid"],
            user_bid=seeded["user_bid"],
        )
        try:
            list(adapter.process(events))
        except Exception as exc:
            return AnalysisResult(
                mode="stream_only",
                sample=sample,
                issues=[f"process_error: {exc}"],
                expected_count=len(expected),
                observed_count=0,
                final_types=[],
            )

        fallback_bid = f"el_{seeded['generated_block_bid']}"
        fallback_used = (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.generated_block_bid
                == seeded["generated_block_bid"],
                LearnGeneratedElement.event_type == "element",
                LearnGeneratedElement.element_bid == fallback_bid,
                LearnGeneratedElement.deleted == 0,
            ).count()
            > 0
        )
        if fallback_used:
            issues.append("fallback_element_used")

        record = get_listen_element_record(
            app,
            shifu_bid=seeded["shifu_bid"],
            outline_bid=seeded["outline_bid"],
            user_bid=seeded["user_bid"],
            preview_mode=False,
        )
        observed = record.elements

        if len(observed) != len(expected):
            issues.append(
                f"final_element_count_mismatch expected={len(expected)} observed={len(observed)}"
            )

        for idx, (expected_item, observed_item) in enumerate(
            zip(expected, observed), start=1
        ):
            expected_type = _element_type_from_mdflow_stream(
                expected_item.stream_type, expected_item.content_text
            )
            if observed_item.element_type != expected_type:
                issues.append(
                    f"element_{idx}_type_mismatch expected={expected_type.value} observed={observed_item.element_type.value}"
                )
            if observed_item.content_text != expected_item.content_text:
                issues.append(f"element_{idx}_content_mismatch")
            if not observed_item.is_final:
                issues.append(f"element_{idx}_not_final")

        return AnalysisResult(
            mode="stream_only",
            sample=sample,
            issues=issues,
            expected_count=len(expected),
            observed_count=len(observed),
            final_types=[item.element_type.value for item in observed],
        )


def _analyze_stream_with_av(
    app: Flask,
    sample: BlockSample,
    parts: list[tuple[str, str, int]],
) -> AnalysisResult:
    from flaskr.service.learn.listen_elements import (
        ListenElementRunAdapter,
        get_listen_element_record,
    )
    from flaskr.service.learn.models import LearnGeneratedElement
    from flaskr.service.tts.pipeline import build_av_segmentation_contract

    _reset_tables(app)
    seeded = _seed_sample(app, sample, suffix="stream-av")
    events = _build_stream_events(
        outline_bid=seeded["outline_bid"],
        generated_block_bid=seeded["generated_block_bid"],
        parts=parts,
    )
    _append_audio_complete_events(
        events=events,
        outline_bid=seeded["outline_bid"],
        generated_block_bid=seeded["generated_block_bid"],
        raw_content=sample.generated_content,
    )
    _append_terminal_events(
        events=events,
        outline_bid=seeded["outline_bid"],
        generated_block_bid=seeded["generated_block_bid"],
    )

    expected_stream = _group_expected_stream_elements(parts)
    av_contract = build_av_segmentation_contract(
        sample.generated_content, seeded["generated_block_bid"]
    )
    speakable_segments = av_contract.get("speakable_segments") or []
    has_av_finalize = bool(speakable_segments)
    expected_visual_count = _expected_visual_segment_count(
        sample.generated_content, seeded["generated_block_bid"]
    )
    issues: list[str] = []

    with app.app_context():
        adapter = ListenElementRunAdapter(
            app,
            shifu_bid=seeded["shifu_bid"],
            outline_bid=seeded["outline_bid"],
            user_bid=seeded["user_bid"],
        )
        try:
            list(adapter.process(events))
        except Exception as exc:
            return AnalysisResult(
                mode="stream_with_av",
                sample=sample,
                issues=[f"process_error: {exc}"],
                expected_count=(
                    expected_visual_count
                    if has_av_finalize and expected_visual_count > 0
                    else len(expected_stream)
                ),
                observed_count=0,
                final_types=[],
            )

        fallback_bid = f"el_{seeded['generated_block_bid']}"
        fallback_used = (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.generated_block_bid
                == seeded["generated_block_bid"],
                LearnGeneratedElement.event_type == "element",
                LearnGeneratedElement.element_bid == fallback_bid,
                LearnGeneratedElement.deleted == 0,
            ).count()
            > 0
        )
        if fallback_used:
            issues.append("fallback_element_used")

        record = get_listen_element_record(
            app,
            shifu_bid=seeded["shifu_bid"],
            outline_bid=seeded["outline_bid"],
            user_bid=seeded["user_bid"],
            preview_mode=False,
        )
        observed = record.elements

        expected_count = (
            expected_visual_count
            if has_av_finalize and expected_visual_count > 0
            else len(expected_stream)
        )
        if len(observed) != expected_count:
            issues.append(
                f"final_element_count_mismatch expected={expected_count} observed={len(observed)}"
            )

        active_provisional = LearnGeneratedElement.query.filter(
            LearnGeneratedElement.generated_block_bid == seeded["generated_block_bid"],
            LearnGeneratedElement.event_type == "element",
            LearnGeneratedElement.status == 1,
            LearnGeneratedElement.deleted == 0,
            LearnGeneratedElement.element_bid.like(
                f"el_{seeded['generated_block_bid']}%"
            ),
        ).count()
        if has_av_finalize and expected_visual_count > 0 and active_provisional > 0:
            issues.append(
                f"active_provisional_rows_remaining count={active_provisional}"
            )

        if has_av_finalize and observed:
            has_audio = any(
                item.payload and item.payload.audio and item.payload.audio.audio_url
                for item in observed
            )
            if not has_audio:
                issues.append("final_elements_missing_audio_payload")

        for idx, observed_item in enumerate(observed, start=1):
            if not observed_item.is_final:
                issues.append(f"element_{idx}_not_final")

        return AnalysisResult(
            mode="stream_with_av",
            sample=sample,
            issues=issues,
            expected_count=expected_count,
            observed_count=len(observed),
            final_types=[item.element_type.value for item in observed],
        )


def _print_summary(
    *,
    mode: str,
    results: list[AnalysisResult],
    show: int,
) -> None:
    abnormal = [item for item in results if item.issues]
    type_counts = Counter()
    for item in results:
        type_counts.update(item.final_types)

    print(
        f"[{mode}] analyzed={len(results)} abnormal={len(abnormal)} "
        f"final_type_distribution={dict(type_counts)}"
    )
    for item in abnormal[:show]:
        print(
            f"  - block_id={item.sample.id} block_bid={item.sample.generated_block_bid} "
            f"expected={item.expected_count} observed={item.observed_count}"
        )
        print(f"    issues={', '.join(item.issues)}")
        print(f"    content={_preview(item.sample.generated_content)}")


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    chunk_sizes = (
        tuple(int(part.strip()) for part in args.chunk_sizes.split(",") if part.strip())
        or DEFAULT_CHUNK_SIZES
    )

    markdown_flow = _bootstrap_mdflow(args.mdflow_root)
    print(
        "Using markdown-flow:",
        getattr(markdown_flow, "__version__", "unknown"),
        getattr(markdown_flow, "__file__", "unknown"),
    )

    samples = _load_samples(input_path, limit=args.limit)
    if not samples:
        raise SystemExit("No samples loaded")

    app, temp_dir = _make_app()
    try:
        stream_formatter_cls = markdown_flow.StreamFormatter
        stream_only_results: list[AnalysisResult] = []
        stream_with_av_results: list[AnalysisResult] = []

        for sample in samples:
            if not sample.generated_content.strip():
                continue
            parts = _format_stream_parts(
                sample.generated_content,
                chunk_sizes=chunk_sizes,
                stream_formatter_cls=stream_formatter_cls,
            )

            if args.mode in {"both", "stream_only"}:
                stream_only_results.append(_analyze_stream_only(app, sample, parts))
            if args.mode in {"both", "stream_with_av"}:
                stream_with_av_results.append(
                    _analyze_stream_with_av(app, sample, parts)
                )

        failed = False
        if stream_only_results:
            _print_summary(
                mode="stream_only",
                results=stream_only_results,
                show=args.show,
            )
            failed = failed or any(item.issues for item in stream_only_results)
        if stream_with_av_results:
            _print_summary(
                mode="stream_with_av",
                results=stream_with_av_results,
                show=args.show,
            )
            failed = failed or any(item.issues for item in stream_with_av_results)
        return 1 if failed else 0
    finally:
        with app.app_context():
            dao.db.session.remove()
            dao.db.drop_all()
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
