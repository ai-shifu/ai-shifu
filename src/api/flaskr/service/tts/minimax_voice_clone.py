"""MiniMax voice cloning service and async orchestration."""

from __future__ import annotations

import io
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests
from flask import Flask

try:
    from pydub import AudioSegment
except Exception:  # pragma: no cover - exercised only when pydub is missing.

    class AudioSegment:  # type: ignore[no-redef]
        @staticmethod
        def from_file(*_args, **_kwargs):
            raise RuntimeError("audio decoder is not available")


from flaskr.common.config import get_config
from flaskr.dao import db
from flaskr.service.billing.api import (
    admit_creator_usage,
    capture_reserved_operation_credits,
    estimate_voice_clone_operation_credits,
    is_billing_enabled,
    quantize_credit_amount,
    release_reserved_operation_credits,
    reserve_operation_credits,
    to_decimal,
)
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.common.oss_utils import OSS_PROFILE_COURSES
from flaskr.service.common.storage import read_storage_bytes, upload_to_storage
from flaskr.service.metering.api import UsageContext, record_tts_usage
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PREVIEW
from flaskr.service.resource.models import Resource
from flaskr.service.shifu.models import DraftShifu
from flaskr.service.tts.models import (
    TTSMiniMaxClonedVoice,
    TTS_MINIMAX_CLONE_BILLING_CHARGED,
    TTS_MINIMAX_CLONE_BILLING_FAILED,
    TTS_MINIMAX_CLONE_BILLING_NOT_REQUIRED,
    TTS_MINIMAX_CLONE_BILLING_RELEASED,
    TTS_MINIMAX_CLONE_BILLING_RESERVED,
    TTS_MINIMAX_CLONE_STATUS_BILLING_PENDING,
    TTS_MINIMAX_CLONE_STATUS_FAILED,
    TTS_MINIMAX_CLONE_STATUS_PROCESSING,
    TTS_MINIMAX_CLONE_STATUS_QUEUED,
    TTS_MINIMAX_CLONE_STATUS_READY,
)
from flaskr.util.datetime import to_utc_iso
from flaskr.util.uuid import generate_id


MINIMAX_FILE_UPLOAD_URL = "https://api.minimaxi.com/v1/files/upload"
MINIMAX_VOICE_CLONE_URL = "https://api.minimaxi.com/v1/voice_clone"
MINIMAX_CLONE_PREVIEW_TEXT = "你好，这是音色复制后的试听效果。"
MINIMAX_CLONE_PREVIEW_MODEL = "speech-2.8-turbo"

_ALLOWED_INPUT_EXTENSIONS = {"mp3", "m4a", "wav", "webm", "ogg", "mp4"}
_SOURCE_MIN_DURATION_MS = 10_000
_SOURCE_MAX_DURATION_MS = 300_000
_PROMPT_MAX_DURATION_MS = 8_000
_MAX_SOURCE_BYTES = 50 * 1024 * 1024
_MAX_PROMPT_BYTES = 10 * 1024 * 1024
_VOICE_ID_RE = re.compile(r"^[A-Za-z](?=.{7,63}$)[A-Za-z0-9_-]*[A-Za-z0-9]$")
_PENDING_AUDIO_BLOBS: dict[str, bytes] = {}


@dataclass(slots=True, frozen=True)
class NormalizedAudioBlob:
    audio_bytes: bytes
    duration_ms: int
    extension: str = "wav"
    content_type: str = "audio/wav"


@dataclass(slots=True, frozen=True)
class StoredResourceRef:
    resource_bid: str
    url: str
    object_key: str


@dataclass(slots=True, frozen=True)
class MiniMaxUploadedFile:
    file_id: str
    extra_info: dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""


@dataclass(slots=True, frozen=True)
class MiniMaxVoiceCloneResult:
    voice_id: str
    demo_audio: str = ""
    status_code: int = 0
    status_msg: str = "success"
    input_sensitive: bool = False
    input_sensitive_type: str | None = None
    extra_info: dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""


@dataclass(slots=True, frozen=True)
class MiniMaxVoiceCloneRunResult:
    status: str
    voice_bid: str
    voice_id: str = ""
    message: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "voice_bid": self.voice_bid,
            "voice_id": self.voice_id,
            "message": self.message,
        }


def is_valid_minimax_custom_voice_id(value: str) -> bool:
    return bool(_VOICE_ID_RE.match(str(value or "").strip()))


