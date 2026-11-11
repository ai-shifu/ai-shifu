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


def materialize_local_images(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Inline only our bounded local image objects, without fetching remote URLs.

    Run after checking the text-envelope budget: base64 is transport encoding,
    not text tokens. Each object was bounded to 5 MiB by the upload endpoint.
    """
    output = []
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            output.append(message)
            continue
        parts = []
        for part in content:
            mapped_part = part
            url = part.get("image_url", {}).get("url", "")
            if part.get("type") == "image_url" and not is_stored_learner_image(url):
                message_text = "invalid learner image storage location"
                raise ValueError(message_text)
            if part.get("type") == "image_url" and url.startswith("/"):
                key_match = IMAGE_KEY.search(url)
                if key_match is None:
                    message_text = "invalid local learner image"
                    raise ValueError(message_text)
                key = key_match[0]
                if url != build_local_storage_url("courses", key):
                    message_text = "invalid local learner image location"
                    raise ValueError(message_text)
                path = get_local_storage_path("courses", key)
                with path.open("rb") as stream:
                    data = stream.read(5 * 1024 * 1024 + 1)
                if len(data) > 5 * 1024 * 1024:
                    message_text = "learner image exceeds size limit"
                    raise ValueError(message_text)
                mime = "jpeg" if key.endswith(".jpg") else key.rsplit(".", 1)[1]
                encoded = base64.b64encode(data).decode("ascii")
                mapped_part = {
                    **part,
                    "image_url": {"url": f"data:image/{mime};base64,{encoded}"},
                }
            parts.append(mapped_part)
        output.append({**message, "content": parts})
    return output
