"""Creator billing route bootstrap."""

from __future__ import annotations

import json

from flask import Flask, request

from flaskr.framework.plugin.inject import inject
from flaskr.service.billing.funcs import build_billing_route_bootstrap
from flaskr.service.common.models import raise_error


def _require_creator() -> None:
    if not getattr(request.user, "is_creator", False):
        raise_error("server.shifu.noPermission")


def _make_common_response(data):
    return json.dumps(
        {"code": 0, "message": "success", "data": data or {}},
        ensure_ascii=False,
    )


@inject
def register_billing_routes(app: Flask, path_prefix: str = "/api/billing") -> None:
    """Register the creator billing bootstrap route."""

    app.logger.info("register billing routes %s", path_prefix)

    @app.route(path_prefix, methods=["GET"])
    def billing_bootstrap_api():
        _require_creator()
        return _make_common_response(build_billing_route_bootstrap(path_prefix))

    return None