def normalize_audio_blob(
    audio_bytes: bytes,
    *,
    filename: str,
    purpose: str,
) -> NormalizedAudioBlob:
    normalized_filename = str(filename or "").strip()
    extension = _extract_extension(normalized_filename)
    if extension not in _ALLOWED_INPUT_EXTENSIONS:
        raise ValueError("unsupported audio file type")
    if not audio_bytes:
        raise ValueError("audio file is empty")

    try:
        segment = AudioSegment.from_file(io.BytesIO(audio_bytes), format=extension)
    except Exception as exc:
        raise ValueError(
            "unable to decode audio; please record again or upload mp3, m4a, or wav"
        ) from exc

    duration_ms = int(len(segment))
    if purpose == "source":
        if duration_ms < _SOURCE_MIN_DURATION_MS:
            raise ValueError("source audio must be at least 10 seconds")
        if duration_ms > _SOURCE_MAX_DURATION_MS:
            raise ValueError("source audio must be no longer than 5 minutes")
    elif purpose == "prompt":
        if duration_ms > _PROMPT_MAX_DURATION_MS:
            raise ValueError("prompt audio must be no longer than 8 seconds")
    else:
        raise ValueError("invalid audio purpose")

    output = io.BytesIO()
    segment.export(output, format="wav")
    return NormalizedAudioBlob(
        audio_bytes=output.getvalue(),
        duration_ms=duration_ms,
        extension="wav",
        content_type="audio/wav",
    )


class MiniMaxVoiceCloneClient:
    def __init__(self) -> None:
        self.api_key = str(get_config("MINIMAX_API_KEY") or "").strip()
        self.group_id = str(get_config("MINIMAX_GROUP_ID") or "").strip()
        if not self.api_key:
            raise ValueError("MINIMAX_API_KEY is not configured")

    def upload_clone_audio(
        self,
        audio_bytes: bytes,
        filename: str,
        content_type: str,
    ) -> MiniMaxUploadedFile:
        return self._upload_file(
            audio_bytes=audio_bytes,
            filename=filename,
            content_type=content_type,
            purpose="voice_clone",
        )

    def upload_prompt_audio(
        self,
        audio_bytes: bytes,
        filename: str,
        content_type: str,
    ) -> MiniMaxUploadedFile:
        return self._upload_file(
            audio_bytes=audio_bytes,
            filename=filename,
            content_type=content_type,
            purpose="prompt_audio",
        )

    def clone_voice(
        self,
        *,
        file_id: str,
        voice_id: str,
        prompt_file_id: str = "",
        preview_text: str = MINIMAX_CLONE_PREVIEW_TEXT,
        preview_model: str = MINIMAX_CLONE_PREVIEW_MODEL,
    ) -> MiniMaxVoiceCloneResult:
        payload: dict[str, Any] = {
            "file_id": _minimax_file_id_payload(file_id),
            "voice_id": voice_id,
            "text": preview_text,
            "model": preview_model,
        }
        if prompt_file_id:
            payload["clone_prompt"] = {
                "prompt_audio": _minimax_file_id_payload(prompt_file_id)
            }

        response = requests.post(
            _with_group_id(MINIMAX_VOICE_CLONE_URL, self.group_id),
            headers=self._headers(json_body=True),
            json=payload,
            timeout=(10, 120),
        )
        response.raise_for_status()
        message = response.json()
        base_resp = message.get("base_resp") or {}
        status_code = int(base_resp.get("status_code") or 0)
        status_msg = str(base_resp.get("status_msg") or "")
        trace_id = str(message.get("trace_id") or "")
        if status_code != 0:
            raise ValueError(
                _format_minimax_error(
                    status_code=status_code, status_msg=status_msg, trace_id=trace_id
                )
            )
        data = message.get("data") or {}
        extra_info = message.get("extra_info") or data.get("extra_info") or {}
        return MiniMaxVoiceCloneResult(
            voice_id=str(data.get("voice_id") or voice_id),
            demo_audio=str(
                data.get("demo_audio")
                or data.get("demo_audio_url")
                or message.get("demo_audio")
                or ""
            ),
            status_code=status_code,
            status_msg=status_msg or "success",
            input_sensitive=bool(
                data.get("input_sensitive") or message.get("input_sensitive") or False
            ),
            input_sensitive_type=data.get("input_sensitive_type")
            or message.get("input_sensitive_type"),
            extra_info=extra_info if isinstance(extra_info, dict) else {},
            trace_id=trace_id,
        )

    def _upload_file(
        self,
        *,
        audio_bytes: bytes,
        filename: str,
        content_type: str,
        purpose: str,
    ) -> MiniMaxUploadedFile:
        files = {
            "file": (
                filename,
                io.BytesIO(audio_bytes),
                content_type or "application/octet-stream",
            )
        }
        response = requests.post(
            _with_group_id(MINIMAX_FILE_UPLOAD_URL, self.group_id),
            headers=self._headers(json_body=False),
            data={"purpose": purpose},
            files=files,
            timeout=(10, 120),
        )
        response.raise_for_status()
        message = response.json()
        base_resp = message.get("base_resp") or {}
        status_code = int(base_resp.get("status_code") or 0)
        status_msg = str(base_resp.get("status_msg") or "")
        trace_id = str(message.get("trace_id") or "")
        if status_code != 0:
            raise ValueError(
                _format_minimax_error(
                    status_code=status_code, status_msg=status_msg, trace_id=trace_id
                )
            )
        data = message.get("data") or {}
        file_data = message.get("file") or {}
        if not isinstance(file_data, dict):
            file_data = {}
        file_id = str(
            data.get("file_id")
            or file_data.get("file_id")
            or message.get("file_id")
            or ""
        )
        if not file_id:
            raise ValueError("MiniMax file upload did not return file_id")
        extra_info = message.get("extra_info") or data.get("extra_info") or file_data
        return MiniMaxUploadedFile(
            file_id=file_id,
            extra_info=extra_info if isinstance(extra_info, dict) else {},
            trace_id=trace_id,
        )

    def _headers(self, *, json_body: bool) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers


