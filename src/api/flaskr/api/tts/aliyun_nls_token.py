"""
Aliyun NLS token helper.

Aliyun RESTful TTS requires a short-lived NLS access token. This module fetches
the token via Aliyun POP OpenAPI (CreateToken) and caches it in Redis when
available, falling back to a process-local in-memory cache when Redis is not
configured.

Docs:
- CreateToken (POP OpenAPI): https://help.aliyun.com/zh/isi/getting-started/obtain-an-access-token
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional, Tuple
from urllib.parse import quote

import requests

from flaskr.common.cache_provider import cache
from flaskr.common.config import get_config
from flaskr.common.log import AppLoggerProxy


logger = AppLoggerProxy(logging.getLogger(__name__))


NLS_META_ENDPOINT = "https://nls-meta.cn-shanghai.aliyuncs.com/"
NLS_CREATE_TOKEN_ACTION = "CreateToken"
NLS_CREATE_TOKEN_VERSION = "2019-02-28"
NLS_CREATE_TOKEN_REGION_ID = "cn-shanghai"

# Refresh slightly early to avoid edge cases around clock skew.
_DEFAULT_REFRESH_LEEWAY_SECONDS = 60


@dataclass(frozen=True)
class AliyunNlsToken:
    token: str
    expire_time: int  # unix epoch seconds

    @property
    def expires_in_seconds(self) -> int:
        return max(0, int(self.expire_time - time.time()))

    def is_expired(self, now: Optional[float] = None) -> bool:
        now_ts = time.time() if now is None else float(now)
        return self.expire_time <= int(now_ts)


def _percent_encode(value: Any) -> str:
    """
    RFC3986 percent encoding compatible with Aliyun POP signing rules.
    """

    if value is None:
        value = ""
    return quote(str(value), safe="-_.~")


def _canonicalized_query(params: dict[str, Any]) -> str:
    """
    Build canonicalized query string from params (excluding Signature).
    """

    parts: list[str] = []
    for key in sorted(params.keys()):
        parts.append(f"{_percent_encode(key)}={_percent_encode(params[key])}")
    return "&".join(parts)


def _string_to_sign(http_method: str, url_path: str, canonical_query: str) -> str:
    return (
        f"{http_method}&{_percent_encode(url_path)}&{_percent_encode(canonical_query)}"
    )


def _sign(string_to_sign: str, access_key_secret: str) -> str:
    mac = hmac.new(
        (access_key_secret + "&").encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha1,
    )
    signature = base64.b64encode(mac.digest()).decode("utf-8")
    return _percent_encode(signature)


def _iso8601_utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _generate_nonce() -> str:
    return str(uuid.uuid4())


def _get_cache_key() -> str:
    prefix = get_config("REDIS_KEY_PREFIX", "") or ""
    return f"{prefix}tts:aliyun:nls_token"


def _get_lock_key() -> str:
    prefix = get_config("REDIS_KEY_PREFIX", "") or ""
    return f"{prefix}tts:aliyun:nls_token:lock"


def _decode_cache_value(raw: Any) -> Optional[AliyunNlsToken]:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if not isinstance(raw, str):
        raw = str(raw)
    raw = raw.strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    token = (data.get("token") or "").strip()
    expire_time = data.get("expire_time")
    try:
        expire_int = int(expire_time)
    except Exception:
        expire_int = 0
    if not token or expire_int <= 0:
        return None
    return AliyunNlsToken(token=token, expire_time=expire_int)


def _store_cache_value(value: AliyunNlsToken) -> None:
    ttl_seconds = max(1, int(value.expire_time - time.time()))
    payload = json.dumps({"token": value.token, "expire_time": value.expire_time})
    cache.set(_get_cache_key(), payload, ex=ttl_seconds)


def _get_access_keys() -> Tuple[str, str]:
    """
    Resolve AccessKeyId/AccessKeySecret for NLS CreateToken.

    Prefer the dedicated variables from Aliyun docs. Fall back to OSS keys when
    present to reduce configuration friction in deployments that already have
    Alibaba Cloud account keys configured.
    """

    ak_id = (get_config("ALIYUN_AK_ID") or "").strip()
    ak_secret = (get_config("ALIYUN_AK_SECRET") or "").strip()
    if ak_id and ak_secret:
        return ak_id, ak_secret

    oss_id = (get_config("ALIBABA_CLOUD_OSS_ACCESS_KEY_ID") or "").strip()
    oss_secret = (get_config("ALIBABA_CLOUD_OSS_ACCESS_KEY_SECRET") or "").strip()
    if oss_id and oss_secret:
        return oss_id, oss_secret

    return "", ""


def _request_new_token(access_key_id: str, access_key_secret: str) -> AliyunNlsToken:
    params = {
        "AccessKeyId": access_key_id,
        "Action": NLS_CREATE_TOKEN_ACTION,
        "Version": NLS_CREATE_TOKEN_VERSION,
        "Format": "JSON",
        "RegionId": NLS_CREATE_TOKEN_REGION_ID,
        "Timestamp": _iso8601_utc_now(),
        "SignatureMethod": "HMAC-SHA1",
        "SignatureVersion": "1.0",
        "SignatureNonce": _generate_nonce(),
    }
    canonical_query = _canonicalized_query(params)
    string_to_sign = _string_to_sign("GET", "/", canonical_query)
    signature = _sign(string_to_sign, access_key_secret)
    url = f"{NLS_META_ENDPOINT}?Signature={signature}&{canonical_query}"

    try:
        resp = requests.get(url, headers={"Accept": "application/json"}, timeout=10)
    except requests.RequestException as exc:
        raise ValueError(f"Aliyun NLS token request failed: {exc}") from exc

    if resp.status_code != 200:
        # POP errors are JSON with fields like Code/Message/RequestId.
        text = (resp.text or "").strip()
        raise ValueError(
            f"Aliyun NLS token request failed: HTTP {resp.status_code}: {text[:200]}"
        )

    try:
        payload = resp.json()
    except Exception as exc:
        raise ValueError(
            f"Aliyun NLS token response is not valid JSON: {resp.text[:200]}"
        ) from exc

    token_obj = payload.get("Token") or {}
    token = (token_obj.get("Id") or "").strip()
    expire_time = token_obj.get("ExpireTime")
    if not token or expire_time is None:
        request_id = payload.get("RequestId") or payload.get("NlsRequestId") or ""
        suffix = f" (request_id={request_id})" if request_id else ""
        raise ValueError(
            "Aliyun NLS token response missing Token.Id or Token.ExpireTime" + suffix
        )

    try:
        expire_int = int(expire_time)
    except Exception as exc:
        raise ValueError(
            f"Aliyun NLS token response has invalid ExpireTime: {expire_time}"
        ) from exc

    return AliyunNlsToken(token=token, expire_time=expire_int)


def get_aliyun_nls_token(
    *,
    force_refresh: bool = False,
    refresh_leeway_seconds: int = _DEFAULT_REFRESH_LEEWAY_SECONDS,
) -> str:
    """
    Get a valid Aliyun NLS access token for RESTful TTS.

    Resolution order:
    1) Use `ALIYUN_TTS_TOKEN` when explicitly configured (manual override).
    2) Use cached token from Redis/in-memory cache.
    3) Fetch a new token using `ALIYUN_AK_ID` + `ALIYUN_AK_SECRET` (or OSS key fallback),
       cache it, and return it.
    """

    override = (get_config("ALIYUN_TTS_TOKEN") or "").strip()
    if override:
        return override

    now = time.time()
    cached = None if force_refresh else _decode_cache_value(cache.get(_get_cache_key()))
    if (
        cached
        and not cached.is_expired(now=now)
        and cached.expires_in_seconds > refresh_leeway_seconds
    ):
        return cached.token

    access_key_id, access_key_secret = _get_access_keys()
    if not access_key_id or not access_key_secret:
        raise ValueError(
            "Aliyun NLS token is not configured. Set ALIYUN_TTS_TOKEN, or set "
            "ALIYUN_AK_ID and ALIYUN_AK_SECRET to auto-fetch a temporary token."
        )

    lock = cache.lock(_get_lock_key(), timeout=15, blocking_timeout=2)
    acquired = False
    try:
        acquired = bool(lock.acquire(blocking=True, blocking_timeout=2))
        if acquired and not force_refresh:
            # Double-check cache after acquiring lock.
            cached2 = _decode_cache_value(cache.get(_get_cache_key()))
            if (
                cached2
                and not cached2.is_expired(now=now)
                and cached2.expires_in_seconds > refresh_leeway_seconds
            ):
                return cached2.token

        try:
            fresh = _request_new_token(access_key_id, access_key_secret)
            _store_cache_value(fresh)
            logger.info(
                "Fetched Aliyun NLS token (expires_in=%ss)",
                max(0, int(fresh.expire_time - time.time())),
            )
            return fresh.token
        except Exception as exc:
            # If we still have a cached token that hasn't expired, use it as a fallback.
            if cached and not cached.is_expired(now=now):
                logger.warning(
                    "Aliyun NLS token refresh failed, falling back to cached token: %s",
                    str(exc)[:200],
                )
                return cached.token
            raise
    finally:
        if acquired:
            try:
                lock.release()
            except Exception:
                pass


def is_aliyun_nls_token_configured() -> bool:
    """
    Return True if the service has enough configuration to obtain an NLS token.

    This function does not perform any network requests.
    """

    if (get_config("ALIYUN_TTS_TOKEN") or "").strip():
        return True
    access_key_id, access_key_secret = _get_access_keys()
    return bool(access_key_id and access_key_secret)
