"""Verify account exclusions are exact, private, and safe for business flows."""

import pytest
from flaskr.service.common import analytics_policy


@pytest.mark.parametrize(
    ("configured", "user_id", "excluded"),
    [
        ([], "user-1", False),
        ("", "user-1", False),
        (" user-1, ,user-2,user-1, ", "user-1", True),
        ([" user-1 ", "", "user-2"], "user-2", True),
        (["user-10"], "user-1", False),
        (["USER-1"], "user-1", False),
        (["user-1"], " user-1 ", False),
        (["user-1"], "", False),
        (["user-1"], None, False),
        (["user-1"], {"user_id": "user-1"}, False),
    ],
)
def test_umami_exclusion_matches_exact_nonempty_account_ids(
    monkeypatch: pytest.MonkeyPatch,
    configured: object,
    user_id: object,
    excluded: bool,
) -> None:
    def get_config(key: str, default: object) -> object:
        assert key == "ANALYTICS_EXCLUDED_USER_IDS"
        assert default == []
        return configured

    monkeypatch.setattr(analytics_policy, "get_config", get_config)

    assert analytics_policy.is_umami_user_excluded(user_id) is excluded


def test_umami_policy_lookup_failure_suppresses_telemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object) -> object:
        raise LookupError

    monkeypatch.setattr(analytics_policy, "get_config", fail)

    assert analytics_policy.is_umami_user_excluded("user-1") is True