def submit_minimax_voice_clone(
    app: Flask,
    *,
    owner_user_bid: str,
    shifu_bid: str,
    display_name: str,
    voice_id: str,
    source_audio_bytes: bytes,
    source_filename: str,
    source_content_type: str,
    source_capture_method: str,
    prompt_audio_bytes: bytes | None = None,
    prompt_filename: str = "",
    prompt_content_type: str = "",
) -> TTSMiniMaxClonedVoice:
    owner_bid = _normalize_required(owner_user_bid, "owner_user_bid")
    normalized_shifu_bid = _normalize_required(shifu_bid, "shifu_bid")
    normalized_display_name = str(display_name or "").strip()[:128]
    if not normalized_display_name:
        raise_param_error("display_name is required")
    normalized_voice_id = (voice_id or "").strip() or _generate_voice_id(owner_bid)
    if not is_valid_minimax_custom_voice_id(normalized_voice_id):
        raise_param_error("voice_id is invalid")
    _validate_audio_upload(
        source_audio_bytes,
        filename=source_filename,
        max_bytes=_MAX_SOURCE_BYTES,
    )
    if prompt_audio_bytes is not None:
        _validate_audio_upload(
            prompt_audio_bytes,
            filename=prompt_filename,
            max_bytes=_MAX_PROMPT_BYTES,
        )

    with app.app_context():
        shifu = _load_owned_shifu(owner_bid, normalized_shifu_bid)
        if (
            TTSMiniMaxClonedVoice.query.filter(
                TTSMiniMaxClonedVoice.deleted == 0,
                TTSMiniMaxClonedVoice.voice_id == normalized_voice_id,
            ).first()
            is not None
        ):
            raise_param_error("voice_id already exists")

        estimate = estimate_voice_clone_operation_credits(app)
        billing_enabled = is_billing_enabled()
        should_bill = billing_enabled and estimate.consumed_credits > _ZERO()
        if should_bill:
            admit_creator_usage(
                app,
                creator_bid=owner_bid,
                shifu_bid=shifu.shifu_bid,
                usage_scene=BILL_USAGE_SCENE_PREVIEW,
            )

        voice_bid = generate_id(app)
        reservation = None
        if should_bill:
            reservation = reserve_operation_credits(
                app,
                creator_bid=owner_bid,
                amount=estimate.consumed_credits,
                operation_type="voice_clone",
                operation_bid=voice_bid,
                metadata={"voice_id": normalized_voice_id},
            )
        try:
            source_resource = _store_resource_bytes(
                app,
                owner_user_bid=owner_bid,
                resource_kind="minimax_voice_clone_source_raw",
                filename=source_filename,
                data=source_audio_bytes,
                content_type=source_content_type or "application/octet-stream",
                object_key=f"tts/minimax/voice-clone/{voice_bid}/raw/{source_filename}",
            )
            _remember_resource_bytes(source_resource.resource_bid, source_audio_bytes)
            prompt_resource: StoredResourceRef | None = None
            if prompt_audio_bytes is not None:
                prompt_resource = _store_resource_bytes(
                    app,
                    owner_user_bid=owner_bid,
                    resource_kind="minimax_voice_clone_prompt_raw",
                    filename=prompt_filename,
                    data=prompt_audio_bytes,
                    content_type=prompt_content_type or "application/octet-stream",
                    object_key=f"tts/minimax/voice-clone/{voice_bid}/prompt/{prompt_filename}",
                )
                _remember_resource_bytes(
                    prompt_resource.resource_bid, prompt_audio_bytes
                )

            row = TTSMiniMaxClonedVoice(
                voice_bid=voice_bid,
                owner_user_bid=owner_bid,
                shifu_bid=normalized_shifu_bid,
                display_name=normalized_display_name,
                voice_id=normalized_voice_id,
                status=TTS_MINIMAX_CLONE_STATUS_QUEUED,
                status_msg="",
                source_capture_method=(source_capture_method or "upload").strip()[:32],
                source_audio_resource_bid=source_resource.resource_bid,
                source_audio_url=source_resource.url,
                source_audio_filename=str(source_filename or "")[:255],
                source_audio_content_type=str(source_content_type or "")[:128],
                prompt_audio_resource_bid=(
                    prompt_resource.resource_bid if prompt_resource is not None else ""
                ),
                prompt_audio_url=(
                    prompt_resource.url if prompt_resource is not None else ""
                ),
                prompt_audio_filename=str(prompt_filename or "")[:255],
                prompt_audio_content_type=str(prompt_content_type or "")[:128],
                billing_status=(
                    TTS_MINIMAX_CLONE_BILLING_NOT_REQUIRED
                    if not should_bill
                    else TTS_MINIMAX_CLONE_BILLING_RESERVED
                ),
                estimated_credits=estimate.consumed_credits,
                billing_reservation_bid=(
                    reservation.reservation_bid if reservation is not None else ""
                ),
                billing_ledger_bid=(
                    reservation.ledger_bid if reservation is not None else ""
                ),
            )
            db.session.add(row)
            db.session.commit()
        except Exception:
            db.session.rollback()
            if reservation is not None and reservation.reservation_bid:
                release_reserved_operation_credits(
                    app,
                    reservation_bid=reservation.reservation_bid,
                    reason="clone_submit_failed",
                )
            raise

    try:
        _enqueue_minimax_clone_task(app, voice_bid=voice_bid)
    except Exception as exc:
        with app.app_context():
            failed = _load_voice_row(voice_bid)
            failed.status = TTS_MINIMAX_CLONE_STATUS_FAILED
            failed.status_msg = _safe_status_message(exc)
            failed.failure_reason = "enqueue_failed"
            if failed.billing_reservation_bid:
                release_reserved_operation_credits(
                    app,
                    reservation_bid=failed.billing_reservation_bid,
                    reason="enqueue_failed",
                )
                failed.billing_status = TTS_MINIMAX_CLONE_BILLING_RELEASED
            db.session.commit()
            return failed

    with app.app_context():
        return _load_voice_row(voice_bid)


