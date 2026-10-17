"""Interpret boolean configuration values consistently across API surfaces."""


def parse_bool(value: object, default: bool = False) -> bool:
    """Accept the existing runtime-config boolean spellings and default policy."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y", "on"}:
        return True
    if normalized in {"false", "0", "no", "n", "off"}:
        return False
    return default
