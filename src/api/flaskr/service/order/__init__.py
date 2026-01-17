from __future__ import annotations

from importlib import import_module
from typing import Any

from .consts import *  # noqa: F403
from ..common.dicts import register_dict

register_dict("order_status", "订单状态", ORDER_STATUS_TYPES)  # noqa
register_dict("learn_status", "学习状态", LEARN_STATUS_TYPES)  # noqa


def __getattr__(name: str) -> Any:
    """Lazy-export symbols from order helpers to avoid circular imports."""
    funs = import_module(".funs", __name__)
    if hasattr(funs, name):
        value = getattr(funs, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
