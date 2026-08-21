"""Exercise a parent-relative cross-service import violation."""

from ...route.user import optional_token_validation
from ..order.route import register_order_handler
from ..profile import funcs


def helper() -> tuple[object, object, object]:
    return register_order_handler, funcs, optional_token_validation
