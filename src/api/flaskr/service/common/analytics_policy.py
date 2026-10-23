"""Apply the shared account exclusion policy before sending Umami data."""

from flaskr.common.config import get_config


def is_umami_user_excluded(user_id: object) -> bool:
    """Match exact account IDs without exposing the configured list to clients."""
    try:
        configured = get_config("ANALYTICS_UMAMI_EXCLUDED_USER_IDS", [])
        if isinstance(configured, str):
            configured = configured.split(",")
        excluded_ids = {
            item.strip()
            for item in (configured or [])
            if isinstance(item, str) and item.strip()
        }
        return isinstance(user_id, str) and bool(user_id) and user_id in excluded_ids
    except Exception:
        # A policy lookup failure may suppress telemetry, never user actions.
        return True
