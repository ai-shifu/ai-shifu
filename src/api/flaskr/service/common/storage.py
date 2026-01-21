from __future__ import annotations

import io
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flask import Flask

from flaskr.service.common.oss_utils import (
    OSS_PROFILE_COURSES,
    OSS_PROFILE_DEFAULT,
    is_oss_profile_configured,
    upload_to_oss,
)
from flaskr.service.config import get_config


STORAGE_PROVIDER_AUTO = "auto"
STORAGE_PROVIDER_OSS = "oss"
STORAGE_PROVIDER_LOCAL = "local"

_ALLOWED_PROFILES = {OSS_PROFILE_DEFAULT, OSS_PROFILE_COURSES}


@dataclass(frozen=True)
class StorageUploadResult:
    provider: str
    url: str
    bucket: str
    object_key: str


def _normalize_profile(profile: str) -> str:
    resolved = (profile or "").strip().lower() or OSS_PROFILE_DEFAULT
    if resolved not in _ALLOWED_PROFILES:
        raise ValueError(f"Unknown storage profile: {profile}")
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
        raise ValueError("object_key is required")
    if key.startswith("/"):
        raise ValueError("object_key must be a relative path")
    if ".." in key.split("/"):
        raise ValueError("object_key must not contain '..'")
    return key


def get_local_storage_root() -> Path:
    root = (get_config("LOCAL_STORAGE_ROOT") or "storage").strip()
    return Path(root)


def get_local_storage_path(profile: str, object_key: str) -> Path:
    resolved_profile = _normalize_profile(profile)
    resolved_key = _normalize_object_key(object_key)

    root = get_local_storage_root()
    target = root / resolved_profile / resolved_key

    root_abs = root.resolve()
    target_abs = target.resolve()
    if os.path.commonpath([str(root_abs), str(target_abs)]) != str(root_abs):
        raise ValueError("Resolved path escapes LOCAL_STORAGE_ROOT")
    return target


def build_local_storage_url(profile: str, object_key: str) -> str:
    resolved_profile = _normalize_profile(profile)
    resolved_key = _normalize_object_key(object_key)

    path_prefix = (get_config("PATH_PREFIX") or "/api").rstrip("/")
    return f"{path_prefix}/storage/{resolved_profile}/{resolved_key}"


def _coerce_to_binary_stream(file_content: Any) -> io.BufferedReader:
    if file_content is None:
        raise ValueError("file_content is required")

    if isinstance(file_content, (bytes, bytearray)):
        return io.BufferedReader(io.BytesIO(file_content))

    if hasattr(file_content, "read"):
        # Werkzeug FileStorage / BytesIO / file object.
        return file_content  # type: ignore[return-value]

    raise TypeError("file_content must be bytes or a file-like object")


def _upload_to_local(
    app: Flask,
    *,
    file_content: Any,
    object_key: str,
    content_type: str,
    profile: str,
) -> StorageUploadResult:
    _unused_app = app
    _unused_content_type = content_type

    resolved_profile = _normalize_profile(profile)
    resolved_key = _normalize_object_key(object_key)

    target_path = get_local_storage_path(resolved_profile, resolved_key)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    stream = _coerce_to_binary_stream(file_content)
    with open(target_path, "wb") as f:
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
    file_content: Any,
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
    file_content: Any,
    object_key: str,
    content_type: str,
    profile: str = OSS_PROFILE_DEFAULT,
    warm_up: bool = True,
) -> StorageUploadResult:
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
        app,
        file_content=file_content,
        object_key=object_key,
        content_type=content_type,
        profile=resolved_profile,
    )
