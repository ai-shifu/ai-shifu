"""Screen offline historical rows into sanitized full-course calibration samples.

This module never opens a database connection. A read-only extraction performed
in the data-owning environment must provide complete published, progress,
generated-block, and usage histories for each candidate. The JSON input may
contain learner identifiers and authored text; stdout contains only aggregate
features, normalized credits, and a course grouping identifier.

Run from ``src/api`` with ``python scripts/course_completion_credit_samples.py
input.json``. Missing evidence excludes a candidate; it never becomes a zero
cost sample. The caller must independently audit the completeness attestations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import SimpleNamespace
from typing import Any

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from flaskr.service.shifu.admin_operations.course_completion_credit_features import (  # noqa: E402
    build_course_completion_credit_features,
    detect_authored_language,
)
from flaskr.service.shifu.admin_operations.course_completion_credit_model import (  # noqa: E402
    CalibrationSample,
    TokenUsage,
    reprice_requests_1x,
)

_COMPLETENESS_KEYS = frozenset(
    {"published_history", "published_rows", "progress", "generated_blocks", "usage"}
)
_LEARN_STATUS_COMPLETED = 603
_BILL_USAGE_LLM = 1101
_BILL_USAGE_PRODUCTION = 1203
_MODEL_TEACHER = 1
_MODEL_CONTENT = 311
_AGENT_FEATURE_CONTRACT = "agent-2.0-author-constraints-v1"
_MACHINE_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")


@dataclass(frozen=True)
class ScreeningResult:
    """A sample or a stable, non-sensitive exclusion reason."""

    sample: CalibrationSample | None
    reason: str | None


class _SampleExclusionError(ValueError):
    """Reject one candidate without carrying raw values to output."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise _SampleExclusionError(reason)


def _mapping(value: object, reason: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), reason)
    return value


def _rows(value: object, reason: str) -> list[Mapping[str, Any]]:
    _require(isinstance(value, list), reason)
    return [_mapping(row, reason) for row in value]


def _text(value: object) -> str:
    return str(value or "").strip()


def _integer(value: object, reason: str) -> int:
    _require(type(value) is int, reason)
    return value


def _timestamp(value: object, reason: str) -> datetime:
    _require(isinstance(value, str) and bool(value), reason)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise _SampleExclusionError(reason) from exc
    _require(parsed.tzinfo is not None, reason)
    return parsed.astimezone(UTC)


