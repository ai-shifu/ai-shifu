"""Offline calibration and read-only prediction for full-course 1x credit use.

The training input is a *verified complete learning run*. Its caller owns
published-version matching, visible-lesson completion, reading-mode filtering,
and joining every billable request. This module reprices those requests and
fits whole-course predictions; the request path only loads a reviewed artifact.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

FEATURE_NAMES = (
    "lesson_count",
    "dynamic_chars_k",
    "static_chars_k",
    "system_chars_k",
    "generated_block_count",
    "interaction_count",
    "char_square_k2",
    "chars_system_k2",
    "chars_blocks_k",
)
REFERENCE_RATE = Decimal("0.000066667")
SCHEMA_VERSION = 1
MIN_SAMPLES = 100
MIN_COURSES = 10
MAX_P50_WAPE = 0.30
MIN_P80_COVERAGE = 0.75
MAX_P80_COVERAGE = 0.85
FEATURE_BOUND_MARGIN = 0.20
DEFAULT_ARTIFACT_PATH = Path(__file__).with_name(
    "course_completion_credit_calibration.json"
)
_CENT = Decimal("0.01")
_NON_INTEGER_COUNTS = "Token counts must be nonnegative integers"
_INVALID_CACHE_COUNT = "Cached input cannot exceed total input"
_INVALID_FEATURE = "Invalid feature"
_NO_VISIBLE_LESSON = "A course needs at least one visible lesson"
_INVALID_QUANTILE_FIT = "Quantile fit needs rows and a valid quantile"
_MISSING_VERSION = "A calibration version is required"
_INVALID_SAMPLE_COURSE = "Each sample needs a course and supported engine"
_INVALID_SAMPLE_TIME = "Each sample needs a language and aware completion time"
_INVALID_SAMPLE_CREDITS = "Each sample needs positive finite repriced credits"
_SOLVER_UNAVAILABLE = "Install calibration dependencies before fitting"
_SOLVER_FAILED = "Calibration linear program did not converge"


@dataclass(frozen=True)
class TokenUsage:
    """Request-level token counts; cached input is a subset of total input."""

    input_tokens: int
    cached_input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class CalibrationSample:
    """One verified complete reading-mode run at its published course version."""

    course_id: str
    engine: str
    language: str
    features: Mapping[str, float]
    credits: Decimal
    completed_at: datetime
    old_estimate_credits: Decimal | None = None


@dataclass(frozen=True)
class CourseCreditPrediction:
    """Calibrated whole-course credit values or an explicit unavailable reason."""

    status: str
    estimated_credits: Decimal | None
    recommended_credits: Decimal | None
    calibration_version: str | None
    reason: str | None = None


class CalibrationSolverError(RuntimeError):
    """Offline fit failed, so no calibration artifact may be published."""


def _half_up(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def reprice_requests_1x(
    requests: Iterable[TokenUsage | Mapping[str, int]],
) -> Decimal:
    """Sum request-level charges with each metric rounded to two decimals."""
    total = Decimal(0)
    for request in requests:
        if isinstance(request, Mapping):
            usage = TokenUsage(
                input_tokens=request["input_tokens"],
                cached_input_tokens=request["cached_input_tokens"],
                output_tokens=request["output_tokens"],
            )
        else:
            usage = request
        counts = (
            usage.input_tokens,
            usage.cached_input_tokens,
            usage.output_tokens,
        )
        if any(type(count) is not int or count < 0 for count in counts):
            raise ValueError(_NON_INTEGER_COUNTS)
        if usage.cached_input_tokens > usage.input_tokens:
            raise ValueError(_INVALID_CACHE_COUNT)
        for count in (
            usage.input_tokens - usage.cached_input_tokens,
            usage.cached_input_tokens,
            usage.output_tokens,
        ):
            total += _half_up(Decimal(count) * REFERENCE_RATE)
    return total


def _feature_vector(features: Mapping[str, float]) -> tuple[float, ...]:
    values: list[float] = []
    for name in FEATURE_NAMES:
        value = features[name]
        if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
            raise TypeError(_INVALID_FEATURE)
        number = float(value)
        if not math.isfinite(number) or number < 0:
            raise ValueError(_INVALID_FEATURE)
        values.append(number)
    if values[0] <= 0:
        raise ValueError(_NO_VISIBLE_LESSON)
    return tuple(values)


def _weighted_quantile(points: Iterable[tuple[float, float]], quantile: float) -> float:
    ordered = sorted((value, weight) for value, weight in points if weight > 0)
    if not ordered:
        return 0.0
    total_weight = sum(weight for _, weight in ordered)
    target = quantile * total_weight
    accumulated = 0.0
    for value, weight in ordered:
        accumulated += weight
        if accumulated >= target:
            return value
    return ordered[-1][0]


def _fit_nonnegative_quantile(
    rows: Sequence[tuple[tuple[float, ...], float, float]], quantile: float
) -> list[float]:
    """Solve weighted pinball loss exactly as a linear program, offline only.

    For each observation, nonnegative ``positive`` and ``negative`` residuals
    satisfy ``X beta + positive - negative = y``. HiGHS minimizes
    ``tau * weight * positive + (1-tau) * weight * negative`` while every
    coefficient remains nonnegative. Import SciPy here so serving never loads it.
    """
    if not 0 < quantile < 1 or not rows:
        raise ValueError(_INVALID_QUANTILE_FIT)
    try:
        from scipy.optimize import linprog
        from scipy.sparse import coo_matrix
    except ImportError as exc:
        raise CalibrationSolverError(_SOLVER_UNAVAILABLE) from exc

    feature_count = len(FEATURE_NAMES)
    sample_count = len(rows)
    row_indices: list[int] = []
    column_indices: list[int] = []
    entries: list[float] = []
    targets = []
    weights = []
    for index, (vector, target, weight) in enumerate(rows):
        if (
            len(vector) != feature_count
            or not math.isfinite(target)
            or not math.isfinite(weight)
            or weight <= 0
            or any(not math.isfinite(value) or value < 0 for value in vector)
        ):
            raise ValueError(_INVALID_QUANTILE_FIT)
        for feature_index, value in enumerate(vector):
            if value:
                row_indices.append(index)
                column_indices.append(feature_index)
                entries.append(value)
        row_indices.extend((index, index))
        column_indices.extend(
            (feature_count + index, feature_count + sample_count + index)
        )
        entries.extend((1.0, -1.0))
        targets.append(target)
        weights.append(weight)
    equality = coo_matrix(
        (entries, (row_indices, column_indices)),
        shape=(sample_count, feature_count + 2 * sample_count),
    ).tocsr()
    objective = (
        [0.0] * feature_count
        + [quantile * weight for weight in weights]
        + [(1 - quantile) * weight for weight in weights]
    )
    solution = linprog(
        objective,
        A_eq=equality,
        b_eq=targets,
        bounds=(0, None),
        method="highs",
    )
    if (
        not solution.success
        or solution.x is None
        or len(solution.x) != feature_count + 2 * sample_count
        or not math.isfinite(solution.fun)
    ):
        raise CalibrationSolverError(_SOLVER_FAILED)
    coefficients = [float(value) for value in solution.x[:feature_count]]
    if any(not math.isfinite(value) or value < -1e-8 for value in coefficients):
        raise CalibrationSolverError(_SOLVER_FAILED)
    return [max(0.0, value) for value in coefficients]


def _dot(coefficients: Sequence[float], vector: Sequence[float]) -> float:
    return sum(
        coefficient * feature
        for coefficient, feature in zip(coefficients, vector, strict=True)
    )


def _course_weights(samples: Sequence[CalibrationSample]) -> dict[str, float]:
    counts: dict[str, int] = {}
    for sample in samples:
        counts[sample.course_id] = counts.get(sample.course_id, 0) + 1
    return {course_id: 1.0 / count for course_id, count in counts.items()}


def _fit_samples(samples: Sequence[CalibrationSample], quantile: float) -> list[float]:
    course_weights = _course_weights(samples)
    rows = [
        (
            _feature_vector(sample.features),
            float(sample.credits),
            course_weights[sample.course_id],
        )
        for sample in samples
    ]
    return _fit_nonnegative_quantile(rows, quantile)


def _fit_constant_chars(samples: Sequence[CalibrationSample]) -> float:
    weights = _course_weights(samples)
    return max(
        0.0,
        _weighted_quantile(
            (
                (float(sample.credits) / chars, weights[sample.course_id] * chars)
                for sample in samples
                if (
                    chars := sum(
                        _feature_vector(sample.features)[index] for index in (1, 2, 3)
                    )
                )
                > 0
            ),
            0.5,
        ),
    )


def _validation_splits(
    samples: Sequence[CalibrationSample],
) -> list[tuple[str, list[CalibrationSample], list[CalibrationSample]]]:
    """Hold whole courses out in folds plus a set selected by recent completion."""
    latest_by_course: dict[str, datetime] = {}
    for sample in samples:
        latest = latest_by_course.get(sample.course_id)
        if latest is None or sample.completed_at > latest:
            latest_by_course[sample.course_id] = sample.completed_at
    ordered = sorted(latest_by_course, key=lambda key: (latest_by_course[key], key))
    if len(ordered) < 3:
        return []
    holdout_count = max(1, math.ceil(len(ordered) * 0.2))
    historical_ids = ordered[:-holdout_count]
    recent_ids = set(ordered[-holdout_count:])
    fold_count = min(5, len(historical_ids))
    splits = []
    for fold in range(fold_count):
        valid_ids = set(historical_ids[fold::fold_count])
        train_ids = set(historical_ids) - valid_ids
        if not train_ids:
            continue
        splits.append(
            (
                "grouped_cv",
                [sample for sample in samples if sample.course_id in train_ids],
                [sample for sample in samples if sample.course_id in valid_ids],
            )
        )
    splits.append(
        (
            "recent_course_holdout",
            [sample for sample in samples if sample.course_id in historical_ids],
            [sample for sample in samples if sample.course_id in recent_ids],
        )
    )
    return splits


def _score_predictions(
    rows: Sequence[tuple[str, float, float, float, float | None, float]],
) -> dict[str, float | None]:
    """Rows are (course, actual, p50, p80, legacy, constant baseline)."""
    counts: dict[str, int] = {}
    for course_id, *_ in rows:
        counts[course_id] = counts.get(course_id, 0) + 1
    weighted_actual = weighted_error = coverage = constant_error = 0.0
    legacy_actual = legacy_error = 0.0
    course_count = len(counts)
    for course_id, actual, p50, p80, legacy, constant in rows:
        weight = 1.0 / (course_count * counts[course_id])
        weighted_actual += weight * actual
        weighted_error += weight * abs(actual - p50)
        constant_error += weight * abs(actual - constant)
        coverage += weight * (p80 >= actual)
        if legacy is not None:
            legacy_actual += weight * actual
            legacy_error += weight * abs(actual - legacy)
    return {
        "p50_wape": weighted_error / weighted_actual if weighted_actual else None,
        "p80_coverage": coverage,
        "constant_chars_wape": (
            constant_error / weighted_actual if weighted_actual else None
        ),
        "legacy_wape": legacy_error / legacy_actual if legacy_actual else None,
    }


def _evaluate_group(samples: Sequence[CalibrationSample]) -> dict[str, Any]:
    predictions: list[tuple[str, float, float, float, float | None, float]] = []
    split_reports = []
    for kind, train, valid in _validation_splits(samples):
        p50 = _fit_samples(train, 0.5)
        p80 = _fit_samples(train, 0.8)
        constant = _fit_constant_chars(train)
        split_rows = []
        for sample in valid:
            vector = _feature_vector(sample.features)
            chars = sum(vector[index] for index in (1, 2, 3))
            split_rows.append(
                (
                    sample.course_id,
                    float(sample.credits),
                    _dot(p50, vector),
                    max(_dot(p50, vector), _dot(p80, vector)),
                    (
                        float(sample.old_estimate_credits)
                        if sample.old_estimate_credits is not None
                        else None
                    ),
                    constant * chars,
                )
            )
        predictions.extend(split_rows)
        split_reports.append(
            {
                "kind": kind,
                "train_course_count": len({row.course_id for row in train}),
                "valid_course_count": len({row.course_id for row in valid}),
                "valid_sample_count": len(valid),
                **_score_predictions(split_rows),
            }
        )
    return {**_score_predictions(predictions), "splits": split_reports}


def _artifact_checksum(artifact: Mapping[str, Any]) -> str:
    unsigned = {key: value for key, value in artifact.items() if key != "sha256"}
    canonical = json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def fit_calibration_groups(
    samples: Iterable[CalibrationSample], *, version: str
) -> dict[str, Any]:
    """Fit offline and return a sealed artifact; only passing groups are usable.

    The caller must build samples from historical published snapshots and fully
    linked request-level metering. This function does not query live data or
    alter billing rates. Rejected groups remain in ``rejected_groups`` so data
    gaps and failed holdout checks are inspectable.
    """
    if not version or not version.strip():
        raise ValueError(_MISSING_VERSION)
    grouped: dict[tuple[str, str], list[CalibrationSample]] = {}
    for sample in samples:
        if not sample.course_id or sample.engine not in {"1.0", "2.0"}:
            raise ValueError(_INVALID_SAMPLE_COURSE)
        if not sample.language or sample.completed_at.tzinfo is None:
            raise ValueError(_INVALID_SAMPLE_TIME)
        if not sample.credits.is_finite() or sample.credits <= 0:
            raise ValueError(_INVALID_SAMPLE_CREDITS)
        _feature_vector(sample.features)
        grouped.setdefault((sample.engine, sample.language), []).append(sample)
    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "version": version.strip(),
        "rate_credits_per_token": str(REFERENCE_RATE),
        "feature_names": list(FEATURE_NAMES),
        "method": "nonnegative_weighted_quantile_regression",
        "groups": {},
        "rejected_groups": {},
    }
    for (engine, language), group in sorted(grouped.items()):
        key = f"{engine}|{language}"
        course_count = len({sample.course_id for sample in group})
        if len(group) < MIN_SAMPLES or course_count < MIN_COURSES:
            artifact["rejected_groups"][key] = {
                "reason": "insufficient_data",
                "sample_count": len(group),
                "course_count": course_count,
            }
            continue
        validation = _evaluate_group(group)
        wape = validation["p50_wape"]
        coverage = validation["p80_coverage"]
        if (
            wape is None
            or wape > MAX_P50_WAPE
            or not MIN_P80_COVERAGE <= coverage <= MAX_P80_COVERAGE
        ):
            artifact["rejected_groups"][key] = {
                "reason": "validation_failed",
                "sample_count": len(group),
                "course_count": course_count,
                "validation": validation,
            }
            continue
        vectors = [_feature_vector(sample.features) for sample in group]
        artifact["groups"][key] = {
            "engine": engine,
            "language": language,
            "sample_count": len(group),
            "course_count": course_count,
            "training_window_start": min(
                sample.completed_at for sample in group
            ).isoformat(),
            "training_window_end": max(
                sample.completed_at for sample in group
            ).isoformat(),
            "coefficients_p50": _fit_samples(group, 0.5),
            "coefficients_p80": _fit_samples(group, 0.8),
            "feature_bounds": [
                [
                    min(vector[index] for vector in vectors),
                    max(vector[index] for vector in vectors),
                ]
                for index in range(len(FEATURE_NAMES))
            ],
            "validation": validation,
        }
    artifact["sha256"] = _artifact_checksum(artifact)
    return artifact


def _validated_group(
    artifact: object, *, engine: str, language: str
) -> tuple[Mapping[str, Any] | None, str]:
    if not isinstance(artifact, dict):
        return None, "invalid_artifact"
    if (
        artifact.get("schema_version") != SCHEMA_VERSION
        or artifact.get("feature_names") != list(FEATURE_NAMES)
        or artifact.get("rate_credits_per_token") != str(REFERENCE_RATE)
        or not isinstance(artifact.get("version"), str)
        or not artifact["version"].strip()
        or artifact.get("method") != "nonnegative_weighted_quantile_regression"
        or not isinstance(artifact.get("sha256"), str)
        or artifact["sha256"] != _artifact_checksum(artifact)
    ):
        return None, "invalid_artifact"
    groups = artifact.get("groups")
    if not isinstance(groups, dict):
        return None, "invalid_artifact"
    group = groups.get(f"{engine}|{language}")
    if group is None:
        return None, "group_unavailable"
    if not isinstance(group, dict):
        return None, "invalid_artifact"
    if (
        group.get("engine") != engine
        or group.get("language") != language
        or type(group.get("sample_count")) is not int
        or group["sample_count"] < MIN_SAMPLES
        or type(group.get("course_count")) is not int
        or group["course_count"] < MIN_COURSES
    ):
        return None, "invalid_artifact"
    validation = group.get("validation")
    if not isinstance(validation, dict):
        return None, "invalid_artifact"
    wape = validation.get("p50_wape")
    coverage = validation.get("p80_coverage")
    if (
        isinstance(wape, bool)
        or not isinstance(wape, (int, float))
        or not math.isfinite(wape)
        or wape < 0
        or wape > MAX_P50_WAPE
        or isinstance(coverage, bool)
        or not isinstance(coverage, (int, float))
        or not math.isfinite(coverage)
        or not MIN_P80_COVERAGE <= coverage <= MAX_P80_COVERAGE
    ):
        return None, "invalid_artifact"
    for name in ("coefficients_p50", "coefficients_p80"):
        coefficients = group.get(name)
        if (
            not isinstance(coefficients, list)
            or len(coefficients) != len(FEATURE_NAMES)
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
                for value in coefficients
            )
        ):
            return None, "invalid_artifact"
    bounds = group.get("feature_bounds")
    if (
        not isinstance(bounds, list)
        or len(bounds) != len(FEATURE_NAMES)
        or any(
            not isinstance(pair, list)
            or len(pair) != 2
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
                for value in pair
            )
            or pair[0] > pair[1]
            for pair in bounds
        )
    ):
        return None, "invalid_artifact"
    maximum_vector = [pair[1] for pair in bounds]
    if any(
        not any(group[name]) or not math.isfinite(_dot(group[name], maximum_vector))
        for name in ("coefficients_p50", "coefficients_p80")
    ):
        return None, "invalid_artifact"
    return group, "calibrated"


def estimate_course_credits(
    features: Mapping[str, float],
    *,
    engine: str,
    language: str,
    artifact_path: Path | str = DEFAULT_ARTIFACT_PATH,
) -> CourseCreditPrediction:
    """Predict whole-course P50/P80 only from an eligible saved calibration."""
    try:
        vector = _feature_vector(features)
    except (KeyError, TypeError, ValueError):
        return CourseCreditPrediction(
            "uncalibrated", None, None, None, "invalid_features"
        )
    try:
        artifact = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return CourseCreditPrediction(
            "uncalibrated", None, None, None, "artifact_missing"
        )
    except (OSError, UnicodeError, ValueError):
        return CourseCreditPrediction(
            "uncalibrated", None, None, None, "invalid_artifact"
        )
    try:
        group, status = _validated_group(artifact, engine=engine, language=language)
    except (TypeError, ValueError):
        return CourseCreditPrediction(
            "uncalibrated", None, None, None, "invalid_artifact"
        )
    if group is None:
        return CourseCreditPrediction(
            "uncalibrated",
            None,
            None,
            artifact.get("version") if isinstance(artifact, dict) else None,
            status,
        )
    for value, (minimum, maximum) in zip(vector, group["feature_bounds"], strict=True):
        lower = minimum * (1 - FEATURE_BOUND_MARGIN)
        upper = maximum * (1 + FEATURE_BOUND_MARGIN)
        if not lower <= value <= upper:
            return CourseCreditPrediction(
                "uncalibrated",
                None,
                None,
                artifact["version"],
                "outside_calibration_range",
            )
    p50 = _half_up(Decimal(str(_dot(group["coefficients_p50"], vector))))
    p80 = _half_up(Decimal(str(_dot(group["coefficients_p80"], vector))))
    return CourseCreditPrediction("calibrated", p50, max(p50, p80), artifact["version"])
