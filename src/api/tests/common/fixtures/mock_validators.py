"""Mock validators for testing configuration validation."""


def mock_port_validator(value: object):
    """Mock port validator that accepts 1-65535."""
    try:
        port = int(value)
    except (ValueError, TypeError):
        return False
    else:
        return 1 <= port <= 65535


def mock_email_validator(value: object):
    """Mock email validator with simple regex."""
    import re

    if not value:
        return False
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, str(value)))


def always_fail_validator(value: object):
    """Fail validation always (test helper)."""
    _ = value
    return False


def always_pass_validator(value: object):
    """Pass validation always (test helper)."""
    _ = value
    return True


def range_validator(min_val: object, max_val: object):
    """Create a range validator for numeric values."""

    def validator(value: object):
        try:
            num = float(value)
        except (ValueError, TypeError):
            return False
        else:
            return min_val <= num <= max_val

    return validator


def string_length_validator(min_len: object = 0, max_len: object = 100):
    """Create a string length validator."""

    def validator(value: object):
        if value is None:
            return False
        s = str(value)
        return min_len <= len(s) <= max_len

    return validator


def regex_validator(pattern: object):
    """Create a regex-based validator."""
    import re

    compiled = re.compile(pattern)

    def validator(value: object):
        if value is None:
            return False
        return bool(compiled.match(str(value)))

    return validator


def url_validator(value: object):
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


def dependency_validator(depends_on_key: object):
    """Create a validator that checks if another config key is set."""
    _ = depends_on_key

    def validator(value: object):
        # In real usage, this would check if depends_on_key is configured
        # For testing, we just check if value is not empty
        return bool(value)

    return validator
