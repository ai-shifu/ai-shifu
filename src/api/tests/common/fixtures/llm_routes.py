"""Install fake LiteLLM routes so tests need no provider credentials."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.common import llm_routing
from flaskr.common.llm_routing import LLMRoute

if TYPE_CHECKING:
    import pytest


def install_llm_routes(
    monkeypatch: pytest.MonkeyPatch,
    routes: dict[str, tuple[str, str]],
    *,
    missing: dict[str, tuple[str, ...]] | None = None,
    exclusive: bool = False,
) -> None:
    """Route ``model -> (provider, provider-local model)`` without credentials.

    ``missing`` marks a model's provider as lacking those credential variables.
    Other ids use real LiteLLM routing unless ``exclusive`` is set, in which
    case they are unroutable.
    """
    from flaskr.api import llm

    real_resolve = llm_routing.resolve_route
    missing = missing or {}

    def resolve(model: object) -> LLMRoute | None:
        key = str(model or "").strip()
        if key in routes:
            provider, invoke_model = routes[key]
            return LLMRoute(
                provider=provider,
                model=invoke_model,
                missing_credentials=tuple(missing.get(key, ())),
            )
        return None if exclusive else real_resolve(model)

    monkeypatch.setattr(llm, "resolve_route", resolve)
    monkeypatch.setattr(llm_routing, "resolve_route", resolve)