def run_minimax_voice_clone(
    app: Flask, *, voice_bid: str
) -> MiniMaxVoiceCloneRunResult:
    normalized_voice_bid = _normalize_required(voice_bid, "voice_bid")
    with app.app_context():
        row = _load_voice_row(normalized_voice_bid)
        if row.status == TTS_MINIMAX_CLONE_STATUS_READY:
            return MiniMaxVoiceCloneRunResult(
                status="already_ready",
                voice_bid=row.voice_bid,
                voice_id=row.voice_id,
            )
        if row.status == TTS_MINIMAX_CLONE_STATUS_PROCESSING:
            return MiniMaxVoiceCloneRunResult(
                status="already_processing",
                voice_bid=row.voice_bid,
                voice_id=row.voice_id,
            )
        if row.status not in {
            TTS_MINIMAX_CLONE_STATUS_QUEUED,
            TTS_MINIMAX_CLONE_STATUS_FAILED,
            TTS_MINIMAX_CLONE_STATUS_BILLING_PENDING,
        }:
            return MiniMaxVoiceCloneRunResult(
                status="skipped",
                voice_bid=row.voice_bid,
                voice_id=row.voice_id,
            )
        row.status = TTS_MINIMAX_CLONE_STATUS_PROCESSING
        row.status_msg = ""
        db.session.commit()

    try:
        return _execute_clone_processing(app, normalized_voice_bid)
    except Exception as exc:
        _mark_clone_failed(
            app,
            voice_bid=normalized_voice_bid,
            exc=exc,
            reason="worker_failed",
        )
        return MiniMaxVoiceCloneRunResult(
            status="failed",
            voice_bid=normalized_voice_bid,
            message=_safe_status_message(exc),
        )


def list_minimax_cloned_voices(
    app: Flask,
    *,
    owner_user_bid: str,
    shifu_bid: str = "",
    include_deleted: bool = False,
) -> list[dict[str, Any]]:
    owner_bid = _normalize_required(owner_user_bid, "owner_user_bid")
    with app.app_context():
        query = TTSMiniMaxClonedVoice.query.filter(
            TTSMiniMaxClonedVoice.owner_user_bid == owner_bid
        )
        if shifu_bid:
            query = query.filter(TTSMiniMaxClonedVoice.shifu_bid == shifu_bid)
        if not include_deleted:
            query = query.filter(TTSMiniMaxClonedVoice.deleted == 0)
        rows = query.order_by(
            TTSMiniMaxClonedVoice.created_at.desc(),
            TTSMiniMaxClonedVoice.id.desc(),
        ).all()
        return [serialize_minimax_cloned_voice(row) for row in rows]


def get_minimax_cloned_voice(
    app: Flask,
    *,
    owner_user_bid: str,
    voice_bid: str,
) -> dict[str, Any]:
    owner_bid = _normalize_required(owner_user_bid, "owner_user_bid")
    normalized_voice_bid = _normalize_required(voice_bid, "voice_bid")
    with app.app_context():
        row = _load_voice_row(normalized_voice_bid)
        if row.owner_user_bid != owner_bid:
            raise_error("server.shifu.noPermission")
        return serialize_minimax_cloned_voice(row)


