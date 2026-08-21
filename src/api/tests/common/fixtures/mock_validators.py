"""Mock validators for testing configuration validation."""

from collections.abc import Callable


def mock_port_validator(value) -> bool:
    """Mock port validator that accepts 1-65535."""
    try:
        port = int(value)
    except (ValueError, TypeError):
        return False
    else:
        return 1 <= port <= 65535


def mock_email_validator(value) -> bool:
    """Mock email validator with simple regex."""
    import re

    if not value:
        return False
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, str(value)))


def always_fail_validator(value) -> bool:
    """Fail validation always (test helper)."""
    _ = value
    return False


def always_pass_validator(value) -> bool:
    """Pass validation always (test helper)."""
    _ = value
    return True


def range_validator(min_val, max_val) -> Callable[[object], bool]:
    """Create a range validator for numeric values."""

    def validator(value):
        try:
            num = float(value)
        except (ValueError, TypeError):
            return False
        else:
            return min_val <= num <= max_val

    return validator


def string_length_validator(min_len=0, max_len=100) -> Callable[[object], bool]:
    """Create a string length validator."""

    def validator(value):
        if value is None:
            return False
        s = str(value)
        return min_len <= len(s) <= max_len

    return validator


def regex_validator(pattern) -> Callable[[object], bool]:
    """Create a regex-based validator."""
    import re

    compiled = re.compile(pattern)

    def validator(value):
        if value is None:
            return False
        return bool(compiled.match(str(value)))

    return validator


def url_validator(value) -> bool:
    """Mock URL validator."""
    import re

    if not value:
        return False
    url_pattern = re.compile(
        r"^https?://"  # http:// or https://
        r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"  # domain...
        r"localhost|"  # localhost...
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...or ip
        r"(?::\d+)?"  # optional port
        r"(?:/?|[/?]\S+)$",
        re.IGNORECASE,
    )
    return bool(url_pattern.match(str(value)))


def dependency_validator(depends_on_key) -> Callable[[object], bool]:
    """Create a validator that checks if another config key is set."""
    _ = depends_on_key

    def validator(value):
        # In real usage, this would check if depends_on_key is configured
        # For testing, we just check if value is not empty
        return bool(value)

    return validator
