import sys
from types import SimpleNamespace

from flaskr.service.order.payment_providers import pingxx


def test_pingxx_client_import_is_cached_by_its_state_owner(monkeypatch):
    sentinel = SimpleNamespace()
    monkeypatch.setattr(pingxx._pingpp_client_state, "client", None)
    monkeypatch.setattr(pingxx._pingpp_client_state, "import_error", None)
    monkeypatch.setitem(sys.modules, "pingpp", sentinel)

    first = pingxx._get_pingpp_client()
    second = pingxx._get_pingpp_client()

    assert first is sentinel
    assert second is sentinel