def _snapshot_outline(
    candidate: Mapping[str, Any], course_id: str
) -> tuple[
    Mapping[str, Any], list[Mapping[str, Any]], list[str], datetime, datetime | None
]:
    snapshot = _mapping(candidate.get("snapshot"), "snapshot_missing")
    published_at = _timestamp(snapshot.get("published_at"), "snapshot_time_invalid")
    next_at_raw = snapshot.get("next_published_at")
    next_at = (
        _timestamp(next_at_raw, "snapshot_time_invalid")
        if next_at_raw is not None
        else None
    )
    _require("next_published_at" in snapshot, "snapshot_history_incomplete")
    _require(next_at is None or next_at > published_at, "snapshot_time_invalid")
    if next_at is None:
        _require(
            snapshot.get("latest_at_cutoff") is True, "snapshot_history_incomplete"
        )

    course = _mapping(snapshot.get("course_row"), "snapshot_course_missing")
    root_raw = snapshot.get("struct")
    if isinstance(root_raw, str):
        try:
            root_raw = json.loads(root_raw)
        except json.JSONDecodeError as exc:
            message = "snapshot_structure_invalid"
            raise _SampleExclusionError(message) from exc
    root = _mapping(root_raw, "snapshot_structure_invalid")
    _require(root.get("type") == "shifu", "snapshot_structure_invalid")
    _require(_text(root.get("bid")) == course_id, "snapshot_course_mismatch")
    _require(_text(course.get("shifu_bid")) == course_id, "snapshot_course_mismatch")
    _require(
        _integer(root.get("id"), "snapshot_course_mismatch")
        == _integer(course.get("id"), "snapshot_course_mismatch"),
        "snapshot_course_mismatch",
    )

    outline_rows = _rows(snapshot.get("outline_rows"), "snapshot_outline_missing")
    row_by_id: dict[int, Mapping[str, Any]] = {}
    for row in outline_rows:
        row_id = _integer(row.get("id"), "snapshot_outline_invalid")
        _require(row_id not in row_by_id, "snapshot_outline_duplicate")
        row_by_id[row_id] = row

    visited_ids: set[int] = set()
    visited_bids: set[str] = set()
    leaves: list[str] = []

    def visit(node: Mapping[str, Any], parent_bid: str, *, hidden_parent: bool) -> None:
        node_id = _integer(node.get("id"), "snapshot_structure_invalid")
        bid = _text(node.get("bid"))
        _require(bool(bid) and node_id not in visited_ids, "snapshot_structure_invalid")
        _require(bid not in visited_bids, "snapshot_structure_invalid")
        row = row_by_id.get(node_id)
        _require(row is not None, "snapshot_outline_missing")
        _require(
            _text(row.get("outline_item_bid")) == bid
            and _text(row.get("shifu_bid")) == course_id
            and _text(row.get("parent_bid")) == parent_bid,
            "snapshot_outline_mismatch",
        )
        visited_ids.add(node_id)
        visited_bids.add(bid)
        children = node.get("children")
        _require(isinstance(children, list), "snapshot_structure_invalid")
        child_outlines = []
        for child_raw in children:
            child = _mapping(child_raw, "snapshot_structure_invalid")
            _require(child.get("type") == "outline", "snapshot_structure_invalid")
            child_outlines.append(child)
        hidden = hidden_parent or bool(row.get("hidden"))
        if not hidden and not child_outlines:
            leaves.append(bid)
        for child in child_outlines:
            visit(child, bid, hidden_parent=hidden)

    root_children = root.get("children")
    _require(isinstance(root_children, list), "snapshot_structure_invalid")
    for child_raw in root_children:
        child = _mapping(child_raw, "snapshot_structure_invalid")
        _require(child.get("type") == "outline", "snapshot_structure_invalid")
        visit(child, "", hidden_parent=False)
    _require(visited_ids == set(row_by_id), "snapshot_outline_mismatch")
    _require(bool(leaves), "no_visible_lessons")
    return course, outline_rows, leaves, published_at, next_at


def _completion_progress(
    candidate: Mapping[str, Any],
    course_id: str,
    leaves: list[str],
    outline_bids: set[str],
    published_at: datetime,
) -> tuple[dict[str, Mapping[str, Any]], datetime, datetime]:
    rows = _rows(candidate.get("progress_rows"), "progress_missing")
    _require(bool(rows), "progress_missing")
    learners = {_text(row.get("user_bid")) for row in rows}
    _require(len(learners) == 1 and "" not in learners, "progress_learner_mismatch")
    progress_by_leaf: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        _require(_text(row.get("shifu_bid")) == course_id, "progress_course_mismatch")
        bid = _text(row.get("outline_item_bid"))
        _require(bid in outline_bids, "progress_version_mismatch")
        created_at = _timestamp(row.get("created_at"), "progress_time_invalid")
        _require(created_at >= published_at, "progress_version_mismatch")
        if bid not in leaves:
            continue
        _require(bid not in progress_by_leaf, "progress_relearned")
        _require(
            row.get("deleted") == 0 and row.get("status") == _LEARN_STATUS_COMPLETED,
            "progress_incomplete",
        )
        _require(bool(_text(row.get("progress_record_bid"))), "progress_link_missing")
        progress_by_leaf[bid] = row
    _require(set(progress_by_leaf) == set(leaves), "progress_incomplete")
    ids = [_text(row["progress_record_bid"]) for row in progress_by_leaf.values()]
    _require(len(set(ids)) == len(ids), "progress_link_duplicate")
    starts = [
        _timestamp(row.get("created_at"), "progress_time_invalid")
        for row in progress_by_leaf.values()
    ]
    finishes = [
        _timestamp(row.get("updated_at"), "progress_time_invalid")
        for row in progress_by_leaf.values()
    ]
    _require(
        all(start <= finish for start, finish in zip(starts, finishes, strict=True)),
        "progress_time_invalid",
    )
    return progress_by_leaf, min(starts), max(finishes)


