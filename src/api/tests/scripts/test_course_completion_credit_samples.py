"""Conservative screening of offline full-course learning samples."""

from __future__ import annotations

import copy
import json
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from scripts.course_completion_credit_samples import (
    main,
    screen_bundle,
    screen_candidate,
)

if TYPE_CHECKING:
    from pathlib import Path


def _candidate() -> dict:
    return {
        "course_id": "course-a",
        "language": "zh",
        "extraction_complete": {
            "published_history": True,
            "published_rows": True,
            "progress": True,
            "generated_blocks": True,
            "usage": True,
        },
        "extraction_cutoff": "2026-09-10T00:00:00Z",
        "metering_started_at": "2026-08-01T00:00:00Z",
        "snapshot": {
            "published_at": "2026-09-01T00:00:00Z",
            "next_published_at": "2026-09-04T00:00:00Z",
            "course_row": {
                "id": 10,
                "shifu_bid": "course-a",
                "llm_system_prompt": "Teach in Chinese.",
                "use_learner_language": 0,
            },
            "struct": {
                "type": "shifu",
                "id": 10,
                "bid": "course-a",
                "children": [
                    {
                        "type": "outline",
                        "id": 11,
                        "bid": "chapter-a",
                        "children": [
                            {
                                "type": "outline",
                                "id": 12,
                                "bid": "lesson-a",
                                "children": [],
                            },
                            {
                                "type": "outline",
                                "id": 13,
                                "bid": "hidden-lesson",
                                "children": [],
                            },
                        ],
                    }
                ],
            },
            "outline_rows": [
                {
                    "id": 11,
                    "outline_item_bid": "chapter-a",
                    "shifu_bid": "course-a",
                    "parent_bid": "",
                    "hidden": 0,
                    "llm_system_prompt": "",
                    "content": "Chapter introduction.",
                },
                {
                    "id": 12,
                    "outline_item_bid": "lesson-a",
                    "shifu_bid": "course-a",
                    "parent_bid": "chapter-a",
                    "hidden": 0,
                    "llm_system_prompt": "",
                    "content": (
                        "请用通俗易懂的方式解释人工智能的基本概念，并结合实际生活中的例子帮助学习者理解。"
                        "学习者应当能够辨别模型的能力边界，并尝试用自己的话重新说明这个概念。"
                    ),
                },
                {
                    "id": 13,
                    "outline_item_bid": "hidden-lesson",
                    "shifu_bid": "course-a",
                    "parent_bid": "chapter-a",
                    "hidden": 1,
                    "llm_system_prompt": "",
                    "content": "Do not teach this hidden lesson.",
                },
            ],
        },
        "progress_rows": [
            {
                "id": 100,
                "progress_record_bid": "progress-a",
                "shifu_bid": "course-a",
                "outline_item_bid": "lesson-a",
                "user_bid": "private-learner-identifier",
                "status": 603,
                "deleted": 0,
                "created_at": "2026-09-02T09:00:00Z",
                "updated_at": "2026-09-02T10:00:00Z",
            }
        ],
        "generated_blocks": [
            {
                "generated_block_bid": "block-a",
                "shifu_bid": "course-a",
                "user_bid": "private-learner-identifier",
                "progress_record_bid": "progress-a",
                "outline_item_bid": "lesson-a",
                "role": 1,
                "type": 311,
                "generation_prompt": "Private lesson prompt",
                "deleted": 0,
                "status": 1,
            }
        ],
        "usage_rows": [
            {
                "usage_bid": "usage-a",
                "shifu_bid": "course-a",
                "user_bid": "private-learner-identifier",
                "outline_item_bid": "lesson-a",
                "request_id": "request-a",
                "progress_record_bid": "progress-a",
                "generated_block_bid": "block-a",
                "usage_type": 1101,
                "record_level": 0,
                "usage_scene": 1203,
                "billable": 1,
                "status": 0,
                "deleted": 0,
                "input": 10000,
                "input_cache": 2000,
                "output": 5000,
                "created_at": "2026-09-02T09:30:00Z",
                "extra": {
                    "learning_mode": "read",
                    "usage_source": "litellm",
                    "generation_name": "lesson_content",
                },
            }
        ],
        "usage_window_proof": {
            "verified": True,
            "source": "bill_usage_user_course_window",
            "evidence_id": "audited-full-usage-window-a",
            "user_bid": "private-learner-identifier",
            "course_id": "course-a",
            "from": "2026-09-02T09:00:00Z",
            "until": "2026-09-02T10:01:00Z",
            "includes_all_scenes_and_types": True,
            "includes_unlinked_rows": True,
            "row_count": 1,
        },
        "engine_proof": {
            "verified": True,
            "engine": "1.0",
            "course_id": "course-a",
            "evidence_id": "audited-deployment-window-a",
            "source": "deployment_window",
            "from": "2026-09-01T00:00:00Z",
            "until": "2026-09-03T00:00:00Z",
        },
    }


