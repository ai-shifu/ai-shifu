"""Apply the shared account exclusion policy before sending analytics data."""

from flaskr.common.config import get_config


def is_analytics_user_excluded(user_bid: object) -> bool:
    """Match exact user business IDs without exposing the configured list."""
    try:
        configured = get_config("ANALYTICS_EXCLUDED_USER_IDS", [])
        if isinstance(configured, str):
            configured = configured.split(",")
        excluded_user_bids = {
            item.strip()
            for item in (configured or [])
            if isinstance(item, str) and item.strip()
        }
        return (
            isinstance(user_bid, str)
            and bool(user_bid)
            and user_bid in excluded_user_bids
        )
    except Exception:
        # A policy lookup failure may suppress telemetry, never user actions.
        return True