def retry_minimax_voice_clone(
    app: Flask,
    *,
    owner_user_bid: str,
    voice_bid: str,
) -> dict[str, Any]:
    owner_bid = _normalize_required(owner_user_bid, "owner_user_bid")
    normalized_voice_bid = _normalize_required(voice_bid, "voice_bid")
    with app.app_context():
        row = _load_voice_row(normalized_voice_bid)
        if row.owner_user_bid != owner_bid:
            raise_error("server.shifu.noPermission")
        if row.status not in {
            TTS_MINIMAX_CLONE_STATUS_FAILED,
            TTS_MINIMAX_CLONE_STATUS_BILLING_PENDING,
        }:
            raise_param_error("voice is not retryable")
        _prepare_retry_billing(app, row)
        row.status = TTS_MINIMAX_CLONE_STATUS_QUEUED
        row.status_msg = ""
        row.failure_reason = ""
        row.retry_count = int(row.retry_count or 0) + 1
        db.session.commit()
    _enqueue_minimax_clone_task(app, voice_bid=normalized_voice_bid)
    with app.app_context():
        return serialize_minimax_cloned_voice(_load_voice_row(normalized_voice_bid))


def delete_minimax_cloned_voice(
    app: Flask,
    *,
    owner_user_bid: str,
    voice_bid: str,
) -> dict[str, Any]:
    owner_bid = _normalize_required(owner_user_bid, "owner_user_bid")
    normalized_voice_bid = _normalize_required(voice_bid, "voice_bid")
    with app.app_context():
        row = _load_voice_row(normalized_voice_bid)
        if row.owner_user_bid != owner_bid:
            raise_error("server.shifu.noPermission")
        row.deleted = 1
        row.deleted_at = datetime.now()
        db.session.commit()
        return serialize_minimax_cloned_voice(row)


def build_minimax_clone_cost(
    app: Flask,
    *,
    creator_bid: str,
    shifu_bid: str = "",
) -> dict[str, Any]:
    normalized_creator_bid = _normalize_required(creator_bid, "creator_bid")
    estimate = estimate_voice_clone_operation_credits(app)
    available = _available_wallet_credits(app, normalized_creator_bid)
    billing_enabled = is_billing_enabled()
    can_submit = (
        not billing_enabled
        or estimate.consumed_credits <= _ZERO()
        or available >= estimate.consumed_credits
    )
    return {
        "provider": "minimax",
        "model": "voice_clone",
        "billing_metric": "tts_request_count",
        "billing_enabled": billing_enabled,
        "estimated_credits": str(estimate.consumed_credits),
        "available_credits": str(available),
        "can_submit": bool(can_submit),
        "shifu_bid": shifu_bid or "",
    }


def serialize_minimax_cloned_voice(row: TTSMiniMaxClonedVoice) -> dict[str, Any]:
    return {
        "voice_bid": row.voice_bid,
        "owner_user_bid": row.owner_user_bid,
        "shifu_bid": row.shifu_bid,
        "display_name": row.display_name,
        "voice_id": row.voice_id,
        "status": row.status,
        "status_msg": row.status_msg or "",
        "failure_reason": row.failure_reason or "",
        "retry_count": int(row.retry_count or 0),
        "source_capture_method": row.source_capture_method or "",
        "source_audio_url": row.source_audio_url or "",
        "source_audio_duration_ms": int(row.source_audio_duration_ms or 0),
        "normalized_audio_url": row.normalized_audio_url or "",
        "normalized_audio_duration_ms": int(row.normalized_audio_duration_ms or 0),
        "prompt_audio_url": row.prompt_audio_url or "",
        "prompt_audio_duration_ms": int(row.prompt_audio_duration_ms or 0),
        "minimax_demo_audio_url": row.minimax_demo_audio_url or "",
        "minimax_trace_id": row.minimax_trace_id or "",
        "billing_status": row.billing_status or "",
        "estimated_credits": str(to_decimal(row.estimated_credits)),
        "charged_credits": str(to_decimal(row.charged_credits)),
        "clone_usage_bid": row.clone_usage_bid or "",
        "created_at": to_utc_iso(row.created_at),
        "updated_at": to_utc_iso(row.updated_at),
        "ready_at": to_utc_iso(row.ready_at),
        "deleted": int(row.deleted or 0),
    }


