"""Exercise the security boundaries protected by the Authlib and DNS upgrades."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from urllib.parse import parse_qs

import dns.exception
import dns.name
import pytest
import requests
from authlib.integrations.requests_client import OAuth2Session
from authlib.jose import JsonWebSignature, jwt
from authlib.jose.errors import BadSignatureError
from authlib.jose.rfc7518 import OctKey


def _base64url(value: bytes) -> bytes:
    return base64.urlsafe_b64encode(value).rstrip(b"=")


@pytest.mark.parametrize("algorithm", ["HS256", "HS384", "HS512"])
@pytest.mark.parametrize("key_form", ["bytes", "string", "jwk", "key", "resolver"])
def test_authlib_rejects_forged_tokens_with_empty_hmac_keys(
    algorithm: str, key_form: str
) -> None:
    empty_jwk = {"kty": "oct", "k": ""}
    keys = {
        "bytes": b"",
        "string": "",
        "jwk": empty_jwk,
        "key": OctKey.import_key(empty_jwk),
        "resolver": lambda _header, _payload: "",
    }
    signing_input = b".".join(
        _base64url(json.dumps(value).encode())
        for value in ({"alg": algorithm}, {"sub": "untrusted-user"})
    )
    signature = hmac.new(
        b"", signing_input, getattr(hashlib, f"sha{algorithm[2:]}")
    ).digest()
    forged = signing_input + b"." + _base64url(signature)

    with pytest.raises(ValueError, match="must not be empty"):
        jwt.decode(forged, keys[key_form])


@pytest.mark.parametrize("key", [None, "configured-verification-key"])
def test_authlib_rejects_jws_without_any_signatures(key: str | None) -> None:
    verifier = JsonWebSignature(algorithms=["HS256"])
    forged = {
        "payload": _base64url(b'{"sub":"untrusted-user"}').decode(),
        "signatures": [],
    }

    with pytest.raises(BadSignatureError):
        verifier.deserialize_json(forged, key)


def test_authlib_preserves_signed_tokens_and_rejects_tampering() -> None:
    verifier = JsonWebSignature(algorithms=["HS256"])
    key = b"test-only-hmac-key-with-32-bytes!!"
    payload = b'{"sub":"legitimate-user"}'
    signed = verifier.serialize_json([{"protected": {"alg": "HS256"}}], payload, key)

    assert verifier.deserialize_json(signed, key)["payload"] == payload
    signed["payload"] = _base64url(b'{"sub":"different-user"}').decode()
    with pytest.raises(BadSignatureError):
        verifier.deserialize_json(signed, key)


@pytest.mark.parametrize("hops", [17, 64])
def test_dns_rejects_excessive_compression_pointer_chains(hops: int) -> None:
    wire = b"\x00\x00" + b"".join(
        (0xC000 + 2 * index).to_bytes(2, "big") for index in range(hops)
    )

    with pytest.raises(dns.exception.FormError, match="pointer chain was too long"):
        dns.name.from_wire(wire, len(wire) - 2)


@pytest.mark.parametrize("hops", [1, 16])
def test_dns_preserves_supported_compression_pointer_chains(hops: int) -> None:
    wire = b"\x00\x00" + b"".join(
        (0xC000 + 2 * index).to_bytes(2, "big") for index in range(hops)
    )

    name, consumed = dns.name.from_wire(wire, len(wire) - 2)

    assert name == dns.name.root
    assert consumed == 2


def test_google_oauth_session_preserves_token_exchange_and_bearer_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[requests.PreparedRequest] = []

    def send(
        _session: requests.Session,
        prepared: requests.PreparedRequest,
        **_kwargs: object,
    ) -> requests.Response:
        sent.append(prepared)
        response = requests.Response()
        response.status_code = 200
        response.headers["Content-Type"] = "application/json"
        response._content = json.dumps(
            {
                "access_token": "test-access-token",
                "token_type": "Bearer",
                "expires_in": 3600,
            }
            if len(sent) == 1
            else {"sub": "google-user", "email_verified": True}
        ).encode()
        return response

    monkeypatch.setattr(requests.Session, "send", send)
    session = OAuth2Session(
        client_id="test-client",
        client_secret="test-client-secret",
        scope=["openid", "email", "profile"],
        redirect_uri="https://app.example.com/oauth/callback",
    )

    token = session.fetch_token("https://provider.example.com/token", code="test-code")
    profile = session.get("https://provider.example.com/userinfo").json()

    assert token["access_token"] == "test-access-token"
    assert parse_qs(sent[0].body)["code"] == ["test-code"]
    assert sent[1].headers["Authorization"] == "Bearer test-access-token"
    assert profile["sub"] == "google-user"
