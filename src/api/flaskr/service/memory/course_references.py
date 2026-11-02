"""Reject retired cross-course aliases without resolving or copying learner values."""

COURSE_REFERENCE_PREFIX = "course:"
SHARED_ANSWER_PREFIX = "share:"


def is_course_reference(key: str) -> bool:
    """Reserve both retired namespaces, including malformed names and old payloads."""
    return key.startswith((COURSE_REFERENCE_PREFIX, SHARED_ANSWER_PREFIX))
