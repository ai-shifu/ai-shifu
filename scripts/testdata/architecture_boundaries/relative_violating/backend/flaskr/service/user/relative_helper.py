from ..order.route import register_order_handler
from ..profile import funcs
from ...route.user import optional_token_validation


def helper():
    return register_order_handler, funcs, optional_token_validation
