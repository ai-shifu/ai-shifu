from __future__ import annotations

import sys
import types

import pytest

from flaskr.service.billing.tasks import replay_usage_settlement_task, settle_usage_task


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


def test_replay_usage_settlement_task_calls_replay_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_app = object()
    monkeypatch.setitem(
        sys.modules,
        "app",
        types.SimpleNamespace(create_app=lambda: fake_app),
    )

    captured: dict[str, object] = {}

    def _fake_replay_bill_usage_settlement(
        app,
        *,
        creator_bid: str = "",
        usage_bid: str = "",
        usage_id=None,
    ):
        captured["app"] = app
        captured["creator_bid"] = creator_bid
        captured["usage_bid"] = usage_bid
        captured["usage_id"] = usage_id
        return {
            "status": "already_settled",
            "creator_bid": creator_bid,
            "usage_bid": usage_bid,
            "replay": True,
        }

    monkeypatch.setattr(
        "flaskr.service.billing.tasks.replay_bill_usage_settlement",
        _fake_replay_bill_usage_settlement,
    )

    payload = replay_usage_settlement_task(
        creator_bid="creator-task-2",
        usage_bid="usage-task-2",
    )

    assert captured == {
        "app": fake_app,
        "creator_bid": "creator-task-2",
        "usage_bid": "usage-task-2",
        "usage_id": None,
    }
    assert payload["status"] == "already_settled"
    assert payload["task_name"] == "billing.replay_usage_settlement"
    assert payload["replay"] is True
