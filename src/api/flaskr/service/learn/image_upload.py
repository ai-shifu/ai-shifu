"""Validate and store raster images submitted by learners."""

from __future__ import annotations

import io
import time
import warnings
from typing import TYPE_CHECKING
from uuid import uuid4

from flaskr.api.llm.learner_images import (
    IMAGE_MARKER,
    MAX_IMAGE_BYTES,
    MAX_LEARNER_IMAGES,
    is_stored_learner_image,
    split_learner_images,
)
from flaskr.common.cache_provider import CacheUnavailableError, cache, redis_cache
from flaskr.common.config import get_redis_key_prefix
from flaskr.dao import get_redis_client
from flaskr.i18n import _
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.common.storage import upload_to_storage
from PIL import Image, UnidentifiedImageError
from redis.exceptions import RedisError

if TYPE_CHECKING:
    from flask import Flask
    from werkzeug.datastructures import FileStorage

UPLOADS_PER_HOUR = 32
SECONDS_PER_HOUR = 3600
IMAGE_FORMATS = {
    "JPEG": ("jpg", "image/jpeg"),
    "PNG": ("png", "image/png"),
    "WEBP": ("webp", "image/webp"),
}


def validate_learner_images(value: object) -> None:
    """Bound attachments across the complete submitted answer, including forged markers."""

    def count(item: object) -> int:
        if isinstance(item, str):
            _plain, images = split_learner_images(item)
            if len(IMAGE_MARKER.findall(item)) != len(images) or not all(
                is_stored_learner_image(url) for url in images
            ):
                raise_param_error(_("server.learn.imageInputInvalid"))
            return len(images)
        if isinstance(item, dict):
            return sum(count(child) for child in item.values())
        if isinstance(item, list):
            return sum(count(child) for child in item)
        return 0

    if count(value) > MAX_LEARNER_IMAGES:
        raise_param_error(_("server.learn.imageInputInvalid"))


def reserve_learner_image_upload(app: Flask, user_bid: str) -> None:
    """Charge one attempt before decoding or storing a learner image."""
    hour = int(time.time()) // SECONDS_PER_HOUR
    key = f"{get_redis_key_prefix(app)}learner-image-upload:{user_bid}:{hour}"
    provider = redis_cache if get_redis_client() is not None else cache
    try:
        # The hour in the key fixes the window. Keep its counter until all
        # requests that could reference this window have finished.
        provider.set(key, 0, ex=2 * SECONDS_PER_HOUR, nx=True)
        count = provider.incr(key)
    except (CacheUnavailableError, RedisError):
        raise_error("server.common.operationFailed")
    if count > UPLOADS_PER_HOUR:
        raise_error("server.learn.imageUploadRateLimited")


def upload_learner_image(app: Flask, file: FileStorage | None) -> str:
    """Reject invalid, animated or excessive raster content before writing storage."""
    if file is None:
        raise_param_error("file")
    data = file.read(MAX_IMAGE_BYTES + 1)
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise_param_error(_("server.learn.imageInputInvalid"))
    formats = tuple(IMAGE_FORMATS)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=formats) as image:
                image_format = image.format
                if (
                    image_format not in IMAGE_FORMATS
                    or image.width * image.height > 20_000_000
                    or getattr(image, "is_animated", False)
                ):
                    raise_param_error(_("server.learn.imageInputInvalid"))
                image.verify()
            with Image.open(io.BytesIO(data), formats=formats) as image:
                image.load()
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise_param_error(_("server.learn.imageInputInvalid"))
    extension, content_type = IMAGE_FORMATS[image_format]
    return upload_to_storage(
        app,
        file_content=data,
        object_key=f"learner-images/{uuid4().hex}.{extension}",
        content_type=content_type,
        profile="courses",
    ).url
