from __future__ import annotations

from flask import Flask

from flaskr.route.config import register_config_handler
from flaskr.route.order import register_order_handler
from flaskr.service.metering.models import BillUsageRecord


def test_legacy_order_route_remains_separate_from_billing_domain() -> None:
    app = Flask(__name__)
    register_order_handler(app, "/api")

    routes = {rule.rule: rule.methods for rule in app.url_map.iter_rules()}

    assert routes["/api/reqiure-to-pay"] >= {"POST"}
    assert routes["/api/init-order"] >= {"POST"}
    assert routes["/api/query-order"] >= {"POST"}
    assert routes["/api/stripe/sync"] >= {"POST"}
    assert routes["/api/stripe/webhook"] >= {"POST"}
    assert routes["/api/admin/orders"] >= {"GET"}
    assert routes["/api/admin/orders/shifus"] >= {"GET"}
    assert routes["/api/admin/orders/import-activation"] >= {"POST"}
    assert routes["/api/admin/orders/<order_bid>"] >= {"GET"}

    for endpoint, view in app.view_functions.items():
        if endpoint == "static":
            continue
        assert not view.__module__.startswith("flaskr.service.billing")


def test_runtime_config_route_keeps_global_fields_and_adds_billing_extensions() -> None:
    app = Flask(__name__)
    register_config_handler(app, "/api")

    runtime_config_rule = next(
        rule for rule in app.url_map.iter_rules() if rule.rule == "/api/runtime-config"
    )

    assert runtime_config_rule.methods >= {"GET"}
    assert app.view_functions[runtime_config_rule.endpoint].__module__ == (
        "flaskr.route.config"
    )


def test_bill_usage_model_keeps_raw_table_shape() -> None:
    table = BillUsageRecord.__table__

    assert BillUsageRecord.__tablename__ == "bill_usage"
    assert "usage_bid" in table.c
    assert "shifu_bid" in table.c
    assert "usage_scene" in table.c
    assert "extra" in table.c
    assert "creator_bid" not in table.c