def _agent_candidate() -> dict:
    candidate = _candidate()
    candidate["engine_proof"]["engine"] = "2.0"
    candidate["engine_proof"]["instrumented_from"] = "2026-09-01T00:00:00Z"
    block = candidate["generated_blocks"][0]
    block["role"] = 0
    block["block_bid"] = ""
    block["generation_prompt"] = ""
    candidate["usage_rows"][0]["extra"]["generation_name"] = "agent_lesson"
    candidate["request_mode_proof"] = {
        "verified": True,
        "source": "request_payload_trace",
        "learning_mode": "read",
        "evidence_id": "audited-request-payloads-a",
        "request_ids": ["request-a"],
    }
    return candidate


def test_accepts_exact_historical_snapshot_and_reprices_each_metric() -> None:
    result = screen_candidate(_candidate())

    assert result.reason is None
    assert result.sample is not None
    assert result.sample.course_id == "course-a"
    assert result.sample.credits == Decimal("0.99")
    assert result.sample.features["lesson_count"] == 1
    assert result.sample.features["dynamic_chars_k"] > 0


def test_accepts_post_instrumentation_agent_turn_and_read_mode_proof() -> None:
    result = screen_candidate(_agent_candidate())

    assert result.reason is None
    assert result.sample is not None
    assert result.sample.engine == "2.0"
    assert result.sample.credits == Decimal("0.99")


def test_agent_follow_up_cost_needs_independent_read_mode_proof() -> None:
    candidate = _agent_candidate()
    follow_up = copy.deepcopy(candidate["usage_rows"][0])
    follow_up["usage_bid"] = "usage-follow-up"
    follow_up["request_id"] = "request-follow-up"
    follow_up["generated_block_bid"] = ""
    follow_up["extra"]["generation_name"] = "lesson_ask/user_follow_ask/title"
    candidate["usage_rows"].append(follow_up)
    candidate["usage_window_proof"]["row_count"] = 2

    assert screen_candidate(candidate).reason == "reading_mode_unverified"
    candidate["request_mode_proof"]["request_ids"].append("request-follow-up")
    result = screen_candidate(candidate)
    assert result.sample is not None
    assert result.sample.credits == Decimal("1.98")


def test_agent_sample_excludes_unproved_instrumentation_or_mode() -> None:
    candidate = _agent_candidate()
    candidate["engine_proof"].pop("instrumented_from")
    assert screen_candidate(candidate).reason == "engine_unverified"

    candidate = _agent_candidate()
    candidate.pop("request_mode_proof")
    assert screen_candidate(candidate).reason == "reading_mode_unverified"

    candidate = _agent_candidate()
    candidate["engine_proof"]["source"] = "per_request_trace"
    assert screen_candidate(candidate).reason == "engine_unverified"


def test_agent_turns_require_exact_request_to_turn_block_linkage() -> None:
    candidate = _agent_candidate()
    candidate["usage_rows"][0]["generated_block_bid"] = ""
    assert screen_candidate(candidate).reason == "usage_block_missing"

    candidate = _agent_candidate()
    extra_turn = copy.deepcopy(candidate["generated_blocks"][0])
    extra_turn["generated_block_bid"] = "unmetered-turn"
    candidate["generated_blocks"].append(extra_turn)
    assert screen_candidate(candidate).reason == "turn_usage_incomplete"

    candidate = _agent_candidate()
    candidate["generated_blocks"][0]["role"] = 1
    assert screen_candidate(candidate).reason == "engine_unverified"


