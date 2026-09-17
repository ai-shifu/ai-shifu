"""Verify ping++ stays importable on Python releases without ``find_module``."""

import sys

import pytest
from flaskr.service.order.payment_providers import pingxx


@pytest.fixture
def _isolated_pingpp_import(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the next ``_get_pingpp_client`` call to import ping++ from scratch."""
    for name in list(sys.modules):
        if name == "pingpp" or name.startswith("pingpp."):
            monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setattr(sys, "meta_path", list(sys.meta_path))
    monkeypatch.setattr(pingxx._pingpp_client_state, "client", None)
    monkeypatch.setattr(pingxx._pingpp_client_state, "import_error", None)


@pytest.mark.usefixtures("_isolated_pingpp_import")
def test_pingpp_and_its_vendored_six_moves_import() -> None:
    """Import the modules ping++ pulls in while its package body executes."""
    client = pingxx._get_pingpp_client()

    assert client is sys.modules["pingpp"]

    from pingpp.six.moves import urllib
    from pingpp.six.moves.urllib.parse import parse_qsl, quote_plus, urlencode

    assert parse_qsl("charge=ok") == [("charge", "ok")]
    assert quote_plus("ok") == "ok"
    assert urlencode({"charge": "ok"}) == "charge=ok"
    assert (
        urllib.parse.urlparse("https://api.pingxx.com/v1/charges").path == "/v1/charges"
    )


@pytest.mark.usefixtures("_isolated_pingpp_import")
def test_pingpp_submodules_using_six_moves_import() -> None:
    """Cover the ping++ modules that import ``six.moves`` without a fallback."""
    pingxx._get_pingpp_client()

    import pingpp.api_requestor
    import pingpp.http_client
    import pingpp.wxpub_oauth
    from pingpp.api_resources import Charge

    assert Charge is not None
    assert pingpp.api_requestor is not None
    assert pingpp.http_client is not None
    assert pingpp.wxpub_oauth is not None