def _execute_clone_processing(
    app: Flask,
    voice_bid: str,
) -> MiniMaxVoiceCloneRunResult:
    with app.app_context():
        row = _load_voice_row(voice_bid)
        row_voice_bid = row.voice_bid
        row_voice_id = row.voice_id
        owner_user_bid = row.owner_user_bid
        source_audio_resource_bid = row.source_audio_resource_bid
        prompt_audio_resource_bid = row.prompt_audio_resource_bid
        source_filename = row.source_audio_filename or "source.webm"
        prompt_filename = row.prompt_audio_filename or "prompt.webm"
        source_bytes = _read_resource_bytes(source_audio_resource_bid)
        prompt_bytes = (
            _read_resource_bytes(prompt_audio_resource_bid)
            if prompt_audio_resource_bid
            else None
        )

    source_audio = normalize_audio_blob(
        source_bytes,
        filename=source_filename,
        purpose="source",
    )
    normalized_resource = _store_resource_bytes(
        app,
        owner_user_bid=owner_user_bid,
        resource_kind="minimax_voice_clone_source_wav",
        filename=f"{row_voice_id}.wav",
        data=source_audio.audio_bytes,
        content_type=source_audio.content_type,
        object_key=f"tts/minimax/voice-clone/{row_voice_bid}/normalized/{row_voice_id}.wav",
    )
    prompt_audio: NormalizedAudioBlob | None = None
    if prompt_bytes is not None:
        prompt_audio = normalize_audio_blob(
            prompt_bytes,
            filename=prompt_filename,
            purpose="prompt",
        )

    client = MiniMaxVoiceCloneClient()
    source_file = client.upload_clone_audio(
        source_audio.audio_bytes,
        filename=f"{row_voice_id}.wav",
        content_type=source_audio.content_type,
    )
    prompt_file_id = ""
    if prompt_audio is not None:
        prompt_file = client.upload_prompt_audio(
            prompt_audio.audio_bytes,
            filename=f"{row_voice_id}_prompt.wav",
            content_type=prompt_audio.content_type,
        )
        prompt_file_id = prompt_file.file_id

    clone_result = client.clone_voice(
        file_id=source_file.file_id,
        voice_id=row_voice_id,
        prompt_file_id=prompt_file_id,
    )
    if clone_result.input_sensitive:
        raise ValueError("MiniMax rejected the audio for sensitive content")

    with app.app_context():
        row = _load_voice_row(voice_bid)
        row.normalized_audio_resource_bid = normalized_resource.resource_bid
        row.normalized_audio_url = normalized_resource.url
        row.normalized_audio_object_key = normalized_resource.object_key
        row.normalized_audio_duration_ms = source_audio.duration_ms
        row.source_audio_duration_ms = source_audio.duration_ms
        if prompt_audio is not None:
            row.prompt_audio_duration_ms = prompt_audio.duration_ms
        row.minimax_source_file_id = source_file.file_id
        row.minimax_prompt_file_id = prompt_file_id
        row.minimax_demo_audio_url = clone_result.demo_audio
        row.minimax_trace_id = clone_result.trace_id
        row.minimax_status_code = clone_result.status_code
        row.minimax_status_msg = clone_result.status_msg
        row.minimax_extra = clone_result.extra_info
        row.status_msg = ""

        usage_bid = _record_voice_clone_usage(app, row, clone_result)
        row.clone_usage_bid = usage_bid
        if row.billing_reservation_bid:
            capture = capture_reserved_operation_credits(
                app,
                reservation_bid=row.billing_reservation_bid,
                usage_bid=usage_bid,
                metadata={
                    "voice_bid": row.voice_bid,
                    "voice_id": row.voice_id,
                    "trace_id": clone_result.trace_id,
                },
            )
            if capture.status in {"captured", "already_captured"}:
                row.billing_status = TTS_MINIMAX_CLONE_BILLING_CHARGED
                row.charged_credits = capture.amount or row.estimated_credits
            else:
                row.billing_status = TTS_MINIMAX_CLONE_BILLING_FAILED
                row.status = TTS_MINIMAX_CLONE_STATUS_BILLING_PENDING
                row.status_msg = "billing capture is pending"
                db.session.commit()
                return MiniMaxVoiceCloneRunResult(
                    status="billing_pending",
                    voice_bid=row.voice_bid,
                    voice_id=row.voice_id,
                )
        else:
            row.billing_status = TTS_MINIMAX_CLONE_BILLING_NOT_REQUIRED
            row.charged_credits = _ZERO()
        row.status = TTS_MINIMAX_CLONE_STATUS_READY
        row.ready_at = datetime.now()
        db.session.commit()
        _cleanup_raw_resources(app, row)
        return MiniMaxVoiceCloneRunResult(
            status="ready",
            voice_bid=row.voice_bid,
            voice_id=row.voice_id,
        )


def _record_voice_clone_usage(
    app: Flask,
    row: TTSMiniMaxClonedVoice,
    result: MiniMaxVoiceCloneResult,
) -> str:
    usage_context = UsageContext(
        user_bid=row.owner_user_bid,
        shifu_bid=row.shifu_bid,
        usage_scene=BILL_USAGE_SCENE_PREVIEW,
        billable=0,
    )
    return record_tts_usage(
        app,
        usage_context,
        provider="minimax",
        model="voice_clone",
        is_stream=False,
        input=len(MINIMAX_CLONE_PREVIEW_TEXT),
        output=0,
        total=len(MINIMAX_CLONE_PREVIEW_TEXT),
        word_count=0,
        duration_ms=0,
        latency_ms=0,
        extra={
            "usage_source": "minimax_voice_clone",
            "voice_bid": row.voice_bid,
            "voice_id": row.voice_id,
            "minimax_trace_id": result.trace_id,
            "minimax_extra_info": result.extra_info,
        },
        enqueue_settlement=False,
    )