def test_usage_block_must_belong_to_same_completed_lesson() -> None:
    candidate = _candidate()
    second_outline = copy.deepcopy(candidate["snapshot"]["outline_rows"][1])
    second_outline["id"] = 14
    second_outline["outline_item_bid"] = "lesson-b"
    candidate["snapshot"]["outline_rows"].append(second_outline)
    candidate["snapshot"]["struct"]["children"][0]["children"].append(
        {"type": "outline", "id": 14, "bid": "lesson-b", "children": []}
    )
    second_progress = copy.deepcopy(candidate["progress_rows"][0])
    second_progress["id"] = 101
    second_progress["outline_item_bid"] = "lesson-b"
    second_progress["progress_record_bid"] = "progress-b"
    candidate["progress_rows"].append(second_progress)
    second_block = copy.deepcopy(candidate["generated_blocks"][0])
    second_block["generated_block_bid"] = "block-b"
    second_block["outline_item_bid"] = "lesson-b"
    second_block["progress_record_bid"] = "progress-b"
    candidate["generated_blocks"].append(second_block)
    second_usage = copy.deepcopy(candidate["usage_rows"][0])
    second_usage["usage_bid"] = "usage-b"
    second_usage["outline_item_bid"] = "lesson-b"
    second_usage["progress_record_bid"] = "progress-b"
    second_usage["generated_block_bid"] = "block-b"
    candidate["usage_rows"].append(second_usage)
    candidate["usage_window_proof"]["row_count"] = 2
    candidate["usage_rows"][0]["generated_block_bid"] = "block-b"

    assert screen_candidate(candidate).reason == "usage_block_mismatch"


def test_usage_and_blocks_must_match_private_learner_identity() -> None:
    candidate = _candidate()
    candidate["usage_rows"][0]["user_bid"] = "different-learner"
    assert screen_candidate(candidate).reason == "usage_link_mismatch"

    candidate = _candidate()
    candidate["generated_blocks"][0]["user_bid"] = "different-learner"
    assert screen_candidate(candidate).reason == "blocks_link_mismatch"


def test_runtime_language_course_or_mismatched_language_is_excluded() -> None:
    candidate = _candidate()
    candidate["snapshot"]["course_row"]["use_learner_language"] = 1
    assert screen_candidate(candidate).reason == "language_unverified"

    candidate = _candidate()
    candidate["language"] = "en"
    assert screen_candidate(candidate).reason == "language_unverified"


@pytest.mark.parametrize(
    ("field", "replacement", "reason"),
    [
        ("engine_proof", None, "engine_unverified"),
        ("extraction_complete", {}, "history_unverified"),
        ("metering_started_at", "2026-09-03T00:00:00Z", "metering_unverified"),
    ],
)
def test_missing_external_proof_excludes_sample(
    field: str, replacement: object, reason: str
) -> None:
    candidate = _candidate()
    candidate[field] = replacement

    assert screen_candidate(candidate).reason == reason


def test_engine_trace_alone_and_partial_user_course_usage_window_are_rejected() -> None:
    candidate = _candidate()
    candidate["engine_proof"]["source"] = "per_request_trace"
    candidate["engine_proof"]["usage_bids"] = ["usage-a"]
    assert screen_candidate(candidate).reason == "engine_unverified"

    candidate = _candidate()
    candidate["usage_window_proof"]["includes_unlinked_rows"] = False
    assert screen_candidate(candidate).reason == "usage_window_unverified"

    candidate = _candidate()
    candidate["usage_window_proof"]["row_count"] = 2
    assert screen_candidate(candidate).reason == "usage_window_unverified"

    candidate = _candidate()
    candidate.pop("usage_window_proof")
    assert screen_candidate(candidate).reason == "usage_window_unverified"


def test_republication_during_learning_excludes_historical_sample() -> None:
    candidate = _candidate()
    candidate["snapshot"]["next_published_at"] = "2026-09-02T09:45:00Z"

    assert screen_candidate(candidate).reason == "snapshot_changed_during_study"


def test_wrong_historical_outline_row_is_rejected() -> None:
    candidate = _candidate()
    candidate["snapshot"]["outline_rows"][1]["id"] = 99

    assert screen_candidate(candidate).reason == "snapshot_outline_missing"


def test_legacy_block_children_fail_closed_at_runtime_leaf_boundary() -> None:
    candidate = _candidate()
    candidate["snapshot"]["struct"]["children"][0]["children"][0]["children"].append(
        {"type": "block", "id": 999, "bid": "legacy-block", "children": []}
    )

    # Runtime regards a node with children as a chapter; an outline-only walk
    # would misclassify this legacy shape as a teachable leaf.
    assert screen_candidate(candidate).reason == "snapshot_structure_invalid"


def test_reset_or_relearning_is_excluded() -> None:
    candidate = _candidate()
    previous = copy.deepcopy(candidate["progress_rows"][0])
    previous["id"] = 99
    previous["status"] = 608
    candidate["progress_rows"].append(previous)

    assert screen_candidate(candidate).reason == "progress_relearned"


