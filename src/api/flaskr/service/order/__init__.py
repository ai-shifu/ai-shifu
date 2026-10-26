"""Order and payment service."""

from __future__ import annotations

from importlib import import_module

from flaskr.service.common.dicts import register_dict

from .consts import *  # noqa: F403

register_dict("order_status", "订单状态", ORDER_STATUS_TYPES)  # noqa: F405
register_dict("learn_status", "学习状态", LEARN_STATUS_TYPES)  # noqa: F405


def __getattr__(name: str) -> object:
    """Lazy-export symbols from order helpers to avoid circular imports."""
    funs = import_module(".funs", __name__)
    if hasattr(funs, name):
        value = getattr(funs, name)
        globals()[name] = value
        return value
    message = f"module '{__name__}' has no attribute '{name}'"
    raise AttributeError(message)
