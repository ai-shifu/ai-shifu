from __future__ import annotations

import importlib
import sys
from types import ModuleType

_ROUTE_PACKAGE = "flaskr.route"
_ROUTE_COMMON = f"{_ROUTE_PACKAGE}.common"
_BILLING_ROUTES_MODULE = "flaskr.service.billing.routes"


def _ensure_route_package() -> None:
    if _ROUTE_PACKAGE in sys.modules:
        return

    importlib.import_module(_ROUTE_PACKAGE)


def _ensure_common_route_module() -> None:
    if _ROUTE_COMMON in sys.modules:
        return

    importlib.import_module(_ROUTE_COMMON)


def load_billing_routes_module() -> ModuleType:
    _ensure_route_package()
    _ensure_common_route_module()

    if _BILLING_ROUTES_MODULE in sys.modules:
        return sys.modules[_BILLING_ROUTES_MODULE]

    return importlib.import_module(_BILLING_ROUTES_MODULE)


def load_register_billing_routes():
    return load_billing_routes_module().register_billing_routes
