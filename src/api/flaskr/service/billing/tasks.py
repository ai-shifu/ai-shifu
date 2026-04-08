"""Task entrypoints for billing background jobs."""

from __future__ import annotations

import os
from typing import Any, Callable

from .settlement import replay_bill_usage_settlement, settle_bill_usage

try:  # pragma: no cover - exercised indirectly when Celery is installed
    from celery import shared_task
except ImportError:  # pragma: no cover - local fallback for non-Celery test envs

    def shared_task(*args, **kwargs):
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            return func

        return decorator


@shared_task(name="billing.settle_usage")
def settle_usage_task(*, creator_bid: str = "", usage_bid: str = "") -> dict[str, Any]:
    """Default async entrypoint for usage credit settlement."""

    os.environ.setdefault("SKIP_APP_AUTOCREATE", "1")
    from app import create_app

    app = create_app()
    payload = settle_bill_usage(app, usage_bid=usage_bid)
    payload["requested_creator_bid"] = str(creator_bid or "").strip() or None
    payload["task_name"] = "billing.settle_usage"
    return payload


@shared_task(name="billing.replay_usage_settlement")
def replay_usage_settlement_task(
    *,
    creator_bid: str = "",
    usage_bid: str = "",
) -> dict[str, Any]:
    """Replay a usage settlement without duplicating ledger consumption."""

    os.environ.setdefault("SKIP_APP_AUTOCREATE", "1")
    from app import create_app

    app = create_app()
    payload = replay_bill_usage_settlement(
        app,
        creator_bid=creator_bid,
        usage_bid=usage_bid,
    )
    payload["task_name"] = "billing.replay_usage_settlement"
    return payload