def _mark_clone_failed(
    app: Flask,
    *,
    voice_bid: str,
    exc: Exception,
    reason: str,
) -> None:
    with app.app_context():
        row = _load_voice_row(voice_bid)
        row.status = TTS_MINIMAX_CLONE_STATUS_FAILED
        row.status_msg = _safe_status_message(exc)
        row.failure_reason = reason
        if row.billing_reservation_bid:
            release = release_reserved_operation_credits(
                app,
                reservation_bid=row.billing_reservation_bid,
                reason=reason,
            )
            if release.status in {"released", "already_released"}:
                row.billing_status = TTS_MINIMAX_CLONE_BILLING_RELEASED
        elif row.billing_status != TTS_MINIMAX_CLONE_BILLING_NOT_REQUIRED:
            row.billing_status = TTS_MINIMAX_CLONE_BILLING_FAILED
        db.session.commit()
        _cleanup_raw_resources(app, row)


def _prepare_retry_billing(app: Flask, row: TTSMiniMaxClonedVoice) -> None:
    estimate = estimate_voice_clone_operation_credits(app)
    billing_enabled = is_billing_enabled()
    should_bill = billing_enabled and estimate.consumed_credits > _ZERO()
    if not should_bill:
        row.billing_status = TTS_MINIMAX_CLONE_BILLING_NOT_REQUIRED
        row.estimated_credits = estimate.consumed_credits
        row.billing_reservation_bid = ""
        row.billing_ledger_bid = ""
        row.charged_credits = _ZERO()
        return

    if (
        row.billing_reservation_bid
        and row.billing_status != TTS_MINIMAX_CLONE_BILLING_RELEASED
    ):
        row.estimated_credits = estimate.consumed_credits
        return

    admit_creator_usage(
        app,
        creator_bid=row.owner_user_bid,
        shifu_bid=row.shifu_bid,
        usage_scene=BILL_USAGE_SCENE_PREVIEW,
    )
    operation_bid = (
        generate_id(app)
        if row.billing_reservation_bid
        else str(row.voice_bid or "").strip()
    )
    reservation = reserve_operation_credits(
        app,
        creator_bid=row.owner_user_bid,
        amount=estimate.consumed_credits,
        operation_type="voice_clone",
        operation_bid=operation_bid,
        metadata={
            "voice_bid": row.voice_bid,
            "voice_id": row.voice_id,
            "retry_count": int(row.retry_count or 0) + 1,
        },
    )
    row.billing_status = TTS_MINIMAX_CLONE_BILLING_RESERVED
    row.estimated_credits = estimate.consumed_credits
    row.charged_credits = _ZERO()
    row.billing_reservation_bid = reservation.reservation_bid
    row.billing_ledger_bid = reservation.ledger_bid


def _load_voice_row(voice_bid: str) -> TTSMiniMaxClonedVoice:
    row = (
        TTSMiniMaxClonedVoice.query.filter(TTSMiniMaxClonedVoice.voice_bid == voice_bid)
        .order_by(TTSMiniMaxClonedVoice.id.desc())
        .first()
    )
    if row is None:
        raise_param_error("voice_bid is invalid")
    return row


def _load_owned_shifu(owner_user_bid: str, shifu_bid: str) -> DraftShifu:
    shifu = (
        DraftShifu.query.filter(
            DraftShifu.shifu_bid == shifu_bid,
            DraftShifu.deleted == 0,
        )
        .order_by(DraftShifu.id.desc())
        .first()
    )
    if shifu is None:
        raise_error("server.shifu.shifuNotFound")
    if shifu.created_user_bid != owner_user_bid:
        raise_error("server.shifu.noPermission")
    return shifu


def _store_resource_bytes(
    app: Flask,
    *,
    owner_user_bid: str,
    resource_kind: str,
    filename: str,
    data: bytes,
    content_type: str,
    object_key: str,
) -> StoredResourceRef:
    safe_object_key = _safe_object_key(object_key)
    upload = upload_to_storage(
        app,
        file_content=io.BytesIO(data),
        object_key=safe_object_key,
        content_type=content_type,
        profile=OSS_PROFILE_COURSES,
        warm_up=False,
    )
    resource_bid = generate_id(app)
    with app.app_context():
        resource = Resource(
            resource_id=resource_bid,
            name=str(filename or resource_kind)[:255],
            type=0,
            oss_bucket=upload.bucket or "",
            oss_name=upload.object_key or safe_object_key,
            url=upload.url or "",
            status=0,
            is_deleted=0,
            created_by=owner_user_bid,
            updated_by=owner_user_bid,
        )
        db.session.add(resource)
        db.session.commit()
    _write_temp_resource_bytes(resource_bid, data)
    return StoredResourceRef(
        resource_bid=resource_bid,
        url=upload.url or "",
        object_key=upload.object_key or safe_object_key,
    )


