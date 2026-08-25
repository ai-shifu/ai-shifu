"""Read and write files through configured storage providers."""

from __future__ import annotations

import io
import os
import shutil
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from flaskr.service.common.oss_utils import (
    OSS_PROFILE_COURSES,
    OSS_PROFILE_DEFAULT,
    create_oss_bucket,
    get_oss_config,
    is_oss_profile_configured,
    upload_to_oss,
)
from flaskr.service.config import get_config

if TYPE_CHECKING:
    from flask import Flask

STORAGE_PROVIDER_AUTO = "auto"
STORAGE_PROVIDER_OSS = "oss"
STORAGE_PROVIDER_LOCAL = "local"

_ALLOWED_PROFILES = {OSS_PROFILE_DEFAULT, OSS_PROFILE_COURSES}


@dataclass(frozen=True)
class StorageUploadResult:
    """Capture the location and metadata of an uploaded object."""

    provider: str
    url: str
    bucket: str
    object_key: str


def _normalize_profile(profile: str) -> str:
    resolved = (profile or "").strip().lower() or OSS_PROFILE_DEFAULT
    if resolved not in _ALLOWED_PROFILES:
        message = f"Unknown storage profile: {profile}"
        raise ValueError(message)
    return resolved


def _resolve_provider(profile: str) -> str:
    configured = (
        (get_config("STORAGE_PROVIDER") or STORAGE_PROVIDER_AUTO).strip().lower()
    )
    if configured not in {
        STORAGE_PROVIDER_AUTO,
        STORAGE_PROVIDER_OSS,
        STORAGE_PROVIDER_LOCAL,
    }:
        return STORAGE_PROVIDER_AUTO

    if configured == STORAGE_PROVIDER_AUTO:
        return (
            STORAGE_PROVIDER_OSS
            if is_oss_profile_configured(profile)
            else STORAGE_PROVIDER_LOCAL
        )

    return configured


def _normalize_object_key(object_key: str) -> str:
    key = (object_key or "").replace("\\", "/").strip()
    if not key:
        message = "object_key is required"
        raise ValueError(message)
    if key.startswith("/"):
        message = "object_key must be a relative path"
        raise ValueError(message)
    if ".." in key.split("/"):
        message = "object_key must not contain '..'"
        raise ValueError(message)
    return key


def get_local_storage_root() -> Path:
    """Return local storage root."""
    root = (get_config("LOCAL_STORAGE_ROOT") or "storage").strip()
    return Path(root)


def get_local_storage_path(profile: str, object_key: str) -> Path:
    """Return local storage path."""
    resolved_profile = _normalize_profile(profile)
    resolved_key = _normalize_object_key(object_key)

    root = get_local_storage_root()
    target = root / resolved_profile / resolved_key

    root_abs = root.resolve()
    target_abs = target.resolve()
    if os.path.commonpath([str(root_abs), str(target_abs)]) != str(root_abs):
        message = "Resolved path escapes LOCAL_STORAGE_ROOT"
        raise ValueError(message)
    return target


def build_local_storage_url(profile: str, object_key: str) -> str:
    """Build local storage URL."""
    resolved_profile = _normalize_profile(profile)
    resolved_key = _normalize_object_key(object_key)

    path_prefix = (get_config("PATH_PREFIX") or "/api").rstrip("/")
    return f"{path_prefix}/storage/{resolved_profile}/{resolved_key}"


def _coerce_to_binary_stream(file_content: object) -> io.BufferedReader:
    if file_content is None:
        message = "file_content is required"
        raise ValueError(message)

    if isinstance(file_content, (bytes, bytearray)):
        return io.BufferedReader(io.BytesIO(file_content))

    if hasattr(file_content, "read"):
        # Werkzeug FileStorage / BytesIO / file object.
        return file_content  # type: ignore[return-value]

    message = "file_content must be bytes or a file-like object"
    raise TypeError(message)


def _upload_to_local(
    *,
    file_content: object,
    object_key: str,
    profile: str,
) -> StorageUploadResult:
    resolved_profile = _normalize_profile(profile)
    resolved_key = _normalize_object_key(object_key)

    target_path = get_local_storage_path(resolved_profile, resolved_key)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    stream = _coerce_to_binary_stream(file_content)
    # Builtin open() avoids CodeQL's Path.open path-injection sink after
    # get_local_storage_path() already confined this path.
    with open(target_path, "wb") as f:  # noqa: PTH123
        shutil.copyfileobj(stream, f)

    return StorageUploadResult(
        provider=STORAGE_PROVIDER_LOCAL,
        url=build_local_storage_url(resolved_profile, resolved_key),
        bucket="",
        object_key=resolved_key,
    )


def _upload_to_oss(
    app: Flask,
    *,
    file_content: object,
    object_key: str,
    content_type: str,
    profile: str,
    warm_up: bool,
) -> StorageUploadResult:
    resolved_profile = _normalize_profile(profile)
    resolved_key = _normalize_object_key(object_key)

    url, bucket_name = upload_to_oss(
        app,
        file_content=file_content,
        file_id=resolved_key,
        content_type=content_type,
        profile=resolved_profile,
        warm_up=warm_up,
    )
    return StorageUploadResult(
        provider=STORAGE_PROVIDER_OSS,
        url=url,
        bucket=bucket_name,
        object_key=resolved_key,
    )


def upload_to_storage(
    app: Flask,
    *,
    file_content: object,
    object_key: str,
    content_type: str,
    profile: str = OSS_PROFILE_DEFAULT,
    warm_up: bool = True,
) -> StorageUploadResult:
    """Upload to storage."""
    resolved_profile = _normalize_profile(profile)
    resolved_provider = _resolve_provider(resolved_profile)

    if resolved_provider == STORAGE_PROVIDER_OSS:
        return _upload_to_oss(
            app,
            file_content=file_content,
            object_key=object_key,
            content_type=content_type,
            profile=resolved_profile,
            warm_up=warm_up,
        )

    return _upload_to_local(
        file_content=file_content,
        object_key=object_key,
        profile=resolved_profile,
    )


def read_storage_bytes(
    *,
    object_key: str,
    profile: str = OSS_PROFILE_DEFAULT,
    bucket_name: str = "",
) -> bytes:
    """Read storage bytes."""
    resolved_profile = _normalize_profile(profile)
    resolved_key = _normalize_object_key(object_key)

    local_path = get_local_storage_path(resolved_profile, resolved_key)
    if local_path.exists():
        return local_path.read_bytes()

    should_try_oss = bool(str(bucket_name or "").strip()) or (
        _resolve_provider(resolved_profile) == STORAGE_PROVIDER_OSS
    )
    if should_try_oss and is_oss_profile_configured(resolved_profile):
        config = get_oss_config(resolved_profile)
        normalized_bucket = str(bucket_name or "").strip()
        if normalized_bucket and normalized_bucket != config.bucket:
            config = replace(config, bucket=normalized_bucket)
        bucket = create_oss_bucket(config)
        return bucket.get_object(resolved_key).read()

    message = f"storage object not found: {resolved_key}"
    raise FileNotFoundError(message)
