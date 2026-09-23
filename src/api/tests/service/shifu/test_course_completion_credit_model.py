"""Offline calibration and conservative runtime predictions."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from flaskr.service.shifu.admin_operations.course_completion_credit_model import (
    FEATURE_NAMES,
    CalibrationSample,
    CalibrationSolverError,
    TokenUsage,
    _artifact_checksum,
    _fit_nonnegative_quantile,
    _validation_splits,
    estimate_course_credits,
    fit_calibration_groups,
    reprice_requests_1x,
)


def _features(*, lessons: float = 2, dynamic: float = 3) -> dict[str, float]:
    values = dict.fromkeys(FEATURE_NAMES, 0.0)
    values["lesson_count"] = lessons
    values["dynamic_chars_k"] = dynamic
    return values


def _artifact() -> dict:
    coefficients_p50 = [0.0] * len(FEATURE_NAMES)
    coefficients_p80 = [0.0] * len(FEATURE_NAMES)
    coefficients_p50[0] = 2.0
    coefficients_p80[0] = 3.0
    artifact = {
        "schema_version": 1,
        "version": "2026-09-23-test",
        "rate_credits_per_token": "0.000066667",
        "feature_names": list(FEATURE_NAMES),
        "method": "nonnegative_weighted_quantile_regression",
        "groups": {
            "2.0|zh": {
                "engine": "2.0",
                "language": "zh",
                "sample_count": 100,
                "course_count": 10,
                "training_window_start": "2026-01-01T00:00:00+00:00",
                "training_window_end": "2026-08-01T00:00:00+00:00",
                "coefficients_p50": coefficients_p50,
                "coefficients_p80": coefficients_p80,
                "feature_bounds": [[0.0, 10.0] for _ in FEATURE_NAMES],
                "validation": {"p50_wape": 0.25, "p80_coverage": 0.8},
            }
        },
        "rejected_groups": {},
    }
    artifact["sha256"] = _artifact_checksum(artifact)
    return artifact


def test_repricing_rounds_each_request_component_and_rejects_bad_cache() -> None:
    assert reprice_requests_1x([TokenUsage(150, 75, 75)]) == Decimal("0.03")
    assert reprice_requests_1x(
        [{"input_tokens": 150, "cached_input_tokens": 75, "output_tokens": 75}]
    ) == Decimal("0.03")
    with pytest.raises(ValueError, match="exceed"):
        reprice_requests_1x([TokenUsage(74, 75, 0)])
    with pytest.raises(ValueError, match="integers"):
        reprice_requests_1x([TokenUsage(1, 0, -1)])


def test_weighted_quantile_solver_respects_nonnegative_coefficients() -> None:
    rows = [(tuple([1.0] + [0.0] * 8), float(index), 1.0) for index in range(1, 101)]
    assert 50.0 <= _fit_nonnegative_quantile(rows, 0.5)[0] <= 51.0
    assert 80.0 <= _fit_nonnegative_quantile(rows, 0.8)[0] <= 81.0
    negatives = [(tuple([1.0] + [0.0] * 8), -1.0, 1.0)]
    assert _fit_nonnegative_quantile(negatives, 0.5)[0] == 0.0


def test_quantile_solver_finds_joint_optimum_missed_by_coordinate_updates() -> None:
    observations = [(0, 6, 1), (6, 2, 1), (6, 6, 4), (1, 3, 1), (3, 4, 2)]
    rows = [
        ((float(first), float(second), *([0.0] * 7)), float(target), 1.0)
        for first, second, target in observations
    ]
    coefficients = _fit_nonnegative_quantile(rows, 0.5)
    absolute_error = sum(
        abs(target - first * coefficients[0] - second * coefficients[1])
        for first, second, target in observations
    )
    assert all(coefficient >= 0 for coefficient in coefficients)
    assert absolute_error == pytest.approx(2.388888888888889)


def test_solver_failure_prevents_fit(monkeypatch: pytest.MonkeyPatch) -> None:
    import scipy.optimize

    monkeypatch.setattr(
        scipy.optimize,
        "linprog",
        lambda *_args, **_kwargs: SimpleNamespace(success=False, x=None, fun=None),
    )
    rows = [(tuple([1.0] + [0.0] * 8), 1.0, 1.0)]
    with pytest.raises(CalibrationSolverError, match="did not converge"):
        _fit_nonnegative_quantile(rows, 0.5)


def test_grouped_validation_never_trains_on_held_out_course() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    samples = [
        CalibrationSample(
            course_id=f"course-{course}",
            engine="2.0",
            language="zh",
            features=_features(),
            credits=Decimal(10),
            completed_at=start + timedelta(days=course, hours=run),
        )
        for course in range(10)
        for run in range(10)
    ]
    splits = _validation_splits(samples)
    assert {sample.course_id for _, _, valid in splits for sample in valid} == {
        f"course-{course}" for course in range(10)
    }
    assert {sample.course_id for sample in splits[-1][2]} == {
        "course-8",
        "course-9",
    }
    for _, train, valid in splits:
        assert {sample.course_id for sample in train}.isdisjoint(
            {sample.course_id for sample in valid}
        )


def test_fit_rejects_insufficient_group_without_publishing_coefficients() -> None:
    sample = CalibrationSample(
        course_id="course-1",
        engine="2.0",
        language="zh",
        features=_features(),
        credits=Decimal(10),
        completed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    artifact = fit_calibration_groups([sample], version="2026-09-23")
    assert artifact["groups"] == {}
    assert artifact["rejected_groups"]["2.0|zh"]["reason"] == "insufficient_data"
    assert artifact["sha256"] == _artifact_checksum(artifact)


def test_fit_publishes_only_group_with_course_held_out_metrics() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    samples = []
    for course in range(10):
        for run in range(10):
            features = _features(
                lessons=1 + course % 3, dynamic=1 + course * 0.3 + run * 0.1
            )
            features["static_chars_k"] = course * 0.2
            cost = (
                2 * features["lesson_count"]
                + 3 * features["dynamic_chars_k"]
                + run * 0.1
            )
            samples.append(
                CalibrationSample(
                    course_id=f"course-{course}",
                    engine="2.0",
                    language="zh",
                    features=features,
                    credits=Decimal(str(cost)),
                    completed_at=start + timedelta(days=course, hours=run),
                    old_estimate_credits=Decimal(10),
                )
            )
    artifact = fit_calibration_groups(samples, version="synthetic-1")
    group = artifact["groups"]["2.0|zh"]
    assert group["sample_count"] == 100
    assert group["course_count"] == 10
    assert group["validation"]["p50_wape"] <= 0.30
    assert 0.75 <= group["validation"]["p80_coverage"] <= 0.85
    assert group["validation"]["constant_chars_wape"] is not None
    assert group["validation"]["legacy_wape"] is not None
    assert group["validation"]["splits"][-1]["kind"] == "recent_course_holdout"


def test_runtime_uses_only_matching_validated_group_and_feature_range(
    tmp_path: Path,
) -> None:
    path = tmp_path / "calibration.json"
    absent = estimate_course_credits(
        _features(), engine="2.0", language="zh", artifact_path=path
    )
    assert absent.status == "uncalibrated"
    assert absent.reason == "artifact_missing"
    assert absent.estimated_credits is None

    artifact = _artifact()
    path.write_text(json.dumps(artifact), encoding="utf-8")
    prediction = estimate_course_credits(
        _features(), engine="2.0", language="zh", artifact_path=path
    )
    assert prediction.status == "calibrated"
    assert prediction.estimated_credits == Decimal("4.00")
    assert prediction.recommended_credits == Decimal("6.00")
    assert prediction.calibration_version == "2026-09-23-test"
    assert (
        estimate_course_credits(
            _features(), engine="1.0", language="zh", artifact_path=path
        ).reason
        == "group_unavailable"
    )
    assert (
        estimate_course_credits(
            _features(lessons=100), engine="2.0", language="zh", artifact_path=path
        ).reason
        == "outside_calibration_range"
    )


def test_runtime_never_extrapolates_zero_or_tiny_feature_range(tmp_path: Path) -> None:
    path = tmp_path / "calibration.json"
    artifact = _artifact()
    artifact["groups"]["2.0|zh"]["feature_bounds"][1] = [0.0, 0.0]
    artifact["groups"]["2.0|zh"]["feature_bounds"][2] = [0.0, 0.01]
    artifact["sha256"] = _artifact_checksum(artifact)
    path.write_text(json.dumps(artifact), encoding="utf-8")
    zero_only = _features(dynamic=0.01)
    assert (
        estimate_course_credits(
            zero_only, engine="2.0", language="zh", artifact_path=path
        ).reason
        == "outside_calibration_range"
    )
    tiny = _features(dynamic=0)
    tiny["static_chars_k"] = 0.20
    assert (
        estimate_course_credits(
            tiny, engine="2.0", language="zh", artifact_path=path
        ).reason
        == "outside_calibration_range"
    )


def test_runtime_rejects_tampering_and_metrics_outside_gate(tmp_path: Path) -> None:
    path = tmp_path / "calibration.json"
    artifact = _artifact()
    artifact["groups"]["2.0|zh"]["coefficients_p50"][0] = 100.0
    path.write_text(json.dumps(artifact), encoding="utf-8")
    assert (
        estimate_course_credits(
            _features(), engine="2.0", language="zh", artifact_path=path
        ).reason
        == "invalid_artifact"
    )
    artifact["sha256"] = _artifact_checksum(artifact)
    artifact["groups"]["2.0|zh"]["validation"]["p80_coverage"] = 0.5
    artifact["sha256"] = _artifact_checksum(artifact)
    path.write_text(json.dumps(artifact), encoding="utf-8")
    assert (
        estimate_course_credits(
            _features(), engine="2.0", language="zh", artifact_path=path
        ).reason
        == "invalid_artifact"
    )


@pytest.mark.parametrize("invalid_json", ["[]", '{"value": NaN}'])
def test_runtime_rejects_malformed_json_values(
    tmp_path: Path, invalid_json: str
) -> None:
    path = tmp_path / "calibration.json"
    path.write_text(invalid_json, encoding="utf-8")
    prediction = estimate_course_credits(
        _features(), engine="2.0", language="zh", artifact_path=path
    )
    assert prediction.reason == "invalid_artifact"
    assert prediction.estimated_credits is None