def _verified_engine(
    candidate: Mapping[str, Any],
    course_id: str,
    started_at: datetime,
    completed_at: datetime,
    usage_rows: list[Mapping[str, Any]],
) -> str:
    proof = _mapping(candidate.get("engine_proof"), "engine_unverified")
    _require(proof.get("verified") is True, "engine_unverified")
    engine = _text(proof.get("engine"))
    _require(engine in {"1.0", "2.0"}, "engine_unverified")
    _require(_text(proof.get("course_id")) == course_id, "engine_unverified")
    _require(bool(_text(proof.get("evidence_id"))), "engine_unverified")
    _require(proof.get("source") == "deployment_window", "engine_unverified")
    window_start = _timestamp(proof.get("from"), "engine_unverified")
    window_end = _timestamp(proof.get("until"), "engine_unverified")
    _require(
        window_start <= started_at and completed_at < window_end,
        "engine_unverified",
    )
    if engine == "2.0":
        # Earlier 2.0 requests did not persist their progress/turn usage
        # context. A deployment audit must prove this run started after
        # the linkage became available. The same audit must identify the
        # prompt behavior: earlier 2.0 deployments did not send inherited
        # author constraints, so their feature vectors are incompatible.
        _require(
            proof.get("feature_contract") == _AGENT_FEATURE_CONTRACT,
            "engine_unverified",
        )
        instrumented_from = _timestamp(
            proof.get("instrumented_from"), "engine_unverified"
        )
        _require(instrumented_from <= started_at, "engine_unverified")
    if engine == "2.0":
        # 2.0's original learning_mode was derived from the listen flag and
        # could mislabel a classroom request as read. Confirm the actual mode
        # of every HTTP request from independent request-payload evidence.
        mode_proof = _mapping(
            candidate.get("request_mode_proof"), "reading_mode_unverified"
        )
        _require(
            mode_proof.get("verified") is True
            and mode_proof.get("source") == "request_payload_trace"
            and _text(mode_proof.get("learning_mode")) == "read"
            and bool(_text(mode_proof.get("evidence_id"))),
            "reading_mode_unverified",
        )
        proven_requests = mode_proof.get("request_ids")
        _require(isinstance(proven_requests, list), "reading_mode_unverified")
        actual_requests = {_text(row.get("request_id")) for row in usage_rows}
        _require(
            "" not in actual_requests
            and actual_requests
            <= {_text(request_id) for request_id in proven_requests},
            "reading_mode_unverified",
        )
    return engine


def _verified_usage_window(
    candidate: Mapping[str, Any],
    course_id: str,
    progress_by_leaf: dict[str, Mapping[str, Any]],
    started_at: datetime,
    completed_at: datetime,
    cutoff: datetime,
) -> None:
    """Require a full unfiltered user/course window, including unlinked calls."""
    proof = _mapping(candidate.get("usage_window_proof"), "usage_window_unverified")
    learner_bid = _text(next(iter(progress_by_leaf.values())).get("user_bid"))
    _require(
        proof.get("verified") is True
        and proof.get("source") == "bill_usage_user_course_window"
        and bool(_text(proof.get("evidence_id")))
        and _text(proof.get("user_bid")) == learner_bid
        and _text(proof.get("course_id")) == course_id
        and proof.get("includes_all_scenes_and_types") is True
        and proof.get("includes_unlinked_rows") is True,
        "usage_window_unverified",
    )
    window_start = _timestamp(proof.get("from"), "usage_window_unverified")
    window_end = _timestamp(proof.get("until"), "usage_window_unverified")
    _require(
        window_start <= started_at and completed_at < window_end <= cutoff,
        "usage_window_unverified",
    )
    rows = _rows(candidate.get("usage_rows"), "usage_window_unverified")
    _require(
        _integer(proof.get("row_count"), "usage_window_unverified") == len(rows),
        "usage_window_unverified",
    )