def _delete_resource_object(app: Flask, resource_bid: str) -> None:
    normalized = str(resource_bid or "").strip()
    if not normalized:
        return
    _PENDING_AUDIO_BLOBS.pop(normalized, None)
    temp_path = _temp_resource_path(normalized)
    try:
        temp_path.unlink(missing_ok=True)
    except Exception:
        pass
    with app.app_context():
        resource = Resource.query.filter(Resource.resource_id == normalized).first()
        if resource is not None:
            resource.is_deleted = 1
            db.session.commit()


def _read_resource_bytes(resource_bid: str) -> bytes:
    normalized = str(resource_bid or "").strip()
    if not normalized:
        raise ValueError("audio resource is missing")
    if normalized in _PENDING_AUDIO_BLOBS:
        return _PENDING_AUDIO_BLOBS[normalized]
    temp_path = _temp_resource_path(normalized)
    if temp_path.exists():
        return temp_path.read_bytes()

    resource = Resource.query.filter(Resource.resource_id == normalized).first()
    if resource is not None and resource.oss_name:
        try:
            return read_storage_bytes(
                profile=OSS_PROFILE_COURSES,
                object_key=resource.oss_name,
                bucket_name=resource.oss_bucket or "",
            )
        except Exception:
            pass
    raise ValueError("source audio is no longer available")


def _cleanup_raw_resources(app: Flask, row: TTSMiniMaxClonedVoice) -> None:
    for resource_bid in (row.source_audio_resource_bid, row.prompt_audio_resource_bid):
        if resource_bid:
            try:
                _delete_resource_object(app, resource_bid)
            except Exception:
                pass


def _remember_resource_bytes(resource_bid: str, data: bytes) -> None:
    normalized = str(resource_bid or "").strip()
    if not normalized:
        return
    _PENDING_AUDIO_BLOBS[normalized] = data
    _write_temp_resource_bytes(normalized, data)


def _write_temp_resource_bytes(resource_bid: str, data: bytes) -> None:
    path = _temp_resource_path(resource_bid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _temp_resource_path(resource_bid: str) -> Path:
    return Path(tempfile.gettempdir()) / "ai-shifu-minimax-voice-clone" / resource_bid


def _enqueue_minimax_clone_task(app: Flask, *, voice_bid: str) -> bool:
    from flaskr.common.celery_app import get_celery_app

    celery_app = get_celery_app(flask_app=app)
    task = celery_app.tasks.get("tts.minimax_clone_voice")
    if task is None:
        raise RuntimeError("tts.minimax_clone_voice task is unavailable")
    task.apply_async(kwargs={"voice_bid": voice_bid})
    return True


def _validate_audio_upload(data: bytes, *, filename: str, max_bytes: int) -> None:
    if not data:
        raise_param_error("audio file is required")
    if len(data) > max_bytes:
        raise_param_error("audio file is too large")
    if _extract_extension(filename) not in _ALLOWED_INPUT_EXTENSIONS:
        raise_param_error("unsupported audio file type")


def _available_wallet_credits(app: Flask, creator_bid: str):
    from flaskr.service.billing.models import CreditWallet

    with app.app_context():
        wallet = (
            CreditWallet.query.filter(
                CreditWallet.deleted == 0,
                CreditWallet.creator_bid == creator_bid,
            )
            .order_by(CreditWallet.id.desc())
            .first()
        )
        if wallet is None:
            return _ZERO()
        return quantize_credit_amount(wallet.available_credits)


def _generate_voice_id(owner_user_bid: str) -> str:
    suffix = os.urandom(4).hex()
    prefix = re.sub(r"[^A-Za-z0-9_]", "", owner_user_bid or "")[:12] or "voice"
    if prefix and prefix[0].isdigit():
        prefix = f"v{prefix}"
    return f"AiShifu_{prefix}_{suffix}"[:64]


def _extract_extension(filename: str) -> str:
    return (
        str(filename or "").strip().rsplit(".", 1)[-1].lower()
        if "." in str(filename or "")
        else ""
    )


def _safe_object_key(object_key: str) -> str:
    normalized = str(object_key or "").replace("\\", "/").strip()
    parts = [part for part in normalized.split("/") if part not in {"", ".", ".."}]
    return "/".join(parts) or f"tts/minimax/voice-clone/{os.urandom(8).hex()}"


def _with_group_id(url: str, group_id: str) -> str:
    if not group_id:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode({'GroupId': group_id})}"


def _minimax_file_id_payload(file_id: str) -> int | str:
    normalized = str(file_id or "").strip()
    if normalized.isdigit():
        return int(normalized)
    return normalized


def _format_minimax_error(
    *,
    status_code: int,
    status_msg: str,
    trace_id: str,
) -> str:
    suffix = f", trace_id={trace_id}" if trace_id else ""
    return f"MiniMax voice clone failed: {status_code} - {status_msg or 'Unknown error'}{suffix}"


def _safe_status_message(exc: Exception) -> str:
    message = str(exc or "").strip() or "operation failed"
    return message[:512]


def _normalize_required(value: str, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise_param_error(f"{field_name} is required")
    return normalized


def _ZERO() -> Any:
    return quantize_credit_amount(0)
