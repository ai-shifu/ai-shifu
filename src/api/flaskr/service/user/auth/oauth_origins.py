"""Validation for the origin an OAuth flow returns the browser to.

Google rejects wildcards in a client's authorized redirect URIs, so every
white-label domain would otherwise need its own entry in the Google console.
Instead all domains share one callback and the browser is sent back to the
domain it started from. That hand-back is an open redirect unless the origin is
checked against domains we actually serve, which is what this module does.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from flask import Flask
from flaskr.common.public_urls import (
    build_google_oauth_callback_url,
    resolve_public_origin,
)

DEFAULT_PORTS = {"http": 80, "https": 443}


def normalize_origin(value: Any) -> str:
    """Reduce a URL to a bare ``scheme://host`` origin, or "" if unusable.

    Credentials and non-default ports are refused rather than carried through:
    only the hostname is checked against our custom domains, so keeping either
    would let ``https://someone@customer.example:8443`` pass that check and then
    be handed the authorization code. An explicit default port is dropped so the
    result compares equal to the browser's own ``window.location.origin``.
    """
    raw_value = str(value or "").strip().rstrip("/")
    if not raw_value:
        return ""
    try:
        parsed = urlsplit(raw_value)
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"}:
        return ""
    if parsed.username or parsed.password:
        return ""
    try:
        port = parsed.port
    except ValueError:
        return ""
    if port is not None and port != DEFAULT_PORTS[parsed.scheme]:
        return ""
    hostname = parsed.hostname
    if not hostname:
        return ""
    return urlunsplit((parsed.scheme, hostname, "", "", ""))


def is_allowed_oauth_origin(app: Flask, origin: Any) -> bool:
    """Return whether the browser may be handed back to this origin.

    Allowed are the deployment's own origin, the origin of the configured
    shared callback, and any custom domain that is verified, TLS-active, and
    still entitled to custom domains.
    """
    normalized_origin = normalize_origin(origin)
    if not normalized_origin:
        return False

    if normalized_origin in _platform_origins():
        return True

    host = urlsplit(normalized_origin).hostname or ""
    if not host:
        return False

    # Only https custom domains are served, so refuse an http look-alike.
    if urlsplit(normalized_origin).scheme != "https":
        return False

    try:
        return _resolve_creator_bid_by_host(app, host) is not None
    except Exception:  # noqa: BLE001 - a lookup failure must never allow an origin
        return False


def resolve_oauth_return_origin(app: Flask, origin: Any) -> str:
    """Return the origin to hand back to, or "" when it is not allowed."""
    normalized_origin = normalize_origin(origin)
    if not normalized_origin:
        return ""
    if not is_allowed_oauth_origin(app, normalized_origin):
        return ""
    return normalized_origin


def _platform_origins() -> set[str]:
    origins: set[str] = set()
    for candidate in (_configured_callback_origin(), _deployment_origin()):
        if candidate:
            origins.add(candidate)
    return origins


def _configured_callback_origin() -> str:
    try:
        return normalize_origin(build_google_oauth_callback_url())
    except RuntimeError:
        return ""


def _deployment_origin() -> str:
    try:
        return normalize_origin(resolve_public_origin())
    except RuntimeError:
        return ""


def _resolve_creator_bid_by_host(app: Flask, host: str) -> str | None:
    # Imported lazily: the user service must not take a hard dependency on
    # billing, which already reaches into user the same way.
    domains = import_module("flaskr.service.billing.domains")
    return domains.resolve_creator_bid_by_host(app, host)
