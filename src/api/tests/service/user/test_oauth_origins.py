"""Origin validation for the shared Google OAuth callback.

All domains share one Google callback because Google rejects wildcards in a
client's authorized redirect URIs. Handing the browser back to the domain it
started from is an open redirect unless the origin is checked, so these tests
pin that check down.
"""

from __future__ import annotations

import flaskr.common.config as common_config
import pytest
from flaskr.service.common.models import AppError
from flaskr.service.user.auth import oauth_origins
from flaskr.service.user.auth.providers.google import (
    _encode_state,
    _require_matching_initiator,
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


class TestNormalizeOrigin:
    """Only the hostname is checked downstream, so nothing else may survive."""

    def test_bare_origin_is_kept(self) -> None:
        assert oauth_origins.normalize_origin(CUSTOM_ORIGIN) == CUSTOM_ORIGIN

    def test_explicit_default_port_is_dropped(self) -> None:
        # Must equal the browser's window.location.origin, or the callback page
        # would forward to a URL it considers different and loop.
        assert oauth_origins.normalize_origin(f"{CUSTOM_ORIGIN}:443") == CUSTOM_ORIGIN
        assert (
            oauth_origins.normalize_origin(f"http://{CUSTOM_DOMAIN}:80")
            == f"http://{CUSTOM_DOMAIN}"
        )

    def test_non_default_port_is_refused(self) -> None:
        assert oauth_origins.normalize_origin(f"{CUSTOM_ORIGIN}:8443") == ""

    def test_userinfo_is_refused(self) -> None:
        assert oauth_origins.normalize_origin(f"https://evil@{CUSTOM_DOMAIN}") == ""
        assert (
            oauth_origins.normalize_origin(f"https://user:pass@{CUSTOM_DOMAIN}:8443")
            == ""
        )

    def test_malformed_port_is_refused(self) -> None:
        assert oauth_origins.normalize_origin(f"{CUSTOM_ORIGIN}:notaport") == ""


class TestPortAndUserinfoAreNotServedDomains:
    """The hostname check must not be reachable with a decorated origin."""

    @pytest.mark.usefixtures("_verified_custom_domain")
    def test_non_default_port_on_a_verified_domain_is_refused(self, app) -> None:
        assert (
            oauth_origins.is_allowed_oauth_origin(app, f"{CUSTOM_ORIGIN}:8443") is False
        )

    @pytest.mark.usefixtures("_verified_custom_domain")
    def test_userinfo_on_a_verified_domain_is_refused(self, app) -> None:
        assert (
            oauth_origins.is_allowed_oauth_origin(app, f"https://evil@{CUSTOM_DOMAIN}")
            is False
        )

    @pytest.mark.usefixtures("_verified_custom_domain")
    def test_explicit_default_port_still_resolves(self, app) -> None:
        assert (
            oauth_origins.resolve_oauth_return_origin(app, f"{CUSTOM_ORIGIN}:443")
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


class TestInitiatorPairing:
    """The return origin comes from forgeable headers, so it is only honored
    together with the session that started the flow.

    Without this, an attacker who owns a verified custom domain could start a
    login with a forged Origin naming their own domain, get a victim to
    authorize, and have the authorization code delivered to them.
    """

    def test_the_starting_session_may_complete_the_flow(self) -> None:
        payload = {"origin": CUSTOM_ORIGIN, "initiator_user_id": "user-1"}
        _require_matching_initiator(payload, "user-1")

    def test_another_session_cannot_complete_the_flow(self, app) -> None:
        # The attack: the code is handed to a domain the victim's session did
        # not start the login from.
        payload = {"origin": CUSTOM_ORIGIN, "initiator_user_id": "attacker"}
        with app.app_context(), pytest.raises(AppError):
            _require_matching_initiator(payload, "victim")

    def test_an_anonymous_callback_cannot_complete_a_forwarded_flow(self, app) -> None:
        payload = {"origin": CUSTOM_ORIGIN, "initiator_user_id": "user-1"}
        for anonymous in (None, "", "   "):
            with app.app_context(), pytest.raises(AppError):
                _require_matching_initiator(payload, anonymous)

    def test_an_origin_without_an_initiator_is_refused(self, app) -> None:
        # A state carrying an origin but no initiator cannot be paired, so it
        # must not be usable rather than falling through unchecked.
        payload = {"origin": CUSTOM_ORIGIN}
        with app.app_context(), pytest.raises(AppError):
            _require_matching_initiator(payload, "user-1")

    def test_same_domain_flows_are_unaffected(self) -> None:
        # No origin means no forwarding, which is the pre-existing behavior and
        # must keep working for anonymous sign-in.
        _require_matching_initiator({}, None)
        _require_matching_initiator({"initiator_user_id": "user-1"}, None)