def _screen_usage(
    candidate: Mapping[str, Any],
    course_id: str,
    progress_by_leaf: dict[str, Mapping[str, Any]],
    started_at: datetime,
    completed_at: datetime,
) -> tuple[list[TokenUsage], list[Mapping[str, Any]]]:
    rows = _rows(candidate.get("usage_rows"), "usage_missing")
    _require(bool(rows), "usage_missing")
    progress_by_id = {
        _text(row["progress_record_bid"]): bid for bid, row in progress_by_leaf.items()
    }
    learner_bid = _text(next(iter(progress_by_leaf.values())).get("user_bid"))
    usage_bids: set[str] = set()
    tokens: list[TokenUsage] = []
    for row in rows:
        usage_bid = _text(row.get("usage_bid"))
        _require(bool(usage_bid) and usage_bid not in usage_bids, "usage_duplicate")
        usage_bids.add(usage_bid)
        _require(_text(row.get("shifu_bid")) == course_id, "usage_link_mismatch")
        _require(_text(row.get("user_bid")) == learner_bid, "usage_link_mismatch")
        progress_bid = _text(row.get("progress_record_bid"))
        _require(
            progress_bid in progress_by_id
            and _text(row.get("outline_item_bid")) == progress_by_id[progress_bid],
            "usage_link_mismatch",
        )
        created_at = _timestamp(row.get("created_at"), "usage_time_invalid")
        _require(started_at <= created_at <= completed_at, "usage_time_invalid")
        _require(
            row.get("usage_type") == _BILL_USAGE_LLM
            and row.get("record_level") == 0
            and row.get("usage_scene") == _BILL_USAGE_PRODUCTION
            and row.get("billable") == 1
            and row.get("status") == 0
            and row.get("deleted") == 0,
            "usage_not_eligible",
        )
        extra = _mapping(row.get("extra"), "usage_metadata_missing")
        _require(extra.get("learning_mode") == "read", "reading_mode_unverified")
        _require(extra.get("usage_source") == "litellm", "usage_tokens_unverified")
        tokens.append(
            TokenUsage(
                input_tokens=_integer(row.get("input"), "usage_tokens_invalid"),
                cached_input_tokens=_integer(
                    row.get("input_cache"), "usage_tokens_invalid"
                ),
                output_tokens=_integer(row.get("output"), "usage_tokens_invalid"),
            )
        )
        _require(tokens[-1].input_tokens > 0, "usage_tokens_invalid")
    return tokens, rows


def _check_generated_blocks(
    candidate: Mapping[str, Any],
    course_id: str,
    progress_by_leaf: dict[str, Mapping[str, Any]],
    usage_rows: list[Mapping[str, Any]],
    *,
    engine: str,
) -> None:
    rows = _rows(candidate.get("generated_blocks"), "blocks_missing")
    progress_by_id = {
        _text(row["progress_record_bid"]): bid for bid, row in progress_by_leaf.items()
    }
    learner_bid = _text(next(iter(progress_by_leaf.values())).get("user_bid"))
    block_by_id: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        block_bid = _text(row.get("generated_block_bid"))
        _require(bool(block_bid) and block_bid not in block_by_id, "blocks_duplicate")
        block_by_id[block_bid] = row
        _require(
            _text(row.get("shifu_bid")) == course_id
            and _text(row.get("user_bid")) == learner_bid,
            "blocks_link_mismatch",
        )
        progress_bid = _text(row.get("progress_record_bid"))
        _require(
            progress_bid in progress_by_id
            and _text(row.get("outline_item_bid")) == progress_by_id[progress_bid],
            "blocks_link_mismatch",
        )
        _require(
            row.get("deleted") == 0 and row.get("status") == 1,
            "blocks_regenerated",
        )
    metered_blocks: set[str] = set()
    agent_metered_blocks: set[str] = set()
    for usage in usage_rows:
        block_bid = _text(usage.get("generated_block_bid"))
        generation_name = _text(
            _mapping(usage.get("extra"), "usage_metadata_missing").get(
                "generation_name"
            )
        )
        if engine == "1.0":
            _require(generation_name != "agent_lesson", "engine_unverified")
        elif generation_name == "agent_lesson":
            _require(bool(block_bid), "usage_block_missing")
            agent_metered_blocks.add(block_bid)
        else:
            _require(
                generation_name.startswith("lesson_ask/") and not block_bid,
                "engine_unverified",
            )
        if block_bid:
            block = block_by_id.get(block_bid)
            _require(block is not None, "usage_block_missing")
            _require(
                _text(block.get("progress_record_bid"))
                == _text(usage.get("progress_record_bid"))
                and _text(block.get("outline_item_bid"))
                == _text(usage.get("outline_item_bid")),
                "usage_block_mismatch",
            )
            metered_blocks.add(block_bid)
    if engine == "2.0":
        turn_blocks_by_leaf: dict[str, set[str]] = {
            bid: set() for bid in progress_by_leaf
        }
        for block_bid, row in block_by_id.items():
            if row.get("type") != _MODEL_CONTENT:
                continue
            _require(
                row.get("role") == 0 and _text(row.get("block_bid")) == "",
                "engine_unverified",
            )
            turn_blocks_by_leaf[_text(row.get("outline_item_bid"))].add(block_bid)
        turn_blocks = set().union(*turn_blocks_by_leaf.values())
        _require(
            all(turn_blocks_by_leaf.values()) and agent_metered_blocks == turn_blocks,
            "turn_usage_incomplete",
        )
    for block_bid, row in block_by_id.items():
        if engine == "1.0" and (
            row.get("role") == _MODEL_TEACHER
            and row.get("type") == _MODEL_CONTENT
            and _text(row.get("generation_prompt"))
        ):
            _require(block_bid in metered_blocks, "usage_block_missing")


