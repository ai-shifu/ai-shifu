"""Bootstrap helpers for the creator billing service."""

from __future__ import annotations

from typing import Any


def build_billing_route_bootstrap(path_prefix: str) -> dict[str, Any]:
    """Return the billing route manifest defined by the design doc."""

    creator_routes = [
        {"method": "GET", "path": f"{path_prefix}/catalog"},
        {"method": "GET", "path": f"{path_prefix}/overview"},
        {"method": "GET", "path": f"{path_prefix}/wallet-buckets"},
        {"method": "GET", "path": f"{path_prefix}/ledger"},
        {"method": "GET", "path": f"{path_prefix}/orders"},
        {"method": "GET", "path": f"{path_prefix}/orders/{{billing_order_bid}}"},
        {
            "method": "POST",
            "path": f"{path_prefix}/orders/{{billing_order_bid}}/sync",
        },
        {"method": "POST", "path": f"{path_prefix}/subscriptions/checkout"},
        {"method": "POST", "path": f"{path_prefix}/subscriptions/cancel"},
        {"method": "POST", "path": f"{path_prefix}/subscriptions/resume"},
        {"method": "POST", "path": f"{path_prefix}/topups/checkout"},
        {"method": "POST", "path": f"{path_prefix}/webhooks/stripe"},
        {"method": "POST", "path": f"{path_prefix}/webhooks/pingxx"},
    ]
    admin_routes = [
        {"method": "GET", "path": "/api/admin/billing/subscriptions"},
        {"method": "GET", "path": "/api/admin/billing/orders"},
        {"method": "POST", "path": "/api/admin/billing/ledger/adjust"},
    ]
    return {
        "service": "billing",
        "status": "bootstrap",
        "path_prefix": path_prefix,
        "creator_routes": creator_routes,
        "admin_routes": admin_routes,
        "notes": [
            "Registered via plugin route loading from flaskr/service.",
            "Keeps creator billing separate from legacy /order tables and routes.",
            "Concrete schema, checkout, sync, webhook, and ledger behavior lands in later tasks.",
        ],
    }
