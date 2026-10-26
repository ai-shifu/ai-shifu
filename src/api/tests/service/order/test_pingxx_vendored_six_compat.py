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


@pytest.mark.usefixtures("_isolated_pingpp_import")
def test_repeated_imports_add_only_one_compatibility_finder() -> None:
    """Every finder on ``sys.meta_path`` is searched on every import miss, so they must not pile up.

    The early return covers the ordinary case, where the modules stay in ``sys.modules`` for the
    life of the process. Anything that drops them -- a reload, or test isolation like the fixture
    here -- brings the code back round to the append.
    """
    pingxx._ensure_vendored_six_importable()
    after_first = [f for f in sys.meta_path if isinstance(f, pingxx._LegacySixFinder)]

    for name in list(sys.modules):
        if name == "pingpp" or name.startswith("pingpp."):
            del sys.modules[name]
    pingxx._ensure_vendored_six_importable()

    finders = [f for f in sys.meta_path if isinstance(f, pingxx._LegacySixFinder)]
    assert len(finders) == len(after_first) <= 1


@pytest.mark.usefixtures("_isolated_pingpp_import")
def test_the_kept_finder_still_serves_a_reimported_pingpp() -> None:
    """Keeping the first finder is only safe if it still works after the modules are dropped.

    It holds the importer from the first load, so this checks that a second import of ping++ and
    its vendored six moves still succeeds rather than finding a stale object.
    """
    first = pingxx._get_pingpp_client()
    assert first is sys.modules["pingpp"]

    for name in list(sys.modules):
        if name == "pingpp" or name.startswith("pingpp."):
            del sys.modules[name]
    pingxx._pingpp_client_state.client = None
    pingxx._pingpp_client_state.import_error = None

    second = pingxx._get_pingpp_client()
    assert second is sys.modules["pingpp"]
    assert "pingpp.six" in sys.modules
    import pingpp.six.moves.urllib.parse  # noqa: F401 - importing it is the assertion