def screen_candidate(candidate: Mapping[str, Any]) -> ScreeningResult:
    """Validate one complete learning run and return an anonymous sample."""
    try:
        candidate = _mapping(candidate, "candidate_invalid")
        attestation = _mapping(
            candidate.get("extraction_complete"), "history_unverified"
        )
        _require(
            all(attestation.get(key) is True for key in _COMPLETENESS_KEYS),
            "history_unverified",
        )
        course_id = _text(candidate.get("course_id"))
        language = _text(candidate.get("language"))
        _require(bool(_MACHINE_ID.fullmatch(course_id)), "course_id_invalid")
        course, outline_rows, leaves, published_at, next_at = _snapshot_outline(
            candidate, course_id
        )
        _require(course.get("use_learner_language") == 0, "language_unverified")
        outline_objects = [SimpleNamespace(**row) for row in outline_rows]
        authored_language = detect_authored_language(outline_objects, leaves)
        _require(
            authored_language != "und" and language == authored_language,
            "language_unverified",
        )
        progress, started_at, completed_at = _completion_progress(
            candidate,
            course_id,
            leaves,
            {_text(row.get("outline_item_bid")) for row in outline_rows},
            published_at,
        )
        cutoff = _timestamp(candidate.get("extraction_cutoff"), "cutoff_invalid")
        _require(
            published_at <= started_at <= completed_at < cutoff,
            "snapshot_time_mismatch",
        )
        _require(
            next_at is None or completed_at < next_at, "snapshot_changed_during_study"
        )
        metering_start = _timestamp(
            candidate.get("metering_started_at"), "metering_unverified"
        )
        _require(metering_start <= started_at, "metering_unverified")
        _verified_usage_window(
            candidate, course_id, progress, started_at, completed_at, cutoff
        )
        usage_tokens, usage_rows = _screen_usage(
            candidate, course_id, progress, started_at, completed_at
        )
        engine = _verified_engine(
            candidate, course_id, started_at, completed_at, usage_rows
        )
        _check_generated_blocks(
            candidate, course_id, progress, usage_rows, engine=engine
        )
        features = build_course_completion_credit_features(
            course=SimpleNamespace(**course),
            outline_items=outline_objects,
            visible_leaf_outline_bids=leaves,
            engine=engine,
            language=language,
        ).as_mapping()
        credit_total = reprice_requests_1x(usage_tokens)
        old_raw = candidate.get("old_estimate_credits")
        old_estimate = None
        if old_raw is not None:
            old_estimate = Decimal(str(old_raw))
            _require(
                old_estimate.is_finite() and old_estimate >= 0, "old_estimate_invalid"
            )
        return ScreeningResult(
            sample=CalibrationSample(
                course_id=course_id,
                engine=engine,
                language=language,
                features=features,
                credits=credit_total,
                completed_at=completed_at,
                old_estimate_credits=old_estimate,
            ),
            reason=None,
        )
    except (
        _SampleExclusionError,
        ValueError,
        TypeError,
        KeyError,
        InvalidOperation,
    ) as exc:
        reason = (
            str(exc) if isinstance(exc, _SampleExclusionError) else "invalid_candidate"
        )
        return ScreeningResult(sample=None, reason=reason)


