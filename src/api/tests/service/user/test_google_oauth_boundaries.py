"""Verify signed OAuth state and provider failures before account mutation."""

from unittest.mock import Mock

import jwt
import pytest
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.user.auth.base import OAuthCallbackRequest, VerificationRequest
from flaskr.service.user.auth.providers import google


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, None),
        ("", None),
        (" ,en-US", None),
        (";q=0.9", None),
        ("FR", "fr"),
        ("en-us;q=0.9,zh-CN;q=0.8", "en-US"),
    ],
)
def test_browser_language_handles_absent_and_weighted_headers(
    app: object, header: str | None, expected: str | None
) -> None:
    headers = {"Accept-Language": header} if header is not None else {}
    with app.test_request_context(headers=headers):
        assert google._extract_browser_language() == expected


def test_signed_state_round_trips_and_is_not_reusable_with_another_secret(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = {
        "language": "fr-FR",
        "origin": "https://example.com",
        "initiator_user_id": "temporary",
    }
    state = google._encode_state(app, payload)
    assert google._decode_state(app, state) == payload
    claims = jwt.decode(state, app.config["SECRET_KEY"], algorithms=["HS256"])
    assert claims["exp"] - claims["iat"] == google.STATE_TTL
    assert len(claims["nonce"]) == 32
    monkeypatch.setitem(app.config, "SECRET_KEY", "different-test-secret")
    assert google._decode_state(app, state) is None


@pytest.mark.parametrize("payload", [None, [], "not-a-mapping"])
def test_state_rejects_signed_non_object_payload(app: object, payload: object) -> None:
    state = jwt.encode(
        {"payload": payload}, app.config["SECRET_KEY"], algorithm="HS256"
    )
    assert google._decode_state(app, state) is None


def test_state_rejects_expired_and_malformed_tokens(app: object) -> None:
    expired = jwt.encode(
        {"exp": 1, "payload": {"language": "en-US"}},
        app.config["SECRET_KEY"],
        algorithm="HS256",
    )
    assert google._decode_state(app, expired) is None
    assert google._decode_state(app, "invalid-token") is None


@pytest.mark.parametrize("state", [None, "", "not-signed"])
def test_invalid_return_state_never_resolves_an_origin(
    app: object, monkeypatch: pytest.MonkeyPatch, state: str | None
) -> None:
    resolver = Mock()
    monkeypatch.setattr(google, "resolve_oauth_return_origin", resolver)
    assert google.resolve_state_return_origin(app, state) == ""
    resolver.assert_not_called()


def test_return_origin_is_revalidated_when_the_signed_state_is_resolved(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = google._encode_state(app, {"origin": "https://revoked.example.com"})
    resolver = Mock(return_value="")
    monkeypatch.setattr(google, "resolve_oauth_return_origin", resolver)
    assert google.resolve_state_return_origin(app, state) == ""
    resolver.assert_called_once_with(app, "https://revoked.example.com")


@pytest.mark.parametrize(
    ("language", "browser_language", "expected"),
    [
        ("fr-FR", "en-US", "fr-FR"),
        (None, "en-us,en;q=0.9", "en-US"),
        (None, None, None),
    ],
)
def test_authorization_redirect_persists_language_and_uses_canonical_callback(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    language: str | None,
    browser_language: str | None,
    expected: str | None,
) -> None:
    session = Mock()
    session.create_authorization_url.return_value = (
        "https://accounts.google.com/authorization",
        "provider-state",
    )
    creator = Mock(return_value=session)
    monkeypatch.setattr(google.GoogleAuthProvider, "_create_session", creator)
    monkeypatch.setattr(
        google,
        "build_google_oauth_callback_url",
        lambda: "https://login.example.com/callback",
    )
    monkeypatch.setattr(google, "resolve_oauth_return_origin", lambda _app, _origin: "")
    headers = {"Accept-Language": browser_language} if browser_language else {}
    with app.test_request_context(headers=headers):
        result = google.GoogleAuthProvider().begin_oauth(
            app,
            {
                "language": language,
                "redirect_uri": "https://untrusted.example.com/callback",
                "login_context": "admin",
            },
        )
    creator.assert_called_once_with(app, "https://login.example.com/callback")
    claims = google._decode_state(app, result["state"])
    assert claims["redirect_uri"] == "https://login.example.com/callback"
    assert claims["login_context"] == "admin"
    assert claims.get("language") == expected
    kwargs = session.create_authorization_url.call_args.kwargs
    assert kwargs.get("hl") == expected
    assert kwargs.get("ui_locales") == expected
    assert "prompt" not in kwargs
    assert "access_type" not in kwargs
    assert result["authorization_url"] == "https://accounts.google.com/authorization"


@pytest.mark.parametrize(
    ("code", "state"),
    [(None, None), ("code", None), (None, "state"), ("code", "invalid-state")],
)
def test_callback_rejects_invalid_input_before_calling_google(
    app: object, monkeypatch: pytest.MonkeyPatch, code: str | None, state: str | None
) -> None:
    creator = Mock()
    monkeypatch.setattr(google.GoogleAuthProvider, "_create_session", creator)
    with app.test_request_context(), pytest.raises(AppError) as error:
        google.GoogleAuthProvider().handle_oauth_callback(
            app, OAuthCallbackRequest(code=code, state=state)
        )
    assert error.value.code == ERROR_CODE["server.user.googleOAuthStateInvalid"]
    creator.assert_not_called()


@pytest.mark.parametrize(
    "profile", [{}, {"sub": "subject"}, {"email": "person@example.com"}]
)
def test_missing_google_identity_does_not_mutate_accounts(
    app: object, monkeypatch: pytest.MonkeyPatch, profile: dict
) -> None:
    session = Mock()
    session.get.return_value.json.return_value = profile
    monkeypatch.setattr(
        google.GoogleAuthProvider, "_create_session", Mock(return_value=session)
    )
    lookup = Mock()
    monkeypatch.setattr(google, "find_credential", lookup)
    with (
        app.test_request_context(),
        pytest.raises(RuntimeError, match="missing required identifiers"),
    ):
        google.GoogleAuthProvider().handle_oauth_callback(
            app,
            OAuthCallbackRequest(
                code="code", state=google._encode_state(app, {"language": "en-US"})
            ),
        )
    lookup.assert_not_called()
    session.get.return_value.raise_for_status.assert_called_once()


def test_google_provider_does_not_accept_code_based_verification(app: object) -> None:
    with pytest.raises(NotImplementedError, match="only supports OAuth"):
        google.GoogleAuthProvider().verify(
            app, VerificationRequest(identifier="person@example.com", code="1234")
        )
