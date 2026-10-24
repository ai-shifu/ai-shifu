"""Verify onboarding eligibility and parameter validation at rollout boundaries."""

from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.user import onboarding


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("not-a-date", None),
        ("2026-99-99", None),
        ("2026-09-20T08:00:00+08:00", datetime(2026, 9, 20)),
        ("2026-09-20", datetime(2026, 9, 20)),
    ],
)
def test_rollout_threshold_normalizes_utc_and_rejects_invalid_dates(
    raw: object, expected: datetime | None
) -> None:
    assert onboarding._parse_rollout_threshold(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, "zh-CN"), ("", "zh-CN"), ("zh-tw", "zh-CN"), ("fr-FR", "en-US")],
)
def test_guide_course_language_uses_the_supported_course_variants(
    raw: str | None, expected: str
) -> None:
    assert onboarding._normalize_language(raw) == expected


@pytest.mark.parametrize(
    "user",
    [
        None,
        SimpleNamespace(is_creator=0),
        SimpleNamespace(is_creator=1, created_at=None),
    ],
)
def test_missing_or_ineligible_creator_never_enters_onboarding(
    user: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        onboarding, "get_dynamic_config", lambda _key, _default: "2026-01-01"
    )
    assert onboarding._resolve_user_segment(user) == onboarding.USER_SEGMENT_INELIGIBLE


def test_creator_eligibility_compares_aware_creation_time_in_utc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        onboarding,
        "get_dynamic_config",
        lambda key, _default: (
            "2026-09-20T00:00:00Z" if key == onboarding.ROLLOUT_CONFIG_KEY else ""
        ),
    )
    user = SimpleNamespace(
        is_creator=1,
        created_at=datetime(2026, 9, 20, 8, tzinfo=timezone(timedelta(hours=8))),
    )
    assert onboarding._resolve_user_segment(user) == onboarding.USER_SEGMENT_NEW_CREATOR
    user.created_at = datetime(2026, 9, 19, 23, tzinfo=UTC)
    assert onboarding._resolve_user_segment(user) == onboarding.USER_SEGMENT_INELIGIBLE


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("user_bid", ""),
        ("scene_key", "unsupported"),
        ("version", "v2"),
        ("trigger_source", "unknown"),
        ("status", "unknown"),
    ],
)
def test_scene_completion_rejects_invalid_contract_before_database_write(
    app: object, field: str, value: str
) -> None:
    kwargs = {
        "user_bid": "account",
        "scene_key": onboarding.SCENE_ADMIN_HOME,
        "version": "v1",
        "trigger_source": "admin_entry",
        "status": "completed",
    }
    kwargs[field] = value
    with app.app_context(), pytest.raises(AppError) as error:
        onboarding.complete_onboarding_scene(app, **kwargs)
    error_key = (
        "server.user.userNotLogin"
        if field == "user_bid"
        else "server.common.paramsError"
    )
    assert error.value.code == ERROR_CODE[error_key]


def test_blank_account_cannot_load_an_onboarding_entity() -> None:
    assert onboarding._load_user_entity(" ") is None
