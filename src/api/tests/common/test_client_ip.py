"""Verify trusted proxy client-address resolution."""

from flask import Flask, request
from flaskr.common.client_ip import (
    resolve_client_ip,
    validate_trusted_proxy_cidrs,
)
from flaskr.route.common import bypass_token_validation


def _resolve(
    app: Flask,
    *,
    remote_addr: str,
    forwarded_for: str | None = None,
    trusted: object = (),
) -> str:
    headers = {"X-Forwarded-For": forwarded_for} if forwarded_for is not None else {}
    with app.test_request_context(
        headers=headers,
        environ_base={"REMOTE_ADDR": remote_addr},
    ):
        return resolve_client_ip(trusted_proxy_cidrs=trusted)


def test_untrusted_peer_cannot_spoof_forwarded_address(app: Flask) -> None:
    assert (
        _resolve(
            app,
            remote_addr="198.51.100.20",
            forwarded_for="203.0.113.99",
        )
        == "198.51.100.20"
    )


def test_trusted_nginx_reports_direct_client(app: Flask) -> None:
    assert (
        _resolve(
            app,
            remote_addr="10.20.0.5",
            forwarded_for="198.51.100.20",
            trusted=["10.20.0.5/32"],
        )
        == "198.51.100.20"
    )


def test_trusted_chain_walks_from_right_and_ignores_prepended_spoof(
    app: Flask,
) -> None:
    assert (
        _resolve(
            app,
            remote_addr="10.20.0.5",
            forwarded_for="192.0.2.88, 198.51.100.20, 203.0.113.7",
            trusted=["10.20.0.5/32", "203.0.113.0/24"],
        )
        == "198.51.100.20"
    )


def test_malformed_or_ambiguous_chain_falls_back_to_peer(app: Flask) -> None:
    trusted = ["10.20.0.5/32"]
    for forwarded in ("", "198.51.100.20,", "not-an-ip", "198.51.100.20:443"):
        assert (
            _resolve(
                app,
                remote_addr="10.20.0.5",
                forwarded_for=forwarded,
                trusted=trusted,
            )
            == "10.20.0.5"
        )


def test_all_trusted_or_oversized_chains_fall_back_to_peer(app: Flask) -> None:
    trusted = ["10.0.0.0/8"]
    assert (
        _resolve(
            app,
            remote_addr="10.20.0.5",
            forwarded_for="10.20.0.4, 10.20.0.3",
            trusted=trusted,
        )
        == "10.20.0.5"
    )
    oversized = ",".join(f"198.51.100.{index}" for index in range(1, 34))
    assert (
        _resolve(
            app,
            remote_addr="10.20.0.5",
            forwarded_for=oversized,
            trusted=trusted,
        )
        == "10.20.0.5"
    )


def test_ipv6_addresses_are_normalized(app: Flask) -> None:
    assert (
        _resolve(
            app,
            remote_addr="2001:db8:1::5",
            forwarded_for="2001:db8:2:0:0:0:0:9",
            trusted=["2001:db8:1::/64"],
        )
        == "2001:db8:2::9"
    )
    assert (
        _resolve(
            app,
            remote_addr="::ffff:10.20.0.5",
            forwarded_for="::ffff:198.51.100.20",
            trusted=["10.20.0.5/32"],
        )
        == "198.51.100.20"
    )


def test_trusted_proxy_configuration_validation() -> None:
    assert validate_trusted_proxy_cidrs("")
    assert validate_trusted_proxy_cidrs("10.0.0.5/32, 2001:db8::/48")
    assert not validate_trusted_proxy_cidrs("10.0.0.0/99")
    assert not validate_trusted_proxy_cidrs("not-a-network")


def test_request_logging_exposes_the_same_resolved_client_ip(
    app: Flask, test_client: object
) -> None:
    app.config["TRUSTED_PROXY_CIDRS"] = "127.0.0.1/32"

    @app.get("/_test/resolved-client-ip")
    @bypass_token_validation
    def resolved_client_ip() -> str:
        return str(request.client_ip)

    response = test_client.get(
        "/_test/resolved-client-ip",
        headers={"X-Forwarded-For": "198.51.100.20"},
    )

    assert response.get_data(as_text=True) == "198.51.100.20"
