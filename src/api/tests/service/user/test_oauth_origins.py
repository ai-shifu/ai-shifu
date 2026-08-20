"""Origin validation for the shared Google OAuth callback.

All domains share one Google callback because Google rejects wildcards in a
client's authorized redirect URIs. Handing the browser back to the domain it
started from is an open redirect unless the origin is checked, so these tests
pin that check down.
"""

from __future__ import annotations

import flaskr.common.config as common_config
import pytest
from flaskr.service.user.auth import oauth_origins
from flaskr.service.user.auth.providers.google import (
    _encode_state,
    resolve_state_return_origin,
)

PLATFORM_CALLBACK = "https://app.example.com/login/google-callback"
PLATFORM_ORIGIN = "https://app.example.com"
CUSTOM_DOMAIN = "learn.customer.example"
CUSTOM_ORIGIN = f"https://{CUSTOM_DOMAIN}"


def _reset_config_cache(*keys: str) -> None:
    for key in keys:
        common_config.__ENHANCED_CONFIG__._cache.pop(key, None)  # noqa: SLF001


@pytest.fixture(autouse=True)
def _shared_callback(monkeypatch):
    """Pin the deployment to one shared callback URL."""
    _reset_config_cache("HOST_URL", "GOOGLE_OAUTH_REDIRECT_URI")
    monkeypatch.setattr(
        oauth_origins,
        "build_google_oauth_callback_url",
        lambda: PLATFORM_CALLBACK,
    )
    monkeypatch.setattr(oauth_origins, "resolve_public_origin", lambda: PLATFORM_ORIGIN)
    yield
    _reset_config_cache("HOST_URL", "GOOGLE_OAUTH_REDIRECT_URI")


@pytest.fixture
def _verified_custom_domain(monkeypatch):
    """Treat exactly one host as a verified, TLS-active custom domain."""
    monkeypatch.setattr(
        oauth_origins,
        "_resolve_creator_bid_by_host",
        lambda app, host: "creator-1" if host == CUSTOM_DOMAIN else None,
    )


class TestIsAllowedOAuthOrigin:
    def test_platform_origin_is_allowed(self, app) -> None:
        assert oauth_origins.is_allowed_oauth_origin(app, PLATFORM_ORIGIN) is True

    @pytest.mark.usefixtures("_verified_custom_domain")
    def test_verified_custom_domain_is_allowed(self, app) -> None:
        assert oauth_origins.is_allowed_oauth_origin(app, CUSTOM_ORIGIN) is True

    @pytest.mark.usefixtures("_verified_custom_domain")
    def test_unknown_domain_is_refused(self, app) -> None:
        # The open-redirect case: an attacker-controlled origin in the state.
        assert (
            oauth_origins.is_allowed_oauth_origin(app, "https://evil.example") is False
        )

    def test_unverified_custom_domain_is_refused(self, app, monkeypatch) -> None:
        # Not yet verified, or entitlement revoked -> no hand-back.
        monkeypatch.setattr(
            oauth_origins, "_resolve_creator_bid_by_host", lambda app, host: None
        )
        assert oauth_origins.is_allowed_oauth_origin(app, CUSTOM_ORIGIN) is False

    @pytest.mark.usefixtures("_verified_custom_domain")
    def test_http_custom_domain_is_refused(self, app) -> None:
        # Only https custom domains are served; refuse a plaintext look-alike.
        assert (
            oauth_origins.is_allowed_oauth_origin(app, f"http://{CUSTOM_DOMAIN}")
            is False
        )

    def test_lookup_failure_refuses_rather_than_allows(self, app, monkeypatch) -> None:
        def _boom(app, host):
            raise RuntimeError("database is down")

        monkeypatch.setattr(oauth_origins, "_resolve_creator_bid_by_host", _boom)
        assert oauth_origins.is_allowed_oauth_origin(app, CUSTOM_ORIGIN) is False

    @pytest.mark.parametrize(
        "value", ["", None, "not-a-url", "javascript:alert(1)", "//evil.example"]
    )
    def test_malformed_origins_are_refused(self, app, value) -> None:
        assert oauth_origins.is_allowed_oauth_origin(app, value) is False

    @pytest.mark.usefixtures("_verified_custom_domain")
    def test_path_and_query_are_stripped(self, app) -> None:
        assert (
            oauth_origins.resolve_oauth_return_origin(
                app, f"{CUSTOM_ORIGIN}/login/google-callback?next=/x"
            )
            == CUSTOM_ORIGIN
        )


class TestResolveStateReturnOrigin:
    @pytest.mark.usefixtures("_verified_custom_domain")
    def test_returns_the_recorded_origin(self, app) -> None:
        state = _encode_state(app, {"origin": CUSTOM_ORIGIN})
        assert resolve_state_return_origin(app, state) == CUSTOM_ORIGIN

    def test_revoked_domain_is_refused_mid_flight(self, app, monkeypatch) -> None:
        # State was minted while the domain was valid; it no longer is.
        state = _encode_state(app, {"origin": CUSTOM_ORIGIN})
        monkeypatch.setattr(
            oauth_origins, "_resolve_creator_bid_by_host", lambda app, host: None
        )
        assert resolve_state_return_origin(app, state) == ""

    def test_state_without_origin_returns_empty(self, app) -> None:
        state = _encode_state(app, {"login_context": "default"})
        assert resolve_state_return_origin(app, state) == ""

    def test_tampered_state_returns_empty(self, app) -> None:
        assert resolve_state_return_origin(app, "not-a-valid-jwt") == ""

    def test_missing_state_returns_empty(self, app) -> None:
        assert resolve_state_return_origin(app, None) == ""
