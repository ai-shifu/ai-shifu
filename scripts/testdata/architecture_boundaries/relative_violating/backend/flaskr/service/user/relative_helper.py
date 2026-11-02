"""Exercise a parent-relative cross-service import violation."""

from ...route.user import optional_token_validation
from ..order.route import register_order_handler
from ..profile import onboarding


def helper() -> object:
    return register_order_handler, onboarding, optional_token_validation
