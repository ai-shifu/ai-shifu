"""Verify domain validation, DNS/TLS evidence, ownership, and atomic updates."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from flaskr.dao import db
from flaskr.service.billing import domains
from flaskr.service.billing.consts import (
    BILLING_DOMAIN_BINDING_STATUS_DISABLED,
    BILLING_DOMAIN_BINDING_STATUS_FAILED,
    BILLING_DOMAIN_BINDING_STATUS_VERIFIED,
    BILLING_DOMAIN_SSL_STATUS_ACTIVE,
    BILLING_DOMAIN_SSL_STATUS_PROVISIONING,
    BILLING_DOMAIN_VERIFICATION_METHOD_DNS_TXT,
)
from flaskr.service.billing.models import BillingDomainBinding
from flaskr.service.common.models import AppError

from tests.service.billing import test_billing_domains as domain_fixtures

billing_domain_client = domain_fixtures.billing_domain_client


@pytest.mark.parametrize(
    "host",
    [
        "",
        "https:///",
        "localhost",
        "127.0.0.1",
        "a..example.com",
        "bad_name.example.com",
        "-bad.example.com",
        "a" * 64 + ".com",
        "a" * 256 + ".com",
        "\ud800.example.com",
    ],
)
def test_invalid_custom_domain_is_rejected_and_optional_resolution_is_empty(
    host: str,
) -> None:
    with pytest.raises(AppError):
        domains.normalize_domain_host(host)
    assert domains.normalize_domain_host(host, strict=False) == ""


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("HTTPS://LEARN.EXAMPLE.COM.:443/path?q=1", "learn.example.com"),
        ("课程.example.com", "xn--9nzo18a.example.com"),
    ],
)
def test_domain_normalization_preserves_only_idna_hostname(
    host: str, expected: str
) -> None:
    assert domains.normalize_domain_host(host) == expected


@pytest.mark.parametrize(
    "method",
    ["dns_txt", str(BILLING_DOMAIN_VERIFICATION_METHOD_DNS_TXT), "invalid", "99999"],
)
def test_domain_bind_validates_verification_method_before_disabling_current_host(
    method: str,
    billing_domain_client: dict,
) -> None:
    app = billing_domain_client["app"]
    valid = method in {"dns_txt", str(BILLING_DOMAIN_VERIFICATION_METHOD_DNS_TXT)}
    if valid:
        result = domains.manage_creator_domain_binding(
            app, "creator-1", {"host": "new.example.com", "verification_method": method}
        )
        assert result.binding.status == "pending"
        row = BillingDomainBinding.query.filter_by(host="new.example.com").one()
        assert row.verification_method == BILLING_DOMAIN_VERIFICATION_METHOD_DNS_TXT
        assert row.verification_token
        assert row.metadata_json["verification_record_value"] == row.verification_token
    else:
        with pytest.raises(AppError):
            domains.manage_creator_domain_binding(
                app,
                "creator-1",
                {"host": "new.example.com", "verification_method": method},
            )
    db.session.expire_all()
    current = BillingDomainBinding.query.filter_by(host="academy.example.com").one()
    assert current.status == (
        BILLING_DOMAIN_BINDING_STATUS_DISABLED
        if valid
        else BILLING_DOMAIN_BINDING_STATUS_VERIFIED
    )
    assert BillingDomainBinding.query.filter_by(host="new.example.com").count() == int(
        valid
    )


@pytest.mark.parametrize(
    ("creator", "payload"),
    [
        ("creator-2", {"action": "verify", "host": "academy.example.com"}),
        ("creator-1", {"action": "other", "host": "new.example.com"}),
        ("creator-1", {"action": "bind", "domain_binding_bid": "binding-verified-1"}),
        ("creator-1", {"action": "verify"}),
        ("creator-1", {"action": "disable"}),
        (
            "creator-3",
            {"action": "disable", "domain_binding_bid": "binding-verified-1"},
        ),
        ("creator-3", {"action": "bind", "host": "academy.example.com"}),
    ],
)
def test_domain_mutation_requires_entitlement_owned_target_and_valid_action(
    creator: str,
    payload: dict,
    billing_domain_client: dict,
) -> None:
    with pytest.raises(AppError):
        domains.manage_creator_domain_binding(
            billing_domain_client["app"], creator, payload
        )
    db.session.expire_all()
    row = BillingDomainBinding.query.filter_by(
        domain_binding_bid="binding-verified-1"
    ).one()
    assert row.creator_bid == "creator-1"
    assert row.status == BILLING_DOMAIN_BINDING_STATUS_VERIFIED


@pytest.mark.parametrize(
    "dns_case",
    [
        "txt-error",
        "txt-mismatch",
        "cname-error",
        "cname-mismatch",
        "no-cname",
        "tls-pending",
        "ready",
    ],
)
def test_domain_verification_uses_dns_and_tls_before_becoming_effective(
    dns_case: str,
    billing_domain_client: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = billing_domain_client["app"]
    app.testing = False
    result = domains.manage_creator_domain_binding(
        app, "creator-1", {"host": "new.example.com"}
    )
    row = BillingDomainBinding.query.filter_by(
        domain_binding_bid=result.binding.domain_binding_bid
    ).one()
    row.metadata_json = {
        **row.metadata_json,
        "cname_target": "" if dns_case == "no-cname" else "edge.example.net",
    }
    db.session.commit()
    calls = []

    def resolve(name: str, record_type: str, **kwargs: object) -> list:
        calls.append((name, record_type, kwargs["lifetime"]))
        if record_type == "TXT":
            if dns_case == "txt-error":
                message = "resolver unavailable"
                raise OSError(message)
            token = (
                "wrong-token" if dns_case == "txt-mismatch" else row.verification_token
            )
            return [SimpleNamespace(strings=[token.encode()])]
        if dns_case == "cname-error":
            message = "resolver unavailable"
            raise OSError(message)
        return [
            SimpleNamespace(
                target="wrong.example.net."
                if dns_case == "cname-mismatch"
                else "EDGE.EXAMPLE.NET."
            )
        ]

    monkeypatch.setattr(domains.dns.resolver, "resolve", resolve)
    tls = Mock(return_value=dns_case != "tls-pending")
    monkeypatch.setattr(domains, "_is_tls_ready", tls)
    verified = domains.manage_creator_domain_binding(
        app,
        "creator-1",
        {"action": "verify", "domain_binding_bid": row.domain_binding_bid},
    )
    db.session.expire_all()
    dns_valid = dns_case in {"no-cname", "tls-pending", "ready"}
    assert row.status == (
        BILLING_DOMAIN_BINDING_STATUS_VERIFIED
        if dns_valid
        else BILLING_DOMAIN_BINDING_STATUS_FAILED
    )
    assert (
        row.last_verified_at is not None if dns_valid else row.last_verified_at is None
    )
    assert verified.binding.is_effective is (dns_case in {"no-cname", "ready"})
    assert calls[0] == ("_ai-shifu.new.example.com", "TXT", 5)
    if dns_valid:
        tls.assert_called_once_with("new.example.com")
        assert row.ssl_status == (
            BILLING_DOMAIN_SSL_STATUS_PROVISIONING
            if dns_case == "tls-pending"
            else BILLING_DOMAIN_SSL_STATUS_ACTIVE
        )
        assert row.metadata_json["ssl_error"] == (
            "certificate_not_ready" if dns_case == "tls-pending" else ""
        )
    else:
        tls.assert_not_called()


@pytest.mark.parametrize("failure", [False, True])
def test_domain_tls_probe_uses_hostname_and_releases_connection(
    failure: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection_manager = MagicMock()
    context = MagicMock()
    if failure:
        context.wrap_socket.side_effect = domains.ssl.SSLError("certificate mismatch")
    monkeypatch.setattr(
        domains.socket, "create_connection", Mock(return_value=connection_manager)
    )
    monkeypatch.setattr(
        domains.ssl, "create_default_context", Mock(return_value=context)
    )
    assert domains._is_tls_ready("learn.example.com") is (not failure)
    domains.socket.create_connection.assert_called_once_with(
        ("learn.example.com", 443), timeout=5
    )
    context.wrap_socket.assert_called_once_with(
        connection_manager.__enter__.return_value, server_hostname="learn.example.com"
    )
    connection_manager.__exit__.assert_called_once()
    assert context.minimum_version == domains.ssl.TLSVersion.TLSv1_2


@pytest.mark.parametrize(
    "selector",
    [
        {},
        {"host": "absent.example.com"},
        {"creator_bid": "creator-3", "host": "academy.example.com"},
    ],
)
def test_background_domain_verification_never_adopts_an_unowned_or_missing_target(
    selector: dict,
    billing_domain_client: dict,
) -> None:
    with pytest.raises(AppError):
        domains.verify_domain_binding(billing_domain_client["app"], **selector)
    assert (
        BillingDomainBinding.query.filter_by(
            status=BILLING_DOMAIN_BINDING_STATUS_VERIFIED
        ).count()
        == 1
    )


def test_domain_rebinding_rolls_back_sibling_disable_when_response_build_fails(
    billing_domain_client: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_serialization(*_args: object, **_kwargs: object) -> None:
        db.session.flush()
        assert (
            BillingDomainBinding.query.filter_by(host="academy.example.com")
            .one()
            .status
            == BILLING_DOMAIN_BINDING_STATUS_DISABLED
        )
        message = "serialization failed"
        raise RuntimeError(message)

    monkeypatch.setattr(domains, "_serialize_domain_binding", fail_serialization)
    with pytest.raises(RuntimeError, match="serialization failed"):
        domains.manage_creator_domain_binding(
            billing_domain_client["app"], "creator-1", {"host": "new.example.com"}
        )
    db.session.expire_all()
    assert BillingDomainBinding.query.filter_by(host="new.example.com").count() == 0
    assert (
        BillingDomainBinding.query.filter_by(host="academy.example.com").one().status
        == BILLING_DOMAIN_BINDING_STATUS_VERIFIED
    )


def test_disabling_domain_by_host_removes_effective_origin_without_deleting_evidence(
    billing_domain_client: dict,
) -> None:
    app = billing_domain_client["app"]
    assert (
        domains.resolve_effective_custom_origin(app, "creator-1")
        == "https://academy.example.com"
    )
    result = domains.manage_creator_domain_binding(
        app, "creator-1", {"action": "disable", "host": "academy.example.com"}
    )
    assert result.binding.status == "disabled"
    assert domains.resolve_effective_custom_origin(app, "creator-1") is None
    assert domains.resolve_creator_bid_by_host(app, "academy.example.com") is None
    assert domains.resolve_effective_custom_origin(app, " ") is None
    row = BillingDomainBinding.query.filter_by(host="academy.example.com").one()
    assert row.deleted == 0
    assert row.verification_token == "token-academy"
