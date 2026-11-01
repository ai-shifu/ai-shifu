"""Tencent Cloud API v3 (TC3-HMAC-SHA256) request signing.

Shared by the TRTC SSE provider and the TextToVoice provider. Both sign a
JSON ``POST /`` request over the ``content-type;host;x-tc-action`` headers.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import time

TC3_ALGORITHM = "TC3-HMAC-SHA256"


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _tc3_sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def build_tc3_headers(
    *,
    host: str,
    service: str,
    action: str,
    version: str,
    region: str,
    payload_json: str,
    secret_id: str,
    secret_key: str,
    timestamp: int | None = None,
    accept: str | None = None,
) -> dict[str, str]:
    """Build signed TC3 request headers for a JSON POST to ``host``.

    ``accept`` adds an ``Accept`` header right after ``Content-Type``; it is
    not part of the signed headers.
    """
    request_timestamp = int(timestamp if timestamp is not None else time.time())
    request_date = dt.datetime.fromtimestamp(
        request_timestamp,
        tz=dt.UTC,
    ).strftime("%Y-%m-%d")
    canonical_headers = (
        f"content-type:application/json\nhost:{host}\nx-tc-action:{action.lower()}\n"
    )
    signed_headers = "content-type;host;x-tc-action"
    canonical_request = "\n".join(
        [
            "POST",
            "/",
            "",
            canonical_headers,
            signed_headers,
            _sha256_hex(payload_json),
        ]
    )
    credential_scope = f"{request_date}/{service}/tc3_request"
    string_to_sign = "\n".join(
        [
            TC3_ALGORITHM,
            str(request_timestamp),
            credential_scope,
            _sha256_hex(canonical_request),
        ]
    )
    secret_date = _tc3_sign(
        ("TC3" + str(secret_key or "")).encode("utf-8"), request_date
    )
    secret_service = _tc3_sign(secret_date, service)
    secret_signing = _tc3_sign(secret_service, "tc3_request")
    signature = hmac.new(
        secret_signing,
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    authorization = (
        f"{TC3_ALGORITHM} Credential={secret_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    headers = {
        "Authorization": authorization,
        "Content-Type": "application/json",
    }
    if accept is not None:
        headers["Accept"] = accept
    headers.update(
        {
            "Host": host,
            "X-TC-Action": action,
            "X-TC-Version": version,
            "X-TC-Region": region,
            "X-TC-Timestamp": str(request_timestamp),
        }
    )
    return headers