def screen_bundle(
    payload: Mapping[str, Any],
) -> tuple[list[CalibrationSample], dict[str, int]]:
    """Screen an offline fixture without returning learner-level raw fields."""
    payload = _mapping(payload, "bundle_invalid")
    candidates = _rows(payload.get("candidates"), "bundle_invalid")
    samples: list[CalibrationSample] = []
    exclusions: Counter[str] = Counter()
    seen_completions: set[str] = set()
    screened = [screen_candidate(candidate) for candidate in candidates]
    identity_by_candidate = [_candidate_identity(candidate) for candidate in candidates]
    histories_by_learner: dict[tuple[str, str], set[str]] = {}
    for identity in identity_by_candidate:
        if identity is not None:
            learner_key, completion_key = identity
            histories_by_learner.setdefault(learner_key, set()).add(completion_key)
    relearned = {
        key for key, histories in histories_by_learner.items() if len(histories) > 1
    }
    for result, identity in zip(screened, identity_by_candidate, strict=True):
        if result.sample is not None:
            if identity is None:
                exclusions["progress_link_missing"] += 1
                continue
            learner_key, completion_key = identity
            if learner_key in relearned:
                exclusions["cross_candidate_relearned"] += 1
                continue
            if completion_key in seen_completions:
                exclusions["duplicate_candidate"] += 1
                continue
            seen_completions.add(completion_key)
            samples.append(result.sample)
        else:
            exclusions[result.reason or "invalid_candidate"] += 1
    return samples, dict(sorted(exclusions.items()))


def _candidate_identity(
    candidate: Mapping[str, Any],
) -> tuple[tuple[str, str], str] | None:
    """Keep private learner identity in memory, never in screened output."""
    course_id = _text(candidate.get("course_id"))
    progress_rows = candidate.get("progress_rows")
    if not course_id or not isinstance(progress_rows, list) or not progress_rows:
        return None
    if not all(isinstance(row, Mapping) for row in progress_rows):
        return None
    learners = {_text(row.get("user_bid")) for row in progress_rows}
    progress_bids = sorted(
        _text(row.get("progress_record_bid")) for row in progress_rows
    )
    if len(learners) != 1 or "" in learners or "" in progress_bids:
        return None
    learner_key = (course_id, next(iter(learners)))
    completion_key = hashlib.sha256(
        json.dumps([course_id, progress_bids], separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return learner_key, completion_key


def _sample_payload(sample: CalibrationSample) -> dict[str, object]:
    return {
        "course_id": sample.course_id,
        "engine": sample.engine,
        "language": sample.language,
        "features": dict(sample.features),
        "credits": format(sample.credits, "f"),
        "completed_at": sample.completed_at.isoformat().replace("+00:00", "Z"),
        "old_estimate_credits": (
            format(sample.old_estimate_credits, "f")
            if sample.old_estimate_credits is not None
            else None
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Read an offline JSON export and print only screened aggregate samples."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input", type=Path, help="Offline JSON export, never a database URL"
    )
    args = parser.parse_args(argv)
    with args.input.open(encoding="utf-8") as stream:
        payload = json.load(stream)
    samples, exclusions = screen_bundle(payload)
    sys.stdout.write(
        json.dumps(
            {
                "samples": [_sample_payload(sample) for sample in samples],
                "excluded": exclusions,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
