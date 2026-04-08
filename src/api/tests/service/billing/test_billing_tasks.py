from __future__ import annotations

import sys
import types

import pytest

from flaskr.service.billing.tasks import settle_usage_task


def test_settle_usage_task_calls_settlement_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_app = object()
    monkeypatch.setitem(
        sys.modules,
        "app",
        types.SimpleNamespace(create_app=lambda: fake_app),
    )

    captured: dict[str, object] = {}

    def _fake_settle_bill_usage(app, *, usage_bid: str = ""):
        captured["app"] = app
        captured["usage_bid"] = usage_bid
        return {
            "status": "settled",
            "creator_bid": "creator-task-1",
            "usage_bid": usage_bid,
        }

    monkeypatch.setattr(
        "flaskr.service.billing.tasks.settle_bill_usage",
        _fake_settle_bill_usage,
    )

    payload = settle_usage_task(
        creator_bid="creator-task-1",
        usage_bid="usage-task-1",
    )

    assert captured == {
        "app": fake_app,
        "usage_bid": "usage-task-1",
    }
    assert payload["status"] == "settled"
    assert payload["task_name"] == "billing.settle_usage"
    assert payload["requested_creator_bid"] == "creator-task-1"


def test_settle_usage_task_normalizes_empty_creator_bid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        sys.modules,
        "app",
        types.SimpleNamespace(create_app=lambda: object()),
    )
    monkeypatch.setattr(
        "flaskr.service.billing.tasks.settle_bill_usage",
        lambda app, *, usage_bid="": {"status": "noop", "usage_bid": usage_bid},
    )

    payload = settle_usage_task(creator_bid="  ", usage_bid="usage-task-2")

    assert payload["status"] == "noop"
    assert payload["requested_creator_bid"] is None
    assert payload["task_name"] == "billing.settle_usage"
