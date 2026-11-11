"""Map persisted learner image attachments to native model content."""

from __future__ import annotations

import base64
import re
from typing import Any
from urllib.parse import urlsplit

from flaskr.service.common.storage import (
    build_local_storage_url,
    get_local_storage_path,
)
from flaskr.service.config import get_config

MAX_LEARNER_IMAGES = 4
MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_MARKER = re.compile(r"!\[learner-image\]\(([^\s()]+)\)")
IMAGE_KEY = re.compile(r"learner-images/[0-9a-f]{32}\.(?:jpg|png|webp)$")


def split_learner_images(text: str) -> tuple[str, list[str]]:
    """Separate reserved attachment markers, leaving ordinary Markdown unchanged."""
    images: list[str] = []

    def replace(match: re.Match[str]) -> str:
        url = match[1]
        try:
            parsed = urlsplit(url)
        except ValueError:
            return match[0]
        if (
            not IMAGE_KEY.search(parsed.path)
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
            or (parsed.scheme not in {"http", "https"} and not url.startswith("/"))
            or url.startswith("//")
        ):
            return match[0]
        images.append(url)
        return ""

    return IMAGE_MARKER.sub(replace, text), images


def is_stored_learner_image(url: str) -> bool:
    """Accept only configured storage locations and opaque learner image keys."""
    key_match = IMAGE_KEY.search(url)
    if key_match is None:
        return False
    key = key_match[0]
    if url.startswith("/"):
        return url == build_local_storage_url("courses", key)
    base = str(get_config("ALIBABA_CLOUD_OSS_COURSES_URL") or "").rstrip("/")
    return bool(base) and url == f"{base}/{key}"


def learner_content(text: str) -> str | list[dict[str, Any]]:
    """Keep text-only inputs intact and expose attached images to vision models."""
    plain, images = split_learner_images(text)
    if not images:
        return text
    return [
        {"type": "text", "text": plain.strip() or "See the attached images."},
        *({"type": "image_url", "image_url": {"url": url}} for url in images),
    ]


def map_learner_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert learner messages only; authored and assistant images stay as text."""
    return [
        {**message, "content": learner_content(message["content"])}
        if message.get("role") == "user" and isinstance(message.get("content"), str)
        else message
        for message in messages
    ]


def _local_image_data_url(url: str) -> str | None:
    key_match = IMAGE_KEY.search(url)
    if key_match is None:
        return None
    key = key_match[0]
    path = get_local_storage_path("courses", key)
    try:
        with path.open("rb") as stream:
            data = stream.read(MAX_IMAGE_BYTES + 1)
    except FileNotFoundError:
        return None
    if not data or len(data) > MAX_IMAGE_BYTES:
        return None
    mime = "jpeg" if key.endswith(".jpg") else key.rsplit(".", 1)[1]
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:image/{mime};base64,{encoded}"


def _materialize_image(part: dict[str, Any]) -> dict[str, Any]:
    url = part.get("image_url", {}).get("url", "")
    if is_stored_learner_image(url):
        if not url.startswith("/"):
            return part
        data_url = _local_image_data_url(url)
        if data_url:
            return {**part, "image_url": {"url": data_url}}
    return {"type": "text", "text": "[Image attachment unavailable]"}


def materialize_local_images(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Inline only our bounded local image objects, without fetching remote URLs.

    Retain the newest attachments within one submission-sized budget. Older
    turns keep their text and attachment notices, and their files are not read.
    Base64 is transport encoding, so this runs after the text-envelope check.
    """
    image_count = sum(
        part.get("type") == "image_url"
        for message in messages
        if isinstance(content := message.get("content"), list)
        for part in content
    )
    skip_images = max(0, image_count - MAX_LEARNER_IMAGES)
    output = []
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            output.append(message)
            continue
        parts = []
        for part in content:
            if part.get("type") != "image_url":
                parts.append(part)
                continue
            if skip_images:
                parts.append(
                    {"type": "text", "text": "[Earlier image attachment omitted]"}
                )
                skip_images -= 1
                continue
            parts.append(_materialize_image(part))
        output.append({**message, "content": parts})
    return output