def test_prior_publication_progress_is_excluded() -> None:
    candidate = _candidate()
    candidate["progress_rows"][0]["created_at"] = "2026-08-31T09:00:00Z"

    assert screen_candidate(candidate).reason == "progress_version_mismatch"


def test_missing_model_usage_for_generated_block_is_excluded() -> None:
    candidate = _candidate()
    candidate["usage_rows"][0]["generated_block_bid"] = ""

    assert screen_candidate(candidate).reason == "usage_block_missing"


def test_follow_up_must_explicitly_record_reading_mode() -> None:
    candidate = _candidate()
    follow_up = copy.deepcopy(candidate["usage_rows"][0])
    follow_up["usage_bid"] = "usage-follow-up"
    follow_up["generated_block_bid"] = ""
    follow_up["extra"]["generation_name"] = "lesson_ask/user_follow_ask"
    follow_up["extra"].pop("learning_mode")
    candidate["usage_rows"].append(follow_up)
    candidate["usage_window_proof"]["row_count"] = 2

    assert screen_candidate(candidate).reason == "reading_mode_unverified"


def test_verified_reading_follow_up_is_included_in_completion_cost() -> None:
    candidate = _candidate()
    follow_up = copy.deepcopy(candidate["usage_rows"][0])
    follow_up["usage_bid"] = "usage-follow-up"
    follow_up["generated_block_bid"] = ""
    follow_up["extra"]["generation_name"] = "lesson_ask/user_follow_ask"
    candidate["usage_rows"].append(follow_up)
    candidate["usage_window_proof"]["row_count"] = 2

    result = screen_candidate(candidate)

    assert result.sample is not None
    assert result.sample.credits == Decimal("1.98")


def test_repeated_candidate_export_counts_only_once() -> None:
    original = _candidate()
    repeated = copy.deepcopy(original)
    repeated["usage_rows"][0]["input"] = 20000

    samples, exclusions = screen_bundle({"candidates": [original, repeated]})

    assert len(samples) == 1
    assert samples[0].credits == Decimal("0.99")
    assert exclusions == {"duplicate_candidate": 1}


def test_same_learner_relearning_in_separate_candidates_excludes_both() -> None:
    first = _candidate()
    second = copy.deepcopy(first)
    second["progress_rows"][0]["progress_record_bid"] = "progress-second"
    second["generated_blocks"][0]["progress_record_bid"] = "progress-second"
    second["usage_rows"][0]["progress_record_bid"] = "progress-second"
    second["usage_rows"][0]["usage_bid"] = "usage-second"

    samples, exclusions = screen_bundle({"candidates": [first, second]})

    assert samples == []
    assert exclusions == {"cross_candidate_relearned": 2}


def test_different_learners_of_same_course_are_separate_samples() -> None:
    first = _candidate()
    second = copy.deepcopy(first)
    second["progress_rows"][0]["user_bid"] = "private-other-learner"
    second["progress_rows"][0]["progress_record_bid"] = "progress-other"
    second["generated_blocks"][0]["user_bid"] = "private-other-learner"
    second["generated_blocks"][0]["progress_record_bid"] = "progress-other"
    second["usage_rows"][0]["user_bid"] = "private-other-learner"
    second["usage_rows"][0]["progress_record_bid"] = "progress-other"
    second["usage_rows"][0]["usage_bid"] = "usage-other"
    second["usage_window_proof"]["user_bid"] = "private-other-learner"

    samples, exclusions = screen_bundle({"candidates": [first, second]})

    assert len(samples) == 2
    assert exclusions == {}


@pytest.mark.parametrize(
    ("field", "value"),
    [("usage_type", 1102), ("usage_scene", 1202), ("billable", 0), ("status", 1)],
)
def test_ineligible_usage_excludes_whole_completion(field: str, value: int) -> None:
    candidate = _candidate()
    candidate["usage_rows"][0][field] = value

    assert screen_candidate(candidate).reason == "usage_not_eligible"


def test_offline_cli_emits_only_aggregate_data(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_path = tmp_path / "private-export.json"
    input_path.write_text(json.dumps({"candidates": [_candidate()]}), encoding="utf-8")

    assert main([str(input_path)]) == 0
    output = capsys.readouterr().out
    data = json.loads(output)
    assert len(data["samples"]) == 1
    assert data["samples"][0]["credits"] == "0.99"
    assert "private-learner-identifier" not in output
    assert "Private lesson prompt" not in output
    assert "请用通俗易懂的方式解释人工智能" not in output
    assert "progress-a" not in output
    assert "usage-a" not in output
