from __future__ import annotations

from urllib.parse import urlencode, urlsplit, urlunsplit

from flask import has_request_context, request

from flaskr.service.config import get_config


GOOGLE_OAUTH_CALLBACK_PATH = "/login/google-callback"
STRIPE_LEARNER_RESULT_PATH = "/payment/stripe/result"
STRIPE_BILLING_RESULT_PATH = "/payment/stripe/billing-result"


def build_google_oauth_callback_url() -> str:
    return build_public_url(GOOGLE_OAUTH_CALLBACK_PATH)


def build_alipay_notify_url() -> str:
    return build_public_url(_api_path("/callback/alipay-notify"))


def build_wechatpay_notify_url() -> str:
    return build_public_url(_api_path("/callback/wechatpay-notify"))


def build_stripe_learner_result_url(*, canceled: bool = False) -> str:
    return _with_canceled(build_public_url(STRIPE_LEARNER_RESULT_PATH), canceled)


def build_stripe_billing_result_url(*, canceled: bool = False) -> str:
    return _with_canceled(build_public_url(STRIPE_BILLING_RESULT_PATH), canceled)


def build_public_url(path: str) -> str:
    origin = resolve_public_origin()
    normalized_path = _normalize_path(path)
    return f"{origin}{normalized_path}"


def resolve_public_origin() -> str:
    configured_origin = _normalize_origin(str(get_config("HOST_URL", "") or ""))
    if configured_origin:
        return configured_origin

    request_origin = _request_origin()
    if request_origin:
        return request_origin

    raise RuntimeError("HOST_URL must be configured to build public callback URLs")


def _api_path(path: str) -> str:
    prefix = str(get_config("PATH_PREFIX", "/api") or "/api").strip() or "/api"
    if not prefix.startswith("/"):
        prefix = f"/{prefix}"
    prefix = prefix.rstrip("/")
    return f"{prefix}{_normalize_path(path)}"


def _request_origin() -> str:
    if not has_request_context():
        return ""

    origin = _first_header_value(request.headers.get("Origin"))
    if origin and origin.lower() != "null":
        return _normalize_origin(origin)

    forwarded_proto = _first_header_value(request.headers.get("X-Forwarded-Proto"))
    forwarded_host = _first_header_value(request.headers.get("X-Forwarded-Host"))
    scheme = forwarded_proto or request.scheme
    host = forwarded_host or request.host
    return _normalize_origin(f"{scheme}://{host}")


def _normalize_origin(value: str) -> str:
    raw_value = str(value or "").strip().rstrip("/")
    if not raw_value:
        return ""

    parsed = urlsplit(raw_value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("HOST_URL must include http(s) scheme and host")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise RuntimeError(
            "HOST_URL must be an origin without path, query, or fragment"
        )
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _normalize_path(path: str) -> str:
    normalized = str(path or "").strip()
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return normalized


def _first_header_value(value: str | None) -> str:
    return str(value or "").split(",", 1)[0].strip()


def _with_canceled(url: str, canceled: bool) -> str:
    if not canceled:
        return url
    parsed = urlsplit(url)
    query = urlencode({"canceled": "1"})
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment)
    )
