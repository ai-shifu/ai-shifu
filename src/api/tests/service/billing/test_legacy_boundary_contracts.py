from __future__ import annotations

from pathlib import Path

from flaskr.service.metering.models import BillUsageRecord

_API_ROOT = Path(__file__).resolve().parents[3]


def test_legacy_order_route_remains_separate_from_billing_domain() -> None:
    source = (_API_ROOT / "flaskr/route/order.py").read_text(encoding="utf-8")

    assert "from flaskr.service.order.admin import (" in source
    assert '@app.route(path_prefix + "/reqiure-to-pay", methods=["POST"])' in source
    assert '@app.route(path_prefix + "/init-order", methods=["POST"])' in source
    assert '@app.route(path_prefix + "/query-order", methods=["POST"])' in source
    assert '@app.route(path_prefix + "/stripe/sync", methods=["POST"])' in source
    assert '@app.route(path_prefix + "/stripe/webhook", methods=["POST"])' in source
    assert '@app.route(path_prefix + "/admin/orders", methods=["GET"])' in source
    assert '@app.route(path_prefix + "/admin/orders/shifus", methods=["GET"])' in source
    assert (
        '@app.route(path_prefix + "/admin/orders/import-activation", methods=["POST"])'
        in source
    )
    assert (
        '@app.route(path_prefix + "/admin/orders/<order_bid>", methods=["GET"])'
        in source
    )
    assert "from flaskr.service.billing" not in source


def test_runtime_config_route_keeps_global_fields_and_adds_billing_extensions() -> None:
    source = (_API_ROOT / "flaskr/route/config.py").read_text(encoding="utf-8")

    assert '@app.route(path_prefix + "/runtime-config", methods=["GET"])' in source
    assert '"logoWideUrl": get_config("LOGO_WIDE_URL", "")' in source
    assert '"logoSquareUrl": get_config("LOGO_SQUARE_URL", "")' in source
    assert '"faviconUrl": get_config("FAVICON_URL", "")' in source
    assert '"homeUrl": get_config("HOME_URL", "/")' in source
    assert 'creator_bid = str(get_shifu_creator_bid() or "").strip()' in source
    assert "runtime_billing = build_runtime_billing_context(" in source
    assert "config.update(runtime_billing)" in source


def test_bill_usage_model_keeps_raw_table_shape() -> None:
    table = BillUsageRecord.__table__

    assert BillUsageRecord.__tablename__ == "bill_usage"
    assert "usage_bid" in table.c
    assert "shifu_bid" in table.c
    assert "usage_scene" in table.c
    assert "extra" in table.c
    assert "creator_bid" not in table.c
