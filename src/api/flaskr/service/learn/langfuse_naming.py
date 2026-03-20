import re


def _normalize_part(value: str, fallback: str) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text or fallback


def _compose_name(
    *,
    chapter_title: str,
    scene: str,
    action: str,
    max_length: int = 180,
) -> str:
    normalized_scene = _normalize_part(scene, "unknown_scene")
    normalized_action = _normalize_part(action, "unknown_action")
    normalized_title = _normalize_part(chapter_title, "untitled_chapter")
    name = f"{normalized_scene}/{normalized_action}/{normalized_title}"
    if len(name) <= max_length:
        return name
    prefix = f"{normalized_scene}/{normalized_action}/"
    available = max_length - len(prefix)
    if available <= 3:
        return name[:max_length]
    return f"{prefix}{normalized_title[: available - 3]}..."


def build_langfuse_trace_name(chapter_title: str, scene: str) -> str:
    return _compose_name(chapter_title=chapter_title, scene=scene, action="trace")


def build_langfuse_span_name(chapter_title: str, scene: str, action: str) -> str:
    return _compose_name(chapter_title=chapter_title, scene=scene, action=action)


def build_langfuse_event_name(chapter_title: str, scene: str, action: str) -> str:
    return _compose_name(chapter_title=chapter_title, scene=scene, action=action)


def build_langfuse_generation_name(chapter_title: str, scene: str, action: str) -> str:
    return _compose_name(chapter_title=chapter_title, scene=scene, action=action)
