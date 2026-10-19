"""Verify collaborators patched on order funs still reach its split modules."""

from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from flaskr.service.order import funs
from flaskr.service.order.funs import _order_credential_scope


def test_order_credential_scope_uses_collaborators_patched_on_funs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    context = SimpleNamespace(integration_bid="integration-1")

    def fake_resolve(_app: object, **kwargs: str) -> SimpleNamespace:
        calls.append(f"resolve:{kwargs['integration_bid']}")
        return context

    def fake_build(received: object) -> dict[str, str]:
        assert received is context
        calls.append("build")
        return {"KEY": "value"}

    def fake_overrides(overrides: dict[str, str]) -> nullcontext[None]:
        calls.append(f"overrides:{overrides['KEY']}")
        return nullcontext()

    monkeypatch.setattr(funs, "resolve_provider_credential_context", fake_resolve)
    monkeypatch.setattr(funs, "build_provider_config_overrides", fake_build)
    monkeypatch.setattr(funs, "config_overrides", fake_overrides)
    order = SimpleNamespace(
        payment_integration_bid="integration-1",
        creator_bid="creator-1",
        payment_channel="stripe",
    )

    with _order_credential_scope(object(), order):
        pass

    assert calls == ["resolve:integration-1", "build", "overrides:value"]
