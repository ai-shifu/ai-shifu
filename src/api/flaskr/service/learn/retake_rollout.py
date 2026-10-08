"""Default-off deployment boundary for retake limits on shared databases."""

from flaskr.common.config import get_config


def retake_namespace(shifu_bid: str) -> str | None:
    """Never fall back to shared sys_configs or treat '*' as a global enable."""
    namespace = get_config("LESSON_RETAKE_NAMESPACE", default="")
    raw_courses = get_config("LESSON_RETAKE_SHIFU_BIDS", default=[])
    if (
        not isinstance(namespace, str)
        or not namespace.strip()
        or len(namespace.strip()) > 32
    ):
        return None
    global_enabled = get_config("LESSON_RETAKE_GLOBAL_ENABLED", default=False)
    if global_enabled is True or global_enabled == "true":
        return namespace.strip() if shifu_bid else None
    if isinstance(raw_courses, str):
        courses = raw_courses.split(",")
    elif isinstance(raw_courses, list):
        courses = raw_courses
    else:
        return None
    enabled = {
        entry.strip()
        for entry in courses
        if isinstance(entry, str) and entry.strip() != "*"
    }
    return namespace.strip() if shifu_bid and shifu_bid in enabled else None
