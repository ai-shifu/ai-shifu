from __future__ import annotations

from flask import Flask

from flaskr.service.shifu.admin_operations import credit_notifications as module


def test_operator_credit_notification_services_delegate_to_billing(monkeypatch):
    app = Flask(__name__)
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(
        module,
        "build_credit_notification_overview",
        lambda received_app: calls.append(("overview", received_app)) or {"total": 1},
    )
    monkeypatch.setattr(
        module,
        "list_credit_notifications",
        lambda received_app, **kwargs: calls.append(("list", kwargs)) or {"items": []},
    )
    monkeypatch.setattr(
        module,
        "get_credit_notification_detail",
        lambda received_app, **kwargs: (
            calls.append(("detail", kwargs))
            or {"notification_bid": kwargs["notification_bid"]}
        ),
    )
    monkeypatch.setattr(
        module,
        "sync_credit_notification_template",
        lambda received_app, **kwargs: (
            calls.append(("sync", kwargs)) or {"template_code": kwargs["template_code"]}
        ),
    )
    monkeypatch.setattr(
        module,
        "list_credit_notification_templates",
        lambda received_app: calls.append(("templates", received_app)) or {"items": []},
    )
    monkeypatch.setattr(
        module,
        "dry_run_credit_notifications",
        lambda received_app, **kwargs: (
            calls.append(("dry_run", kwargs)) or {"ok": True}
        ),
    )
    monkeypatch.setattr(
        module,
        "requeue_credit_notification",
        lambda received_app, **kwargs: (
            calls.append(("requeue", kwargs)) or {"status": "enqueued"}
        ),
    )

    assert module.get_operator_credit_notification_overview(app) == {"total": 1}
    assert module.list_operator_credit_notifications(
        app,
        page_index=2,
        page_size=30,
        filters={"status": "sent"},
    ) == {"items": []}
    assert module.get_operator_credit_notification_detail(
        app,
        notification_bid="notification-1",
    ) == {"notification_bid": "notification-1"}
    assert module.sync_operator_credit_notification_template(
        app,
        notification_type="credit_granted",
        template_code="SMS_001",
    ) == {"template_code": "SMS_001"}
    assert module.list_operator_credit_notification_templates(app) == {"items": []}
    assert module.dry_run_operator_credit_notifications(
        app,
        notification_type="low_balance",
        creator_bid="creator-1",
    ) == {"ok": True}
    assert module.requeue_operator_credit_notification(
        app,
        notification_bid="notification-2",
    ) == {"status": "enqueued"}

    assert calls == [
        ("overview", app),
        ("list", {"page_index": 2, "page_size": 30, "filters": {"status": "sent"}}),
        ("detail", {"notification_bid": "notification-1"}),
        (
            "sync",
            {"notification_type": "credit_granted", "template_code": "SMS_001"},
        ),
        ("templates", app),
        ("dry_run", {"notification_type": "low_balance", "creator_bid": "creator-1"}),
        ("requeue", {"notification_bid": "notification-2"}),
    ]


def test_operator_credit_notification_config_preserves_opt_out(monkeypatch):
    app = Flask(__name__)
    saved_payloads: list[tuple[object, dict[str, object], bool]] = []
    policies = [{"version": 1}, {"version": 2}]

    monkeypatch.setattr(
        module,
        "load_credit_notification_policy_for_operator",
        lambda: policies.pop(0),
    )

    def fake_save_policy(
        received_app: Flask,
        payload: dict[str, object],
        *,
        preserve_opt_out: bool,
    ) -> None:
        saved_payloads.append((received_app, payload, preserve_opt_out))

    monkeypatch.setattr(module, "save_credit_notification_policy", fake_save_policy)

    assert module.get_operator_credit_notification_config(app) == {"version": 1}
    assert module.update_operator_credit_notification_config(
        app,
        payload={"enabled": True},
    ) == {"version": 2}
    assert saved_payloads == [(app, {"enabled": True}, True)]
