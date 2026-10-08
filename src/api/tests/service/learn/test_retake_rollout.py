"""A shared course database must not accidentally enable production retakes."""

import pytest
from flaskr.service.learn import retake_rollout


@pytest.mark.parametrize(
    ("namespace", "courses", "expected"),
    [
        ("", ["course"], None),
        ("dev02", [], None),
        ("dev02", "course,other", "dev02"),
        ("dev02", [" course "], "dev02"),
        ("dev02", ["other"], None),
        ("dev02", "*", None),
        ("dev02", {"course": True}, None),
        (True, ["course"], None),
        ("x" * 33, ["course"], None),
    ],
)
def test_deployment_and_explicit_course_are_both_required(
    monkeypatch: pytest.MonkeyPatch,
    namespace: object,
    courses: object,
    expected: str | None,
) -> None:
    values = {"LESSON_RETAKE_NAMESPACE": namespace, "LESSON_RETAKE_SHIFU_BIDS": courses}
    monkeypatch.setattr(
        retake_rollout, "get_config", lambda key, default=None: values.get(key, default)
    )
    assert retake_rollout.retake_namespace("course") == expected


@pytest.mark.parametrize("enabled", [True, "true"])
def test_global_rollout_requires_namespace_and_enables_every_course(
    monkeypatch: pytest.MonkeyPatch, enabled: bool | str
) -> None:
    values = {
        "LESSON_RETAKE_NAMESPACE": "dev02",
        "LESSON_RETAKE_GLOBAL_ENABLED": enabled,
    }
    monkeypatch.setattr(
        retake_rollout, "get_config", lambda key, default=None: values.get(key, default)
    )
    assert retake_rollout.retake_namespace("any-course") == "dev02"
    assert retake_rollout.retake_namespace("") is None
    values["LESSON_RETAKE_NAMESPACE"] = ""
    assert retake_rollout.retake_namespace("any-course") is None
