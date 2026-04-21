from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import types

_API_ROOT = Path(__file__).resolve().parents[3]
_ROUTE_DIR = _API_ROOT / "flaskr" / "route"
_BILLING_ROUTE_FILE = _API_ROOT / "flaskr" / "service" / "billing" / "routes.py"
_ROUTE_PACKAGE = "flaskr.route"
_ROUTE_COMMON = f"{_ROUTE_PACKAGE}.common"
_BILLING_ROUTES_MODULE = "flaskr.service.billing.routes"


def _ensure_route_package() -> None:
    if _ROUTE_PACKAGE in sys.modules:
        return

    package = types.ModuleType(_ROUTE_PACKAGE)
    package.__path__ = [str(_ROUTE_DIR)]
    sys.modules[_ROUTE_PACKAGE] = package


def _ensure_common_route_module() -> None:
    if _ROUTE_COMMON in sys.modules:
        return

    common_spec = importlib.util.spec_from_file_location(
        _ROUTE_COMMON,
        _ROUTE_DIR / "common.py",
    )
    assert common_spec is not None and common_spec.loader is not None
    common_module = importlib.util.module_from_spec(common_spec)
    sys.modules[_ROUTE_COMMON] = common_module
    common_spec.loader.exec_module(common_module)


def load_billing_routes_module() -> ModuleType:
    _ensure_route_package()
    _ensure_common_route_module()

    if _BILLING_ROUTES_MODULE in sys.modules:
        return sys.modules[_BILLING_ROUTES_MODULE]

    spec = importlib.util.spec_from_file_location(
        _BILLING_ROUTES_MODULE,
        _BILLING_ROUTE_FILE,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_BILLING_ROUTES_MODULE] = module
    spec.loader.exec_module(module)
    return module


def load_register_billing_routes():
    return load_billing_routes_module().register_billing_routes
