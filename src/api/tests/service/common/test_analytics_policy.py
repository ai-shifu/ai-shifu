"""Verify account exclusions are exact, private, and safe for business flows."""

import pytest
from flaskr.service.common import analytics_policy


@pytest.mark.parametrize(
    ("configured", "user_bid", "excluded"),
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
        (["user-1"], {"user_bid": "user-1"}, False),
    ],
)
def test_analytics_exclusion_matches_exact_nonempty_user_bids(
    monkeypatch: pytest.MonkeyPatch,
    configured: object,
    user_bid: object,
    excluded: bool,
) -> None:
    def get_config(key: str, default: object) -> object:
        assert key == "ANALYTICS_EXCLUDED_USER_IDS"
        assert default == []
        return configured

    monkeypatch.setattr(analytics_policy, "get_config", get_config)

    assert analytics_policy.is_analytics_user_excluded(user_bid) is excluded


def test_analytics_policy_lookup_failure_suppresses_telemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object) -> object:
        raise LookupError

    monkeypatch.setattr(analytics_policy, "get_config", fail)

    assert analytics_policy.is_analytics_user_excluded("user-1") is True
