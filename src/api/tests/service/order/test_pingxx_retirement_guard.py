"""Keep Ping++ retired: no client, no payment path, history stays read-only.

China payments moved to native Alipay and WeChat Pay on 2026-11-25. Ping++ rows
remain in the database, so a few modules still read them; everything else must
not mention Ping++ again.
"""

from __future__ import annotations

import re
from pathlib import Path

from flask import Flask
from flaskr.route.callback import register_callback_handler
from flaskr.service.order import payment_providers

API_ROOT = Path(__file__).resolve().parents[3]
FLASKR_ROOT = API_ROOT / "flaskr"

# Modules allowed to mention Ping++, each only to read or tolerate history.
PINGXX_HISTORY_READERS = {
    # The order_pingxx_orders table and the legacy Order.payment_channel value.
    "flaskr/service/order/models.py": "Ping++ snapshot model",
    "flaskr/service/order/raw_snapshots.py": "read-only Ping++ snapshot query",
    "flaskr/service/order/funs.py": "learner payment detail of a Ping++ order",
    "flaskr/service/order/admin.py": "operator order list and detail",
    "flaskr/service/order/admin_dtos.py": "operator Ping++ detail fields",
    "flaskr/service/billing/payment_policy.py": "Ping++ subscriptions renew natively",
    "flaskr/service/billing/checkout.py": "pending Ping++ billing orders expire",
    "flaskr/service/billing/queries.py": "operator filter by historical provider",
}

_PINGPP_IMPORT = re.compile(r"^\s*(?:import|from)\s+pingpp\b", re.MULTILINE)
_PINGXX = re.compile(r"pingxx", re.IGNORECASE)


def _python_sources() -> list[Path]:
    return [
        path
        for path in FLASKR_ROOT.rglob("*.py")
        if "migrations" not in path.parts and "__pycache__" not in path.parts
    ]


def test_nothing_imports_the_ping_plus_plus_client() -> None:
    offenders = [
        str(path.relative_to(API_ROOT))
        for path in _python_sources()
        if _PINGPP_IMPORT.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_the_ping_plus_plus_client_is_not_a_dependency() -> None:
    for name in ("requirements.txt", "requirements-ci.txt"):
        requirements = (API_ROOT / name).read_text(encoding="utf-8").lower()
        assert not re.search(r"^pingpp\b", requirements, re.MULTILINE), name


def test_ping_plus_plus_is_mentioned_only_by_history_readers() -> None:
    mentions = {
        str(path.relative_to(API_ROOT))
        for path in _python_sources()
        if _PINGXX.search(path.read_text(encoding="utf-8"))
    }
    assert mentions - set(PINGXX_HISTORY_READERS) == set(), (
        "Ping++ is retired; new code must use the native providers. If a module "
        "must read historical Ping++ rows, add it to PINGXX_HISTORY_READERS with "
        "the reason."
    )


def test_ping_plus_plus_has_no_provider_or_callback() -> None:
    assert "pingxx" not in payment_providers._PROVIDER_REGISTRY
    app = Flask(__name__)
    register_callback_handler(app, "/api/callback")
    routes = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/api/callback/pingxx-callback" not in routes
    assert "/api/callback/alipay-notify" in routes
    assert "/api/callback/wechatpay-notify" in routes
