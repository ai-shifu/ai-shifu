from __future__ import annotations

import flaskr.service.order.admin as order_admin
from flaskr.i18n import _


def test_import_activation_orders_unexpected_failure_returns_specific_message(
    app, monkeypatch
):
    def raise_unexpected(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(order_admin, "import_activation_order", raise_unexpected)

    with app.app_context():
        result = order_admin.import_activation_orders(
            app,
            ["13800138000"],
            course_id="course-1",
            contact_type="phone",
        )

    assert result["success"] == []
    assert result["failed"] == [
        {
            "mobile": "13800138000",
            "message": _("server.order.importActivationFailed"),
        }
    ]


def test_import_activation_orders_from_entries_unexpected_failure_returns_specific_message(
    app, monkeypatch
):
    def raise_unexpected(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(order_admin, "import_activation_order", raise_unexpected)

    with app.app_context():
        result = order_admin.import_activation_orders_from_entries(
            app,
            [{"mobile": "user@example.com", "nickname": "User"}],
            course_id="course-1",
            contact_type="email",
        )

    assert result["success"] == []
    assert result["failed"] == [
        {
            "mobile": "user@example.com",
            "message": _("server.order.importActivationFailed"),
        }
    ]
